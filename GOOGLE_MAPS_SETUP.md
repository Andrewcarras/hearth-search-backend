# Google Maps API Setup

## Why We Need This

The current geocoding system uses OpenStreetMap Nominatim, which is **very limited** and often fails to find specific businesses like gyms, restaurants, or shopping centers.

**Google Maps Places API** provides:
- ✅ Real, up-to-date business locations
- ✅ Accurate gym, restaurant, store locations
- ✅ Better POI coverage for "near X" queries
- ✅ Fast and reliable

## Cost

Google Maps Places API pricing:
- **Free tier**: $200/month credit (enough for ~40,000 POI lookups per month)
- **After free tier**: $0.032 per search request

For our use case (real estate search with occasional "near gym" queries):
- **Expected cost**: $0-5/month (well within free tier)
- Each "homes near gym" query = 1 API call

## Setup Instructions

### Step 1: Get Google Maps API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable **Places API (New)** or **Places API**
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > API Key**
6. Copy the API key (starts with `AIza...`)

### Step 2: Restrict the API Key (Security)

**Important**: Restrict the key to prevent unauthorized use!

1. Click on the API key you just created
2. Under **API restrictions**:
   - Select "Restrict key"
   - Check only: **Places API** and **Places API (New)**
3. Under **Application restrictions** (optional):
   - None (Lambda calls from AWS IPs which vary)
   - Or set IP restrictions if you know your NAT gateway IPs
4. Save

### Step 3: Add to Lambda

Run this command with your API key:

```bash
# Replace YOUR_API_KEY_HERE with your actual key
aws lambda update-function-configuration \
  --function-name hearth-search \
  --region us-east-1 \
  --environment "Variables={
    OS_INDEX=listings,
    TEXT_DIM=1024,
    IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1,
    IMAGE_DIM=1024,
    OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com,
    LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0,
    LOG_LEVEL=INFO,
    TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0,
    GOOGLE_MAPS_API_KEY=YOUR_API_KEY_HERE
  }"
```

### Step 4: Deploy Updated Code

```bash
# Package and deploy
cd /tmp/lambda_package
cp ~/hearth_backend_new/common.py .
zip -r ~/hearth_backend_new/google_maps_integration.zip .

# Deploy
cd ~/hearth_backend_new
aws lambda update-function-code \
  --function-name hearth-search \
  --zip-file fileb://google_maps_integration.zip \
  --region us-east-1
```

### Step 5: Test

```bash
# Test gym search
curl -X POST "http://54.163.59.108/search" \
  -H "Content-Type: application/json" \
  -d '{"q": "homes near a gym", "size": 10}'
```

Check logs to see Google Maps API in action:
```bash
aws logs tail /aws/lambda/hearth-search --follow
```

You should see: `Geocoded POI 'gym' to {'lat': 40.xxx, 'lon': -111.xxx} (name: Gold's Gym)`

## Fallback Behavior

**Without API Key**: Falls back to Nominatim (free but limited, often returns 0 results)
**With API Key**: Uses Google Maps (accurate, finds real businesses)

The code is already implemented to gracefully fall back if the key is not set, so the system won't break without it - it just won't find gyms/restaurants as well.

## Alternative: AWS Location Service

If you prefer to stay within AWS ecosystem:

```bash
# Enable AWS Location Service (similar pricing to Google)
aws location create-place-index \
  --index-name hearth-poi-index \
  --data-source Esri \
  --region us-east-1
```

Then update `common.py` to use AWS Location Service instead of Google Maps.

## Summary

**Without Google Maps**: "homes near a gym" returns 0 results ❌
**With Google Maps**: Finds actual gyms and returns homes within distance ✅

The free tier ($200/month) is more than enough for a demo/production app with moderate usage.
