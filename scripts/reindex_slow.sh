#!/bin/bash
# Slower re-indexing with only 3 parallel Lambda instances to avoid Bedrock throttling
# This will process all 1588 listings with less API pressure

echo "Starting slower re-indexing of 1588 listings across 3 Lambda instances..."
echo "This approach avoids Bedrock throttling by reducing parallel API calls"
echo ""

# Split into 3 batches of ~530 listings each
for i in {0..2}; do
  start=$((i * 530))
  end=$((start + 530))
  if [ $end -gt 1588 ]; then
    end=1588
  fi
  count=$((end - start))

  echo "Launching batch $((i+1))/3: listings $start-$((end-1)) ($count listings)"

  aws lambda invoke \
    --function-name hearth-upload-listings \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"bucket\": \"demo-hearth-data\", \"key\": \"murray_listings.json\", \"start\": $start, \"limit\": $count}" \
    --region us-east-1 \
    --invocation-type Event \
    /tmp/slow_batch_${i}.json &

  # Add small delay between launches to stagger API calls
  sleep 2
done

wait
echo ""
echo "✓ All 3 batches launched with staggered timing!"
echo "Expected completion: ~20-30 minutes"
echo ""
echo "This will re-index ALL listings, updating the 127 that failed with throttling"
echo "Monitor progress: ./scripts/monitor_reindex.sh"
