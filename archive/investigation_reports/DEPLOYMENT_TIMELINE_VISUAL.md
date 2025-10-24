# Lambda Deployment Timeline - Visual Summary
## Oct 22-23, 2025 - Search Quality Degradation

---

## QUICK ANSWER

**What broke?** Lambda was deployed with OLD code from 2 hours earlier, reverting a critical bug fix.

**When?** Oct 23, 00:10 EDT (04:10 UTC)

**Why?** Manual `git reset` to commit `ac6660b`, then deployed without realizing the fix in `46d9f51` was lost.

**Fix?** Deploy latest code from `origin/main` (commit `dce8f7c`)

---

## VISUAL TIMELINE

```
Oct 22, 2025 (EDT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

22:13  ┌─────────────────────────────────────────────────┐
       │ ac6660b - Implement RRF diversification         │
       │ STATUS: Basic fallback (matches blue skies) ❌  │
       │ DEPLOYED: Multiple times 20:08-22:23           │
       └─────────────────────────────────────────────────┘
         │
         │ (1 hour of active development)
         ▼

22:24  ┌─────────────────────────────────────────────────┐
       │ 46d9f51 - Fix sub-query ambiguity              │
       │ STATUS: Smart fallback (only blue houses) ✅    │
       │ CHANGE: Enhanced LLM prompt + fallback logic   │
       └─────────────────────────────────────────────────┘
         │
         │ (5 UI-only commits)
         ▼

23:39  ┌─────────────────────────────────────────────────┐
       │ dce8f7c - Add auto-refresh to dashboard        │
       │ STATUS: Latest code (all fixes included) ✅     │
       │ PUSHED TO: origin/main                         │
       └─────────────────────────────────────────────────┘

23:54  ⚠️  Git reset to 46d9f51 (testing?)

Oct 23, 2025 (EDT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

00:09  ❌ Git reset to ac6660b
       │
       │ CRITICAL: Reverted to 2-hour-old code
       │ LOST FIX: Sub-query ambiguity fix from 46d9f51
       ▼

00:10  ┌─────────────────────────────────────────────────┐
       │ Lambda Deployment (UpdateFunctionCode)         │
       │ CODE: ac6660b (Oct 22, 22:13)                  │
       │ STATUS: REGRESSION DEPLOYED ❌                  │
       │ CodeSha256: Wx7MWoE3OILwhGYW6sHHgoKEB...       │
       └─────────────────────────────────────────────────┘
         │
         │ (Lambda now running old code)
         ▼

03:30  🔍 Search queries work (using single-query mode?)

05:30  ❌ Search quality issues reported
       │  "blue homes" returns brick houses with blue skies
       └─ Multi-query mode affected
```

---

## CODE VERSION COMPARISON

```
┌─────────────────────────────────────────────────────────────────┐
│                        DEPLOYED VERSION                         │
│                     (ac6660b - Oct 22, 22:13)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Fallback Logic (when LLM fails):                              │
│  ────────────────────────────────                              │
│  "blue_exterior" → "blue exterior"                             │
│  "white_exterior" → "white exterior"                           │
│  "granite_countertops" → "granite countertops"                 │
│                                                                 │
│  ❌ Matches: Blue skies, blue interiors, blue houses          │
│  ❌ Weight: All features = 1.0 (no prioritization)            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

                              VS

┌─────────────────────────────────────────────────────────────────┐
│                      LATEST VERSION (FIX)                       │
│                   (dce8f7c / origin/main)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Smart Fallback Logic:                                         │
│  ──────────────────────                                        │
│  "blue_exterior" → "blue painted house exterior facade siding  │
│                     building" (weight=2.0)                     │
│  "white_exterior" → "white painted exterior house facade       │
│                      siding" (weight=2.0)                      │
│  "granite_countertops" → "granite stone countertops kitchen    │
│                           surfaces" (weight=1.0)               │
│                                                                 │
│  ✅ Matches: ONLY blue exterior houses                         │
│  ✅ Weight: Exterior=2.0, Interior=1.0 (proper priority)      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## GIT COMMIT GRAPH

```
origin/main → dce8f7c  ← LATEST (has fix)
              ↓
            b94ff15    (UI only)
              ↓
            0bf68b5    (UI only)
              ↓
            0bfe73d    (UI only)
              ↓
            4be2778    (UI only)
              ↓
            46d9f51    ← FIX APPLIED ✅
              ↓
            39d4c61    (cleanup only)
              ↓
local HEAD → ac6660b   ← DEPLOYED (missing fix) ❌
              ↓
            15c009b
              ↓
             ...
```

---

## LAMBDA DEPLOYMENT HISTORY

```
ALL UPDATES TO hearth-search-v2 (Oct 22-23):
═══════════════════════════════════════════

20:08 EDT ──┐
20:10 EDT   │
20:11 EDT   │
20:18 EDT   ├─ Development iterations
20:23 EDT   │  (pre-RRF testing)
20:32 EDT   │
21:26 EDT   │
21:28 EDT ──┘

21:31 EDT ──┐
21:33 EDT   │
21:36 EDT   ├─ RRF implementation
21:55 EDT   │  (ac6660b or earlier)
21:56 EDT   │
22:07 EDT   │
22:23 EDT ──┘

          ⏸️  (Development pause - commits 46d9f51 through dce8f7c)

00:10 EDT ──── ❌ REGRESSION DEPLOYED (ac6660b)
              Missing fix from 46d9f51

          ⏸️  (Lambda not updated since)

CURRENT ────── Still running old code (ac6660b)
```

---

## WHAT CHANGED IN THE FIX?

### File: `search.py`
### Function: `split_query_into_sub_queries()`
### Lines Changed: ~70 lines

**Changes:**

1. **Enhanced LLM Prompt** (lines 720-732)
   - Added "CRITICAL" warning about sky/background matches
   - More examples: white, blue, gray exteriors
   - Explicit keywords: "painted", "siding", "building"

2. **Smart Fallback Logic** (lines 770-815)
   - **OLD:** Simple string replacement (`blue_exterior` → `blue exterior`)
   - **NEW:** Context-aware logic:
     - Exterior colors → Add "painted house exterior facade siding building" (weight=2.0)
     - Countertops → Add "stone countertops kitchen surfaces" (weight=1.0)
     - Floors → Add "flooring floors interior wood planks" (weight=1.0)
     - Styles → Add "architecture exterior design house style" (weight=1.5)

3. **Weight Prioritization**
   - **OLD:** All features = 1.0
   - **NEW:** Exterior=2.0, Style=1.5, Interior=1.0

---

## HOW TO VERIFY CURRENT STATE

```bash
# Check current Lambda deployment
aws lambda get-function --function-name hearth-search-v2 \
  --query 'Configuration.[LastModified,Description]' \
  --output table

# Expected output:
# LastModified: 2025-10-23T04:10:18.000+0000
# Description: Adaptive K selection for multi-feature image queries

# Check local git state
git status

# Expected output:
# On branch main
# Your branch is behind 'origin/main' by 7 commits

# Check commit hash
git rev-parse HEAD

# Expected output:
# ac6660b84680896399bb7fc569ba2bfdfbf04247
```

---

## HOW TO FIX

### Option 1: Fast-Forward to Latest (Recommended)

```bash
# Sync with remote
git pull origin main --ff-only

# Verify we have the fix
git log --oneline -1
# Should show: dce8f7c Add auto-refresh to analytics dashboard

# Deploy to Lambda
./deploy_lambda.sh search
```

### Option 2: Cherry-Pick Just the Fix

```bash
# Apply only the fix commit
git cherry-pick 46d9f51

# Deploy to Lambda
./deploy_lambda.sh search
```

### Option 3: Manual Reset to Fix Commit

```bash
# Reset to the commit with the fix
git reset --hard 46d9f51

# Deploy to Lambda
./deploy_lambda.sh search
```

**⚠️ WARNING:** Option 1 is recommended. Options 2-3 will leave you in a detached state or behind origin.

---

## VERIFICATION TESTS

### Test 1: Check Sub-Query Generation

```bash
# Query with multi-query mode
curl -X POST https://your-lambda-url/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "blue homes with granite countertops",
    "use_multi_query": true,
    "k": 10,
    "include_scoring_details": true
  }' | jq '.debug_info.sub_queries'
```

**Expected (FIXED):**
```json
[
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
```

**Current (BROKEN):**
```json
[
  {
    "query": "blue exterior",
    "feature": "blue_exterior",
    "weight": 1.0
  },
  {
    "query": "granite countertops",
    "feature": "granite_countertops",
    "weight": 1.0
  }
]
```

### Test 2: Check Result Quality

```bash
# Run query and check top 3 results
curl -X POST https://your-lambda-url/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "blue homes",
    "use_multi_query": true,
    "k": 3
  }' | jq '.results[] | {zpid, address, tags: .visual_features_exterior}'
```

**Expected (FIXED):** All 3 results should have "blue_exterior" tag

**Current (BROKEN):** Results may have brick exteriors (matched blue sky)

---

## FILES AFFECTED

```
Modified Files Between ac6660b and dce8f7c:
──────────────────────────────────────────

search.py                                    ← CRITICAL (search logic)
ui/analytics.html                            (dashboard UI)
ui/analytics.js                              (dashboard JS)
ui/search.html                               (search UI)
docs/features/SCORE_BREAKDOWN_MULTI_QUERY_FIX.md  (documentation)
docs/features/SUB_QUERY_AMBIGUITY_FIX.md     (documentation)
docs/README.md                               (documentation)
```

**Only `search.py` affects Lambda behavior.**

---

## SUMMARY STATISTICS

| Metric | Value |
|--------|-------|
| **Commits Behind** | 7 commits |
| **Critical Commit Missing** | 46d9f51 (Oct 22, 22:24 EDT) |
| **Deployed Commit** | ac6660b (Oct 22, 22:13 EDT) |
| **Time Between** | 11 minutes |
| **Lines Changed** | ~70 lines in search.py |
| **Files Changed** | 1 file (search.py) + 6 UI/docs |
| **Deployment Time** | Oct 23, 00:10 EDT |
| **Hours Broken** | ~5 hours (00:10 - 05:30 EDT) |

---

## NEXT STEPS

1. ✅ **Immediate:** Deploy latest code (`origin/main`)
2. ✅ **Verify:** Test "blue homes" query with multi-query mode
3. ✅ **Monitor:** Check CloudWatch logs for errors
4. ⏸️ **Document:** Add deployment checklist to prevent future regressions
5. ⏸️ **Automate:** Add commit hash to Lambda environment variables
6. ⏸️ **Test:** Add regression test for sub-query generation

---

*Timeline Generated: 2025-10-23*
*Analysis: Complete deployment history from CloudTrail + Git reflog*
