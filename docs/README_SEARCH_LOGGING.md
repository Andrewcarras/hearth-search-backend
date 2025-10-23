# Search Logging & Analysis System

**Status:** ✅ Production Ready
**Version:** 2.0
**Last Updated:** October 22, 2025

---

## Overview

Complete search logging and analysis system that captures every search query with full context, provides interactive analysis tools, and automated quality alerting.

**Total Cost:** ~$1.13/month for 10,000 searches/day
- DynamoDB: $0.31/month
- CloudWatch Logs: $0.32/month
- CloudWatch Alarms: $0.50/month

---

## Quick Start

### Analyze a Search

```bash
# Get query_id from search response
curl -X POST https://ectmd6vfzh.execute-api.us-east-1.amazonaws.com/search \
  -H "Content-Type: application/json" \
  -d '{"q": "Modern homes with granite countertops", "size": 10, "index": "listings-v2"}' \
  | jq '.query_id'

# Analyze it
python analyze_search.py --query-id <query-id>
```

### Common Commands

```bash
# Recent searches
python analyze_search.py --recent --limit 10

# Find slow searches
python analyze_search.py --slow --threshold 5000

# Find poor quality searches
python analyze_search.py --poor-quality --threshold 0.02

# Performance statistics
python analyze_search.py --stats

# Compare two searches
python analyze_search.py --compare query-id-1 query-id-2
```

---

## What's Logged

Every search captures **22 fields** including:

### Request Context
- query_id, timestamp, query_hash
- query_text, query_length
- size, index, boost_mode, search_mode, strategy

### Query Analysis
- extracted_constraints (must_have, hard_filters, architecture_style, query_type)
- multi_query_status (for multi-query mode)

### Performance Timing
- constraint_extraction_ms
- embedding_generation_ms (+ Bedrock API call count)
- bm25_ms, knn_text_ms, knn_image_ms
- rrf_fusion_ms, tag_boosting_ms
- total_ms

### Search Results
- Top 10 results with zpid, score, feature matches, property details
- result_counts (BM25 hits, kNN hits, RRF fused, final returned)
- result_overlap (BM25∩Text, BM25∩Image, Text∩Image, All Three)

### Quality Metrics
- avg_score, score_variance
- avg_feature_match_ratio
- perfect_matches, partial_matches, no_matches
- source_distribution

### Error Tracking
- errors (component, type, message, fallback_used, impact)
- warnings (component, message, impact)

---

## Architecture

```
┌─────────────────┐
│   Search API    │
│  (search.py)    │
└────────┬────────┘
         │
         ├─────► DynamoDB (SearchQueryLogs)
         │       - 90 day retention
         │       - Pay-per-request
         │
         └─────► CloudWatch Logs
                 - Structured JSON
                 - 30 day retention


┌─────────────────┐       ┌──────────────────┐
│  Metric Filters │──────►│  CloudWatch      │
│  - Errors       │       │  Alarms          │
│  - Slow queries │       │  - HighErrorRate │
│  - Poor quality │       │  - SlowQueries   │
└─────────────────┘       │  - PoorQuality   │
                          │  - LambdaErrors  │
                          │  - Throttles     │
                          └────────┬─────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │   SNS Topic     │
                          │ (Email alerts)  │
                          └─────────────────┘


┌──────────────────────┐
│  Analysis Tools      │
│                      │
│ search_log_reader.py │──► Fetch & analyze logs
│ analyze_search.py    │──► Interactive CLI
└──────────────────────┘
```

---

## Components

### 1. Logging Infrastructure

**Files:**
- `search_logger.py` - Core logging module (10,984 bytes)
- `search.py` - Instrumented handler (~80 lines added)

**Resources:**
- DynamoDB table: `SearchQueryLogs`
- CloudWatch log group: `/aws/lambda/hearth-search-v2`

**Deployment:**
```bash
./deploy_lambda.sh search
```

---

### 2. Analysis Tools

**Files:**
- `search_log_reader.py` - Helper functions (17,932 bytes)
  - 10 fetch functions
  - 5 analysis functions

- `analyze_search.py` - CLI tool (10,623 bytes)
  - 9 commands
  - Interactive analysis

**Usage:**
```bash
python analyze_search.py --help
```

---

### 3. Automated Alerts

**Files:**
- `create_search_alerts.sh` - Alert setup script (4,523 bytes)

**Resources:**
- SNS Topic: `SearchQualityAlerts`
- 3 Metric Filters
- 5 CloudWatch Alarms

**Deployment:**
```bash
./create_search_alerts.sh
```

**Subscribe to alerts:**
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:692859949078:SearchQualityAlerts \
  --protocol email \
  --notification-endpoint your-email@example.com
```

---

## Analysis Commands

### By Query ID
```bash
python analyze_search.py --query-id c2e9602c-c173-472d-95bd-b6f861aba910
```
Complete analysis of specific search.

### By Query Text
```bash
python analyze_search.py --text "White houses with granite countertops"
```
Find all searches with exact query text.

### Recent Searches
```bash
python analyze_search.py --recent --limit 10 --details
```
Show N most recent searches, optionally with full details.

### Slow Searches
```bash
python analyze_search.py --slow --threshold 5000
```
Find searches slower than 5 seconds, show slowest component.

### Searches with Errors
```bash
python analyze_search.py --errors --details
```
List all searches that encountered errors.

### Poor Quality Searches
```bash
python analyze_search.py --poor-quality --threshold 0.02
```
Find searches with avg_score < 0.02.

### Performance Statistics
```bash
python analyze_search.py --stats --limit 100
```
Show min, max, avg, median, p95, p99 latencies.

### Compare Searches
```bash
python analyze_search.py --compare query-id-1 query-id-2
```
Side-by-side comparison showing timing and quality differences.

---

## Example Output

```
================================================================================
SEARCH LOG: c2e9602c-c173-472d-95bd-b6f861aba910
================================================================================

Query: "Modern homes with granite countertops"
Timestamp: 2025-10-22 19:16:46
Total Time: 2075.57 ms

Parameters:
  Index: listings-v2
  Size: 5
  Strategy: hybrid
  Search Mode: adaptive

Extracted Constraints:
  Must Have Tags: ['modern', 'granite_countertops']
  Architecture Style: modern
  Query Type: material

Timing Breakdown:
  constraint_extraction_ms      :  1124.90 ms ( 54.2%)
  knn_image_ms                  :   383.22 ms ( 18.5%)
  bm25_ms                       :   204.08 ms (  9.8%)
  embedding_generation_ms       :   197.99 ms (  9.5%)
  knn_text_ms                   :   159.65 ms (  7.7%)
  tag_boosting_ms               :     3.72 ms (  0.2%)
  rrf_fusion_ms                 :     0.10 ms (  0.0%)
  Bedrock API Calls             : 1

Result Quality: POOR - No feature matches
  Total Results: 5
  Avg Score: 0.023800
  Score Variance: 0.00000300

Feature Matching:
  Perfect Matches: 0
  Partial Matches: 0
  No Matches: 5
  Avg Match Ratio: 0.00%

Strategy Overlap:
  BM25 ∩ Text kNN: 0
  BM25 ∩ Image kNN: 0
  Text ∩ Image kNN: 0
  All Three: 0

⚠️  WARNINGS (1):
  - tag_boosting: feature_tags empty for 5/5 results
    Impact: high

Top 5 Results:
  1. zpid=2061545371 | score=0.026829
     Sandy, UT | $3,200,000 | 6bd/6ba
  2. zpid=2090556397 | score=0.023810
     Sandy, UT | $800,000 | 4bd/3ba
  3. zpid=453896301 | score=0.023256
     Salt Lake City, UT | $3,461 | 3bd/2ba

================================================================================
```

---

## CloudWatch Alarms

| Alarm | Condition | Threshold | Period | Status |
|-------|-----------|-----------|--------|--------|
| Search-HighErrorRate | Errors > 10 | 10 errors | 5 min | OK |
| Search-SlowQueries | Slow (>5s) > 5 | 5 queries | 5 min | INSUFFICIENT_DATA |
| Search-PoorQuality | Poor quality > 10 | 10 searches | 5 min | INSUFFICIENT_DATA |
| Search-LambdaErrors | Lambda errors > 5 | 5 errors | 2 min | INSUFFICIENT_DATA |
| Search-LambdaThrottles | Throttling > 0 | 1 throttle | 1 min | OK |

**View alarms:**
```bash
aws cloudwatch describe-alarms --alarm-name-prefix Search-
```

---

## Key Insights Discovered

### 1. Performance Bottleneck: Constraint Extraction

**Finding:** 54-68% of search time spent in constraint extraction

**Data:**
- Query "Mid century": 1137ms (68.5%)
- Query "Modern homes...": 1125ms (54.2%)

**Recommendation:** Profile and optimize `extract_query_constraints()`

---

### 2. Feature Matching Broken

**Finding:** feature_tags field empty for all properties

**Impact:**
- Tag boosting cannot work
- Zero feature matches despite constraints extracted
- Quality severely degraded

**Recommendation:** Investigate data pipeline

---

### 3. Strategy Divergence

**Finding:** Zero overlap between BM25, kNN text, and kNN image

**Data:**
- BM25 ∩ Text kNN: 0-1 properties
- BM25 ∩ Image kNN: 0 properties
- All Three: 0 properties

**Recommendation:** Analyze top 20 results from each strategy

---

## Python API Usage

### Fetch and Analyze

```python
from search_log_reader import (
    get_search_by_query_id,
    get_recent_searches,
    analyze_timing,
    analyze_result_quality
)

# Get specific search
search = get_search_by_query_id('c2e9602c-c173-472d-95bd-b6f861aba910')

# Analyze timing
timing = analyze_timing(search)
print(f"Slowest: {timing['slowest_component']}")
print(f"Total: {timing['total_ms']} ms")

# Analyze quality
quality = analyze_result_quality(search)
print(f"Assessment: {quality['quality_assessment']}")
print(f"Avg Score: {quality['avg_score']}")
```

### Export for ML/Analysis

```python
import json
from search_log_reader import get_recent_searches

# Get last 1000 searches
searches = get_recent_searches(1000)

# Export to JSON
with open('searches.json', 'w') as f:
    json.dump(searches, f, indent=2)

# Now use with pandas:
import pandas as pd
df = pd.DataFrame(searches)
```

---

## Monitoring Dashboard

View alarms in AWS Console:
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#alarmsV2:

Or via CLI:
```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix Search- \
  --query 'MetricAlarms[*].[AlarmName,StateValue,MetricName]' \
  --output table
```

---

## Cost Breakdown

### DynamoDB (SearchQueryLogs)
- **Writes:** 10,000/day × 30 = 300,000/mo → $0.08/mo
- **Storage:** 300,000 × 3KB = 900MB → $0.23/mo
- **Reads:** 1,000/mo → $0.0003/mo
- **Subtotal:** $0.31/month

### CloudWatch Logs
- **Ingestion:** 20MB/day × 30 = 600MB/mo → $0.30/mo
- **Storage:** 600MB × $0.03/GB → $0.02/mo
- **Subtotal:** $0.32/month

### CloudWatch Alarms
- **5 alarms:** 5 × $0.10 = $0.50/mo
- **Subtotal:** $0.50/month

### SNS Notifications
- **Email:** Free (first 1,000/mo)
- **Subtotal:** $0.00/month

**Grand Total:** ~$1.13/month (for 10,000 searches/day)

---

## Files Reference

### Core Logging
- `search_logger.py` - Logging module
- `search.py` - Instrumented handler
- `deploy_lambda.sh` - Deployment script

### Analysis Tools
- `search_log_reader.py` - Helper functions
- `analyze_search.py` - CLI tool

### Monitoring
- `create_search_alerts.sh` - Alert setup

### Documentation
- `SEARCH_LOGGING_IMPLEMENTATION_COMPLETE.md` - Phase 1 details
- `PHASE_2_ANALYSIS_TOOLS_COMPLETE.md` - Phase 2 details
- `README_SEARCH_LOGGING.md` - This file

---

## Troubleshooting

### No logs in DynamoDB

Check Lambda logs:
```bash
aws logs tail /aws/lambda/hearth-search-v2 --since 5m
```

Verify table exists:
```bash
aws dynamodb describe-table --table-name SearchQueryLogs
```

### Analysis tool not finding searches

Wait 2-3 seconds after search for DynamoDB write:
```bash
sleep 3 && python analyze_search.py --query-id <id>
```

### Alarms not triggering

Check metric data:
```bash
aws cloudwatch get-metric-statistics \
  --namespace Hearth/Search \
  --metric-name SlowSearchCount \
  --start-time 2025-10-22T00:00:00Z \
  --end-time 2025-10-22T23:59:59Z \
  --period 300 \
  --statistics Sum
```

---

## Future Enhancements (Optional)

### Phase 3: Visualization Dashboard
- Real-time search monitoring UI
- Performance trend charts
- Quality heatmaps
- Error tracking dashboard

### Phase 4: Advanced Analytics
- ML-based relevance scoring
- A/B test framework
- User behavior analysis
- Query clustering

---

## Support

### View Logs
```bash
aws logs tail /aws/lambda/hearth-search-v2 --follow
```

### Query DynamoDB Directly
```bash
aws dynamodb scan --table-name SearchQueryLogs --limit 1
```

### Check Alarm Status
```bash
aws cloudwatch describe-alarms --alarm-name-prefix Search-
```

---

## Version History

**v2.0** (October 22, 2025)
- ✅ Phase 2: Analysis tools complete
- ✅ Interactive CLI tool
- ✅ Automated alerting
- ✅ Performance statistics

**v1.0** (October 22, 2025)
- ✅ Phase 1: Logging infrastructure complete
- ✅ DynamoDB logging
- ✅ CloudWatch structured logs
- ✅ Comprehensive data capture

---

## Summary

✅ **Production-Ready Search Logging & Analysis System**

**What You Get:**
- Complete search telemetry (22 fields per search)
- Interactive analysis tools (9 CLI commands)
- Automated quality alerts (5 CloudWatch alarms)
- Performance diagnostics (timing breakdown, percentiles)
- Quality assessment (GOOD/MODERATE/POOR)
- Search comparison tools

**Cost:** $1.13/month for 10,000 searches/day

**User Experience:**
- Every search returns query_id
- Instant analysis: `python analyze_search.py --query-id <id>`
- Complete diagnosis in <2 seconds
- Systematic quality investigation

**Developer Experience:**
- Zero-config logging (automatic)
- Python API for custom analysis
- Export to JSON/pandas for ML
- CloudWatch dashboards ready

The system is fully operational and ready for production use!
