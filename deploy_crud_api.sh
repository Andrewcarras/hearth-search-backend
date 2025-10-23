#!/bin/bash
set -e

echo "======================================"
echo "Deploying Hearth CRUD API"
echo "======================================"
echo ""

# Configuration
API_ID="mwf1h5nbxe"
FUNCTION_NAME="hearth-crud-listings"
LAMBDA_ROLE="arn:aws:iam::692859949078:role/RealEstateListingsLambdaRole"
REGION="us-east-1"
STAGE="prod"

# Step 1: Build Lambda package
echo "Step 1: Building Lambda package..."
echo "-----------------------------------"

# Create temporary build directory
BUILD_DIR=$(mktemp -d)
echo "Build directory: $BUILD_DIR"

# Copy source files
cp crud_listings.py "$BUILD_DIR/lambda_function.py"
cp common.py "$BUILD_DIR/"
cp cache_utils.py "$BUILD_DIR/" 2>/dev/null || echo "  (cache_utils.py not found, skipping)"

# Install dependencies in build directory
cd "$BUILD_DIR"
pip install -q -t . boto3 opensearch-py requests-aws4auth pytz numpy requests 2>&1 | grep -v "Requirement already satisfied" || true

# Create zip package
zip -qr /tmp/crud_listings.zip .
cd -

echo "✓ Package created: /tmp/crud_listings.zip"
ls -lh /tmp/crud_listings.zip
echo ""

# Step 2: Create or update Lambda function
echo "Step 2: Deploying Lambda function..."
echo "-----------------------------------"

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Lambda function exists, updating code..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb:///tmp/crud_listings.zip \
        --region "$REGION" \
        --output json > /tmp/lambda_update.json

    echo "✓ Lambda code updated"

    # Wait for update to complete
    echo "  Waiting for update to complete..."
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

else
    echo "Creating new Lambda function..."
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime python3.11 \
        --role "$LAMBDA_ROLE" \
        --handler lambda_function.update_listing_handler \
        --zip-file fileb:///tmp/crud_listings.zip \
        --timeout 30 \
        --memory-size 512 \
        --region "$REGION" \
        --environment Variables="{
            OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com,
            OS_INDEX=listings-v2,
            TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0,
            IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1,
            LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
        }" \
        --output json > /tmp/lambda_create.json

    echo "✓ Lambda function created"

    # Wait for function to be active
    echo "  Waiting for function to be active..."
    aws lambda wait function-active --function-name "$FUNCTION_NAME" --region "$REGION"
fi

echo ""

# Step 3: Create API Gateway integration
echo "Step 3: Setting up API Gateway integration..."
echo "-----------------------------------"

FUNCTION_ARN="arn:aws:lambda:$REGION:692859949078:function:$FUNCTION_NAME"

# Check if integration exists
EXISTING_INTEGRATION=$(aws apigatewayv2 get-integrations \
    --api-id "$API_ID" \
    --region "$REGION" \
    --query "Items[?IntegrationUri=='$FUNCTION_ARN'].IntegrationId" \
    --output text)

if [ -n "$EXISTING_INTEGRATION" ]; then
    echo "Integration already exists: $EXISTING_INTEGRATION"
    INTEGRATION_ID="$EXISTING_INTEGRATION"
else
    echo "Creating new integration..."
    INTEGRATION_ID=$(aws apigatewayv2 create-integration \
        --api-id "$API_ID" \
        --integration-type AWS_PROXY \
        --integration-uri "$FUNCTION_ARN" \
        --payload-format-version 2.0 \
        --region "$REGION" \
        --query 'IntegrationId' \
        --output text)

    echo "✓ Integration created: $INTEGRATION_ID"
fi

echo ""

# Step 4: Add Lambda permission for API Gateway
echo "Step 4: Adding Lambda invoke permission..."
echo "-----------------------------------"

aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id apigateway-crud-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:692859949078:$API_ID/*/*" \
    --region "$REGION" 2>&1 | grep -v "ResourceConflictException" || echo "  (Permission already exists)"

echo "✓ Permission configured"
echo ""

# Step 5: Create API Gateway routes
echo "Step 5: Creating API Gateway routes..."
echo "-----------------------------------"

# Define routes
declare -a ROUTES=(
    "PATCH /$STAGE/listings/{zpid}"
    "POST /$STAGE/listings"
    "DELETE /$STAGE/listings/{zpid}"
)

for ROUTE_KEY in "${ROUTES[@]}"; do
    echo "  Creating route: $ROUTE_KEY"

    # Check if route exists
    EXISTING_ROUTE=$(aws apigatewayv2 get-routes \
        --api-id "$API_ID" \
        --region "$REGION" \
        --query "Items[?RouteKey=='$ROUTE_KEY'].RouteId" \
        --output text)

    if [ -n "$EXISTING_ROUTE" ]; then
        echo "    Route already exists: $EXISTING_ROUTE"
    else
        aws apigatewayv2 create-route \
            --api-id "$API_ID" \
            --route-key "$ROUTE_KEY" \
            --target "integrations/$INTEGRATION_ID" \
            --region "$REGION" \
            --output json > /dev/null
        echo "    ✓ Created"
    fi
done

echo ""
echo "======================================"
echo "✓ CRUD API Deployment Complete!"
echo "======================================"
echo ""
echo "Available endpoints:"
echo "  Base URL: https://$API_ID.execute-api.$REGION.amazonaws.com/$STAGE"
echo ""
echo "  PATCH /listings/{zpid}  - Update listing"
echo "  POST  /listings         - Create listing"
echo "  DELETE /listings/{zpid} - Delete listing"
echo ""
echo "Lambda function: $FUNCTION_NAME"
echo "Integration ID: $INTEGRATION_ID"
echo ""

# Cleanup
rm -rf "$BUILD_DIR"
echo "✓ Cleaned up temporary files"
echo ""
