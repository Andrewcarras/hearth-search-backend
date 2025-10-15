#!/bin/bash
# Index N random listings from murray_listings.json
# Usage: ./scripts/index_listings.sh <count>

set -e

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <count>"
    echo "Example: $0 50"
    exit 1
fi

COUNT=$1

echo "📦 Selecting $COUNT random unique listings from murray_listings.json..."

# Download murray_listings and select N random
aws s3 cp s3://demo-hearth-data/murray_listings.json /tmp/murray_listings.json > /dev/null 2>&1

python3 << EOFPY
import json
import random

# Load all listings
with open('/tmp/murray_listings.json') as f:
    all_listings = json.load(f)

print(f"Total available: {len(all_listings)} listings")

if $COUNT > len(all_listings):
    print(f"ERROR: Only {len(all_listings)} available")
    exit(1)

# Select random
selected = random.sample(all_listings, $COUNT)

# Save
output = {"listings": selected}
with open('/tmp/selected_listings.json', 'w') as f:
    json.dump(output, f)

print(f"✅ Selected $COUNT random listings")
print(f"\nSample zpids:")
for i, l in enumerate(selected[:5], 1):
    print(f"  {i}. {l.get('zpid')} - {l.get('address', {}).get('streetAddress', 'N/A')}")
EOFPY

# Upload to S3
S3_KEY="batch_${COUNT}_listings_$(date +%s).json"
aws s3 cp /tmp/selected_listings.json "s3://demo-hearth-data/$S3_KEY" > /dev/null

echo ""
echo "📤 Uploaded to: s3://demo-hearth-data/$S3_KEY"
echo ""
echo "🚀 Invoking Lambda to index $COUNT listings..."

# Invoke Lambda
cat > /tmp/lambda_payload.json << EOF
{"bucket":"demo-hearth-data","key":"$S3_KEY"}
EOF

aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type Event \
  --payload file:///tmp/lambda_payload.json \
  --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  /tmp/lambda_response.json > /dev/null

echo "✅ Lambda invoked successfully"
echo ""1
echo "⏱️  Estimated time: ~$((COUNT * 2)) minutes"
echo ""
echo "📊 Monitor progress:"
echo "   aws logs tail /aws/lambda/hearth-upload-listings --follow --region us-east-1"
echo ""
echo "🔍 Check indexed count:"
echo "   curl -s -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"q\":\"homes\",\"size\":100}' | jq '.total'"
