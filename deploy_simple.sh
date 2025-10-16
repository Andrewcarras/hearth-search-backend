#!/bin/bash
set -e

# Ultra-simple Lambda deployment - mimic the working 36MB Lambda
# Python 3.13, numpy in package, NO cleanup, NO layers

ROLE="arn:aws:iam::692859949078:role/RealEstateListingsLambdaRole"

echo "Building hearth-search-v2..."
rm -rf /tmp/lambda_search
mkdir /tmp/lambda_search
cd /tmp/lambda_search

pip3.11 install boto3 opensearch-py requests-aws4auth pytz -t . --quiet || \
pip3 install boto3 opensearch-py requests-aws4auth pytz -t . --quiet

cp ~/hearth_backend_new/search.py .
cp ~/hearth_backend_new/common.py .
cp ~/hearth_backend_new/cache_utils.py .

zip -qr ~/hearth_backend_new/search.zip .

echo "Building hearth-search-detailed-scoring..."
rm -rf /tmp/lambda_scoring
mkdir /tmp/lambda_scoring
cd /tmp/lambda_scoring

pip3.11 install boto3 opensearch-py requests-aws4auth pytz -t . --quiet || \
pip3 install boto3 opensearch-py requests-aws4auth pytz -t . --quiet

cp ~/hearth_backend_new/search_detailed_scoring.py .
cp ~/hearth_backend_new/common.py .
cp ~/hearth_backend_new/cache_utils.py .

zip -qr ~/hearth_backend_new/scoring.zip .

cd ~/hearth_backend_new

echo "Deploying..."

# Create or update search Lambda
aws lambda create-function \
  --function-name hearth-search-v2 \
  --runtime python3.11 \
  --role $ROLE \
  --handler search.handler \
  --zip-file fileb://search.zip \
  --timeout 300 \
  --memory-size 1024 \
  --environment "Variables={OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com,OS_INDEX=listings,TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0,IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1,LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0,GOOGLE_PLACES_API_KEY=AIzaSyA2h1lYru9wtk3EwqbjdH46UehIqWZeUJ8}" \
  2>/dev/null || \
aws lambda update-function-code --function-name hearth-search-v2 --zip-file fileb://search.zip

# Create or update scoring Lambda
aws lambda create-function \
  --function-name hearth-search-detailed-scoring \
  --runtime python3.11 \
  --role $ROLE \
  --handler search_detailed_scoring.handler \
  --zip-file fileb://scoring.zip \
  --timeout 300 \
  --memory-size 1024 \
  --environment "Variables={OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com,OS_INDEX=listings,TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0,IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1,LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0,GOOGLE_PLACES_API_KEY=AIzaSyA2h1lYru9wtk3EwqbjdH46UehIqWZeUJ8}" \
  2>/dev/null || \
aws lambda update-function-code --function-name hearth-search-detailed-scoring --zip-file fileb://scoring.zip

# API Gateway permissions
aws lambda add-permission --function-name hearth-search-v2 --statement-id api --action lambda:InvokeFunction --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:us-east-1:692859949078:mwf1h5nbxe/*/*" 2>/dev/null || true
aws lambda add-permission --function-name hearth-search-detailed-scoring --statement-id api --action lambda:InvokeFunction --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:us-east-1:692859949078:f2o144zh31/*/*" 2>/dev/null || true

echo "Done!"
ls -lh search.zip scoring.zip
