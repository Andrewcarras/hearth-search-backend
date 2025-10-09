# Re-indexing Guide

## Monitoring Progress

Use the monitoring script to check current status:

```bash
./monitor_reindex.sh
```

This shows:
- Number of listings processed
- Current batch being worked on
- Active Lambda instances
- Estimated time to completion

## What Gets Indexed

The upload Lambda processes each listing with:

1. **Geo Coordinates** (`geo` field)
   - Latitude/longitude from Zillow data
   - Required for proximity-based search ("homes near a gym")
   - Enables `geo_distance` filters in OpenSearch

2. **Visual Feature Detection** (Rekognition + Claude Vision)
   - Architecture style classification (modern, craftsman, ranch, etc.)
   - Visual features: balconies, porches, fences, garages
   - Exterior colors and materials
   - Interior features from multiple images

3. **Text Embeddings** (Titan)
   - 1024-dim vector embeddings for semantic search
   - Generated from property descriptions

4. **Image Embeddings** (Titan)
   - 1024-dim vector embeddings for visual search
   - Averaged from all property photos

## Triggering Re-indexing

### Full Re-index

Re-process all 1,588 listings:

```bash
aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type Event \
  --payload '{"bucket": "demo-hearth-data", "key": "murray_listings.json", "start": 0, "limit": 100}' \
  --region us-east-1 \
  response.json
```

The Lambda will:
1. Process 100 listings
2. Self-invoke for next batch (start=100)
3. Continue until all listings processed
4. Stop automatically when complete

### Partial Re-index

Re-process specific range:

```bash
# Process listings 500-600
aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type Event \
  --payload '{"bucket": "demo-hearth-data", "key": "murray_listings.json", "start": 500, "limit": 100}' \
  --region us-east-1 \
  response.json
```

## Performance

- **Speed**: ~100 listings per 13 minutes
- **Total time**: ~3.5 hours for all 1,588 listings
- **Batch size**: 100 listings per Lambda invocation
- **Timeout**: 15 minutes per invocation (includes safety buffer)

## Checking Logs

### View Recent Activity

```bash
aws logs tail /aws/lambda/hearth-upload-listings --since 10m --region us-east-1
```

### Follow Live Progress

```bash
aws logs tail /aws/lambda/hearth-upload-listings --follow --region us-east-1
```

### Check for Errors

```bash
aws logs tail /aws/lambda/hearth-upload-listings --since 1h --region us-east-1 | grep ERROR
```

## Cost Estimate

**One-time re-indexing cost** (1,588 listings):
- Rekognition: ~$9.50 (6 images per listing)
- Claude Vision: ~$4.76 (1 image per listing)
- Bedrock Titan: ~$1.20 (embeddings)
- Lambda compute: ~$0.03

**Total**: ~$15 one-time

## Troubleshooting

### Re-indexing Appears Stuck

**Check if still running**:
```bash
./monitor_reindex.sh
```

**Check for Lambda errors**:
```bash
aws logs tail /aws/lambda/hearth-upload-listings --since 30m | grep -E "ERROR|Exception"
```

**Restart from last position**:
```bash
# If stuck at listing 400, restart from there
aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type Event \
  --payload '{"bucket": "demo-hearth-data", "key": "murray_listings.json", "start": 400, "limit": 100}' \
  response.json
```

### OpenSearch Returns 429/502 Errors

This is normal during heavy indexing. The Lambda has retry logic with exponential backoff.

**Check logs**:
```bash
aws logs tail /aws/lambda/hearth-upload-listings --since 5m | grep "429\|502"
```

The retries will succeed - no action needed.

### Verify Completion

Check total indexed count:

```bash
curl -X GET "https://search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com/listings/_count" \
  --aws-sigv4 "aws:amz:us-east-1:es"
```

Should show `{"count": 1588}` when complete.

## After Re-indexing

Once complete, all search features will work:

✅ Feature queries ("homes with pool")
✅ Architecture style ("modern homes")
✅ Geo-location ("homes near a gym")
✅ Combined queries ("modern 3 bed homes with pool near gym")

Test with:
```bash
curl -X POST "http://54.163.59.108/search" \
  -H "Content-Type: application/json" \
  -d '{"q": "modern homes with pool", "size": 10}'
```
