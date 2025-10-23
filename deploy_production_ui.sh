#!/bin/bash

INSTANCE_ID="i-044e6ddd7ab8353f9"
PRODUCTION_UI="ui/production.html"

echo "Deploying production UI to instance $INSTANCE_ID..."

# Upload to S3
aws s3 cp "$PRODUCTION_UI" s3://demo-hearth-data/ui/production.html

# Deploy to EC2 via SSM
COMMAND_ID=$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Deploy Production UI" \
  --parameters 'commands=[
    "sudo aws s3 cp s3://demo-hearth-data/ui/production.html /usr/share/nginx/html/index.html",
    "sudo nginx -s reload",
    "echo Production UI deployed successfully"
  ]' \
  --query 'Command.CommandId' \
  --output text)

echo "Deployment command sent: $COMMAND_ID"
echo "Waiting for completion..."

# Wait for command to complete
sleep 5

# Check result
aws ssm get-command-invocation \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --query 'StandardOutputContent' \
  --output text

echo ""
echo "✓ Deployment complete!"
echo ""
echo "Production UI available at: http://54.226.26.203/"
