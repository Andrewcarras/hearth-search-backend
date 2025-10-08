# Re-indexing Status

## Current Re-indexing: October 8, 2025

**Status**: In Progress ✅

### Progress
- **Listings processed**: 313 / 1588 (10.0%)
- **Active Lambda instances**: 3
- **Estimated completion**: ~25-30 minutes from start

### What's Being Updated

This re-indexing adds critical improvements to all existing listings:

1. **Geo Coordinates** (`geo` field)
   - Enables proximity-based search ("Show me houses near a gym")
   - Uses latitude/longitude from listing JSON
   - Required for `geo_distance` filters in OpenSearch

2. **Comprehensive Feature Detection** (All images processed)
   - Rekognition on ALL images (not just first)
   - Detects carpet, hardwood, tile, vinyl, laminate flooring
   - Identifies outdoor features across multiple photos
   - Improves accuracy of "no carpet", "all hardwood" queries

3. **Architecture Style Classification** (Claude Vision)
   - High-quality classification using Claude 3 Sonnet
   - Detects: modern, craftsman, ranch, contemporary, traditional, victorian, etc.
   - Visual feature tagging: balconies, porches, fences, garages

### Monitoring Progress

Use the monitoring script to check status:

```bash
./watch_reindex_progress.sh
```

Or manually check logs:

```bash
aws logs tail /aws/lambda/hearth-upload-listings --follow
```

### Cost Estimate

**Total cost for re-indexing 1588 listings**: ~$15 one-time

- Rekognition: $9.53 (6 images × 1588 listings × $0.001)
- Claude Vision: $4.76 (1 image × 1588 listings × $0.003)
- Bedrock Titan: $1.21 (embeddings + text processing)
- Lambda: $0.03 (compute time)

This is a **one-time cost** - the system does NOT auto-re-index or loop.

### Why This Works (No $200 Bill)

✅ **Proper termination logic**: Lambda only self-invokes if `has_more = true`
✅ **Start/limit tracking**: Each invocation processes a specific batch
✅ **Zpid-based upsert**: Re-running won't duplicate costs
✅ **Manual trigger only**: No auto-triggers from S3/schedules

See [REKOGNITION_COST_ANALYSIS.md](REKOGNITION_COST_ANALYSIS.md) for details.

### Testing After Completion

Once re-indexing completes (313/1588 → 1588/1588), test these queries:

```bash
# Geolocation search
curl -X POST "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search" \
  -H "Content-Type: application/json" \
  -d '{"q": "Show me houses near a gym", "size": 5}'

# Flooring search
curl -X POST "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search" \
  -H "Content-Type: application/json" \
  -d '{"q": "Show me houses with all hardwood floors and no carpet", "size": 5}'

# Combined search
curl -X POST "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search" \
  -H "Content-Type: application/json" \
  -d '{"q": "modern homes with a balcony within 5 miles of a gym", "size": 3}'
```

### Triggered By

Lambda invocation:
```bash
aws lambda invoke \
  --function-name hearth-upload-listings \
  --cli-binary-format raw-in-base64-out \
  --payload '{"bucket": "demo-hearth-data", "key": "murray_listings.json", "start": 0, "limit": 100}' \
  --invocation-type Event \
  response_reindex.json
```

The Lambda will self-invoke for batches:
- Invocation 1: start=0, limit=100 → processes 0-99, invokes start=100
- Invocation 2: start=100, limit=100 → processes 100-199, invokes start=200
- ... continues until start >= 1588, then stops

### Next Steps

1. ⏳ Wait for re-indexing to complete (~20-25 more minutes)
2. ✅ Verify completion: `./watch_reindex_progress.sh` shows 1588/1588
3. 🧪 Test all query types (proximity, flooring, architecture, combined)
4. 📊 Verify results include geo coordinates and comprehensive features

## Recent Re-indexing History

- **October 8, 2025 6:15 PM**: Started full re-index to add geo coordinates and comprehensive feature detection (In Progress: 10%)
