#!/bin/bash
# Parallel re-indexing script - splits 1588 listings into 10 concurrent batches

echo "Starting parallel re-indexing of 1588 listings across 10 Lambda instances..."

# Split into 10 batches of ~159 listings each
for i in {0..9}; do
  start=$((i * 159))
  echo "Launching batch $((i+1))/10: listings $start-$((start+159))"
  
  aws lambda invoke \
    --function-name hearth-upload-listings \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"bucket\": \"demo-hearth-data\", \"key\": \"murray_listings.json\", \"start\": $start, \"limit\": 159}" \
    --region us-east-1 \
    --invocation-type Event \
    /tmp/batch_${i}.json &
done

wait
echo "✓ All 10 parallel batches launched!"
echo "Expected completion: ~1-2 hours (vs 10-12 hours serial)"
echo ""
echo "Monitor progress:"
echo "  aws logs tail /aws/lambda/hearth-upload-listings --follow"
