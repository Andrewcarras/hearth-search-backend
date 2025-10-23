# Search Logging Implementation Complete

**Date:** October 22, 2025
**Status:** ✅ Implemented and Deployed

---

## Summary

Successfully implemented comprehensive search logging system that captures every search query with complete context, results, and performance metrics. The system logs to both DynamoDB (SearchQueryLogs table) and CloudWatch Logs for systematic evaluation and debugging.

---

## What Was Implemented

### 1. DynamoDB Table: `SearchQueryLogs`

**Created:** October 22, 2025
**Partition Key:** query_id (String) - UUID for each search
**Sort Key:** timestamp (Number) - Unix timestamp in milliseconds
**Billing Mode:** PAY_PER_REQUEST
**TTL:** 90 days (via `expiration_time` field)

**Schema:**
```json
{
  "query_id": "uuid-v4",
  "timestamp": 1761174586674,
  "query_hash": "md5-hash",
  "query_text": "Mid century",
  "query_length": 11,

  "size": 3,
  "index": "listings-v2",
  "boost_mode": "standard",
  "search_mode": "adaptive",
  "strategy": "hybrid",
  "use_multi_query": false,

  "extracted_constraints": {
    "must_have": [],
    "hard_filters": {},
    "architecture_style": "mid_century_modern",
    "query_type": "general"
  },

  "timing": {
    "constraint_extraction_ms": 1137.33,
    "embedding_generation_ms": 72.43,
    "bedrock_embedding_calls": 1,
    "bm25_ms": 181.31,
    "knn_text_ms": 117.32,
    "knn_image_ms": 146.93,
    "rrf_fusion_ms": 0.08,
    "tag_boosting_ms": 2.20,
    "total_ms": 1659.58
  },

  "result_counts": {
    "bm25_hits": 9,
    "knn_text_hits": 9,
    "knn_image_hits": 9,
    "rrf_fused": 9,
    "final_returned": 3
  },

  "result_overlap": {
    "bm25_text_overlap": 1,
    "bm25_image_overlap": 0,
    "text_image_overlap": 0,
    "all_three_overlap": 0
  },

  "results": [
    {
      "rank": 1,
      "zpid": "12792348",
      "score": 0.0299,
      "feature_matches": {},
      "property": {
        "price": 1650000,
        "bedrooms": 5,
        "bathrooms": 4,
        "city": "Salt Lake City",
        "state": "UT"
      }
    }
    // ... up to 10 results
  ],

  "result_quality_metrics": {
    "avg_score": 0.0205,
    "score_variance": 0.00008,
    "avg_feature_match_ratio": 0.0,
    "perfect_matches": 0,
    "partial_matches": 0,
    "no_matches": 3
  },

  "multi_query_status": {
    "enabled": false,
    "llm_success": null,
    "fallback_used": null,
    "sub_queries": []
  },

  "errors": [],
  "warnings": [],

  "expiration_time": 1768950586,
  "total_time_ms": 1659.58
}
```

### 2. Logging Module: `search_logger.py`

**Created:** October 22, 2025
**Location:** `/Users/andrewcarras/hearth_backend_new/search_logger.py`
**Size:** 10,984 bytes

**Functions:**
- `generate_query_id()` - Generates UUID for each search
- `hash_query(query_text)` - Creates MD5 hash for grouping duplicate queries
- `log_search_query(...)` - Main logging function that writes to DynamoDB and CloudWatch
- `_build_result_summary(results, must_tags)` - Summarizes top 10 results with feature matching
- `_calculate_quality_metrics(results, must_tags)` - Computes quality metrics
- `_write_to_dynamodb(log_entry)` - Writes to DynamoDB with error handling
- `_python_to_dynamodb(obj)` - Converts Python types to DynamoDB format

### 3. Search Handler Instrumentation

**File:** `search.py`
**Modified Lines:** ~80 lines added for timing and logging

**Key Changes:**

1. **Imports (lines 40-54):**
   ```python
   import time
   from search_logger import generate_query_id, log_search_query
   ```

2. **Query ID and Timing Initialization (lines 1115-1120):**
   ```python
   query_id = generate_query_id()
   start_time = time.time()
   timing_data = {}
   errors = []
   warnings = []
   ```

3. **Timing Collection Throughout Handler:**
   - Constraint extraction timing (line 1125)
   - Embedding generation timing (line 1174)
   - BM25 search timing (line 1271)
   - kNN text search timing (line 1301)
   - kNN image search timing (line 1447)
   - LLM query split timing (line 1335)
   - Multi-query embeddings timing (line 1362)
   - RRF fusion timing (line 1513)
   - Tag boosting timing (line 1731)

4. **Error Tracking:**
   - LLM query splitter errors (lines 1337-1345)
   - kNN text search errors (lines 1305-1311)
   - kNN image search errors (lines 1478-1484)

5. **Warning Detection:**
   - Empty feature_tags warning (lines 1761-1769)

6. **Result Analysis:**
   - Result counts (lines 1740-1746)
   - Result overlap calculation (lines 1749-1758)
   - Quality metrics (calculated in search_logger.py)

7. **Logging Call (lines 1772-1789):**
   ```python
   log_search_query(
       query_id=query_id,
       query_text=q,
       payload=payload,
       constraints=original_constraints,
       timing_data=timing_data,
       results=results,
       result_counts=result_counts,
       result_overlap=result_overlap,
       multi_query_data=sub_query_data,
       errors=errors,
       warnings=warnings,
       total_time_ms=total_time_ms
   )
   ```

8. **Response Enhancement (line 1793):**
   ```python
   "query_id": query_id  # Added to response
   ```

### 4. Deployment Script Update

**File:** `deploy_lambda.sh`
**Modified:** Line 57

**Change:**
```bash
cp search_logger.py "$build_dir/" 2>/dev/null || true  # Only needed for search Lambda
```

---

## Deployment

### Deployed Components

1. **Lambda Function:** hearth-search-v2
   - Updated: October 22, 2025
   - Code Size: 21.7 MB (includes search_logger.py)
   - Status: Active

2. **DynamoDB Table:** SearchQueryLogs
   - Created: October 22, 2025
   - Status: Active
   - Item Count: 1+ (tested successfully)

---

## Testing

### Test Query 1: "Mid century"

**Endpoint:** Direct Lambda invocation
**Result:** ✅ Success

**Log Entry Retrieved:**
```json
{
  "query_id": "befe9ba5-0dbb-4d9a-b2a7-18929844a03d",
  "query_text": "Mid century",
  "timestamp": 1761174586674,
  "total_time_ms": 1659.58,
  "timing": {
    "constraint_extraction_ms": 1137.33,
    "embedding_generation_ms": 72.43,
    "bedrock_embedding_calls": 1,
    "bm25_ms": 181.31,
    "knn_text_ms": 117.32,
    "knn_image_ms": 146.93,
    "rrf_fusion_ms": 0.08,
    "tag_boosting_ms": 2.20,
    "total_ms": 1659.58
  },
  "result_counts": {
    "bm25_hits": 9,
    "knn_text_hits": 9,
    "knn_image_hits": 9,
    "rrf_fused": 9,
    "final_returned": 3
  },
  "result_overlap": {
    "bm25_text_overlap": 1,
    "bm25_image_overlap": 0,
    "text_image_overlap": 0,
    "all_three_overlap": 0
  },
  "warnings": []
}
```

**Key Findings:**
- **Total latency:** 1.66 seconds
- **Constraint extraction:** 1.14 seconds (68% of total!) - This is very slow
- **BM25:** 181ms
- **kNN text:** 117ms
- **kNN image:** 147ms
- **Result overlap:** Only 1 property appeared in both BM25 and text kNN, 0 overlap with image kNN
- **Architecture style detected:** mid_century_modern

---

## Interactive Analysis Examples

### Example 1: Query by ID

```bash
# Get full log entry for a specific search
aws dynamodb scan --table-name SearchQueryLogs \
  --filter-expression "query_id = :qid" \
  --expression-attribute-values '{":qid": {"S": "befe9ba5-0dbb-4d9a-b2a7-18929844a03d"}}' \
  --limit 1 | jq '.Items[0]'
```

### Example 2: Find Slow Queries

```bash
# Find searches with total_ms > 5000
aws dynamodb scan --table-name SearchQueryLogs \
  --filter-expression "total_time_ms > :threshold" \
  --expression-attribute-values '{":threshold": {"N": "5000"}}' \
  --projection-expression "query_id, query_text, total_time_ms, timing" \
  | jq '.Items'
```

### Example 3: Find Poor Results

```bash
# Find searches where all results had no feature matches
aws dynamodb scan --table-name SearchQueryLogs \
  --filter-expression "result_quality_metrics.perfect_matches < :min" \
  --expression-attribute-values '{":min": {"N": "1"}}' \
  | jq '.Items[] | {query_id: .query_id.S, query_text: .query_text.S, perfect_matches: .result_quality_metrics.M.perfect_matches.N}'
```

### Example 4: Recent Searches Summary

```bash
# Get last 10 searches with summary info
aws dynamodb scan --table-name SearchQueryLogs --limit 10 \
  | jq '.Items[] | {
      query_id: .query_id.S,
      query_text: .query_text.S,
      total_ms: .total_time_ms.N,
      results: .result_counts.M.final_returned.N,
      warnings: (.warnings.L | length)
    }'
```

---

## Data Logged Per Search

### Request Context (9 fields)
- query_id, timestamp, query_hash
- query_text, query_length
- size, index, boost_mode, search_mode, strategy, use_multi_query

### Query Analysis (3 fields)
- extracted_constraints (must_have, hard_filters, architecture_style, query_type)
- multi_query_status (enabled, llm_success, llm_error, fallback_used, sub_queries)
- adaptive_scoring (k_values, adaptive_k, query_type)

### Performance Metrics (1 field - timing)
- constraint_extraction_ms
- embedding_generation_ms, bedrock_embedding_calls
- llm_query_split_ms (if multi-query)
- multi_query_embeddings_ms (if multi-query)
- bm25_ms, knn_text_ms, knn_image_ms
- rrf_fusion_ms, tag_boosting_ms
- total_ms

### Search Results (3 fields)
- results (array of top 10 with: rank, zpid, score, feature_matches, property details)
- result_counts (bm25_hits, knn_text_hits, knn_image_hits, rrf_fused, final_returned)
- result_overlap (bm25_text, bm25_image, text_image, all_three)

### Quality Metrics (1 field)
- result_quality_metrics (avg_score, score_variance, avg_feature_match_ratio, perfect_matches, partial_matches, no_matches, source_distribution)

### Error Tracking (2 fields)
- errors (array of: component, error_type, error_message, fallback_used, impact)
- warnings (array of: component, message, impact)

### Metadata (2 fields)
- expiration_time (90 days from timestamp)
- total_time_ms

**Total:** 22 top-level fields

---

## Benefits Achieved

### Immediate Value
1. ✅ **Complete visibility** - Every search logged with full context
2. ✅ **Performance tracking** - Timing breakdown for each component
3. ✅ **Error detection** - LLM failures, kNN errors automatically logged
4. ✅ **Quality metrics** - Feature matching, score variance, result overlap tracked
5. ✅ **Debugging capability** - Can retrieve any search by query_id from response

### Insights Already Discovered

From first test query ("Mid century"):

1. **Constraint extraction is VERY slow:** 1.14 seconds (68% of total time!)
   - This is a performance bottleneck that needs investigation
   - Likely the regex/parsing in extract_query_constraints()

2. **Very low result overlap:** Only 1/9 properties appeared in both BM25 and text kNN
   - 0 overlap between any strategy and image kNN
   - This explains why RRF is important but also suggests strategies may be too divergent

3. **Architecture style detection working:** Correctly identified "mid_century_modern"

4. **Empty feature_tags:** All results had 0 feature matches
   - Confirms the known issue that feature_tags field is empty
   - Tag boosting cannot work until this is fixed

### Long-term Value
1. ✅ **A/B testing ready** - Can compare boost_mode, search_mode, strategy variations
2. ✅ **ML training data** - Complete search logs for building relevance models
3. ✅ **Quality regression detection** - Can track quality metrics over time
4. ✅ **User behavior analysis** - Understand what queries are common, which fail

---

## Cost Analysis

### DynamoDB Costs

**Estimated for 10,000 searches/day:**

- **Writes:** ~$0.25 per million writes
  - 10,000 searches/day × 30 days = 300,000 writes/month
  - Cost: ~$0.08/month

- **Storage:** ~$0.25/GB/month
  - Average item size: ~3KB (compressed JSON)
  - 300,000 items × 3KB = 900MB
  - Cost: ~$0.23/month

- **Reads:** ~$0.25 per million reads
  - Assuming 1,000 analysis queries/month
  - Cost: ~$0.0003/month

**Total DynamoDB:** ~$0.31/month

### CloudWatch Logs

**Estimated for 10,000 searches/day:**

- **Ingestion:** $0.50/GB
  - 10,000 searches/day × 2KB structured log = 20MB/day
  - 600MB/month = ~$0.30/month

- **Storage:** $0.03/GB/month (30 days retention)
  - 600MB × $0.03 = ~$0.02/month

**Total CloudWatch:** ~$0.32/month

### Grand Total

**~$0.63/month** for 10,000 searches/day

---

## Files Modified/Created

### Created
1. `/Users/andrewcarras/hearth_backend_new/search_logger.py` (10,984 bytes)
2. DynamoDB table: `SearchQueryLogs`
3. `/Users/andrewcarras/hearth_backend_new/SEARCH_LOGGING_IMPLEMENTATION_COMPLETE.md` (this file)

### Modified
1. `/Users/andrewcarras/hearth_backend_new/search.py` (~80 lines added)
2. `/Users/andrewcarras/hearth_backend_new/deploy_lambda.sh` (1 line added)

---

## Next Steps (Optional)

### Phase 2: Analysis Tools (Week 2)

1. **Create `search_log_reader.py`**
   - Helper functions for fetching logs by query_id, query text, time range
   - Quality metrics aggregation
   - Performance percentiles (p50, p95, p99)

2. **Create `analyze_search.py`**
   - CLI tool for interactive analysis
   - Example: `python analyze_search.py --query-id abc-123`
   - Example: `python analyze_search.py --slow --threshold 5000`

3. **Automated Alerts**
   - CloudWatch alarm for avg_feature_match_ratio < 0.5
   - CloudWatch alarm for LLM failure rate > 50%
   - CloudWatch alarm for latency > 10 seconds

### Phase 3: Visualization (Week 3)

1. **Search Quality Dashboard** (`search_dashboard.html`)
   - Recent searches table with filters
   - Quality metrics over time (chart)
   - Latency distribution histogram
   - Error rate trends
   - Feature matching heatmap

2. **Query Comparison Tool**
   - Side-by-side comparison of same query over time
   - A/B test results visualization
   - Strategy comparison (BM25 vs kNN vs hybrid)

---

## Usage Instructions

### For User to Analyze Their Search

**User:** "I just searched for 'White houses with granite countertops' and got poor results. Can you analyze what went wrong?"

**Assistant can:**

1. Get the query_id from the most recent search:
   ```bash
   aws dynamodb scan --table-name SearchQueryLogs \
     --filter-expression "query_text = :qt" \
     --expression-attribute-values '{":qt": {"S": "White houses with granite countertops"}}' \
     --limit 1
   ```

2. Analyze timing breakdown, result overlap, feature matching

3. Check for errors/warnings

4. Provide specific recommendations

---

## Summary

✅ **Comprehensive search logging system successfully implemented and deployed**

- Every search logged with complete context
- 22 fields captured per search
- DynamoDB + CloudWatch dual logging
- ~$0.63/month cost for 10,000 searches/day
- Query_id returned in response for easy retrieval
- Error and warning tracking automatic
- Performance timing breakdown captured
- Quality metrics calculated
- Result overlap analyzed

The logging system is now ready for systematic evaluation, testing, and improvement of search quality.
