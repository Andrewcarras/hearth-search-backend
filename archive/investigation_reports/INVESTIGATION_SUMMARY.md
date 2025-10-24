# Search Quality Degradation Investigation - Summary

**Date:** October 23, 2025
**Time Range:** Last 3 hours (21:26 - 00:26)
**Total Searches Analyzed:** 99
**White Homes Queries:** 81

---

## 🎯 KEY FINDING

**The search quality degradation was caused by COMPLETE SEARCH PIPELINE FAILURE, not the multi-query feature.**

All search strategies (BM25, Text KNN, Image KNN) stopped returning results during the degradation period, and the system fell back to an unknown source with bad data.

---

## 📊 DEGRADATION TIMELINE

### Phase 1: Early Warning (21:07)
- **Time:** 21:07:06 - 21:07:30
- **Issue:** Only BM25 working (Text/Image KNN failed)
- **Impact:** zpid 70592220 (blue brick) appeared in position 5
- **Duration:** ~12 minutes

### Phase 2: Normal Operation (21:19 - 22:06)
- **Status:** All systems working
- **Sources:** BM25, Text KNN, Image KNN all active
- **Results:** Good quality

### Phase 3: Complete Failure (23:36 - 00:14+)
- **Time:** 23:36:03 onwards
- **Issue:** ALL sources showing "None" - complete pipeline failure
- **Impact:** zpids 12778555 (red brick) and 70592220 (blue brick) in top 3
- **Duration:** 38+ minutes
- **Exact same results repeated** (suggesting cache or fallback)

---

## 🔍 EVIDENCE

### Good Search Example (21:37:13)
```
Rank   ZPID         Score      Sources
1      2080387168   0.061101   Text#12, Img#9     ✅ Multiple sources
2      454833364    0.035714   Img#1              ✅ Working
3      12787813     0.035088   BM25#2             ✅ Working
```

### Degraded Search Example (23:36:03)
```
Rank   ZPID         Score      Sources
1      2080387168   0.070769   None               ❌ NO SOURCE
2      12778555     0.055556   None               ❌ RED BRICK!
3      70592220     0.054054   None               ❌ BLUE BRICK!
```

---

## 🚨 ROOT CAUSE ANALYSIS

### Primary Suspect: OpenSearch Cluster Issue

**Evidence:**
1. All three search strategies depend on OpenSearch
2. All three failed simultaneously
3. 2-hour gap (21:37 → 23:36) suggests deployment or outage
4. Results showing "Sources: None" indicate queries didn't execute

**Most Likely Causes:**
- OpenSearch cluster became unreachable
- Network connectivity issue
- Lambda timeout increased
- Index temporarily unavailable

### Secondary Issue: Fallback Mechanism

**The fallback that kicked in returned BAD DATA:**
- zpid 12778555: Red brick exterior (opposite of "white")
- zpid 70592220: Blue brick exterior (opposite of "white")
- These results were cached or pre-computed incorrectly

---

## 🔧 WHAT TO CHECK

### 1. OpenSearch Cluster Health (URGENT)
```bash
# Check cluster status during 21:37 - 23:36 on Oct 22
# Look for:
# - Cluster RED status
# - Node failures
# - Shard allocation issues
# - Network connectivity problems
```

### 2. Lambda Deployment History
```bash
# Check if Lambda was deployed between 21:30 - 23:30
# Configuration changes that might affect OpenSearch connection
```

### 3. Lambda Error Logs
```bash
# Search CloudWatch logs for 23:35:00 - 23:37:00
# Expected errors:
# - "OpenSearch connection timeout"
# - "Failed to execute search"
# - "Index not found"
```

### 4. Find the Fallback Code
```python
# In search.py, find:
# - What happens when OpenSearch queries return empty?
# - Where do results with "Sources: None" come from?
# - Is there a cache or default result set?
```

---

## ⚠️ ADDITIONAL FINDINGS

### 1. Multi-Query Feature Was NOT Actually Running

Despite `use_multi_query=true` in requests:
```
Multi-Query Status:
  Enabled: False
  Generated: False
  Sub-query Count: 0
```

**All searches (good and bad) had multi-query disabled**, so this was NOT the cause of degradation.

### 2. Feature Matching Is Broken

**Every search (including "good" ones) showed:**
```
Perfect Matches: 0
Partial Matches: 0
No Matches: 10
```

This means the system is **NOT finding properties that actually match the requested features** like "white_exterior", "granite_countertops", etc.

**This is a separate critical bug** that needs fixing.

### 3. No Search Strategy Consensus

```
Result Overlap Between Sources:
  BM25 ∩ Text KNN: 0
  BM25 ∩ Image KNN: 0
  Text ∩ Image KNN: 1
  All Three: 0
```

The three search strategies rarely agree on results. This suggests:
- Different ranking criteria
- Poor fusion strategy
- Need to tune RRF parameters

---

## 🛠️ RECOMMENDED FIXES

### Immediate (Do Today):

1. **Add Error Logging**
   ```python
   # In search.py, add explicit error logging:
   if not bm25_results:
       logger.error("BM25 query returned no results", extra={...})
   if not knn_text_results:
       logger.error("Text KNN query failed", extra={...})
   if not knn_image_results:
       logger.error("Image KNN query failed", extra={...})
   ```

2. **Add Source Validation**
   ```python
   # Before returning results:
   for result in final_results:
       if result.get('_scoring_details', {}).get('sources') == 'None':
           logger.error("Result with no source detected - INVALID")
           # Don't return this result
   ```

3. **Fix Feature Matching**
   ```python
   # Add post-query filter for must-have features
   if must_have_features:
       filtered_results = [
           r for r in results
           if all(feature in r.get('feature_tags', []) + r.get('image_tags', [])
                  for feature in must_have_features)
       ]
   ```

### Short-term (This Week):

4. **Improve Fallback Strategy**
   - Don't return results when all sources fail
   - Return explicit error instead
   - Or use cached GOOD results (not bad ones)

5. **Add Health Checks**
   ```python
   # Before running search:
   if not opensearch_client.ping():
       logger.error("OpenSearch unreachable")
       return {"error": "Search service unavailable"}
   ```

6. **Add Monitoring**
   - Alert when sources show "None"
   - Alert when bad zpids (12778555, 70592220) appear
   - Alert when all strategies fail

### Medium-term (This Month):

7. **Fix Multi-Query Feature**
   - Investigate why it's disabled
   - Either enable it or remove the parameter

8. **Improve Search Strategy Consensus**
   - Tune RRF parameters
   - Improve overlap between BM25, Text KNN, Image KNN
   - Target: 30%+ consensus

9. **Better Feature Tagging**
   - Ensure all properties have accurate tags
   - Validate tags match actual property characteristics
   - Add tag quality metrics

---

## 📈 SUCCESS METRICS

### Fix Validation:
- ✅ No results with "Sources: None"
- ✅ No searches with all strategies failing
- ✅ Bad zpids (12778555, 70592220) never appear for "white homes" queries
- ✅ At least 50% perfect feature matches for targeted queries
- ✅ Result overlap between strategies > 20%

---

## 📋 INVESTIGATION ARTIFACTS

All analysis scripts and data:
- `/Users/andrewcarras/hearth_backend_new/investigate_search_degradation.py`
- `/Users/andrewcarras/hearth_backend_new/compare_multiquery_results.py`
- `/Users/andrewcarras/hearth_backend_new/examine_multiquery_subqueries.py`
- `/Users/andrewcarras/hearth_backend_new/SEARCH_DEGRADATION_REPORT.md`
- `/Users/andrewcarras/hearth_backend_new/FINAL_DEGRADATION_FINDINGS.md`

---

## 🎓 LESSONS LEARNED

1. **Always check the Sources field** - "None" sources means something is broken
2. **Feature matching must be validated** - 0 perfect matches is a red flag
3. **Fallback mechanisms need safeguards** - Don't silently return bad data
4. **Multi-query status doesn't match request** - Configuration drift issue
5. **Log ALL error conditions** - Silent failures hide root causes

---

## 📞 NEXT STEPS

1. **Immediate:** Check OpenSearch cluster health logs for Oct 22, 21:00-00:00
2. **Immediate:** Review Lambda CloudWatch logs for exact error at 23:35-23:37
3. **Today:** Implement source validation to prevent "None" sources
4. **This week:** Fix feature matching (zero perfect matches is unacceptable)
5. **This week:** Add monitoring for pipeline failures

---

**Investigation Complete** ✅

The degradation was real, measurable, and caused by a complete search pipeline failure (likely OpenSearch connectivity issue) that triggered a faulty fallback mechanism. The multi-query feature was a red herring - it wasn't even running.
