#!/bin/bash
# Deploy updated UI to EC2

set -e

INSTANCE_IP="54.163.59.108"
KEY_FILE="hearth-demo-key.pem"

echo "=== Deploying Updated UI to EC2 ==="
echo ""

# Check if key file exists
if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key file $KEY_FILE not found"
    echo "Attempting to retrieve instance without SSH..."
    
    # Try to get instance ID and use Systems Manager
    INSTANCE_ID=$(aws ec2 describe-instances \
        --filters "Name=ip-address,Values=$INSTANCE_IP" "Name=instance-state-name,Values=running" \
        --query "Reservations[0].Instances[0].InstanceId" \
        --output text \
        --region us-east-1 2>/dev/null)
    
    if [ "$INSTANCE_ID" != "None" ] && [ -n "$INSTANCE_ID" ]; then
        echo "Found instance: $INSTANCE_ID"
        echo "Using Systems Manager to update files..."
        
        # Copy app.py
        APP_CONTENT=$(cat app.py | base64)
        aws ssm send-command \
            --instance-ids "$INSTANCE_ID" \
            --document-name "AWS-RunShellScript" \
            --parameters "commands=[\"echo '$APP_CONTENT' | base64 -d > /opt/hearth-ui/app.py\"]" \
            --region us-east-1 >/dev/null
        
        # Copy index.html
        HTML_CONTENT=$(cat templates/index.html | base64)
        aws ssm send-command \
            --instance-ids "$INSTANCE_ID" \
            --document-name "AWS-RunShellScript" \
            --parameters "commands=[\"echo '$HTML_CONTENT' | base64 -d > /opt/hearth-ui/templates/index.html\", \"systemctl restart hearth-ui\"]" \
            --region us-east-1 >/dev/null
        
        echo "✓ Files updated via Systems Manager"
        echo "✓ Service restarted"
        exit 0
    else
        echo "Could not find instance. Trying direct file upload via AWS CLI..."
        # Fall through to alternative method
    fi
fi

# Alternative: Direct SSH if key exists
if [ -f "$KEY_FILE" ]; then
    echo "Step 1: Copying files to EC2..."
    scp -i "$KEY_FILE" -o StrictHostKeyChecking=no \
        app.py ec2-user@$INSTANCE_IP:/tmp/app.py
    
    scp -i "$KEY_FILE" -o StrictHostKeyChecking=no \
        templates/index.html ec2-user@$INSTANCE_IP:/tmp/index.html
    
    echo "✓ Files copied"
    echo ""
    echo "Step 2: Moving files and restarting service..."
    
    ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no ec2-user@$INSTANCE_IP << 'ENDSSH'
sudo cp /tmp/app.py /opt/hearth-ui/app.py
sudo cp /tmp/index.html /opt/hearth-ui/templates/index.html
sudo systemctl restart hearth-ui
sudo systemctl status hearth-ui --no-pager
ENDSSH
    
    echo ""
    echo "=========================================="
    echo "✓ UI Updated Successfully!"
    echo "=========================================="
    echo ""
    echo "View the updated UI at:"
    echo "  http://$INSTANCE_IP"
    echo ""
else
    echo "Error: No SSH key and no alternative method available"
    exit 1
fi
