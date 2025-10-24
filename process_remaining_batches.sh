#!/bin/bash

# Process all remaining batches (800-3195)
# Each batch is 100 properties

START_BATCH=9
CURRENT_OFFSET=900

echo "=========================================="
echo "BATCH PROCESSOR - REMAINING PROPERTIES"
echo "=========================================="
echo "Starting from batch $START_BATCH (offset $CURRENT_OFFSET)"
echo ""

for batch in {9..32}; do
    offset=$((batch * 100))
    log_file="/tmp/batch_$(printf '%03d' $batch)_${offset}.log"

    echo "=========================================="
    echo "Processing Batch $batch ($((offset-100))-$offset)"
    echo "Log: $log_file"
    echo "=========================================="

    # Run the batch
    echo "yes" | python -u update_architecture_fast.py --start $((offset-100)) --limit 100 --clear-cache > "$log_file" 2>&1

    # Check if successful
    if grep -q "✅ Update complete!" "$log_file"; then
        echo "✅ Batch $batch completed successfully"

        # Extract key stats
        updated=$(grep "updated:" "$log_file" | awk '{print $2}')
        cost=$(grep "Actual cost:" "$log_file" | awk '{print $3}')

        echo "   Updated: $updated properties"
        echo "   Cost: $cost"
        echo ""
    else
        echo "❌ Batch $batch failed or incomplete"
        echo "Check log: $log_file"
        # Continue anyway - don't exit
    fi

    # Brief pause between batches
    sleep 5
done

echo ""
echo "=========================================="
echo "ALL BATCHES COMPLETE!"
echo "=========================================="
echo "Processed batches 8-32"
echo ""
echo "Total summary:"
for log in /tmp/batch_0*.log; do
    if grep -q "Actual cost:" "$log" 2>/dev/null; then
        grep "Actual cost:" "$log"
    fi
done | awk '{sum+=$3} END {print "Total cost: $" sum}'
