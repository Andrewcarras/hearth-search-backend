#!/bin/bash
#
# Upload all listings in batches of 10 to avoid Lambda timeouts
# Each batch processes embeddings which takes time

BUCKET="demo-hearth-data"
KEY="murray_listings.json"
BATCH_SIZE=10
START=0
TOTAL=1588

echo "Starting upload of $TOTAL listings in batches of $BATCH_SIZE..."

while [ $START -lt $TOTAL ]; do
    echo ""
    echo "=== Processing batch starting at $START ==="

    aws lambda invoke \
        --function-name hearth-upload-listings \
        --cli-binary-format raw-in-base64-out \
        --payload "{\"bucket\":\"$BUCKET\",\"key\":\"$KEY\",\"start\":$START,\"limit\":$BATCH_SIZE}" \
        --region us-east-1 \
        response_batch_$START.json

    # Check if successful
    if [ $? -eq 0 ]; then
        # Extract processed count (parse nested JSON body)
        PROCESSED=$(cat response_batch_$START.json | jq -r '.body | fromjson | .batch.processed // 0' 2>/dev/null)
        echo "✓ Processed $PROCESSED listings"

        # Move to next batch
        START=$((START + BATCH_SIZE))

        # Brief pause to avoid rate limits
        sleep 2
    else
        echo "✗ Batch failed, retrying..."
        sleep 5
    fi
done

echo ""
echo "=== Upload complete! ==="
echo "Total listings uploaded: $TOTAL"
echo ""
echo "Now test search with:"
echo "aws lambda invoke --function-name hearth-search --cli-binary-format raw-in-base64-out --payload '{\"q\":\"house\",\"size\":10}' search_result.json --region us-east-1 && cat search_result.json | jq"
