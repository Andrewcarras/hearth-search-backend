#!/bin/bash

# Deploy password-protected internal demo to http://54.234.198.245

INTERNAL_INSTANCE_ID="i-03e61f15aa312c332"
SEARCH_UI="ui/search.html"

echo "========================================="
echo "Deploying Internal Demo with Password Protection"
echo "========================================="
echo ""
echo "Server: http://54.234.198.245/"
echo "Password: hearth-internal-pass"
echo ""

# Upload to S3
echo "Uploading search.html to S3..."
aws s3 cp "$SEARCH_UI" s3://demo-hearth-data/ui/internal_demo_search.html

# Deploy to internal EC2 via SSM
echo "Deploying to internal server..."
COMMAND_ID=$(aws ssm send-command \
  --instance-ids "$INTERNAL_INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Deploy Password-Protected Internal Demo" \
  --parameters 'commands=[
    "sudo aws s3 cp s3://demo-hearth-data/ui/internal_demo_search.html /usr/share/nginx/html/index.html",
    "sudo nginx -s reload || sudo systemctl reload nginx",
    "echo Internal demo deployed successfully"
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
echo "========================================="
echo "✓ Deployment Complete!"
echo "========================================="
echo ""
echo "Internal Demo: http://54.234.198.245/"
echo "Password: hearth-internal-pass"
echo ""
echo "This password protects the ENTIRE internal demo environment."
echo "All navigation pages (BM25 Test, kNN Tests, Admin, CRUD, Analytics)"
echo "will be accessible after authentication."
