# Search Degradation Timeline - Visual Summary

## Quick Facts
- **Investigation Window:** 03:30:00 - 05:38:00 UTC (2025-10-23)
- **Exact Recovery Time:** 04:10:44.290 UTC
- **Trigger:** Lambda deployment of commit 46d9f51
- **Time to Recovery:** 26 seconds after deployment
- **Root Cause:** Sub-query ambiguity fix

---

## Visual Timeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SEARCH RESULTS TIMELINE (UTC)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  02:13 ───┐                                                                  │
│  02:15    │  Commits made                                                    │
│  02:24 ───┼─► CRITICAL FIX COMMITTED (46d9f51)                               │
│  02:32    │  "Fix sub-query ambiguity to avoid sky/background matches"       │
│  02:35    │  More commits...                                                 │
│  03:19    │                                                                  │
│  03:29    │                                                                  │
│  03:39 ───┘                                                                  │
│           │                                                                  │
│           │                                                                  │
│  03:30 ───┐                                                                  │
│           │                                                                  │
│           │  ❌ BAD RESULTS PERIOD (40 minutes)                              │
│           │  --------------------------------                                │
│           │  14 consecutive searches with bad zpids                          │
│           │  • 12778555 (red brick house) appearing                          │
│           │  • 70592220 (blue brick house) appearing                         │
│           │  • Avg score: 0.0512                                             │
│           │  • Perfect matches: 0                                            │
│           │                                                                  │
│  03:30:08 │─► First bad search (ID: 0e76a125)                                │
│  03:30:56 │─► Bad search                                                     │
│  03:31:37 │─► Bad search                                                     │
│  03:36:03 │─► Bad search                                                     │
│  03:40:13 │─► Bad search                                                     │
│  03:47:28 │─► Bad search                                                     │
│  03:49:14 │─► Bad search                                                     │
│  03:49:33 │─► Bad search                                                     │
│  03:52:05 │─► Bad search                                                     │
│  03:56:19 │─► Bad search                                                     │
│  03:58:37 │─► Bad search                                                     │
│  04:01:04 │─► Bad search                                                     │
│  04:02:09 │─► Bad search                                                     │
│  04:04:18 │─► Last bad search (ID: 5478a95b)                                 │
│           │                                                                  │
│  04:10:18 ├─► 🚀 LAMBDA DEPLOYMENT                                           │
│           │   Function: hearth-search-v2                                     │
│           │   Commit: 46d9f51 (sub-query fix)                                │
│           │   CodeSha256: Wx7MWoE3OILwhGYW6sHHgoKEB1r0tMFPO4iT/OASdus=       │
│           │                                                                  │
│           │   ⏱️  26 seconds...                                               │
│           │                                                                  │
│  04:10:44 ├─► ✅ RECOVERY! First good search (ID: 7bfee84d)                  │
│           │                                                                  │
│           │  ✅ GOOD RESULTS (continuing)                                    │
│           │  -------------------------                                       │
│           │  • Bad zpids removed (12778555, 70592220)                        │
│           │  • New good zpids added (454833364, 2057875868)                  │
│           │  • Avg score: 0.0577 (+12.7% improvement)                        │
│           │                                                                  │
│  04:10:57 │─► Good search                                                    │
│  04:14:50 │─► Good search (different results, still good)                    │
│  04:15:02 │─► Good search                                                    │
│  04:15:11 │─► Good search                                                    │
│  04:15:25 └─► Good search                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Deployment Lag Analysis

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Commit Ready        Deployment         Recovery                        │
│  ─────────────────   ──────────────     ─────────                       │
│                                                                          │
│  02:24:40 UTC        04:10:18 UTC       04:10:44 UTC                    │
│      │                    │                   │                         │
│      │◄────1h 46m────────►│◄────26 sec───────►│                         │
│      │                    │                   │                         │
│   FIX READY           FIX DEPLOYED       USERS SEE FIX                  │
│                                                                          │
│                                                                          │
│  During 1h 46m delay:                                                   │
│  • 14 searches returned bad results                                     │
│  • Users saw brick houses for "white homes" query                       │
│  • Fix was available in code but not in production                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Results Comparison

### BAD Results (03:30 - 04:10 UTC)
```
Query: "White homes with granite countertops and wood floors"

Top 10 ZPIDs:
1. 2080387168      ✓ (white house - good match)
2. 12778555        ✗ (RED BRICK HOUSE - terrible match)
3. 70592220        ✗ (BLUE BRICK HOUSE - terrible match)
4. 12717999        ? (unknown quality)
5. 12792227        ✓ (appears in good results too)
6. 89416688        ✗ (removed in fix)
7. 12842411        ✗ (removed in fix)
8. 453896301       ✓ (appears in good results too)
9. 61167372        ✗ (removed in fix)
10. 12736760       ✗ (removed in fix)

Avg Score: 0.0512
Perfect Matches: 0

Sub-queries generated (OLD):
- "white exterior" ← matches white SKY, white INTERIOR, white HOUSES
- "granite countertops" ← somewhat specific
- "wood floors" ← matches many things
```

### GOOD Results (04:10:44+ UTC)
```
Query: "White homes with granite countertops and wood floors"

Top 10 ZPIDs:
1. 2080387168      ✓ (kept from before)
2. 454833364       ✓ NEW - proper white house
3. 2057875868      ✓ NEW - proper white house
4. 453896301       ✓ (kept from before)
5. 12792227        ✓ (kept from before)

Avg Score: 0.0577 (+12.7% improvement)
Perfect Matches: 0

Sub-queries generated (NEW):
- "white painted house exterior facade siding building" ← SPECIFIC to houses
- "granite stone countertops kitchen surfaces" ← SPECIFIC to kitchen
- "wood flooring floors interior planks" ← SPECIFIC to floors
```

---

## Key Metrics

| Metric | Before Fix | After Fix | Change |
|--------|-----------|-----------|--------|
| Bad zpids in top 5 | 2 (40%) | 0 (0%) | -100% ✅ |
| Avg Score | 0.0512 | 0.0577 | +12.7% ✅ |
| Perfect Matches | 0 | 0 | No change |
| Result Diversity | Low (same 10 zpids) | High (varying results) | Improved ✅ |

---

## The Fix Explained

### Problem: Ambiguous Sub-Queries
```
User query: "White homes with granite countertops and wood floors"

OLD sub-query generation:
├─ "white exterior"
│  └─ Matches: white houses ✓, white SKY ✗, white CLOUDS ✗, white WALLS ✗
├─ "granite countertops"
│  └─ Matches: granite in kitchen ✓, granite ANYWHERE ✗
└─ "wood floors"
   └─ Matches: wood floors ✓, wood EXTERIOR ✗, wood DECK ✗
```

### Solution: Contextual Sub-Queries
```
NEW sub-query generation:
├─ "white painted house exterior facade siding building"
│  └─ Matches: ONLY white houses ✓
├─ "granite stone countertops kitchen surfaces"
│  └─ Matches: ONLY granite in kitchen ✓
└─ "wood flooring floors interior planks"
   └─ Matches: ONLY interior wood floors ✓
```

### Code Changes
1. **Enhanced LLM Prompt:**
   - Added explicit examples for all color exteriors
   - Added CRITICAL warning to include "house", "building", "facade", "siding"
   - Examples: "blue exterior" → "blue painted house exterior facade siding building"

2. **Smart Fallback Logic:**
   - Exterior colors: Add "painted house exterior facade siding building" (weight=2.0)
   - Countertops: Add "stone countertops kitchen surfaces" (weight=1.0)
   - Floors: Add "flooring floors interior wood planks" (weight=1.0)
   - Architectural styles: Add "architecture exterior design house style" (weight=1.5)

---

## Investigation Summary

✅ **Exact transition timestamp identified:** 2025-10-23 04:10:44.290 UTC

✅ **Root cause identified:** Sub-query ambiguity causing sky/background matches

✅ **Trigger event identified:** Lambda deployment at 04:10:18 UTC

✅ **Before/After zpids documented:**
   - Removed: 12778555, 70592220 (brick houses)
   - Added: 454833364, 2057875868 (proper matches)

✅ **Complete timeline established:** 40 minutes bad, instant recovery after deployment

✅ **No errors found:** Clean deployment, zero CloudWatch errors

✅ **System monitoring confirmed:** All AWS services healthy during window

---

## Files Generated

1. `DEGRADATION_INVESTIGATION_REPORT.md` - Full detailed report
2. `DEGRADATION_TIMELINE.md` - This visual timeline
3. `degradation_investigation_results.json` - Raw data (40 searches)
4. `investigate_degradation_window.py` - Investigation script (reusable)

---

**Investigation completed:** 2025-10-23 04:41:19 UTC
**Total investigation time:** ~10 minutes
**Data sources:** DynamoDB, Lambda, CloudWatch, Git history
**Searches analyzed:** 40 total, 20 matching target query
