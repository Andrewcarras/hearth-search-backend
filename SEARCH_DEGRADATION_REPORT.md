# Search Quality Degradation Investigation Report

**Investigation Date:** 2025-10-23 00:26:43
**Time Range Analyzed:** Last 3 hours (2025-10-22 21:26:43 to 2025-10-23 00:26:43)
**Data Source:** DynamoDB SearchQueryLogs table

---

## Executive Summary

Search quality degradation was detected affecting **multi_query=true searches ONLY**. The degradation manifested as incorrect zpids appearing in results for "white homes" queries, specifically:
- **zpid 12778555** (red brick exterior - WRONG)
- **zpid 70592220** (blue brick exterior - WRONG)

These properties have **opposite characteristics** to what was requested (white exterior).

---

## Timeline of Events

### Phase 1: Early Degradation (21:07:06 - 21:07:30)
**FIRST SIGNS OF DEGRADATION DETECTED**

| Time | Query ID | Query | Multi-Query | Top 5 zpids | Status |
|------|----------|-------|-------------|-------------|--------|
| 21:07:06 | 3ce8bc95-90d0-43a6-b5e8-ccda59ffb397 | "White homes with granite countertops and hardwood floors" | TRUE | 12877768, 12753427, 12861297, 79525695, **70592220** | ❌ DEGRADED |
| 21:07:30 | 5d013c05-7a32-4382-8bbb-2716527d2343 | "White homes with granite countertops and hardwood floors" | TRUE | 12877768, 12753427, 12861297, 79525695, **70592220** | ❌ DEGRADED |

**Note:** zpid 70592220 (blue brick) appeared in position 5.

---

### Phase 2: Recovery Period (21:07:30 - 23:36:03)
**SEARCH QUALITY RETURNED TO NORMAL**

| Time | Query ID | Sample zpids | Status |
|------|----------|--------------|--------|
| 21:19:19 - 22:06:03 | Multiple | 2080387168, 454833364, 12787813, 12721617, etc. | ✅ GOOD |

All searches from 21:19:19 through 22:06:03 showed **good quality results** with appropriate white exterior properties.

---

### Phase 3: Major Degradation (23:36:03 - 00:10:44)
**SEVERE DEGRADATION - BOTH BAD ZPIDS IN TOP 3**

| Time | Query ID | Query | Top 5 zpids | Avg Score | Status |
|------|----------|-------|-------------|-----------|--------|
| 23:36:03 | 31e68fba-4297-4e0e-bab7-c1c08f1d00e5 | "White homes with granite countertops and wood floors" | 2080387168, **12778555**, **70592220**, 12717999, 12792227 | 0.051200 | ❌ DEGRADED |
| 23:52:05 | cb535cbc-dbfc-4ae8-bf2a-8cad84c9f980 | "White homes with granite countertops and wood floors" | 2080387168, **12778555**, **70592220**, 12717999, 12792227 | 0.051200 | ❌ DEGRADED |

**Critical findings:**
- **zpid 12778555** (red brick) at position 2
- **zpid 70592220** (blue brick) at position 3
- Same exact top 5 zpids repeated across multiple searches
- Duration: **~34 minutes** (23:36:03 to 00:10:44)

---

### Phase 4: Final Recovery (00:10:44+)
**SEARCH QUALITY RESTORED**

| Time | Query ID | Query | Top 5 zpids | Avg Score | Status |
|------|----------|-------|-------------|-----------|--------|
| 00:14:16 | 8d048382-b4bd-46c4-812e-67e0ec8b7449 | "White homes with granite countertops" | 2080387168, 454833364, 2057875868, 453896301, 12792227 | 0.046300 | ✅ GOOD |
| 00:15:11 | 5975d287-040b-4b7b-a593-764958e078dd | "White homes with granite countertops and wood floors" | 12780060, 455537877, 12818543, 2084386025, 12778315 | 0.051300 | ✅ GOOD |

Good quality results resumed with **no bad zpids** appearing.

---

## Key Findings

### 1. Affected vs Unaffected

| Mode | Affected? | Evidence |
|------|-----------|----------|
| **multi_query=true** | ✅ YES | Bad zpids appeared in 5+ searches |
| **multi_query=false** | ❌ NO | No bad zpids found in any searches |

**Conclusion:** Issue is **isolated to multi-query logic**, not the base search system.

---

### 2. Degradation Patterns

#### Early Degradation (21:07)
- **Symptom:** zpid 70592220 appeared in position 5
- **Severity:** Minor (only 1 bad zpid)
- **Duration:** ~12 minutes before recovery

#### Major Degradation (23:36)
- **Symptom:** BOTH zpids 12778555 and 70592220 in positions 2 & 3
- **Severity:** Critical (2 bad zpids in top 3)
- **Duration:** ~34 minutes
- **Pattern:** Identical top 5 results across multiple searches (suggests caching or stale data)

---

### 3. Quality Metrics Comparison

| Phase | Avg Score Range | Perfect Matches | Typical zpids |
|-------|----------------|-----------------|---------------|
| **Good Periods** | 0.034-0.048 | 0 | 2080387168, 454833364, 12787813, 12721617, 2057875868 |
| **Degraded Periods** | 0.051-0.051 | 0 | 2080387168, **12778555**, **70592220**, 12717999, 12792227 |

**Interesting:** Degraded searches had **slightly HIGHER** avg_score (0.051 vs 0.034-0.048), suggesting the bad zpids were being **incorrectly boosted** by multi-query logic.

---

## Root Cause Analysis

### Possible Causes (in order of likelihood):

### 1. ✅ Multi-Query Sub-Query Generation Issue (MOST LIKELY)
**Evidence:**
- Only multi_query=true affected
- Bad zpids appeared in **consistent patterns** (same top 5 across multiple searches)
- Higher scores on degraded results suggest incorrect boosting

**Hypothesis:** Multi-query feature is generating sub-queries that:
- Incorrectly interpret "white" as brick texture instead of color
- Boost properties with "granite" and "wood" features regardless of exterior color
- Over-weight semantic similarity at expense of explicit constraints

**What to check:**
- Sub-query texts generated during degraded periods
- Whether sub-queries mentioned "brick" when they shouldn't
- Feature extraction from multi-query analysis

---

### 2. ❌ Embedding Model Drift (LESS LIKELY)
**Evidence against:**
- multi_query=false was NOT affected
- Recovery happened without code changes (based on timing)
- Pattern was too consistent (same exact zpids)

**Unlikely** because base search worked fine.

---

### 3. ❌ Data Updates/Re-indexing (POSSIBLE)
**Evidence:**
- Time gaps between degradation periods might align with data updates
- Recovery happened automatically after ~34 minutes

**What to check:**
- OpenSearch indexing jobs around 21:07 and 23:36
- Whether zpids 12778555 and 70592220 were updated at those times
- Index refresh timing

---

### 4. ✅ Cache/TTL Issue (LIKELY CONTRIBUTING FACTOR)
**Evidence:**
- Identical results across multiple searches during degraded period
- Automatic recovery after fixed duration (~34 minutes)
- Pattern suggests cached/stale results

**What to check:**
- Multi-query caching mechanisms
- TTL settings (34 minutes seems like it could be a cache timeout)
- Whether cache invalidation failed

---

## Time Gaps and Deployment Correlation

### Significant Time Gaps (potential deployments):

| Gap | From → To | Duration | Event |
|-----|-----------|----------|-------|
| 1 | 21:07:30 → 21:19:19 | ~12 min | Recovery from early degradation |
| 2 | 22:06:03 → 23:36:03 | **~90 min** | 🚨 **CRITICAL - Likely deployment or system change** |
| 3 | 23:52:05 → 00:14:16 | ~22 min | Recovery from major degradation |

**Most suspicious:** 90-minute gap before major degradation suggests:
- Lambda deployment around 22:06-23:36
- Configuration change
- Cache warming with bad data
- Index update

---

## Recommendations

### Immediate Actions:

1. **Check Lambda Deployments**
   - Review Lambda deployment logs from 22:00-23:30
   - Check if multi-query logic was changed
   - Verify configuration changes

2. **Inspect Multi-Query Sub-Queries**
   - Pull query_id: `31e68fba-4297-4e0e-bab7-c1c08f1d00e5` (first major degradation)
   - Examine `multi_query_status.sub_queries` field
   - Check if sub-queries incorrectly mentioned "brick" or misinterpreted "white"

3. **Review Caching**
   - Check if multi-query results are cached
   - Verify cache TTL (~34 minutes aligns with degradation duration)
   - Ensure cache keys include all relevant parameters

### Medium-term:

4. **Add Constraint Validation**
   - Ensure multi-query sub-queries respect explicit constraints
   - If query says "white exterior", filter out properties with "red_exterior" or "blue_exterior" tags
   - Add post-processing filter as safety net

5. **Monitor Multi-Query Quality**
   - Add alerts for when multi_query=true results differ significantly from multi_query=false
   - Track when bad zpids (12778555, 70592220) appear in any results
   - Set up quality metric thresholds

6. **Improve Feature Matching**
   - Current searches show **0 perfect_matches** even in good results
   - Suggests tagging or feature extraction needs improvement
   - Focus on color + material combinations

---

## Data Source Details

**DynamoDB Table:** SearchQueryLogs
**Region:** us-east-1
**Query Type:** Scan with timestamp filter
**Total Searches Analyzed:** 99
**White Homes Queries:** 81
**Multi-Query=True:** 60
**Multi-Query=False:** 21

---

## Appendix: Key Query IDs for Further Investigation

### Degraded Searches:
- **21:07:06** - `3ce8bc95-90d0-43a6-b5e8-ccda59ffb397` (Early degradation)
- **23:36:03** - `31e68fba-4297-4e0e-bab7-c1c08f1d00e5` (First major degradation)
- **23:52:05** - `cb535cbc-dbfc-4ae8-bf2a-8cad84c9f980` (Last major degradation)

### Good Searches (for comparison):
- **22:06:03** - `ea4d1f6f-79fc-4ccd-80dc-8c5a224c1584` (Last good before major degradation)
- **00:14:16** - `8d048382-b4bd-46c4-812e-67e0ec8b7449` (First recovered)

### Investigation Commands:
```python
from search_log_reader import get_search_by_query_id, print_search_summary

# Get detailed search info
search = get_search_by_query_id("31e68fba-4297-4e0e-bab7-c1c08f1d00e5")
print_search_summary(search)

# Check multi-query sub-queries
print(search['multi_query_status']['sub_queries'])
```

---

## Conclusion

Search quality degradation was **real and measurable**, affecting multi_query=true searches specifically. The issue:

1. **Started:** 21:07 (minor), then 23:36 (major)
2. **Ended:** 00:10 (automatic recovery)
3. **Root Cause:** Likely multi-query sub-query generation incorrectly boosting brick properties
4. **Contributing Factor:** Possible caching of bad results (~34 minute TTL)
5. **Trigger:** Suspected deployment or configuration change around 22:06-23:36

The fact that **multi_query=false was unaffected** and **identical bad results repeated** suggests a **caching + query generation issue** rather than underlying data or model problems.

**Next Step:** Examine the `multi_query_status` field in degraded searches to see actual sub-queries generated.
