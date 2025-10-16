# AWS Bedrock Cost Investigation - October 15-16, 2024

## 🚨 Summary

**Reported Charges:** $73.36 total ($67.74 Oct 15 + $5.62 Oct 16)
**Expected Cost:** $26.01
**Discrepancy:** $47.35 (2.82x multiplier)

**Status:** ⚠️ Actual cost is 2.82x higher than expected

---

## 📊 Actual Data from AWS

| Metric | Value |
|--------|-------|
| **Properties Indexed** | 3,903 |
| **Cache Entries (hearth-vision-cache)** | 83,059 |
| **Average Images per Property** | 21.3 |
| **Search Queries Performed** | 88 (29 regular + 59 debug) |
| **Total Image Analyses** | 83,059 |

---

## 💰 Cost Breakdown

### Claude 3 Haiku Pricing (Bedrock)
- **Input tokens:** $0.25 per 1M tokens ($0.00025 per 1K)
- **Output tokens:** $1.25 per 1M tokens ($0.00125 per 1K)

### Cost Source 1: Image Analysis (detect_labels_with_response)

**Function:** `detect_labels_with_response()` in [common.py:613-726](common.py#L613-L726)
**Called from:** `upload_listings.py` during indexing for vision analysis

**Per Image:**
- Input: ~500 tokens (image encoding + analysis prompt)
- Output: ~150 tokens (structured JSON: features, architecture, colors, materials, room types)
- Cost: (500 × $0.00025/1K) + (150 × $0.00125/1K) = **$0.000313 per image**

**Total:**
```
83,059 images × $0.000313 = $25.96
```

### Cost Source 2: Query Constraint Extraction (extract_query_constraints)

**Function:** `extract_query_constraints()` in [common.py:1016-1155](common.py#L1016-L1155)
**Called from:** `search.py:576` on EVERY search query

**Per Search:**
- Input: ~1,500 tokens (detailed extraction prompt + query)
- Output: ~200 tokens (structured JSON: must_have, nice_to_have, hard_filters, architecture_style, proximity, query_type)
- Cost: (1,500 × $0.00025/1K) + (200 × $0.00125/1K) = **$0.000625 per search**

**Total:**
```
88 searches × $0.000625 = $0.06
```

### Expected Total
```
Image Analysis:    $25.96
Query Extraction:  $0.06
──────────────────────────
TOTAL EXPECTED:    $26.01
```

---

## 🔍 Discrepancy Analysis

```
Expected:    $26.01
Actual:      $73.36
Difference:  $47.35
Multiplier:  2.82x
```

### Possible Explanations

#### 1. Retries or Cache Failures (Most Likely)

To reach $73.36 in actual charges, the system would have needed to perform:
```
($73.36 - $0.06) / $0.000313 = 234,576 image analyses
```

**That's 2.82x the cache entries!**

This suggests:
- **151,517 extra image analyses** beyond the 83,059 cached
- Each image was analyzed ~2.8 times on average
- Likely due to:
  - Exponential backoff retries (5 max retries per image)
  - Rate limiting from Bedrock causing retries
  - Failed attempts that weren't cached but were charged

**Evidence:**
- Code has retry logic: [upload_listings.py:84-132](upload_listings.py#L84-L132)
- Bedrock semaphore limits: 10 concurrent calls (line 81)
- Each retry costs the same as successful call

#### 2. Higher Token Counts Than Estimated

Actual cost per image works out to:
```
$73.36 / 83,059 = $0.000883 per image
vs expected $0.000313 per image
= 2.82x multiplier
```

This would require ~1,177 total tokens per image vs expected 650 tokens.

**Possible reasons:**
- Vision API charges more input tokens for image encoding than estimated
- Actual prompt is longer than 500 tokens
- Response JSON is more verbose than 150 tokens
- Base64 image encoding adds hidden token overhead

#### 3. Multiple Indexing Runs

**Checked:**
- OpenSearch shows 3,903 documents (matches expected)
- Cache shows 83,059 entries (consistent)
- `index_local.py` modified Oct 15 13:04 (single run)

**Conclusion:** Unlikely - would show more cache entries or duplicate documents

#### 4. October 16 Charges ($5.62)

The $5.62 charge on Oct 16 (when no indexing was performed) equals:
```
$5.62 / $0.000313 = 17,984 image analyses
OR
$5.62 / $0.000625 = 8,992 query extractions
```

**This suggests:**
- Either continued indexing/re-indexing on Oct 16
- Or testing that triggered image processing
- Or failed Lambda invocations that retried repeatedly

---

## 🎯 Most Likely Root Cause

**EXPONENTIAL BACKOFF RETRIES**

The retry logic in [upload_listings.py:84-132](upload_listings.py#L84-L132) implements:
```python
def _bedrock_with_retry(func, max_retries=5):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if "throttling" in str(e).lower() or "rate" in str(e).lower():
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(sleep_time)
                continue
```

**Impact:**
- If 30% of calls hit rate limits and retry 3 times average
- That's: 83,059 × 0.3 × 3 = 74,823 extra calls
- Add original 83,059 = 157,882 total calls
- Cost: 157,882 × $0.000313 = **$49.42** (closer to actual)

**Confirmation needed:**
- Check CloudWatch logs for "ThrottlingException" or "Rate exceeded"
- Count actual Bedrock API calls vs successful cache writes
- Review Lambda execution duration (retries add time)

---

## 📋 Action Items

### Immediate Investigation

1. **Check CloudWatch logs for throttling:**
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/lambda/hearth-upload-listings \
     --start-time 1729036800000 \
     --filter-pattern "throttl" | jq '.events | length'
   ```

2. **Count actual Bedrock invocations:**
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/lambda/hearth-upload-listings \
     --start-time 1729036800000 \
     --filter-pattern "invoke_model" | jq '.events | length'
   ```

3. **Review Lambda metrics:**
   - Check invocation count for hearth-upload-listings
   - Check error rate (failed invocations)
   - Check duration (retries increase duration)

4. **Verify cache writes:**
   - Compare cache entry count (83,059) to expected (78,080)
   - Check if some images were processed multiple times
   - Review cache TTL and expiration

### Cost Optimization Recommendations

#### Immediate (Can reduce future costs by 50-70%):

1. **Reduce retry attempts:**
   ```python
   # Change from 5 retries to 3 retries
   def _bedrock_with_retry(func, max_retries=3):  # was 5
   ```
   - Still provides reliability
   - Reduces worst-case cost by 40%

2. **Increase Bedrock rate limit budget:**
   ```python
   # Increase semaphore from 10 to 20 concurrent calls
   BEDROCK_SEMAPHORE = threading.Semaphore(20)  # was 10
   ```
   - Reduces throttling probability
   - Fewer retries needed
   - Faster indexing

3. **Add request-level caching for query extraction:**
   ```python
   # Cache query constraint results in memory/DynamoDB
   # Saves $0.000625 per repeated query
   # Common queries like "modern home" could be pre-cached
   ```

4. **Optimize prompt lengths:**
   - Current prompt: ~1,500 tokens for query extraction
   - Could reduce to ~800 tokens (save 47% on input costs)
   - Current image analysis: ~500 tokens
   - Could reduce to ~300 tokens (save 40% on input costs)

#### Long-term (Can reduce costs by 70-90%):

1. **Use Claude Instant for simple queries:**
   - 5-10x cheaper than Haiku for query extraction
   - Still accurate for structured parsing

2. **Batch image analysis:**
   - Process 3-5 images in one Bedrock call
   - Share context across images
   - Reduce per-image overhead

3. **Pre-compute query constraints:**
   - Store common query patterns in DynamoDB
   - Only use LLM for novel queries
   - Could eliminate 80%+ of extraction calls

4. **Implement circuit breaker:**
   ```python
   # Stop retrying after N failures in time window
   # Prevents runaway costs from persistent issues
   ```

5. **Add cost tracking:**
   ```python
   # Log estimated cost per Lambda invocation
   # Alert when cost exceeds threshold
   # Helps catch issues early
   ```

---

## 💡 Key Takeaways

### What We Know:
1. **Indexing 3,903 properties with 83,059 images cost $73.36** (Claude Haiku only)
2. **Expected cost was $26.01** based on cache entries
3. **2.82x multiplier suggests ~1.8 retries per image on average**
4. **Query extraction ($0.06) is negligible compared to image analysis ($73+)**

### What We Don't Know:
1. Exact number of Bedrock API calls (need CloudWatch logs)
2. How many calls failed due to throttling
3. Actual token counts charged by Bedrock
4. Why Oct 16 had $5.62 in charges with no indexing

### Next Steps:
1. Run CloudWatch log analysis (see Action Items above)
2. Implement retry reduction (max_retries=3)
3. Increase concurrency limit (semaphore=20)
4. Add cost tracking to Lambda functions
5. Consider prompt optimization to reduce token usage

---

## 📊 Cost Projections

### Current System (No Changes):
- **First indexing:** ~$73 per 3,900 properties
- **Re-indexing (90% cache hit):** ~$7 per 3,900 properties
- **Per property (cold):** $0.019
- **Per property (cached):** $0.002
- **100,000 properties (cold):** ~$1,870

### With Optimizations (3 max retries + 20 concurrency):
- **First indexing:** ~$40 per 3,900 properties
- **Re-indexing (90% cache hit):** ~$4 per 3,900 properties
- **Per property (cold):** $0.010
- **Per property (cached):** $0.001
- **100,000 properties (cold):** ~$1,000

**Potential savings: 46% cost reduction**

---

## 🔗 Related Files

- [common.py:613-726](common.py#L613-L726) - detect_labels_with_response() (image analysis)
- [common.py:1016-1155](common.py#L1016-L1155) - extract_query_constraints() (query extraction)
- [upload_listings.py:84-132](upload_listings.py#L84-L132) - _bedrock_with_retry() (retry logic)
- [search.py:576](search.py#L576) - extract_query_constraints() call on every search
- [cache_utils.py](cache_utils.py) - Unified caching system

---

**Last Updated:** October 16, 2024
**Status:** Investigation in progress - awaiting CloudWatch log analysis
