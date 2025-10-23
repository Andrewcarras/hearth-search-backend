#!/bin/bash

API_ID="f2o144zh31"
FUNCTION_ARN="arn:aws:lambda:us-east-1:692859949078:function:hearth-production-analytics"
REGION="us-east-1"

echo "========================================="
echo "Setting up Production Analytics API Routes"
echo "========================================="
echo ""
echo "API ID: $API_ID"
echo "Function: hearth-production-analytics"
echo ""

# Create integration
echo "Creating Lambda integration..."
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id $API_ID \
    --integration-type AWS_PROXY \
    --integration-uri $FUNCTION_ARN \
    --payload-format-version 2.0 \
    --query 'IntegrationId' \
    --output text \
    --region $REGION)

echo "✓ Integration created: $INTEGRATION_ID"
echo ""

# Add Lambda permission for API Gateway to invoke
echo "Adding Lambda invoke permission..."
aws lambda add-permission \
    --function-name hearth-production-analytics \
    --statement-id apigateway-production-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:692859949078:$API_ID/*/*" \
    --region $REGION 2>/dev/null

echo "✓ Permission added"
echo ""

# Define routes
routes=(
    "POST /production/log-search"
    "POST /production/log-feedback"
    "POST /production/report-issue"
    "POST /production/update-session"
    "POST /production/end-session"
    "GET /production/analytics/overview"
    "GET /production/analytics/searches"
    "GET /production/analytics/feedback"
    "GET /production/analytics/sessions"
    "GET /production/analytics/session/{session_id}"
    "GET /production/analytics/properties/top-clicked"
    "GET /production/analytics/properties/top-rated"
    "GET /production/analytics/issues"
    "POST /production/analytics/issue/{issue_id}/status"
    "GET /production/analytics/export/feedback"
    "GET /production/analytics/export/searches"
    "OPTIONS /production/{proxy+}"
)

echo "Creating routes..."
for route in "${routes[@]}"; do
    method=$(echo $route | awk '{print $1}')
    path=$(echo $route | awk '{print $2}')

    echo "  Creating: $method $path"

    aws apigatewayv2 create-route \
        --api-id $API_ID \
        --route-key "$method $path" \
        --target "integrations/$INTEGRATION_ID" \
        --region $REGION > /dev/null
done

echo "✓ All routes created"
echo ""

# Update CORS settings
echo "Updating CORS settings..."
aws apigatewayv2 update-api \
    --api-id $API_ID \
    --cors-configuration '{
        "AllowOrigins": ["*"],
        "AllowMethods": ["GET", "POST", "OPTIONS"],
        "AllowHeaders": ["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
        "MaxAge": 86400
    }' \
    --region $REGION > /dev/null

echo "✓ CORS updated"
echo ""

echo "========================================="
echo "✓ API Setup Complete!"
echo "========================================="
echo ""
echo "API Endpoint: https://$API_ID.execute-api.$REGION.amazonaws.com"
echo ""
echo "Available routes:"
echo "  POST   /production/log-search"
echo "  POST   /production/log-feedback"
echo "  POST   /production/report-issue"
echo "  POST   /production/update-session"
echo "  POST   /production/end-session"
echo "  GET    /production/analytics/overview"
echo "  GET    /production/analytics/searches"
echo "  GET    /production/analytics/feedback"
echo "  GET    /production/analytics/sessions"
echo "  GET    /production/analytics/session/{id}"
echo "  GET    /production/analytics/properties/top-clicked"
echo "  GET    /production/analytics/properties/top-rated"
echo "  GET    /production/analytics/issues"
echo "  POST   /production/analytics/issue/{id}/status"
echo "  GET    /production/analytics/export/feedback"
echo "  GET    /production/analytics/export/searches"
echo ""
echo "Test endpoint:"
echo "curl https://$API_ID.execute-api.$REGION.amazonaws.com/production/analytics/overview"
