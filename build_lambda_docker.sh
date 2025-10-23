#!/bin/bash
set -e

# Build Lambda packages using Docker to match Lambda runtime exactly
# This ensures we get the same binary wheels Lambda will use

echo "Building Lambda packages using Docker (matching Lambda runtime)..."

# Build for search Lambda
docker run --rm \
    -v "$PWD":/var/task \
    public.ecr.aws/lambda/python:3.11 \
    bash -c "
        pip install --target /tmp/package \
            boto3 \
            opensearch-py \
            requests-aws4auth \
            pytz \
            numpy \
            -q && \
        cp /var/task/search.py /tmp/package/ && \
        cp /var/task/common.py /tmp/package/ && \
        cp /var/task/cache_utils.py /tmp/package/ && \
        cd /tmp/package && \
        zip -qr /var/task/hearth-search-v2-docker.zip .
    "

echo "✓ Built hearth-search-v2-docker.zip"

# Build for detailed scoring Lambda
docker run --rm \
    -v "$PWD":/var/task \
    public.ecr.aws/lambda/python:3.11 \
    bash -c "
        pip install --target /tmp/package \
            boto3 \
            opensearch-py \
            requests-aws4auth \
            pytz \
            numpy \
            -q && \
        cp /var/task/search_detailed_scoring.py /tmp/package/ && \
        cp /var/task/common.py /tmp/package/ && \
        cp /var/task/cache_utils.py /tmp/package/ && \
        cd /tmp/package && \
        zip -qr /var/task/hearth-search-detailed-scoring-docker.zip .
    "

echo "✓ Built hearth-search-detailed-scoring-docker.zip"

# Deploy them
echo ""
echo "Deploying Lambdas..."

aws lambda update-function-code \
    --function-name hearth-search-v2 \
    --zip-file fileb://hearth-search-v2-docker.zip \
    2>&1 > /dev/null || \
aws lambda create-function \
    --function-name hearth-search-v2 \
    --runtime python3.11 \
    --role arn:aws:iam::692859949078:role/RealEstateListingsLambdaRole \
    --handler search.handler \
    --zip-file fileb://hearth-search-v2-docker.zip \
    --timeout 300 \
    --memory-size 1024 \
    --environment "Variables={
        OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com,
        OS_INDEX=listings,
        TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0,
        IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1,
        LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0,
        GOOGLE_PLACES_API_KEY=AIzaSyA2h1lYru9wtk3EwqbjdH46UehIqWZeUJ8
    }"

echo "✓ Deployed hearth-search-v2"

aws lambda update-function-code \
    --function-name hearth-search-detailed-scoring \
    --zip-file fileb://hearth-search-detailed-scoring-docker.zip \
    2>&1 > /dev/null || \
aws lambda create-function \
    --function-name hearth-search-detailed-scoring \
    --runtime python3.11 \
    --role arn:aws:iam::692859949078:role/RealEstateListingsLambdaRole \
    --handler search_detailed_scoring.handler \
    --zip-file fileb://hearth-search-detailed-scoring-docker.zip \
    --timeout 300 \
    --memory-size 1024 \
    --environment "Variables={
        OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com,
        OS_INDEX=listings,
        TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0,
        IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1,
        LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0,
        GOOGLE_PLACES_API_KEY=AIzaSyA2h1lYru9wtk3EwqbjdH46UehIqWZeUJ8
    }"

echo "✓ Deployed hearth-search-detailed-scoring"

# Add API Gateway permissions
aws lambda add-permission \
    --function-name hearth-search-v2 \
    --statement-id apigateway \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:us-east-1:692859949078:mwf1h5nbxe/*/*" \
    2>/dev/null || echo "  (Permission already exists)"

aws lambda add-permission \
    --function-name hearth-search-detailed-scoring \
    --statement-id apigateway \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:us-east-1:692859949078:f2o144zh31/*/*" \
    2>/dev/null || echo "  (Permission already exists)"

echo ""
echo "Done! Lambdas deployed using Docker build"
echo "Testing..."

sleep 5

curl -s -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
    -H "Content-Type: application/json" \
    -d '{"query": "modern home", "limit": 3, "index": "listings-v2"}' | \
    jq 'if .results then "✓ hearth-search-v2 WORKING!" else "✗ Error: \(.message)" end' -r

curl -s -X POST https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search/debug \
    -H "Content-Type: application/json" \
    -d '{"q": "modern home", "size": 3, "index": "listings-v2"}' | \
    jq 'if .debug_info then "✓ hearth-search-detailed-scoring WORKING!" else "✗ Error: \(.message)" end' -r
