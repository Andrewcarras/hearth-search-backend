#!/bin/bash
#
# Start the Flask UI for testing Hearth search
#

echo "Starting Hearth Search Test UI..."
echo ""
echo "The UI will be available at:"
echo "  http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

source .venv/bin/activate
python3 app.py
