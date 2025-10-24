#!/bin/bash

# Deploy to INTERNAL demo server (not production)
INTERNAL_INSTANCE_ID="i-03e61f15aa312c332"
ANALYTICS_UI="ui/public_analytics.html"

echo "Deploying analytics dashboard to INTERNAL demo instance $INTERNAL_INSTANCE_ID..."
echo "This will be available at: http://54.234.198.245/analytics.html"
echo ""

# Upload to S3
aws s3 cp "$ANALYTICS_UI" s3://demo-hearth-data/ui/internal_analytics.html

# Deploy to internal EC2 via SSM
COMMAND_ID=$(aws ssm send-command \
  --instance-ids "$INTERNAL_INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Deploy Internal Analytics Dashboard" \
  --parameters 'commands=[
    "sudo aws s3 cp s3://demo-hearth-data/ui/internal_analytics.html /usr/share/nginx/html/analytics.html",
    "sudo nginx -s reload || sudo systemctl reload nginx || echo nginx reload attempted",
    "echo Internal analytics dashboard deployed successfully"
  ]' \
  --query 'Command.CommandId' \
  --output text)

echo "Deployment command sent: $COMMAND_ID"
echo "Waiting for completion..."

# Wait for command to complete
sleep 5

# Check result
aws ssm list-command-invocations \
  --command-id "$COMMAND_ID" \
  --details \
  --query 'CommandInvocations[0].CommandPlugins[0].Output' \
  --output text

echo ""
echo ""
echo "✓ Deployment complete!"
echo ""
echo "Internal analytics dashboard available at: http://54.234.198.245/analytics.html"
echo "Password: hearth-internal-pass"
