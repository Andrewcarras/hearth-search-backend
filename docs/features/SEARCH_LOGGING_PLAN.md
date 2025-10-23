# Comprehensive Search Logging Plan

## Executive Summary

Goal: Log every search request with complete context, results, and performance metrics to enable systematic evaluation, testing, and improvement of search quality.

---

## 1. Logging Architecture

### Storage Strategy
**Primary:** New DynamoDB table `SearchQueryLogs`
- **Why DynamoDB:** Already in use, serverless, pay-per-request, fast writes, TTL support
- **Retention:** 90 days with automatic TTL (configurable)
- **Cost:** ~$0.25 per million writes (1.25KB items)

**Secondary:** CloudWatch Logs (structured JSON)
- **Why:** Already available, good for debugging, searchable
- **Retention:** 30 days
- **Cost:** Included in Lambda execution

### Table Schema: `SearchQueryLogs`

```
Partition Key: query_id (String) - UUID for each search
Sort Key: timestamp (Number) - Unix timestamp in milliseconds

Global Secondary Index (GSI):
- GSI1: user_session_id + timestamp (for session analysis)
- GSI2: query_hash + timestamp (for duplicate query analysis)
```

---

## 2. Data Model - What to Log

### A. Request Context (User Input)
```json
{
  "query_id": "uuid-v4",
  "timestamp": 1729650000000,
  "user_session_id": "session-uuid",  // From cookie/header
  "user_ip": "1.2.3.4",  // Hashed for privacy
  "user_agent": "Mozilla/5.0...",

  // Query details
  "query_text": "White houses with granite countertops and wood floors",
  "query_hash": "md5-hash",  // For grouping duplicate queries
  "query_length": 52,

  // Search parameters
  "size": 10,
  "index": "listings-v2",
  "boost_mode": "standard",
  "search_mode": "adaptive",
  "strategy": "hybrid",
  "use_multi_query": true,
  "custom_filters": {...}
}
```

### B. Query Analysis (Extracted Features)
```json
{
  "extracted_constraints": {
    "must_have": ["white_exterior", "granite_countertops", "hardwood_floors"],
    "nice_to_have": [],
    "hard_filters": {},
    "architecture_style": null,
    "query_type": "material"
  },

  "multi_query_status": {
    "enabled": true,
    "llm_success": false,
    "llm_error": "Expecting value: line 1 column 1 (char 0)",
    "fallback_used": true,
    "sub_queries": [
      {
        "query": "white exterior",
        "feature": "white_exterior",
        "weight": 1.0,
        "embedding_generated": true
      },
      {
        "query": "granite countertops",
        "feature": "granite_countertops",
        "weight": 1.0,
        "embedding_generated": true
      },
      {
        "query": "hardwood floors",
        "feature": "hardwood_floors",
        "weight": 1.0,
        "embedding_generated": true
      }
    ]
  },

  "adaptive_scoring": {
    "k_values": {"bm25": 55, "knn_text": 55, "knn_image": 55},
    "adaptive_k": 3,
    "query_type": "material"
  }
}
```

### C. Search Execution (Performance Metrics)
```json
{
  "timing": {
    "total_ms": 5618,
    "llm_query_split_ms": 1200,  // Time spent on LLM call
    "constraint_extraction_ms": 50,
    "bm25_ms": 172,
    "knn_text_ms": 208,
    "knn_image_ms": 337,
    "rrf_fusion_ms": 5,
    "tag_boosting_ms": 2,
    "result_formatting_ms": 10,
    "bedrock_embedding_calls": 3,
    "bedrock_embedding_ms": 450,
    "opensearch_calls": 3
  },

  "result_counts": {
    "bm25_hits": 30,
    "knn_text_hits": 30,
    "knn_image_hits": 30,
    "rrf_fused": 30,
    "final_returned": 10
  },

  "result_overlap": {
    "bm25_text_overlap": 0,  // How many results appeared in both
    "bm25_image_overlap": 0,
    "text_image_overlap": 0,
    "all_three_overlap": 0
  }
}
```

### D. Search Results (Quality Metrics)
```json
{
  "results": [
    {
      "rank": 1,
      "zpid": "12772463",
      "score": 0.01786,

      // Feature matching
      "feature_matches": {
        "white_exterior": true,
        "granite_countertops": true,
        "hardwood_floors": true,
        "match_ratio": 1.0  // 3/3
      },

      // Scoring breakdown
      "scoring": {
        "bm25_rank": 1,
        "bm25_score": 12.026,
        "bm25_contribution": 0.01786,
        "knn_text_rank": null,
        "knn_text_score": null,
        "knn_text_contribution": 0,
        "knn_image_rank": null,
        "knn_image_score": null,
        "knn_image_contribution": 0,
        "rrf_total": 0.01786,
        "tag_boost": 1.0,
        "first_image_boost": 1.0
      },

      // Property details (for evaluation)
      "property": {
        "price": 450000,
        "bedrooms": 3,
        "bathrooms": 2,
        "city": "Atlanta",
        "state": "GA",
        "has_description": true,
        "description_length": 250,
        "image_count": 35,
        "feature_tag_count": 0,  // CRITICAL: Shows feature_tags empty
        "image_tag_count": 150
      }
    }
    // ... up to 10 results
  ],

  "result_quality_metrics": {
    "avg_score": 0.0178,
    "score_variance": 0.0001,
    "avg_feature_match_ratio": 0.8,  // 8/10 results have all features
    "perfect_matches": 8,  // Results with match_ratio = 1.0
    "partial_matches": 2,  // Results with 0 < match_ratio < 1.0
    "no_matches": 0,  // Results with match_ratio = 0

    "source_distribution": {
      "bm25_only": 3,  // Only ranked in BM25
      "knn_text_only": 3,
      "knn_image_only": 3,
      "multiple_sources": 1  // Appeared in 2+ result sets
    }
  }
}
```

### E. Error Tracking
```json
{
  "errors": [
    {
      "component": "llm_query_splitter",
      "error_type": "JSONDecodeError",
      "error_message": "Expecting value: line 1 column 1 (char 0)",
      "fallback_used": true,
      "impact": "medium"  // Used fallback, still got results
    }
  ],

  "warnings": [
    {
      "component": "tag_boosting",
      "message": "feature_tags empty for 10/10 results",
      "impact": "high"  // Tag boosting not working
    }
  ]
}
```

---

## 3. Implementation Plan

### Phase 1: Core Logging Infrastructure (Day 1)
1. **Create DynamoDB table** `SearchQueryLogs`
   - Partition key: `query_id`
   - Sort key: `timestamp`
   - TTL attribute: `expiration_time` (90 days)
   - GSIs for session and query hash analysis

2. **Add logging utility function** in `search.py`
   ```python
   def log_search_query(
       query_id: str,
       request_data: dict,
       extracted_constraints: dict,
       timing_data: dict,
       results: list,
       errors: list,
       warnings: list
   ) -> None:
       """Log complete search query to DynamoDB and CloudWatch"""
   ```

3. **Instrument search handler**
   - Generate `query_id` at start
   - Collect timing data throughout execution
   - Call `log_search_query()` before returning response

### Phase 2: Quality Analysis Tools (Day 2-3)
1. **Create analysis script** `analyze_search_logs.py`
   - Query DynamoDB for last N searches
   - Generate quality reports
   - Identify patterns in poor results

2. **Key metrics to track:**
   - Average feature match ratio by query type
   - LLM failure rate
   - Multi-query vs single-query performance
   - Source overlap (BM25/kNN overlap)
   - Tag boosting effectiveness
   - Latency percentiles (p50, p95, p99)

3. **Automated alerts:**
   - Feature match ratio < 0.5 for queries with 3+ features
   - LLM failure rate > 50%
   - Latency > 10 seconds
   - Zero overlap between BM25 and kNN

### Phase 3: Search Quality Dashboard (Day 4-5)
1. **Create web dashboard** `search_dashboard.html`
   - Recent searches table
   - Quality metrics over time
   - Feature matching heatmap
   - Latency distribution
   - Error rate trends

2. **Query comparison tool**
   - Compare results for same query over time
   - A/B test different search modes
   - Side-by-side result comparison

---

## 4. Privacy & Compliance

### Data Retention
- **Personal data:** Hash IP addresses, don't store PII
- **Query text:** Store as-is (real estate queries not sensitive)
- **TTL:** Auto-delete after 90 days
- **Opt-out:** Respect Do Not Track headers

### Data Access
- **Who:** Development team only
- **Purpose:** Search quality improvement
- **Audit:** Log all access to search logs table

---

## 5. Cost Estimation

### DynamoDB Costs
- **Writes:** ~$0.25 per million writes (1.25KB items)
- **Reads:** ~$0.25 per million reads (query analysis)
- **Storage:** ~$0.25/GB/month (90 days retention)
- **Estimated:** ~$5/month for 10,000 searches/day

### CloudWatch Logs
- **Ingestion:** $0.50/GB
- **Storage:** $0.03/GB/month
- **Estimated:** ~$2/month for 10,000 searches/day

**Total:** ~$7/month

---

## 6. Key Benefits

### Immediate Value
1. **Debugging:** Full context for every failed search
2. **Root cause analysis:** See exactly why results are poor
3. **Performance monitoring:** Track latency regressions
4. **Feature validation:** Measure impact of code changes

### Long-term Value
1. **ML training data:** Build relevance models from user behavior
2. **A/B testing:** Compare search algorithms scientifically
3. **Business intelligence:** Understand what users search for
4. **Quality regression detection:** Automated tests against historical baselines

---

## 7. Example Use Cases

### Use Case 1: Debug Poor Results
**Problem:** "White houses with granite countertops" returns bad results
**Solution:**
```bash
python analyze_search_logs.py --query-text "White houses" --last-24h
```
**Findings:**
- LLM failing 100% of time → "Expecting value: line 1 column 1"
- feature_tags empty for all results → Tag boosting not working
- BM25/kNN zero overlap → Different result sets

### Use Case 2: A/B Test Multi-Query Mode
**Question:** Does multi-query improve results?
**Method:**
```python
# Compare searches with use_multi_query=true vs false
results = compare_search_modes(
    query_text="White houses with granite countertops",
    mode_a="multi_query",
    mode_b="single_query",
    sample_size=100
)
# Show: avg_feature_match_ratio, avg_score, latency
```

### Use Case 3: Track Quality Over Time
**Goal:** Ensure search quality doesn't regress
**Method:**
```python
# Daily quality report
metrics = get_daily_quality_metrics(days=30)
# Alert if: feature_match_ratio drops >10% or latency increases >20%
```

---

## 8. Implementation Priority

### Must Have (Week 1)
- [x] DynamoDB table creation
- [x] Core logging function
- [x] Instrument search handler
- [x] Basic CloudWatch structured logs

### Should Have (Week 2)
- [ ] Analysis script with key metrics
- [ ] Query comparison tool
- [ ] Automated quality alerts

### Nice to Have (Week 3+)
- [ ] Web dashboard
- [ ] ML training data export
- [ ] Advanced analytics (user sessions, query refinement patterns)

---

## 9. Sample Queries for Analysis

```python
# Find all searches with low feature match ratio
aws dynamodb query \
  --table-name SearchQueryLogs \
  --filter-expression "result_quality_metrics.avg_feature_match_ratio < :threshold" \
  --expression-attribute-values '{":threshold": {"N": "0.5"}}'

# Find searches with high latency
aws dynamodb scan \
  --table-name SearchQueryLogs \
  --filter-expression "timing.total_ms > :max_latency" \
  --expression-attribute-values '{":max_latency": {"N": "5000"}}'

# Find most common queries with poor results
aws dynamodb query \
  --table-name SearchQueryLogs \
  --index-name query_hash-timestamp-index \
  --key-condition-expression "query_hash = :hash" \
  --filter-expression "result_quality_metrics.perfect_matches < :min"
```

---

## 10. Rollout Strategy

### Phase 1: Silent Logging (Day 1-2)
- Deploy logging code
- Log to CloudWatch only (no DynamoDB)
- Validate data structure
- No impact on latency

### Phase 2: DynamoDB Logging (Day 3-4)
- Enable DynamoDB writes
- Monitor latency impact (<5ms acceptable)
- Log sample 10% of traffic initially
- Gradually increase to 100%

### Phase 3: Analysis Tools (Day 5+)
- Deploy analysis scripts
- Create quality reports
- Share findings with team
- Iterate on metrics

---

## 11. Success Metrics

Within 30 days of deployment:
1. **Coverage:** Log 100% of searches with <5ms overhead
2. **Insights:** Identify top 3 root causes of poor results
3. **Improvements:** Deploy 2+ fixes based on log analysis
4. **Quality:** Increase avg_feature_match_ratio by 20%
5. **Reliability:** LLM failure rate < 10% (via prompt fix)

---

## Next Steps

1. **Review this plan** - Approve/modify approach
2. **Create DynamoDB table** - 5 minutes
3. **Implement logging function** - 2 hours
4. **Instrument search handler** - 1 hour
5. **Deploy and validate** - 1 hour
6. **Analyze first 1000 searches** - Next day

**Total Time to First Insights:** ~1 day
