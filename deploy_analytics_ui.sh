#!/bin/bash

INSTANCE_ID="i-044e6ddd7ab8353f9"
ANALYTICS_UI="ui/public_analytics.html"

echo "Deploying analytics dashboard to instance $INSTANCE_ID..."

# Upload to S3
aws s3 cp "$ANALYTICS_UI" s3://demo-hearth-data/ui/public_analytics.html

# Deploy to EC2 via SSM
COMMAND_ID=$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Deploy Analytics Dashboard" \
  --parameters 'commands=[
    "sudo aws s3 cp s3://demo-hearth-data/ui/public_analytics.html /usr/share/nginx/html/analytics.html",
    "sudo nginx -s reload",
    "echo Analytics dashboard deployed successfully"
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
echo "Analytics dashboard available at: http://54.226.26.203/analytics.html"
