#!/bin/bash
#
# Update Flask UI on existing EC2 instance to use API Gateway
#

set -e

REGION="us-east-1"

echo "=== Updating EC2 UI to use API Gateway Endpoint ==="
echo ""

# Find running EC2 instance
echo "Step 1: Finding EC2 instance..."
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=hearth-demo-ui" "Name=instance-state-name,Values=running" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text \
    --region $REGION 2>/dev/null)

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
    echo "❌ No running EC2 instance found with tag Name=hearth-demo-ui"
    echo ""
    echo "To deploy a new instance, run:"
    echo "  cd scripts && ./deploy_ec2.sh"
    exit 1
fi

PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --region $REGION \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo "✓ Found instance: $INSTANCE_ID"
echo "✓ Public IP: $PUBLIC_IP"
echo ""

# Use SSM Session Manager or SSH to update the app
echo "Step 2: Updating Flask app code..."

# Create updated app.py
cat > /tmp/app.py << 'EOF'
from flask import Flask, render_template, request, jsonify
import requests
import json

app = Flask(__name__)

# Use API Gateway endpoint (production, always up-to-date)
API_ENDPOINT = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('q', '').strip()
    size = int(data.get('size', 20))

    filters = {}
    if data.get('price_min'):
        filters['price_min'] = int(data['price_min'])
    if data.get('price_max'):
        filters['price_max'] = int(data['price_max'])
    if data.get('beds_min'):
        filters['beds_min'] = int(data['beds_min'])
    if data.get('baths_min'):
        filters['baths_min'] = int(data['baths_min'])

    payload = {'q': query, 'size': size}
    if filters:
        payload['filters'] = filters

    try:
        # Use API Gateway endpoint for latest backend features
        response = requests.post(
            API_ENDPOINT,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
EOF

# Try SSM Session Manager first (no SSH key needed)
echo "Attempting to update via AWS Systems Manager..."
COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/hearth-ui",
        "cat > app.py << '\''APPEOF'\''",
        "from flask import Flask, render_template, request, jsonify",
        "import requests",
        "import json",
        "",
        "app = Flask(__name__)",
        "",
        "# Use API Gateway endpoint (production, always up-to-date)",
        "API_ENDPOINT = '\''https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search'\''",
        "",
        "@app.route('\''/'\'') ",
        "def index():",
        "    return render_template('\''index.html'\'')",
        "",
        "@app.route('\''/search'\'', methods=['\''POST'\''])",
        "def search():",
        "    data = request.json",
        "    query = data.get('\''q'\'', '\'\'').strip()",
        "    size = int(data.get('\''size'\'', 20))",
        "",
        "    filters = {}",
        "    if data.get('\''price_min'\''):",
        "        filters['\''price_min'\''] = int(data['\''price_min'\''])",
        "    if data.get('\''price_max'\''):",
        "        filters['\''price_max'\''] = int(data['\''price_max'\''])",
        "    if data.get('\''beds_min'\''):",
        "        filters['\''beds_min'\''] = int(data['\''beds_min'\''])",
        "    if data.get('\''baths_min'\''):",
        "        filters['\''baths_min'\''] = int(data['\''baths_min'\''])",
        "",
        "    payload = {'\''q'\'': query, '\''size'\'': size}",
        "    if filters:",
        "        payload['\''filters'\''] = filters",
        "",
        "    try:",
        "        response = requests.post(API_ENDPOINT, json=payload, headers={'\''Content-Type'\'': '\''application/json'\''}, timeout=30)",
        "        response.raise_for_status()",
        "        return jsonify(response.json())",
        "    except requests.exceptions.RequestException as e:",
        "        return jsonify({'\''error'\'': str(e)}), 500",
        "    except Exception as e:",
        "        return jsonify({'\''error'\'': str(e)}), 500",
        "",
        "if __name__ == '\''__main__'\'':",
        "    app.run(host='\''0.0.0.0'\'', port=80, debug=False)",
        "APPEOF",
        "python3.11 -m pip install requests",
        "systemctl restart hearth-ui",
        "sleep 2",
        "systemctl status hearth-ui --no-pager"
    ]' \
    --region $REGION \
    --output text \
    --query 'Command.CommandId' 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$COMMAND_ID" ]; then
    echo "✓ Command sent via SSM: $COMMAND_ID"
    echo ""
    echo "Waiting for command to complete..."
    sleep 5

    aws ssm get-command-invocation \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --region $REGION \
        --query 'StandardOutputContent' \
        --output text 2>/dev/null || echo "Command still running..."

    echo ""
    echo "✓ Update complete!"
else
    echo "⚠️  SSM not available. Using alternative method..."
    echo ""
    echo "Manual update required. SSH into the instance and run:"
    echo ""
    echo "  ssh -i hearth-demo-key.pem ec2-user@$PUBLIC_IP"
    echo ""
    echo "Then run these commands:"
    echo ""
    echo "  sudo su -"
    echo "  cd /opt/hearth-ui"
    echo "  cat > app.py << 'EOF'"
    cat /tmp/app.py
    echo "EOF"
    echo "  python3.11 -m pip install requests"
    echo "  systemctl restart hearth-ui"
    echo ""
fi

echo ""
echo "=========================================="
echo "✓ UI Updated to use API Gateway"
echo "=========================================="
echo ""
echo "Instance: $INSTANCE_ID"
echo "URL: http://$PUBLIC_IP"
echo ""
echo "Changes:"
echo "  ✓ Now using API Gateway endpoint"
echo "  ✓ Always gets latest backend features"
echo "  ✓ Better performance and reliability"
echo ""
echo "Test the UI:"
echo "  curl -s http://$PUBLIC_IP/ | grep -o '<title>.*</title>'"
echo ""
