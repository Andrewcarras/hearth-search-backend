#!/bin/bash
set -e

# Hearth Lambda Deployment Script
# Usage: ./deploy_lambda.sh [search|debug|both]

LAMBDA_ROLE="arn:aws:iam::692859949078:role/RealEstateListingsLambdaRole"
REGION="us-east-1"
RUNTIME="python3.11"
TIMEOUT=300
MEMORY=1024
NUMPY_LAYER="arn:aws:lambda:us-east-1:692859949078:layer:scikit-numpy:2"

# Environment variables for both Lambdas
ENV_VARS="Variables={
    OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com,
    OS_INDEX=listings,
    TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0,
    IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1,
    LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0,
    GOOGLE_PLACES_API_KEY=AIzaSyA2h1lYru9wtk3EwqbjdH46UehIqWZeUJ8
}"

echo "======================================"
echo "Hearth Lambda Deployment Script"
echo "======================================"

# Function to build Lambda package
build_package() {
    local function_name=$1
    local handler_file=$2
    local build_dir="/tmp/lambda_build_${function_name}"
    local zip_file="${function_name}.zip"

    echo ""
    echo "Building package for ${function_name}..."

    # Clean build directory
    rm -rf "$build_dir"
    mkdir -p "$build_dir"

    # Install dependencies (including numpy in package - layers are broken)
    echo "  Installing dependencies..."
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
    cp search_logger.py "$build_dir/" 2>/dev/null || true  # Only needed for search Lambda
    cp architecture_style_mappings.py "$build_dir/" 2>/dev/null || true  # Architecture style mappings

    # Clean up cache files
    find "$build_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$build_dir" -type f -name "*.pyc" -delete 2>/dev/null || true

    # Create zip
    echo "  Creating zip package..."
    cd "$build_dir"
    zip -qr "${OLDPWD}/${zip_file}" .
    cd "$OLDPWD"

    local size=$(du -h "${zip_file}" | cut -f1)
    echo "  ✓ Package created: ${zip_file} (${size})"

    # Clean up build directory
    rm -rf "$build_dir"
}

# Function to create Lambda
create_lambda() {
    local function_name=$1
    local handler=$2
    local zip_file=$3

    echo ""
    echo "Creating Lambda function: ${function_name}..."

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

    echo "  ✓ Lambda function created successfully"
}

# Function to update Lambda
update_lambda() {
    local function_name=$1
    local zip_file=$2

    echo ""
    echo "Updating Lambda function: ${function_name}..."

    aws lambda update-function-code \
        --function-name "${function_name}" \
        --zip-file "fileb://${zip_file}" \
        --output json \
        | jq '{FunctionName, CodeSize, LastUpdateStatus}'

    echo "  Waiting for update to complete..."
    aws lambda wait function-updated --function-name "${function_name}"

    echo "  ✓ Lambda function updated successfully"
}

# Function to check if Lambda exists
lambda_exists() {
    aws lambda get-function --function-name "$1" &>/dev/null
}

# Deploy production search Lambda
deploy_search() {
    echo ""
    echo "======================================"
    echo "Deploying hearth-search-v2"
    echo "======================================"

    build_package "hearth-search-v2" "search.py"

    if lambda_exists "hearth-search-v2"; then
        update_lambda "hearth-search-v2" "hearth-search-v2.zip"
    else
        create_lambda "hearth-search-v2" "search.lambda_handler" "hearth-search-v2.zip"
    fi

    rm -f hearth-search-v2.zip
}

# Deploy detailed scoring Lambda
deploy_detailed_scoring() {
    echo ""
    echo "======================================"
    echo "Deploying hearth-search-detailed-scoring"
    echo "======================================"

    build_package "hearth-search-detailed-scoring" "search_detailed_scoring.py"

    if lambda_exists "hearth-search-detailed-scoring"; then
        update_lambda "hearth-search-detailed-scoring" "hearth-search-detailed-scoring.zip"
    else
        create_lambda "hearth-search-detailed-scoring" "search_detailed_scoring.handler" "hearth-search-detailed-scoring.zip"
    fi

    rm -f hearth-search-detailed-scoring.zip
}

# Main deployment logic
case "${1:-both}" in
    search)
        deploy_search
        ;;
    scoring|detailed)
        deploy_detailed_scoring
        ;;
    both)
        deploy_search
        deploy_detailed_scoring
        ;;
    *)
        echo "Usage: $0 [search|scoring|both]"
        exit 1
        ;;
esac

echo ""
echo "======================================"
echo "Deployment Complete!"
echo "======================================"
