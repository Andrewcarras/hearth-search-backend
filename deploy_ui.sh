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

# Upload all UI files to S3 first as backup
aws s3 cp ui/search.html s3://demo-hearth-data/ui/search.html
aws s3 cp ui/admin.html s3://demo-hearth-data/ui/admin.html
aws s3 cp ui/crud.html s3://demo-hearth-data/ui/crud.html
aws s3 cp ui/test_bm25.html s3://demo-hearth-data/ui/test_bm25.html
aws s3 cp ui/test_knn_text.html s3://demo-hearth-data/ui/test_knn_text.html
aws s3 cp ui/test_knn_image.html s3://demo-hearth-data/ui/test_knn_image.html
aws s3 cp ui/multi_query_comparison.html s3://demo-hearth-data/ui/multi_query_comparison.html
aws s3 cp ui/analytics.html s3://demo-hearth-data/ui/analytics.html
aws s3 cp ui/analytics.js s3://demo-hearth-data/ui/analytics.js
aws s3 cp ui/style_detector.html s3://demo-hearth-data/ui/style_detector.html

# Deploy to EC2 via SSM
COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --comment "Deploy Hearth UI" \
    --parameters 'commands=[
        "sudo aws s3 cp s3://demo-hearth-data/ui/search.html /usr/share/nginx/html/search.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/search.html /usr/share/nginx/html/index.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/admin.html /usr/share/nginx/html/admin.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/crud.html /usr/share/nginx/html/crud.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/test_bm25.html /usr/share/nginx/html/test_bm25.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/test_knn_text.html /usr/share/nginx/html/test_knn_text.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/test_knn_image.html /usr/share/nginx/html/test_knn_image.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/multi_query_comparison.html /usr/share/nginx/html/multi_query_comparison.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/analytics.html /usr/share/nginx/html/analytics.html",
        "sudo aws s3 cp s3://demo-hearth-data/ui/analytics.js /usr/share/nginx/html/analytics.js",
        "sudo aws s3 cp s3://demo-hearth-data/ui/style_detector.html /usr/share/nginx/html/style_detector.html",
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
