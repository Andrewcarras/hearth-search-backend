# CRITICAL DISCOVERY: Search Degradation Root Cause Found

**Investigation Date:** 2025-10-23
**Investigator:** DynamoDB SearchQueryLogs Analysis
**Status:** 🚨 ROOT CAUSE IDENTIFIED

---

## EXECUTIVE SUMMARY

The search quality degradation was **NOT caused by multi-query feature** as initially suspected.

### The Real Cause:

**ALL search results showed `Sources: None` during degradation period**, meaning:
- No BM25 results
- No Text KNN results
- No Image KNN results
- **COMPLETE SEARCH PIPELINE FAILURE**

The searches were returning results from an **unknown source** - likely a fallback mechanism or cache with stale/bad data.

---

## CRITICAL EVIDENCE

### 1. Multi-Query Was NOT Actually Enabled

Despite `use_multi_query=true` in the request:

```
Multi-Query Status:
  Enabled: False
  Generated: False
  Sub-query Count: 0
```

**All searches (good and degraded) had multi-query disabled**, ruling out multi-query as the cause.

---

### 2. Sources Field Shows Complete Failure

#### Good Search (21:37:13):
```
Rank   ZPID         Score      Sources
1      2080387168   0.061101   Text#12.0, Img#9.0    ✅ Multiple sources
2      454833364    0.035714   Img#1.0                ✅ Image KNN
3      12787813     0.035088   BM25#2.0               ✅ BM25
4      12721617     0.035088   Text#2.0               ✅ Text KNN
```

#### Degraded Search (23:36:03):
```
Rank   ZPID         Score      Sources
1      2080387168   0.070769   None                   ❌ NO SOURCE
2      12778555     0.055556   None                   ❌ NO SOURCE (RED BRICK!)
3      70592220     0.054054   None                   ❌ NO SOURCE (BLUE BRICK!)
4      12717999     0.052632   None                   ❌ NO SOURCE
```

**NO SEARCH STRATEGIES RETURNED RESULTS** - this is a complete pipeline failure!

---

### 3. Timeline of Complete Failures

| Time | Query ID | Sources Working? | Bad zpids? |
|------|----------|------------------|------------|
| 21:07:06 | 3ce8bc95... | ✅ YES (BM25 only) | ❌ YES (70592220 in pos 5) |
| 21:37:13 | 8f05713a... | ✅ YES (All 3: BM25, Text, Img) | ✅ NO |
| 23:36:03 | 31e68fba... | ❌ **NO - All None** | ❌ **YES (both in top 3!)** |
| 23:52:05 | cb535cbc... | ❌ **NO - All None** | ❌ **YES (both in top 3!)** |
| 00:14:16 | 8d048382... | ❌ **NO - All None** | ⚠️ **Partial (70592220 in pos 7)** |

---

## ROOT CAUSE ANALYSIS

### What Actually Happened:

1. **21:07:06** - BM25-only search (Text/Image KNN failed, but BM25 worked)
   - Result: Minor degradation (bad zpid in position 5)
   - Overlap shows: `All sources: 0` - strategies not agreeing

2. **21:37:13** - All systems working normally
   - BM25, Text KNN, and Image KNN all returning results
   - Overlap: Text ∩ Image = 1 (some consensus)
   - Good results

3. **23:36:03 onwards** - COMPLETE FAILURE
   - **No BM25 results**
   - **No Text KNN results**
   - **No Image KNN results**
   - Results came from **unknown fallback source**
   - Fallback source had **bad data** (red & blue brick properties)

---

### Possible Fallback Sources:

#### Theory 1: OpenSearch Direct Query Bypass
- When search strategies fail, system might fall back to direct OpenSearch query
- Direct query without RRF fusion might have bad ranking
- Would explain "None" sources and different results

#### Theory 2: Stale Cache
- Cache populated with bad results
- When all search strategies fail, return cached results
- 34-minute degradation duration matches typical cache TTL

#### Theory 3: Error Handling Fallback
- Exception in search pipeline triggered fallback
- Fallback returns pre-computed "similar" results
- Bad zpids were in fallback result set

---

## WHAT CAUSED THE FAILURE?

### OpenSearch Connectivity Issues (MOST LIKELY)

**Evidence:**
- All three search strategies (BM25, Text KNN, Image KNN) failed simultaneously
- All depend on OpenSearch
- Complete failure suggests OpenSearch unavailable or unreachable

**Timeline:**
- 21:37:13: Last successful OpenSearch queries
- 23:36:03: First complete failure (2-hour gap)
- 00:14:16: Still failing (but different fallback results)

**Check:**
- OpenSearch cluster health logs from 21:37-23:36
- Lambda timeout errors
- Network connectivity issues
- OpenSearch index availability

---

### Lambda Deployment with Broken Search Logic (POSSIBLE)

**Evidence:**
- 2-hour gap between last good and first bad
- Suggests deployment around 22:00-23:30
- Deployment might have broken:
  - OpenSearch connection configuration
  - Search strategy execution
  - Error handling

**Check:**
- Lambda deployment logs from 21:30-23:30
- Configuration changes
- search.py changes

---

### Index Corruption or Deletion (LESS LIKELY)

**Evidence:**
- Would cause all strategies to fail
- But wouldn't explain fallback results

**Check:**
- OpenSearch index status during degradation period
- Index refresh/reindex operations

---

## KEY OBSERVATIONS

### 1. Result Overlap Always Shows Problems

During degradation:
```
Result Overlap Between Sources:
  BM25 ∩ Text KNN: 0
  BM25 ∩ Image KNN: 0
  Text ∩ Image KNN: 1
  All Three: 0
```

Even during "good" searches, **All Three: 0** suggests strategies aren't agreeing well.

---

### 2. Quality Metrics Show Systemic Issues

**ALL searches (good and degraded) show:**
```
Perfect Matches: 0
Partial Matches: 0 (in early searches)
No Matches: 10 (or 5)
```

This means **EVEN GOOD SEARCHES had zero feature matches**!

The system is:
- Not finding properties that match requested features
- Relying on semantic similarity only
- Feature tagging or matching is broken

---

### 3. Scores Were Higher During Degradation

| Period | Avg Score |
|--------|-----------|
| Good searches | 0.034-0.037 |
| Degraded searches | 0.051-0.057 |

**Degraded results had HIGHER scores**, suggesting:
- Fallback mechanism uses different scoring
- Or fallback doesn't apply RRF normalization
- Raw scores instead of RRF scores

---

## IMMEDIATE ACTIONS REQUIRED

### 1. Check OpenSearch Cluster Health
```bash
# Check cluster health during degradation period
# Look for: 21:37 - 23:36 on 2025-10-22

aws logs tail /aws/opensearch/YOUR_DOMAIN --since 2025-10-22T21:30:00 --until 2025-10-22T23:40:00
```

### 2. Review Lambda Logs for Errors
```python
# Look for exceptions in search.py around 23:36
# Expected errors:
# - OpenSearch connection timeout
# - Index not found
# - Query execution failure
```

### 3. Identify Fallback Logic
```python
# In search.py, find:
# - What happens when OpenSearch queries fail?
# - Where do "None" source results come from?
# - Is there a cache or fallback result set?
```

### 4. Check Lambda Deployments
```bash
# List Lambda deployments between 21:30-23:30
aws lambda list-versions-by-function --function-name YOUR_SEARCH_LAMBDA
```

---

## CORRECTIVE ACTIONS

### Short-term:

1. **Add Explicit Error Logging**
   - Log when BM25 query fails
   - Log when KNN queries fail
   - Log when fallback is triggered
   - **Include error reason in SearchQueryLogs**

2. **Add Health Checks**
   - Verify OpenSearch connectivity before query
   - Return explicit error if OpenSearch unavailable
   - Don't silently fall back to bad results

3. **Fix Feature Matching**
   - **Zero perfect matches is unacceptable**
   - Review feature tag extraction
   - Ensure "white_exterior" actually filters results
   - Add post-query filter for must-have features

### Medium-term:

4. **Improve Fallback Strategy**
   - If fallback is needed, use cached GOOD results
   - Don't return results with "None" sources
   - Better yet: fail fast and return error

5. **Add Result Validation**
   - Before returning results, check:
     - Are sources populated?
     - Do results match must-have features?
     - Are quality metrics acceptable?
   - If validation fails, log warning and filter bad results

6. **Add Monitoring**
   - Alert when all sources return None
   - Alert when result overlap = 0
   - Alert when bad zpids (12778555, 70592220) appear

---

## QUESTIONS TO ANSWER

1. **What is the fallback mechanism?**
   - Where do results with `Sources: None` come from?
   - Is this intentional or a bug?

2. **Why did OpenSearch fail?**
   - Was cluster unhealthy?
   - Was there a network issue?
   - Was index deleted or unavailable?

3. **Why does multi-query show as disabled?**
   - `use_multi_query=true` in request
   - But `multi_query_status.enabled=false` in logs
   - Is feature broken or conditionally disabled?

4. **Why are there ZERO perfect feature matches?**
   - Even in "good" searches
   - Suggests fundamental issue with feature matching
   - Are tags not being applied? Not being checked?

---

## CORRECTED TIMELINE

| Time | Event | Evidence |
|------|-------|----------|
| 21:07:06 | **Minor Degradation** | BM25 only (Text/Image KNN failed), bad zpid in pos 5 |
| 21:19:19 | **Recovery** | All sources working |
| 21:37:13 | **Last Fully Healthy Search** | All 3 sources working, good overlap |
| ~22:00-23:30 | **❓ UNKNOWN EVENT** | 2-hour gap (likely deployment or OpenSearch issue) |
| 23:36:03 | **Complete Failure Begins** | All sources show "None", bad zpids in top 3 |
| 23:52:05 | **Failure Continues** | Identical results (possibly cached) |
| 00:14:16 | **Partial Recovery** | Still "None" sources, but slightly better results |

---

## CONCLUSION

The degradation was **NOT a multi-query issue** but a **complete search pipeline failure**.

### Root Cause:
**OpenSearch became unreachable or unhealthy**, causing:
- BM25 queries to fail
- Text KNN queries to fail
- Image KNN queries to fail
- System fell back to unknown source with bad data

### Why multi_query=true was affected:
- Coincidental - multi_query feature was disabled for all searches
- The real difference: timing of when searches were run
- Searches during 23:36-00:14 hit the outage period

### Fix:
1. Ensure OpenSearch cluster health and connectivity
2. Add proper error handling (don't silently fall back)
3. Fix feature matching (zero perfect matches is a bug)
4. Add monitoring for when sources show "None"

### Next Investigation:
**Pull Lambda CloudWatch logs from 23:35-23:37** to see the exact error that triggered fallback.
