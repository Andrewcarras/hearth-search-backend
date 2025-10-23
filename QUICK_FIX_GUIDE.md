# Quick Fix Guide - Lambda Deployment Regression
## Immediate Steps to Restore Search Quality

---

## PROBLEM IDENTIFIED

**Lambda is running OLD code from Oct 22, 22:13 EDT (commit `ac6660b`)**

This version is missing the critical fix from commit `46d9f51` (Oct 22, 22:24 EDT) that prevents "blue homes" from matching brick houses with blue skies.

---

## SOLUTION: Deploy Latest Code

### Step 1: Sync Local Repository

```bash
cd /Users/andrewcarras/hearth_backend_new

# Check current state
git status
# Output: Your branch is behind 'origin/main' by 7 commits

# Sync with remote (includes the fix)
git pull origin main --ff-only

# Verify we're at latest
git log --oneline -1
# Expected: dce8f7c Add auto-refresh to analytics dashboard
```

### Step 2: Deploy to Lambda

```bash
# Deploy search Lambda
./deploy_lambda.sh search

# Wait for deployment to complete (usually 30-60 seconds)
```

### Step 3: Verify Deployment

```bash
# Check Lambda update time
aws lambda get-function --function-name hearth-search-v2 \
  --query 'Configuration.LastModified' \
  --output text

# Should show current timestamp (2025-10-23T09:XX:XX)
```

---

## VERIFICATION: Test Search Quality

### Test 1: Check Sub-Query Generation

```bash
# Test multi-query mode with a "blue homes" query
curl -X POST https://xzozj6vdkv5zfm747ahlykddzu0hdmhl.lambda-url.us-east-1.on.aws/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "blue homes with granite countertops",
    "use_multi_query": true,
    "k": 10,
    "include_scoring_details": true
  }' | jq '.debug_info.sub_queries'
```

**Expected Output (FIXED):**
```json
[
  {
    "query": "blue painted house exterior facade siding building",
    "feature": "blue_exterior",
    "context": "exterior_primary",
    "weight": 2.0,
    "search_strategy": "max"
  },
  {
    "query": "granite stone countertops kitchen surfaces",
    "feature": "granite_countertops",
    "context": "interior_secondary",
    "weight": 1.0,
    "search_strategy": "max"
  }
]
```

**Previous Output (BROKEN):**
```json
[
  {
    "query": "blue exterior",
    "feature": "blue_exterior",
    "context": "general",
    "weight": 1.0,
    "search_strategy": "max"
  },
  {
    "query": "granite countertops",
    "feature": "granite_countertops",
    "context": "general",
    "weight": 1.0,
    "search_strategy": "max"
  }
]
```

### Test 2: Check Result Quality

```bash
# Run "blue homes" query and check exterior colors
curl -X POST https://xzozj6vdkv5zfm747ahlykddzu0hdmhl.lambda-url.us-east-1.on.aws/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "blue homes",
    "use_multi_query": true,
    "k": 5
  }' | jq '.results[] | {
    zpid,
    address: .address.full,
    exterior_color: .visual_features_exterior
  }'
```

**Expected (FIXED):** All results should include "blue_exterior" tag

**Previous (BROKEN):** Results included brick houses (matched blue sky in images)

---

## WHAT WAS FIXED?

### The Problem (ac6660b - DEPLOYED)

When the LLM fails to generate sub-queries, the fallback logic creates simple queries:
- "blue_exterior" → "blue exterior"
- This matches: Blue houses ✅, Blue skies ✅, Blue interiors ✅

### The Fix (46d9f51 - IN LATEST)

Smart fallback adds context based on feature type:
- "blue_exterior" → "blue painted house exterior facade siding building"
- This matches: Blue houses ONLY ✅

---

## ROLLBACK PLAN (If Issues Occur)

If the new deployment causes unexpected issues:

```bash
# Option 1: Revert to known stable (ac6660b)
git reset --hard ac6660b
./deploy_lambda.sh search

# Option 2: Revert to last working version with fix (46d9f51)
git reset --hard 46d9f51
./deploy_lambda.sh search

# Option 3: Use AWS Lambda versioning
aws lambda update-function-configuration \
  --function-name hearth-search-v2 \
  --description "Reverted to ac6660b due to issue"
```

---

## MONITORING

### Check Lambda Logs

```bash
# View recent Lambda logs
aws logs tail /aws/lambda/hearth-search-v2 --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/hearth-search-v2 \
  --filter-pattern "ERROR" \
  --start-time $(date -u -v-1H +%s)000
```

### Key Metrics to Monitor

1. **Sub-Query Generation**
   - Look for: "🔀 MULTI-QUERY mode enabled"
   - Verify: Sub-queries include context words (e.g., "painted house")

2. **Search Quality**
   - Test queries: "blue homes", "white houses", "gray exterior"
   - Check: Results match the queried color

3. **Error Rate**
   - Monitor: Lambda errors/invocations ratio
   - Expected: < 1% error rate

---

## TIMELINE OF EVENTS (For Reference)

| Time (EDT) | Event | Commit | Status |
|------------|-------|--------|--------|
| Oct 22, 22:13 | RRF implementation | ac6660b | Basic fallback |
| Oct 22, 22:24 | **Sub-query fix** | **46d9f51** | **Smart fallback** |
| Oct 22, 23:39 | Latest commit | dce8f7c | UI updates |
| Oct 23, 00:09 | Git reset to old | ac6660b | **REGRESSION** |
| Oct 23, 00:10 | Lambda deployed | ac6660b | **BROKEN** |
| Oct 23, 05:30 | Issues reported | - | Investigation |

---

## ROOT CAUSE

**What happened:**
1. Developer committed fix at 22:24 EDT (46d9f51)
2. Several UI commits followed (22:32 - 23:39 EDT)
3. Developer reset to ac6660b at 00:09 EDT (unknown reason)
4. Lambda deployed at 00:10 EDT with OLD code
5. Fix from 46d9f51 was lost

**Why:**
- Local HEAD was reset to ac6660b (2 hours older than latest)
- Deployment script deployed from local HEAD
- No pre-deployment check for sync with origin

**Lesson:**
- Always check: `git status` before deploying
- Use explicit commit hashes in deploy script
- Add commit hash to Lambda environment variables

---

## PREVENTION

### Add to Deploy Script (deploy_lambda.sh)

```bash
# Add after line 10:
echo "======================================"
echo "Pre-deployment Checks"
echo "======================================"

# Check if local is in sync with origin
LOCAL_HEAD=$(git rev-parse HEAD)
ORIGIN_HEAD=$(git rev-parse origin/main)

if [ "$LOCAL_HEAD" != "$ORIGIN_HEAD" ]; then
    echo "⚠️  WARNING: Local HEAD is not in sync with origin/main"
    echo "   Local:  $LOCAL_HEAD"
    echo "   Origin: $ORIGIN_HEAD"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Deployment cancelled."
        exit 1
    fi
fi

# Log commit hash
COMMIT_HASH=$(git rev-parse --short HEAD)
echo "Deploying commit: $COMMIT_HASH"
```

### Add Commit Hash to Lambda

```bash
# Add to ENV_VARS in deploy_lambda.sh:
ENV_VARS="Variables={
    OS_HOST=...,
    OS_INDEX=...,
    ...
    GIT_COMMIT_HASH=$(git rev-parse --short HEAD),
    DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
}"
```

### Add Logging to Lambda

```python
# Add to search.py after line 57:
COMMIT_HASH = os.getenv("GIT_COMMIT_HASH", "unknown")
DEPLOYED_AT = os.getenv("DEPLOYED_AT", "unknown")

logger.info(f"Lambda starting: commit={COMMIT_HASH}, deployed={DEPLOYED_AT}")
```

---

## CONTACT

**Issue Detected:** 2025-10-23 05:30 EDT
**Root Cause Identified:** 2025-10-23 (investigation)
**Fix Available:** Deploy latest from origin/main (dce8f7c)

**Questions?**
- Review: `/Users/andrewcarras/hearth_backend_new/LAMBDA_DEPLOYMENT_REGRESSION_ANALYSIS.md`
- Visual: `/Users/andrewcarras/hearth_backend_new/DEPLOYMENT_TIMELINE_VISUAL.md`

---

## QUICK SUMMARY

```
PROBLEM:    Lambda running old code (ac6660b from Oct 22, 22:13)
MISSING:    Critical fix from 46d9f51 (Oct 22, 22:24)
IMPACT:     "blue homes" matches brick houses with blue skies
FIX:        git pull origin main && ./deploy_lambda.sh search
VERIFY:     Test "blue homes" query with multi-query mode
DURATION:   5 minutes (pull + deploy + test)
```

---

*Guide Created: 2025-10-23*
*Next Action: Execute Step 1-3 above*
