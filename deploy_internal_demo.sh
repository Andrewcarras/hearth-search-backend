#!/bin/bash

# Deploy ALL UI files to INTERNAL DEMO ONLY (http://54.234.198.245)
# DO NOT USE FOR PUBLIC DEMO (http://54.226.26.203)
# This updates the navigation menus across all pages

INTERNAL_INSTANCE_ID="i-03e61f15aa312c332"

echo "========================================="
echo "Deploying to INTERNAL DEMO ONLY"
echo "========================================="
echo ""
echo "Internal Demo: http://54.234.198.245/"
echo "Public Demo: http://54.226.26.203/ (NOT TOUCHED)"
echo ""

# Upload all UI files to S3
echo "Uploading UI files to S3..."
aws s3 cp ui/search.html s3://demo-hearth-data/ui/search.html
aws s3 cp ui/admin.html s3://demo-hearth-data/ui/admin.html
aws s3 cp ui/crud.html s3://demo-hearth-data/ui/crud.html
aws s3 cp ui/test_bm25.html s3://demo-hearth-data/ui/test_bm25.html
aws s3 cp ui/test_knn_text.html s3://demo-hearth-data/ui/test_knn_text.html
aws s3 cp ui/test_knn_image.html s3://demo-hearth-data/ui/test_knn_image.html
aws s3 cp ui/analytics.html s3://demo-hearth-data/ui/analytics.html
aws s3 cp ui/analytics.js s3://demo-hearth-data/ui/analytics.js
aws s3 cp ui/style_detector.html s3://demo-hearth-data/ui/style_detector.html
aws s3 cp ui/multi_query_comparison.html s3://demo-hearth-data/ui/multi_query_comparison.html

echo ""
echo "Deploying to internal server..."

# Deploy to internal EC2 via SSM
COMMAND_ID=$(aws ssm send-command \
  --instance-ids "$INTERNAL_INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Deploy All UI Files with Fixed Navigation" \
  --parameters 'commands=[
    "sudo aws s3 cp s3://demo-hearth-data/ui/search.html /usr/share/nginx/html/index.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/search.html /usr/share/nginx/html/search.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/admin.html /usr/share/nginx/html/admin.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/crud.html /usr/share/nginx/html/crud.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/test_bm25.html /usr/share/nginx/html/test_bm25.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/test_knn_text.html /usr/share/nginx/html/test_knn_text.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/test_knn_image.html /usr/share/nginx/html/test_knn_image.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/analytics.html /usr/share/nginx/html/analytics.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/analytics.js /usr/share/nginx/html/analytics.js",
    "sudo aws s3 cp s3://demo-hearth-data/ui/style_detector.html /usr/share/nginx/html/style_detector.html",
    "sudo aws s3 cp s3://demo-hearth-data/ui/multi_query_comparison.html /usr/share/nginx/html/multi_query_comparison.html",
    "sudo nginx -s reload || sudo systemctl reload nginx",
    "echo All UI files deployed successfully"
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
echo "All UI files deployed with consistent navigation:"
echo "  - Main Search"
echo "  - BM25 Test"
echo "  - kNN Text Test"
echo "  - kNN Image Test"
echo "  - Admin Lookup"
echo "  - CRUD Manager"
echo "  - Analytics Dashboard (updated label)"
echo "  - Style Detector (added)"
echo ""
echo "Removed: Public Testing link"
echo ""
echo "Visit: http://54.234.198.245/"
echo ""
