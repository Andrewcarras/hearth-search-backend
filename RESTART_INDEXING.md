# How to Restart Re-Indexing After Bedrock Throttling

## Current Situation

**Problem:** Severe Bedrock throttling (33,000+ errors in 5 min)
- All re-indexing Lambda invocations are being throttled
- 0 listings successfully indexed in OpenSearch
- UI shows 503 errors because there's no data to search

**Cause:** Too many parallel Lambda invocations hitting Bedrock simultaneously
- Multiple Lambdas processing 150 listings each
- Each listing = 7 Bedrock API calls (1 text + 6 image embeddings)
- Result: ~10,000+ concurrent Bedrock requests (way over limit)

## Solution: Restart with Slower Rate

### Step 1: Wait for Current Invocations to Stop (30 minutes)

Lambda functions timeout after 15 minutes, so all current invocations will stop naturally.
Also gives Bedrock quotas time to reset.

```bash
# Check if invocations have stopped
aws logs tail /aws/lambda/hearth-upload-listings --since 2m --region us-east-1 | grep "Self-invoked"
```

If no output → invocations have stopped ✓

### Step 2: Delete the Broken Index

```bash
aws lambda invoke \
  --function-name hearth-upload-listings \
  --region us-east-1 \
  --payload '{"operation": "delete_index"}' \
  --cli-binary-format raw-in-base64-out \
  response.json

cat response.json
```

### Step 3: Start Re-Indexing with SLOWER Rate

**Key change: `limit: 50` instead of 150**

This reduces concurrent Bedrock calls by 3x:
- 50 listings × 7 calls = 350 Bedrock requests per Lambda
- Much less likely to hit throttling

```bash
aws lambda invoke \
  --function-name hearth-upload-listings \
  --region us-east-1 \
  --payload '{"bucket": "demo-hearth-data", "key": "murray_listings.json", "start": 0, "limit": 50}' \
  --cli-binary-format raw-in-base64-out \
  --invocation-type Event \
  response.json

echo "✓ Re-indexing started with slower rate (50 listings per batch)"
```

### Step 4: Monitor Progress

```bash
# Check progress every 30 seconds
watch -n 30 'aws logs tail /aws/lambda/hearth-upload-listings --since 2m --region us-east-1 | grep "Self-invoked" | tail -1'
```

### Step 5: Verify Indexing is Working

After 10 minutes, check if listings are actually being indexed:

```bash
curl -s "https://search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com/listings/_count" | python3 -c "import json, sys; print(f'Indexed: {json.load(sys.stdin).get(\"count\", 0)} listings')"
```

Should show > 0 if throttling has settled.

### Step 6: Check for Throttling

```bash
aws logs tail /aws/lambda/hearth-upload-listings --since 5m --region us-east-1 | grep -c "ThrottlingException"
```

- **< 100**: Good, proceeding normally
- **100-1000**: Some throttling, but manageable
- **> 1000**: Still heavily throttled, wait longer or reduce to limit=25

## Timeline with Slow Re-Indexing

- **Batch size**: 50 listings
- **Batches needed**: 1,588 / 50 = 32 batches
- **Time per batch**: ~7-10 minutes (slower due to Bedrock API calls)
- **Total time**: ~4-5 hours

This is slower, but actually completes successfully without throttling.

## Alternative: Request Higher Bedrock Quotas

If you need faster re-indexing:

1. Go to AWS Service Quotas console
2. Search for "Bedrock"
3. Request quota increase for:
   - "Invoke model requests per minute" (currently 3000-5000)
   - Request 20,000 per minute

Takes 24-48 hours for AWS to approve.

## When to Run This

**Wait at least 30 minutes from now** before running Step 2-3 above.

Current time when this was written: ~23:05 UTC (Oct 9, 2025)
**Recommended restart time**: 23:35 UTC or later

This gives:
- Time for current Lambdas to timeout
- Time for Bedrock quotas to reset
- Clean slate for slow re-indexing
