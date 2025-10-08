#!/bin/bash
#
# Monitor upload progress in real-time
#

echo "Monitoring upload progress (Ctrl+C to exit)..."
echo ""

while true; do
    # Clear screen
    clear

    # Get current batch
    CURRENT=$(grep "Processing batch starting at" upload_progress.log | tail -1 | grep -o "at [0-9]*" | grep -o "[0-9]*")

    if [ -z "$CURRENT" ]; then
        echo "Upload not started yet..."
    else
        # Calculate progress
        TOTAL=1588
        PROCESSED=$CURRENT
        PERCENT=$((PROCESSED * 100 / TOTAL))

        echo "═══════════════════════════════════════════════════════"
        echo "  HEARTH BACKEND UPLOAD PROGRESS"
        echo "═══════════════════════════════════════════════════════"
        echo ""
        echo "  Current batch:    $CURRENT / $TOTAL"
        echo "  Progress:         $PERCENT%"
        echo ""

        # Progress bar
        FILLED=$((PERCENT / 2))
        printf "  ["
        for i in $(seq 1 50); do
            if [ $i -le $FILLED ]; then
                printf "█"
            else
                printf "░"
            fi
        done
        printf "] $PERCENT%%\n"
        echo ""

        # Show last few lines
        echo "  Recent activity:"
        echo "  ────────────────────────────────────────────────────"
        tail -8 upload_progress.log | sed 's/^/  /'
        echo ""

        # Check if complete
        if [ $CURRENT -ge $TOTAL ]; then
            echo "✓ Upload complete!"
            break
        fi
    fi

    sleep 3
done
