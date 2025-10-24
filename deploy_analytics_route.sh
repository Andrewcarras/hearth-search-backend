#!/bin/bash

# Deploy /log-search-quality route to API Gateway
# This script adds the missing analytics route to the hearth-api Gateway

set -e

API_ID="mqgsb4xb2g"
REGION="us-east-1"
LAMBDA_ARN="arn:aws:lambda:us-east-1:692859949078:function:hearth-production-analytics"

echo "🚀 Adding /log-search-quality route to API Gateway $API_ID..."

# Get root resource ID
ROOT_ID=$(aws apigateway get-resources --rest-api-id $API_ID --region $REGION --query 'items[?path==`/`].id' --output text)
echo "Root resource ID: $ROOT_ID"

# Create /production resource first
echo "Creating /production resource..."
PROD_RESPONSE=$(aws apigateway create-resource \
  --rest-api-id $API_ID \
  --region $REGION \
  --parent-id $ROOT_ID \
  --path-part "production" \
  2>&1) || {
    echo "Production resource may already exist, fetching..."
    PROD_ID=$(aws apigateway get-resources --rest-api-id $API_ID --region $REGION --query 'items[?path==`/production`].id' --output text)
  }

if [ -z "$PROD_ID" ]; then
  PROD_ID=$(echo $PROD_RESPONSE | jq -r '.id')
fi

echo "Production resource ID: $PROD_ID"

# Create /production/log-search-quality resource
echo "Creating /production/log-search-quality resource..."
RESOURCE_RESPONSE=$(aws apigateway create-resource \
  --rest-api-id $API_ID \
  --region $REGION \
  --parent-id $PROD_ID \
  --path-part "log-search-quality" \
  2>&1) || {
    # Resource might already exist
    echo "Resource may already exist, fetching existing..."
    RESOURCE_ID=$(aws apigateway get-resources --rest-api-id $API_ID --region $REGION --query 'items[?path==`/production/log-search-quality`].id' --output text)
  }

if [ -z "$RESOURCE_ID" ]; then
  RESOURCE_ID=$(echo $RESOURCE_RESPONSE | jq -r '.id')
fi

echo "Resource ID: $RESOURCE_ID"

# Create POST method
echo "Creating POST method..."
aws apigateway put-method \
  --rest-api-id $API_ID \
  --region $REGION \
  --resource-id $RESOURCE_ID \
  --http-method POST \
  --authorization-type NONE \
  --no-api-key-required 2>/dev/null || echo "Method may already exist"

# Set up Lambda integration
echo "Setting up Lambda integration..."
aws apigateway put-integration \
  --rest-api-id $API_ID \
  --region $REGION \
  --resource-id $RESOURCE_ID \
  --http-method POST \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations" 2>/dev/null || echo "Integration may already exist"

# Add OPTIONS method for CORS
echo "Adding CORS OPTIONS method..."
aws apigateway put-method \
  --rest-api-id $API_ID \
  --region $REGION \
  --resource-id $RESOURCE_ID \
  --http-method OPTIONS \
  --authorization-type NONE \
  --no-api-key-required 2>/dev/null || echo "OPTIONS method may already exist"

# Set up OPTIONS integration (CORS preflight)
aws apigateway put-integration \
  --rest-api-id $API_ID \
  --region $REGION \
  --resource-id $RESOURCE_ID \
  --http-method OPTIONS \
  --type MOCK \
  --request-templates '{"application/json": "{\"statusCode\": 200}"}' 2>/dev/null || echo "OPTIONS integration may already exist"

# Set OPTIONS response
aws apigateway put-method-response \
  --rest-api-id $API_ID \
  --region $REGION \
  --resource-id $RESOURCE_ID \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters '{"method.response.header.Access-Control-Allow-Headers":true,"method.response.header.Access-Control-Allow-Methods":true,"method.response.header.Access-Control-Allow-Origin":true}' 2>/dev/null || echo "OPTIONS response may already exist"

aws apigateway put-integration-response \
  --rest-api-id $API_ID \
  --region $REGION \
  --resource-id $RESOURCE_ID \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters '{"method.response.header.Access-Control-Allow-Headers":"'\''Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'\''","method.response.header.Access-Control-Allow-Methods":"'\''POST,OPTIONS'\''","method.response.header.Access-Control-Allow-Origin":"'\''*'\''"}' 2>/dev/null || echo "OPTIONS integration response may already exist"

# Grant Lambda permission to be invoked by API Gateway
echo "Granting Lambda invoke permission to API Gateway..."
aws lambda add-permission \
  --function-name hearth-production-analytics \
  --region $REGION \
  --statement-id apigateway-log-search-quality-$(date +%s) \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:692859949078:$API_ID/*/POST/production/log-search-quality" 2>/dev/null || echo "Permission may already exist"

# Deploy to prod stage
echo "Deploying to prod stage..."
aws apigateway create-deployment \
  --rest-api-id $API_ID \
  --region $REGION \
  --stage-name prod

echo "✅ Route deployed successfully!"
echo ""
echo "Endpoint: https://$API_ID.execute-api.$REGION.amazonaws.com/prod/production/log-search-quality"
echo ""
echo "Test with:"
echo "curl -X POST https://$API_ID.execute-api.$REGION.amazonaws.com/prod/production/log-search-quality -H 'Content-Type: application/json' -d '{\"session_id\":\"test\",\"rating\":5}'"
