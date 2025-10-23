#!/bin/bash

FUNCTION_NAME="hearth-production-analytics"
ROLE_ARN="arn:aws:iam::692859949078:role/lambda-dynamodb-role"

echo "======================================"
echo "Deploying Production Analytics Lambda"
echo "======================================"
echo ""

# Create deployment package
echo "Creating deployment package..."
mkdir -p /tmp/production-analytics-package
cp production_analytics.py /tmp/production-analytics-package/lambda_function.py

cd /tmp/production-analytics-package
zip -r ../production-analytics.zip .
cd -

echo "✓ Package created"
echo ""

# Check if function exists
FUNCTION_EXISTS=$(aws lambda get-function --function-name $FUNCTION_NAME 2>&1)

if echo "$FUNCTION_EXISTS" | grep -q "ResourceNotFoundException"; then
    echo "Creating new Lambda function..."
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime python3.11 \
        --role $ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb:///tmp/production-analytics.zip \
        --timeout 30 \
        --memory-size 512 \
        --environment "Variables={SESSION_TIMEOUT_MINUTES=30}" \
        --region us-east-1

    echo "✓ Function created"
else
    echo "Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb:///tmp/production-analytics.zip \
        --region us-east-1

    echo "✓ Function updated"
fi

echo ""
echo "Waiting for function to be ready..."
aws lambda wait function-updated --function-name $FUNCTION_NAME --region us-east-1

echo ""
echo "======================================"
echo "✓ Deployment Complete!"
echo "======================================"
echo ""
echo "Function: $FUNCTION_NAME"
echo "Region: us-east-1"
echo ""
echo "Next steps:"
echo "1. Set up API Gateway"
echo "2. Configure CORS"
echo "3. Test endpoints"
