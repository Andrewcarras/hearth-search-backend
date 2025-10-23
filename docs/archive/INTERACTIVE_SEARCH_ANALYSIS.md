# Interactive Search Analysis - "Ask Claude to Analyze My Search"

## Overview

Enable you to say: **"I just searched for 'white houses with granite', analyze that search"** and Claude can pull the complete logs and analyze them.

---

## How It Works

### 1. Each Search Gets a Unique Query ID

When you make a search, the response includes:
```json
{
  "query_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "results": [...],
  "debug_info": {
    "query_text": "White houses with granite countertops",
    "timestamp": 1729650123456,
    "total_time_ms": 2341
  }
}
```

### 2. Query ID is Also Logged to CloudWatch

**CloudWatch Log Entry:**
```json
{
  "level": "INFO",
  "query_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "event": "SEARCH_COMPLETE",
  "query_text": "White houses with granite countertops",
  "timestamp": 1729650123456,
  "full_log": {
    // Complete detailed log
  }
}
```

### 3. Query ID is Stored in DynamoDB

**DynamoDB Item:**
- **Partition Key:** `query_id` = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
- **Data:** Complete search log with all details

**Additional Indexes:**
- **GSI: query_text-timestamp-index** - Find searches by text + time
- **GSI: timestamp-index** - Find most recent searches

---

## User Experience - How You'd Use It

### Option 1: Reference by Query ID (Most Precise)
```
You: "I just made a search, the query_id is a1b2c3d4-e5f6-7890-abcd-ef1234567890, analyze it"

Claude:
1. Fetches from DynamoDB: aws dynamodb get-item --table-name SearchQueryLogs --key '{"query_id": {"S": "a1b2c3d4..."}}'
2. Reads complete log with all details
3. Analyzes: timing, results quality, errors, feature matches
4. Reports findings
```

### Option 2: Reference by Query Text + Approximate Time (More Natural)
```
You: "I just searched for 'white houses with granite' about 2 minutes ago, analyze it"

Claude:
1. Queries DynamoDB GSI:
   - query_hash = md5("white houses with granite")
   - timestamp between (now - 5min) and now
2. Finds the most recent matching search
3. Analyzes complete log
4. Reports findings
```

### Option 3: Just "My Last Search" (Simplest)
```
You: "Analyze my last search"

Claude:
1. Queries CloudWatch for most recent search from this Lambda
2. Extracts query_id
3. Fetches full details from DynamoDB
4. Analyzes and reports
```

### Option 4: Compare Multiple Searches
```
You: "I just searched for 'white houses' twice - once with multi-query enabled and once without. Compare them."

Claude:
1. Finds both searches by query text in last 10 minutes
2. Fetches both complete logs
3. Side-by-side comparison:
   - Results overlap
   - Feature match ratio
   - Latency difference
   - Quality scores
```

---

## What Claude Can Analyze

### Immediate Insights
1. **Why did this query return poor results?**
   - Feature match breakdown
   - Which search method found which results
   - LLM success/failure
   - Tag boosting effectiveness

2. **Why was this query slow?**
   - Timing breakdown by component
   - Bedrock call latency
   - OpenSearch query times
   - Multi-query overhead

3. **Which features are missing?**
   - Compare requested features vs actual matches
   - Show which properties are false positives
   - Identify data quality issues (e.g., feature_tags empty)

4. **How did scoring work?**
   - RRF fusion analysis
   - BM25 vs kNN contributions
   - Tag boost impact
   - First-image boost application

### Deep Analysis
1. **Result overlap analysis**
   - Venn diagram of BM25/kNN text/kNN image
   - Show properties only in one source
   - Identify why sources disagree

2. **Quality regression detection**
   - Compare this search to historical searches for same query
   - Show quality trends over time
   - Flag if this result is worse than usual

3. **Error root cause**
   - Trace errors through call stack
   - Show fallback behavior
   - Identify if errors impacted results

---

## Implementation Requirements

### A. Return query_id in Search Response
**Modify search.py to return:**
```python
return {
    "statusCode": 200,
    "body": json.dumps({
        "query_id": query_id,  # ADD THIS
        "results": final_results,
        "total": len(final_results),
        "debug_info": {...}
    })
}
```

### B. Add query_id to CloudWatch Logs
**Add structured logging:**
```python
logger.info(
    "SEARCH_COMPLETE",
    extra={
        "query_id": query_id,
        "query_text": q,
        "result_count": len(results),
        "total_time_ms": total_time
    }
)
```

### C. Create Helper Functions for Claude

**File: `search_log_reader.py`**
```python
def get_search_by_id(query_id: str) -> dict:
    """Fetch complete search log by query_id"""
    response = dynamodb.get_item(
        TableName='SearchQueryLogs',
        Key={'query_id': {'S': query_id}}
    )
    return response['Item']

def get_recent_searches(query_text: str, minutes: int = 10) -> list:
    """Find recent searches matching query text"""
    # Query GSI by query_hash + timestamp range

def get_last_search(minutes: int = 5) -> dict:
    """Get most recent search from CloudWatch or DynamoDB"""

def compare_searches(query_id_1: str, query_id_2: str) -> dict:
    """Compare two searches side-by-side"""
```

### D. Create Analysis Templates

**File: `analyze_search.py`**
```python
def analyze_search_quality(log: dict) -> str:
    """Generate human-readable analysis of search quality"""

    analysis = []

    # Feature match analysis
    perfect = log['result_quality_metrics']['perfect_matches']
    total = len(log['results'])
    analysis.append(f"Feature Matches: {perfect}/{total} results matched all features")

    # Timing analysis
    timing = log['timing']
    if timing['total_ms'] > 5000:
        analysis.append(f"⚠️ SLOW: {timing['total_ms']}ms total")
        analysis.append(f"  - LLM: {timing['llm_query_split_ms']}ms")
        analysis.append(f"  - Embeddings: {timing['bedrock_embedding_ms']}ms")

    # Error analysis
    if log['errors']:
        analysis.append(f"❌ Errors: {len(log['errors'])}")
        for err in log['errors']:
            analysis.append(f"  - {err['component']}: {err['error_message']}")

    # Result overlap analysis
    overlap = log['result_overlap']
    if overlap['all_three_overlap'] == 0:
        analysis.append("⚠️ Zero overlap between BM25/kNN text/kNN image")
        analysis.append("  → Different search methods finding completely different properties")

    return "\n".join(analysis)
```

---

## Example Interaction Flows

### Example 1: Debug Poor Results

```
You: "I just searched for 'white houses with granite countertops', query_id is abc-123,
     analyze why the results are bad"

Claude:
> Running: aws dynamodb get-item --table-name SearchQueryLogs --key '{"query_id": {"S": "abc-123"}}'
> Fetched complete search log (5.2KB)
> Analyzing...

SEARCH ANALYSIS for "white houses with granite countertops"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 QUALITY METRICS
  ✓ Perfect matches: 8/10 results (80%)
  ⚠️ Partial matches: 2/10 results (20%)

🔍 FEATURE MATCH BREAKDOWN
  Top Result (zpid: 12772463):
    ✓ white_exterior: YES (1 tag)
    ✓ granite_countertops: YES (3 tags)
    ✓ hardwood_floors: YES (3 tags)
    Score: 0.0179 (rank 1 in BM25 only)

  Result #3 (zpid: 12859406):
    ❌ white_exterior: NO
    ✓ granite_countertops: YES
    ✓ hardwood_floors: YES
    → This is a false positive (missing key feature)

⚡ PERFORMANCE
  Total time: 5,618ms (SLOW)
  Breakdown:
    - LLM query split: 1,200ms ❌ FAILED
    - Bedrock embeddings: 450ms (3 calls)
    - BM25 search: 172ms ✓
    - kNN searches: 545ms ✓

❌ ERRORS DETECTED
  1. LLM query splitter failed
     Error: "Expecting value: line 1 column 1 (char 0)"
     Impact: Used fallback (still generated 3 sub-queries)

  2. feature_tags field empty for 10/10 results
     Impact: Tag boosting not working (boost_factor = 1.0 for all)
     → No bonus for perfect matches!

🔄 RESULT OVERLAP
  BM25 ∩ kNN text: 0 results
  BM25 ∩ kNN image: 0 results
  kNN text ∩ kNN image: 0 results
  → ZERO OVERLAP - Each method finding completely different properties!

  BM25 results: Matching text "white", "granite", "countertops" in description
  kNN text: Matching semantic meaning of query
  kNN image: Matching visual similarity to query embedding

  ⚠️ This explains low scores - each property only appears in ONE ranking list

🎯 ROOT CAUSES OF POOR RESULTS
  1. ❌ feature_tags empty → Tag boosting ineffective
  2. ❌ Zero result overlap → RRF can't properly combine rankings
  3. ⚠️ LLM failing → Adding 1.2s latency with no benefit

💡 RECOMMENDATIONS
  1. Fix LLM prompt (remove invalid JSON pipe chars)
  2. Investigate why feature_tags is empty for all properties
  3. Reduce visual_features_text boost from 2.5 to 1.0
  4. Consider making multi-query the default (improves 80% match rate)
```

### Example 2: Compare Two Searches

```
You: "I searched for 'white houses with granite' twice in the last 5 minutes -
     once with multi-query enabled and once without. Compare them."

Claude:
> Querying DynamoDB for recent searches matching "white houses with granite"...
> Found 2 searches:
>   1. query_id: abc-123 (use_multi_query: false, 2 min ago)
>   2. query_id: def-456 (use_multi_query: true, 1 min ago)
> Fetching complete logs...
> Comparing...

SEARCH COMPARISON: Multi-Query ON vs OFF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                          │ Multi-Query OFF │ Multi-Query ON
━━━━━━━━━━━━━━━━━━━━━━━━━━┼━━━━━━━━━━━━━━━━━┼━━━━━━━━━━━━━━
Latency                   │ 2,100ms ✓       │ 5,618ms ⚠️
Perfect feature matches   │ 2/10 (20%) ❌   │ 8/10 (80%) ✓
Average score            │ 0.0178          │ 0.0198 ✓
Result overlap (3 sources)│ 0 ❌            │ 1 ⚠️
LLM success              │ N/A             │ Failed

TOP RESULT COMPARISON:
  Multi-Query OFF: zpid 12772463, score 0.0178
    - BM25 rank 1 only
    - Features: white ✓, granite ✓, hardwood ✓

  Multi-Query ON: zpid 2080387168, score 0.0287
    - kNN image rank 1, BM25 rank 3
    - Features: white ✓, granite ✓, hardwood ✓
    - Better score due to appearing in multiple rankings

🎯 VERDICT: Multi-query mode finds better matches (+60% quality)
            at cost of 2.6x higher latency (+3.5 seconds)

💡 The latency comes from:
   - LLM call: 1,200ms (failing but still attempted)
   - 3x embedding calls: 450ms (3 sub-queries vs 1)
   - 3x OpenSearch queries: 850ms more
```

---

## Tools Claude Would Use

### 1. AWS CLI Commands
```bash
# Get specific search
aws dynamodb get-item \
  --table-name SearchQueryLogs \
  --key '{"query_id": {"S": "abc-123"}}'

# Find recent searches by query text
aws dynamodb query \
  --table-name SearchQueryLogs \
  --index-name query_hash-timestamp-index \
  --key-condition-expression "query_hash = :hash AND #ts BETWEEN :start AND :end"

# Get last 10 searches
aws dynamodb scan \
  --table-name SearchQueryLogs \
  --limit 10 \
  --scan-index-forward false
```

### 2. CloudWatch Logs Insights
```sql
fields @timestamp, query_id, query_text, total_time_ms
| filter event = "SEARCH_COMPLETE"
| sort @timestamp desc
| limit 10
```

### 3. Python Analysis Scripts
```python
# Quick analysis
python analyze_search.py --query-id abc-123

# Compare searches
python analyze_search.py --compare abc-123 def-456

# Recent searches
python analyze_search.py --last 10
```

---

## Response Time Expectations

- **Fetch by query_id:** ~100-200ms (DynamoDB GetItem)
- **Find by query text:** ~300-500ms (DynamoDB Query on GSI)
- **Analysis generation:** ~500ms-1s (Python processing)
- **Total:** ~1-2 seconds for complete analysis

---

## Privacy & Data Retention

- **Query ID:** Included in response, can be shared
- **Search logs:** Retained 90 days, then auto-deleted
- **No PII:** IP addresses hashed, no user identification
- **Access:** Only via this Claude session or development team

---

## Summary

**Yes, you'll be able to say:**
- "Analyze my last search"
- "I just searched for X, analyze it"
- "Query ID abc-123, why are the results bad?"
- "Compare my last two searches"
- "Show me all searches for 'white houses' today"

**Claude will:**
1. Fetch the complete log from DynamoDB or CloudWatch
2. Analyze quality, timing, errors, feature matches
3. Provide detailed breakdown with root causes
4. Suggest specific fixes
5. Compare with historical data if available

**This enables:**
- Real-time debugging of search quality
- A/B testing different search modes
- Understanding exactly why results are good/bad
- Tracking quality improvements over time
