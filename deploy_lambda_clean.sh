#!/bin/bash
set -e

# Clean Lambda Deployment Script - NO LAYERS, NUMPY IN PACKAGE
# This script properly packages numpy by removing source/build artifacts

LAMBDA_ROLE="arn:aws:iam::692859949078:role/RealEstateListingsLambdaRole"
REGION="us-east-1"
RUNTIME="python3.11"
TIMEOUT=300
MEMORY=1024

ENV_VARS="Variables={
    OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com,
    OS_INDEX=listings,
    TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0,
    IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1,
    LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0,
    GOOGLE_PLACES_API_KEY=AIzaSyA2h1lYru9wtk3EwqbjdH46UehIqWZeUJ8
}"

echo "======================================"
echo "Clean Lambda Deployment (No Layers)"
echo "======================================"

build_clean_package() {
    local function_name=$1
    local handler_file=$2
    local build_dir="/tmp/lambda_clean_${function_name}"
    local zip_file="${function_name}.zip"

    echo ""
    echo "Building ${function_name}..."

    # Clean build directory
    rm -rf "$build_dir"
    mkdir -p "$build_dir"

    # Install dependencies
    echo "  Installing Python dependencies..."
    python3.11 -m pip install --target "$build_dir" \
        boto3 \
        opensearch-py \
        requests-aws4auth \
        pytz \
        numpy \
        --quiet 2>&1 || \
    pip3 install --target "$build_dir" \
        boto3 \
        opensearch-py \
        requests-aws4auth \
        pytz \
        numpy \
        --quiet

    # Copy source files
    echo "  Copying source files..."
    cp "${handler_file}" "$build_dir/"
    cp common.py "$build_dir/"
    cp cache_utils.py "$build_dir/"

    # Just clean cache files - don't touch source
    echo "  Cleaning cache files..."
    find "$build_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$build_dir" -type f -name "*.pyc" -delete 2>/dev/null || true

    # Create zip package
    echo "  Creating zip package..."
    cd "$build_dir"
    zip -qr "${OLDPWD}/${zip_file}" .
    cd "$OLDPWD"

    local size=$(du -h "${zip_file}" | cut -f1)
    echo "  ✓ Package created: ${zip_file} (${size})"

    # Clean up build directory
    rm -rf "$build_dir"
}

create_lambda() {
    local function_name=$1
    local handler=$2
    local zip_file=$3

    echo ""
    echo "Creating Lambda: ${function_name}..."

    aws lambda create-function \
        --function-name "${function_name}" \
        --runtime "${RUNTIME}" \
        --role "${LAMBDA_ROLE}" \
        --handler "${handler}" \
        --zip-file "fileb://${zip_file}" \
        --timeout ${TIMEOUT} \
        --memory-size ${MEMORY} \
        --environment "${ENV_VARS}" \
        --region "${REGION}" \
        --output json \
        | jq '{FunctionName, Runtime, CodeSize, State}'

    echo "  Waiting for function to be active..."
    aws lambda wait function-active --function-name "${function_name}"

    echo "  ✓ Lambda created successfully"
}

add_api_gateway_permission() {
    local function_name=$1
    local api_id=$2

    echo "  Adding API Gateway permission..."
    aws lambda add-permission \
        --function-name "${function_name}" \
        --statement-id apigateway-invoke \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:${REGION}:692859949078:${api_id}/*/*" \
        --output json > /dev/null 2>&1 || echo "  (Permission may already exist)"
}

# Deploy main search Lambda
echo ""
echo "======================================"
echo "Deploying hearth-search-v2"
echo "======================================"

build_clean_package "hearth-search-v2" "search.py"
create_lambda "hearth-search-v2" "search.handler" "hearth-search-v2.zip"
add_api_gateway_permission "hearth-search-v2" "mwf1h5nbxe"
rm -f hearth-search-v2.zip

# Deploy detailed scoring Lambda
echo ""
echo "======================================"
echo "Deploying hearth-search-detailed-scoring"
echo "======================================"

build_clean_package "hearth-search-detailed-scoring" "search_detailed_scoring.py"
create_lambda "hearth-search-detailed-scoring" "search_detailed_scoring.handler" "hearth-search-detailed-scoring.zip"
add_api_gateway_permission "hearth-search-detailed-scoring" "f2o144zh31"
rm -f hearth-search-detailed-scoring.zip

echo ""
echo "======================================"
echo "Deployment Complete!"
echo "======================================"
echo ""
echo "Testing Lambdas..."
echo ""

# Test main search
echo -n "Testing hearth-search-v2: "
result=$(aws lambda invoke \
    --function-name hearth-search-v2 \
    --payload '{"body": "{\"query\": \"test\", \"limit\": 1, \"index\": \"listings-v2\"}"}' \
    /tmp/test_response.json 2>&1 > /dev/null && cat /tmp/test_response.json | jq -r 'if .statusCode then "SUCCESS" else "FAILED" end' 2>/dev/null || echo "FAILED")
echo "$result"

# Test detailed scoring
echo -n "Testing hearth-search-detailed-scoring: "
result=$(aws lambda invoke \
    --function-name hearth-search-detailed-scoring \
    --payload '{"body": "{\"q\": \"test\", \"size\": 1, \"index\": \"listings-v2\"}"}' \
    /tmp/test_response2.json 2>&1 > /dev/null && cat /tmp/test_response2.json | jq -r 'if .statusCode then "SUCCESS" else "FAILED" end' 2>/dev/null || echo "FAILED")
echo "$result"

echo ""
echo "Done!"
