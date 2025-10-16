#!/bin/bash
# Deploy Hearth UI to EC2 instance
# Usage: ./deploy_ui.sh <instance-id>

set -e

INSTANCE_ID=${1}
if [ -z "$INSTANCE_ID" ]; then
    echo "Usage: ./deploy_ui.sh <instance-id>"
    exit 1
fi

echo "Deploying UI to instance $INSTANCE_ID..."

# Upload to S3 first as backup
aws s3 cp ui/search.html s3://demo-hearth-data/ui/search.html

# Deploy to EC2 via SSM
COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --comment "Deploy Hearth UI" \
    --parameters 'commands=[
        "sudo aws s3 cp s3://demo-hearth-data/ui/search.html /usr/share/nginx/html/index.html",
        "sudo nginx -s reload",
        "echo UI deployed successfully"
    ]' \
    --query 'Command.CommandId' \
    --output text)

echo "Deployment command sent: $COMMAND_ID"
echo "Waiting for completion..."

sleep 3
aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --query 'StandardOutputContent' \
    --output text

echo "✓ Deployment complete!"
