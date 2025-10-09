#!/bin/bash
# Add Google Maps API key to Lambda function

if [ -z "$1" ]; then
    echo "Usage: ./add_google_maps_key.sh YOUR_API_KEY"
    echo ""
    echo "Get your API key from: https://console.cloud.google.com/apis/credentials"
    echo ""
    echo "Example:"
    echo "  ./add_google_maps_key.sh AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    exit 1
fi

API_KEY="$1"

echo "Adding Google Maps API key to hearth-search Lambda..."

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
    GOOGLE_MAPS_API_KEY=$API_KEY
  }" > /dev/null

echo "✓ API key added successfully!"
echo ""
echo "Testing gym search..."
sleep 5

# Test the search
aws lambda invoke \
  --function-name hearth-search \
  --region us-east-1 \
  --payload '{"q": "homes near a gym", "size": 5}' \
  --cli-binary-format raw-in-base64-out \
  response_test.json > /dev/null 2>&1

RESULTS=$(cat response_test.json | python3 -c "import json, sys; d=json.load(sys.stdin); body=json.loads(d['body']); print(body['total'])" 2>/dev/null || echo "0")

echo "Results found: $RESULTS homes"
echo ""

if [ "$RESULTS" -gt 0 ]; then
    echo "✅ SUCCESS! Google Maps API is working!"
    echo ""
    echo "Check logs to see gym location:"
    echo "  aws logs tail /aws/lambda/hearth-search --since 1m | grep 'Geocoded POI'"
else
    echo "⚠️  Still getting 0 results. This may be because:"
    echo "  1. Re-indexing is still in progress (only ~400 listings indexed)"
    echo "  2. No homes within 5km of the found gym"
    echo "  3. API key needs Places API enabled"
    echo ""
    echo "Check logs:"
    echo "  aws logs tail /aws/lambda/hearth-search --since 1m"
fi

rm -f response_test.json
