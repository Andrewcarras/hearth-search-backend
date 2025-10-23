# Quick Reference: Search Degradation Investigation

## The Answer in 30 Seconds

**When did results change?**
2025-10-23 04:10:44.290 UTC

**What changed?**
Results IMPROVED (not degraded) - bad zpids removed

**Why?**
Lambda deployment of sub-query ambiguity fix

**Evidence?**
14 bad searches → instant recovery → 6+ good searches

---

## Key Facts

| Question | Answer |
|----------|--------|
| Exact recovery time | 04:10:44.290 UTC (to the millisecond) |
| What was deployed | hearth-search-v2 (commit 46d9f51) |
| Deployment time | 04:10:18 UTC |
| Time to effect | 26 seconds |
| Bad zpids removed | 12778555, 70592220 |
| Quality improvement | +12.7% avg score |
| Searches analyzed | 40 total, 20 target query |
| CloudWatch errors | 0 |

---

## Before/After ZPIDs

### BEFORE (BAD)
Top 5: 2080387168, **12778555**, **70592220**, 12717999, 12792227

### AFTER (GOOD)
Top 5: 2080387168, **454833364**, **2057875868**, 453896301, 12792227

**Change:** Removed brick houses, added proper white houses

---

## What Was Fixed

**Problem:** "white exterior" sub-query matched white SKIES
**Solution:** "white painted house exterior facade siding building" sub-query only matches HOUSES

---

## Key Query IDs

- **Last bad:** 5478a95b-a77a-4451-9087-6c157c7d99fa (04:04:18 UTC)
- **First good:** 7bfee84d-c610-427c-903d-d5195eddf317 (04:10:44 UTC)

---

## Investigation Files

1. `EXECUTIVE_SUMMARY.md` - Start here (2 min read)
2. `DEGRADATION_TIMELINE.md` - Visual timeline (5 min read)
3. `DEGRADATION_INVESTIGATION_REPORT.md` - Full technical details (15 min read)
4. `degradation_investigation_results.json` - Raw data
5. `investigate_degradation_window.py` - Reusable investigation script

---

## Commit Details

```
Commit: 46d9f51d038d38244e3c6e34736d796a94748a83
Date: 2025-10-22 22:24:40 -0400 (02:24:40 UTC)
Deployed: 2025-10-23 04:10:18 UTC
Delay: 1 hour 46 minutes
Message: "Fix sub-query ambiguity to avoid sky/background matches"
```

---

## Status

✅ Issue resolved
✅ Quality improved
✅ No errors found
✅ System stable

**Current state:** All searches returning proper results
