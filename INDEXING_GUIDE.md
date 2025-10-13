# Hearth Listing Indexing Guide

## Current System Status (2025-10-13)

✅ **Production Status:**
- **Indexed**: 1,358+ / 1,588 listings (85.5%, indexing in progress)
- **Search API**: https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search
- **OpenSearch**: Green, fully operational
- **Caching**: DynamoDB - 90% cost savings on re-indexing

## Quick Start: Index All Listings Locally

**Recommended Method:** Use `index_local.py` to run indexing on your computer (not Lambda):

```bash
# Start indexing (runs on your computer with full control)
python index_local.py
```

**Benefits:**
- ✅ Full control (Ctrl+C to stop anytime)
- ✅ No Lambda timeouts
- ✅ Better debugging and progress visibility
- ✅ Same DynamoDB caching (saves Bedrock costs)
- ✅ OpenSearch verification (confirms each listing is indexed)

**Progress Tracking:**
```bash
# Check how many listings are indexed
python /tmp/check_opensearch_count.py
```

**Timing:** ~30-40 seconds per listing (with caching)
- 100 listings = ~50-60 minutes
- 500 listings = ~4-6 hours
- 1,588 listings = ~12-16 hours

## Alternative: Lambda-Based Indexing

If you prefer to use Lambda (not recommended due to complexity):

### 1. Clear the Index (Fresh Start)

```bash
aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type RequestResponse \
  --payload '{"operation":"delete_index"}' \
  --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  /tmp/delete_response.json
```

### 2. Set Lambda Concurrency to 1 (IMPORTANT!)

```bash
# Prevent infinite loops by allowing only 1 concurrent execution
aws lambda put-function-concurrency \
  --function-name hearth-upload-listings \
  --reserved-concurrent-executions 1 \
  --region us-east-1
```

### 3. Invoke Lambda to Start Indexing

```bash
# Index all listings from S3
aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type Event \
  --payload '{"bucket":"demo-hearth-data","key":"murray_listings.json","start":0,"limit":50}' \
  --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  /tmp/response.json
```

**Note:** Lambda will self-invoke to process remaining listings in batches.

### 4. Monitor Progress

```bash
# Watch Lambda logs
aws logs tail /aws/lambda/hearth-upload-listings --follow --region us-east-1

# Check indexed count
python /tmp/check_opensearch_count.py
```

### 5. Stop Lambda Indexing

```bash
# Set concurrency to 0 to stop all invocations
aws lambda put-function-concurrency \
  --function-name hearth-upload-listings \
  --reserved-concurrent-executions 0 \
  --region us-east-1
```

## Verified Search Features

The AI vision analysis detects these features:

- **"blue homes"** → Blue exterior colors
- **"vaulted ceilings"** → High/vaulted ceilings
- **"granite countertops"** → Kitchen granite surfaces
- **"bright and airy"** → Natural light/open spaces
- **"2-car garage"** → Garage types
- **"hardwood floors"** → Floor materials
- **"stainless steel appliances"** → Kitchen appliances
- **"large windows"** → Window features
- **"brick exterior"** → Exterior materials
- **"fireplace"** → Indoor features

## Cost Optimization

✅ **DynamoDB Caching (Critical!):**
- Text embeddings cached by MD5 hash
- Image embeddings cached by URL
- Claude Vision analysis cached by URL
- **Result:** Re-indexing costs ~$0.10 instead of $1.50+ (90% savings)

✅ **Image Resolution:**
- Using 576px images for embeddings (cost-optimized)
- Full resolution stored in `images` array for UI display

✅ **Vision Model:**
- Claude Haiku: $0.00025 per image
- 75% cheaper than Rekognition
- Better feature detection

## System Architecture

```
┌─────────────────────┐
│  S3: murray_listings│ 1,588 listings
│  .json              │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐      ┌────────────────┐
│ index_local.py      │◄────►│ DynamoDB Cache │
│ OR                  │      │ (embeddings +  │
│ Lambda: upload      │      │  vision)       │
│                     │      └────────────────┘
│ - Vision Analysis   │
│ - Text Embeddings   │
│ - Image Embeddings  │
└─────────┬───────────┘
          │
          ▼
    ┌────────────┐
    │ OpenSearch │ kNN + BM25 hybrid search
    │ 1,358+/1,588│
    └─────┬──────┘
          │
          ▼
    ┌────────────┐
    │ Search API │ https://...amazonaws.com/prod/search
    └────────────┘
```

## Files

- **[index_local.py](index_local.py)** - Local indexing script (recommended)
- **[upload_listings.py](upload_listings.py)** - Lambda handler
- **[search.py](search.py)** - Search Lambda handler
- **[common.py](common.py)** - Shared utilities (vision, embeddings, caching)

## Troubleshooting

**Issue:** Indexing seems stuck
**Solution:** Check progress with `python /tmp/check_opensearch_count.py`

**Issue:** "Skipping duplicate invocation" errors
**Solution:** DynamoDB job table has stale entries. Use `index_local.py` which generates unique job IDs.

**Issue:** Search returns 0 results
**Cause:** Listings still indexing or embeddings failed
**Solution:** Check `has_valid_embeddings=True` in OpenSearch documents

**Issue:** High Bedrock costs
**Cause:** Not using DynamoDB cache
**Solution:** Verify cache table exists and code has caching logic in `common.py`

## Next Steps

1. ✅ **Continue indexing:** `index_local.py` is running
2. **Monitor progress:** `python /tmp/check_opensearch_count.py`
3. **Test searches:** http://34.228.111.56/
4. **Review costs:** CloudWatch → Bedrock API usage
