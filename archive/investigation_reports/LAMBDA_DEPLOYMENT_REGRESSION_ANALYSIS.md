# Lambda Deployment Regression Analysis
## Investigation: Oct 23, 2025 - Search Quality Degradation

---

## EXECUTIVE SUMMARY

**ROOT CAUSE IDENTIFIED:** Accidental code revert during Lambda deployment at 04:10 UTC (00:10 EDT).

The Lambda function `hearth-search-v2` was deployed with code from commit `ac6660b` (Oct 22, 22:13 EDT), which **REVERTED** critical bug fixes that were working in commits `46d9f51` through `dce8f7c` (Oct 22, 22:24 - 23:39 EDT).

**Impact:** Multi-query search mode began returning incorrect results due to ambiguous sub-query generation, causing "blue homes" to match brick houses with blue skies instead of blue exteriors.

---

## DEPLOYMENT TIMELINE

### Critical Events (All times EDT)

| Time | Event | Commit | Status |
|------|-------|--------|--------|
| **22:13** | Commit: "Implement RRF diversification" | `ac6660b` | ❌ OLD (basic fallback) |
| 22:15 | Commit: "Clean up temporary test scripts" | `39d4c61` | ✅ No code changes |
| **22:24** | Commit: "Fix sub-query ambiguity" | `46d9f51` | ✅ **FIX APPLIED** |
| 22:32 | Commit: "Add standalone Multi-Query page" | `4be2778` | ✅ UI only |
| 22:35 | Commit: "Remove Multi-Query button" | `0bfe73d` | ✅ UI only |
| 23:19 | Commit: "Add multi-query toggle to main UI" | `0bf68b5` | ✅ UI only |
| 23:29 | Commit: "Fix score breakdown consistency" | `b94ff15` | ✅ UI only |
| 23:39 | Commit: "Add auto-refresh to dashboard" | `dce8f7c` | ✅ UI only |
| **23:54** | Git reset to 46d9f51 (intermediate state) | - | ⚠️ Testing? |
| **00:09** | Git reset to ac6660b | - | ❌ **REVERT TO OLD CODE** |
| **00:10** | Lambda deployment (UpdateFunctionCode) | `ac6660b` | ❌ **REGRESSION DEPLOYED** |

### Lambda Deployment History (Oct 22-23)

```
ALL DEPLOYMENTS (Oct 22, 20:00 - Oct 23, 04:10 UTC):
- 2025-10-22 20:08:22 EDT - UpdateFunctionCode
- 2025-10-22 20:10:04 EDT - UpdateFunctionCode
- 2025-10-22 20:11:42 EDT - UpdateFunctionCode
- 2025-10-22 20:18:43 EDT - UpdateFunctionCode
- 2025-10-22 20:23:37 EDT - UpdateFunctionCode
- 2025-10-22 20:32:07 EDT - UpdateFunctionCode
- 2025-10-22 21:26:39 EDT - UpdateFunctionCode
- 2025-10-22 21:28:59 EDT - UpdateFunctionCode
- 2025-10-22 21:31:59 EDT - UpdateFunctionCode
- 2025-10-22 21:33:50 EDT - UpdateFunctionCode
- 2025-10-22 21:36:41 EDT - UpdateFunctionCode
- 2025-10-22 21:55:39 EDT - UpdateFunctionCode
- 2025-10-22 21:56:52 EDT - UpdateFunctionCode
- 2025-10-22 22:07:30 EDT - UpdateFunctionCode
- 2025-10-22 22:23:08 EDT - UpdateFunctionCode
- 2025-10-23 00:10:18 EDT - UpdateFunctionCode ← REGRESSION DEPLOYMENT
```

**Currently Deployed:**
- Last Modified: `2025-10-23T04:10:18.000+0000` (00:10 EDT)
- CodeSha256: `Wx7MWoE3OILwhGYW6sHHgoKEB1r0tMFPO4iT/OASdus=`
- Commit: `ac6660b` (Oct 22, 22:13 EDT)
- Description: "Adaptive K selection for multi-feature image queries"

---

## CODE COMPARISON: WORKING vs BROKEN

### WORKING Code (commit 46d9f51 - Oct 22, 22:24 EDT)

**Location:** `/Users/andrewcarras/hearth_backend_new/search.py`, function `split_query_into_sub_queries()`

#### LLM Prompt Enhancement
```python
IMPORTANT DISTINCTIONS TO AVOID AMBIGUITY:
- "White house" → "white painted exterior house facade siding" (NOT "white kitchen" or "white walls")
- "Blue exterior" → "blue painted house exterior facade siding building" (NOT "blue sky" or "blue interior")
- "Gray exterior" → "gray painted house exterior facade siding building" (NOT "gray sky" or "gray interior")
- "Granite countertops" → "granite stone countertops kitchen surfaces" (specify KITCHEN)
- "Hardwood floors" → "hardwood flooring floors interior wood planks" (specify FLOORS)
- "Modern home" → "modern architecture exterior design contemporary house style building"

**CRITICAL**: For exterior colors, ALWAYS include words like "house", "building", "facade", "siding", "painted" to distinguish from sky, landscape, or interior elements.
```

#### Smart Fallback Logic (when LLM fails)
```python
except Exception as e:
    logger.warning(f"LLM query splitting failed: {e}, falling back to smart default sub-queries")
    # Fallback: create smart sub-queries with proper context
    sub_queries = []
    for feature in must_have_features[:3]:  # Limit to 3
        # Smart fallback that adds context based on feature type
        if '_exterior' in feature or feature.endswith('_exterior'):
            # Exterior color: add explicit house/building context to avoid sky matches
            color = feature.replace('_exterior', '')
            query = f"{color} painted house exterior facade siding building"
            context = "exterior_primary"
            weight = 2.0
        elif 'countertops' in feature:
            # Countertops: specify kitchen
            material = feature.replace('_countertops', '')
            query = f"{material} stone countertops kitchen surfaces"
            context = "interior_secondary"
            weight = 1.0
        elif 'floors' in feature or 'flooring' in feature:
            # Flooring: specify interior floors
            material = feature.replace('_floors', '').replace('_flooring', '')
            query = f"{material} flooring floors interior wood planks"
            context = "interior_secondary"
            weight = 1.0
        elif any(style in feature for style in ['modern', 'craftsman', 'colonial', 'victorian', 'ranch']):
            # Architectural style
            query = f"{feature.replace('_', ' ')} architecture exterior design house style"
            context = "architectural_style"
            weight = 1.5
        else:
            # Generic fallback
            query = feature.replace('_', ' ')
            context = "general"
            weight = 1.0

        sub_queries.append({
            "query": query,
            "feature": feature,
            "context": context,
            "weight": weight,
            "search_strategy": "max",
            "rationale": "smart_fallback"
        })

    return {
        "sub_queries": sub_queries,
        "combination_strategy": "weighted_sum",
        "primary_feature": must_have_features[0] if must_have_features else None
    }
```

---

### BROKEN Code (commit ac6660b - CURRENTLY DEPLOYED)

**Location:** Same file and function

#### LLM Prompt (Less Specific)
```python
IMPORTANT DISTINCTIONS:
- "White house" → "white exterior house facade" (NOT "white kitchen" or "white walls")
- "Blue exterior" → "blue exterior house outside facade" (emphasize OUTSIDE)
- "Granite countertops" → "granite countertops kitchen" (specify KITCHEN)
- "Modern home" → "modern architecture exterior design contemporary style"
```

❌ **Missing:** CRITICAL warning about sky/background matches
❌ **Missing:** Examples for gray exterior, hardwood floors
❌ **Missing:** Explicit "painted", "siding", "building" keywords

#### Basic Fallback Logic (when LLM fails)
```python
except Exception as e:
    logger.warning(f"LLM query splitting failed: {e}, falling back to single query")
    # Fallback: create basic sub-queries from features
    return {
        "sub_queries": [
            {
                "query": f"{feature.replace('_', ' ')}",
                "feature": feature,
                "context": "general",
                "weight": 1.0,
                "search_strategy": "max",
                "rationale": "fallback"
            }
            for feature in must_have_features[:3]  # Limit to 3
        ],
        "combination_strategy": "weighted_sum",
        "primary_feature": must_have_features[0] if must_have_features else None
    }
```

❌ **Problem:** "blue_exterior" becomes "blue exterior" (matches blue skies)
❌ **Problem:** All features get weight=1.0 (no prioritization)
❌ **Problem:** No context-specific handling

---

## TECHNICAL IMPACT

### Sub-Query Generation Comparison

| Feature | OLD CODE (broken) | NEW CODE (working) |
|---------|-------------------|-------------------|
| `blue_exterior` | "blue exterior" | "blue painted house exterior facade siding building" |
| `white_exterior` | "white exterior" | "white painted exterior house facade siding" |
| `granite_countertops` | "granite countertops" | "granite stone countertops kitchen surfaces" |
| `hardwood_floors` | "hardwood floors" | "hardwood flooring floors interior wood planks" |

### Query: "blue homes with granite countertops"

**BROKEN (ac6660b):**
```json
{
  "sub_queries": [
    {"query": "blue exterior", "weight": 1.0},
    {"query": "granite countertops", "weight": 1.0}
  ]
}
```
→ Matches: Blue skies ✅, Blue interiors ✅, Blue houses ✅ (TOO BROAD)

**WORKING (46d9f51):**
```json
{
  "sub_queries": [
    {"query": "blue painted house exterior facade siding building", "weight": 2.0},
    {"query": "granite stone countertops kitchen surfaces", "weight": 1.0}
  ]
}
```
→ Matches: Only blue exterior houses ✅ (PRECISE)

---

## ROOT CAUSE ANALYSIS

### What Happened?

1. **Oct 22, 22:13 EDT**: Commit `ac6660b` introduced RRF diversification but had **basic fallback logic**
2. **Oct 22, 22:24 EDT**: Commit `46d9f51` **FIXED** the ambiguity issue with smart fallback
3. **Oct 22, 22:24-23:39 EDT**: Several UI-only commits (no search.py changes)
4. **Oct 22, 23:54 EDT**: Git reset to `46d9f51` (unknown reason - testing?)
5. **Oct 23, 00:09 EDT**: Git reset to `ac6660b` ← **CRITICAL ERROR**
6. **Oct 23, 00:10 EDT**: Lambda deployed with old code

### Why It Happened?

**Hypothesis:** Developer reverted to `ac6660b` to re-deploy the "last known stable" RRF code, not realizing:
- Commits `46d9f51` through `dce8f7c` were **improvements**, not regressions
- Only `46d9f51` contained search.py changes (others were UI-only)
- The fix for sub-query ambiguity was lost

**Evidence:**
```bash
$ git reflog --date=iso
ac6660b HEAD@{2025-10-23 00:09:50 -0400}: reset: moving to ac6660b
46d9f51 HEAD@{2025-10-22 23:54:41 -0400}: reset: moving to 46d9f51
dce8f7c HEAD@{2025-10-22 23:39:10 -0400}: commit: Add auto-refresh to analytics dashboard
...
```

The reflog shows **two git resets** before deployment, suggesting confusion about which version to deploy.

---

## GIT HISTORY ANALYSIS

### Commits Between Working and Broken Versions

```bash
$ git log ac6660b..dce8f7c --oneline

dce8f7c Add auto-refresh to analytics dashboard          (ui/analytics.html, ui/analytics.js)
b94ff15 Fix score breakdown consistency for multi-query  (ui/search.html, docs/)
0bf68b5 Add multi-query mode toggle to main search UI    (ui/search.html)
0bfe73d Remove Multi-Query Search button from navigation (ui/search.html)
4be2778 Add standalone Multi-Query Search page           (ui/comparison.html)
46d9f51 Fix sub-query ambiguity to avoid sky/background  (search.py ← CRITICAL FIX)
39d4c61 Clean up temporary test scripts                  (scripts/archive/)
```

**Key Finding:** Only commit `46d9f51` changed `search.py` - all others are UI-only.

---

## COMPARISON WITH ORIGIN/MAIN

**Local HEAD:** `ac6660b` (old code, deployed to Lambda)
**Remote origin/main:** `dce8f7c` (latest code with fixes)

```bash
$ git status
On branch main
Your branch is behind 'origin/main' by 7 commits, and can be fast-forwarded.
```

**Conclusion:** Local repository is OUT OF SYNC with remote. The Lambda was deployed from an outdated local state.

---

## NO UNCOMMITTED CHANGES

```bash
$ git diff search.py
(no output)

$ git diff --stat ac6660b HEAD
(no output)
```

**Conclusion:** Current working directory matches `ac6660b` exactly. No uncommitted changes. The regression is purely from deploying the wrong commit.

---

## RRF AND GREEDY SELECTION LOGIC

### Status: NO CHANGES

Checked all versions between `ac6660b` and `dce8f7c`:
- `calculate_multi_query_image_score()` - **IDENTICAL**
- `calculate_multi_query_image_score_detailed()` - **IDENTICAL**
- Greedy diversification algorithm - **IDENTICAL**
- RRF scoring weights - **IDENTICAL**

**Conclusion:** The core RRF/greedy logic did NOT change. Only the sub-query generation changed.

---

## RESOLUTION STEPS

### Immediate Fix (Deploy Latest Code)

```bash
# 1. Sync with remote
git fetch origin
git reset --hard origin/main

# 2. Verify we have the fix
git log --oneline -5
# Should show: dce8f7c Add auto-refresh to analytics dashboard

# 3. Deploy to Lambda
./deploy_lambda.sh search

# 4. Verify deployment
aws lambda get-function --function-name hearth-search-v2 \
  --query 'Configuration.LastModified' --output text
```

### Verify Fix

Run test query:
```bash
curl -X POST https://your-lambda-url/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "blue homes with granite countertops",
    "use_multi_query": true,
    "k": 10
  }' | jq '.sub_queries'
```

**Expected output:**
```json
{
  "sub_queries": [
    {
      "query": "blue painted house exterior facade siding building",
      "feature": "blue_exterior",
      "weight": 2.0
    },
    {
      "query": "granite stone countertops kitchen surfaces",
      "feature": "granite_countertops",
      "weight": 1.0
    }
  ]
}
```

---

## PREVENTION RECOMMENDATIONS

### 1. Deployment Process
- [ ] Add commit hash to Lambda description on deployment
- [ ] Require explicit commit hash in deploy script (e.g., `./deploy.sh ac6660b`)
- [ ] Add pre-deployment check: "Is local branch synced with origin?"

### 2. Code Review
- [ ] Tag stable releases (e.g., `v1.5.2-rrf-fix`)
- [ ] Never use `git reset` in production workflow
- [ ] Use `git revert` to undo commits (preserves history)

### 3. Monitoring
- [ ] Add Lambda environment variable: `GIT_COMMIT_HASH`
- [ ] Log commit hash on Lambda startup
- [ ] CloudWatch alarm: "Unexpected code version deployed"

### 4. Testing
- [ ] Add integration test: "blue homes" should return blue exterior houses
- [ ] Add regression test: "blue homes" should NOT match brick houses with blue skies
- [ ] Run tests before deployment

---

## APPENDIX: KEY FILE LOCATIONS

### Deployed Lambda Code
- **Function:** `hearth-search-v2`
- **Region:** `us-east-1`
- **Runtime:** `python3.11`
- **Handler:** `search.lambda_handler`

### Local Repository
- **Path:** `/Users/andrewcarras/hearth_backend_new`
- **Branch:** `main`
- **HEAD:** `ac6660b` (OUTDATED)
- **Remote:** `origin/main` at `dce8f7c` (LATEST)

### Critical Files
- **Search Logic:** `/Users/andrewcarras/hearth_backend_new/search.py`
- **Deploy Script:** `/Users/andrewcarras/hearth_backend_new/deploy_lambda.sh`
- **Common Utils:** `/Users/andrewcarras/hearth_backend_new/common.py`

---

## SUMMARY

**Problem:** Lambda deployed with old code from `ac6660b` instead of latest `dce8f7c`

**Impact:** Sub-query generation broken, causing incorrect multi-query search results

**Root Cause:** Manual `git reset` to old commit before deployment

**Fix:** Deploy latest code from `origin/main` (commit `dce8f7c`)

**Timeline:**
- ✅ Working: Oct 22, 22:24 - 23:54 EDT (commit 46d9f51)
- ❌ Broken: Oct 23, 00:10+ EDT (commit ac6660b deployed)

**Next Steps:**
1. Deploy latest code (`dce8f7c` or `origin/main`)
2. Test multi-query searches
3. Implement deployment safeguards

---

*Report Generated: 2025-10-23*
*Analysis Tool: Claude Code*
