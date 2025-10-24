# Deployment Guide

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [SCRIPTS.md](SCRIPTS.md), [AWS_INFRASTRUCTURE.md](AWS_INFRASTRUCTURE.md)

This guide covers deploying all Hearth Search components to production.

---

## Table of Contents

1. [Lambda Deployment](#lambda-deployment)
2. [Production UI Deployment](#production-ui-deployment)
3. [Internal Testing UI Deployment](#internal-testing-ui-deployment)
4. [Data Upload](#data-upload)
5. [Environment Variables](#environment-variables)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)

---

## Lambda Deployment

### Search Lambda (hearth-search-v2)

Deploy the main search Lambda using the deployment script:

```bash
./deploy_lambda.sh
```

**What it does**:
- Packages Lambda code and dependencies
- Creates deployment.zip
- Updates hearth-search-v2 Lambda function
- Sets environment variables

**Critical Configuration** (deploy_lambda.sh:17):
```bash
OS_INDEX=listings-v2  # MUST be listings-v2 (NOT "listings")
```

**Environment Variables Set**:
- `OS_HOST`: OpenSearch endpoint
- `OS_INDEX`: `listings-v2` (critical!)
- `BEDROCK_MODEL`: Claude model for embeddings
- `CLIP_MODEL`: CLIP model for image embeddings

**Verification**:
```bash
# Check Lambda configuration
aws lambda get-function-configuration --function-name hearth-search-v2 | grep OS_INDEX

# Should output: "OS_INDEX": "listings-v2"
```

### CRUD Lambda (hearth-crud-listings)

The CRUD Lambda is deployed separately for update/create/delete operations.

```bash
# Deploy CRUD Lambda
./deploy_crud_api.sh
```

**Endpoint**: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`

**Operations**:
- `POST /listings` - Create new property
- `PATCH /listings/{zpid}` - Update property
- `DELETE /listings/{zpid}` - Delete property

### Analytics Lambda (hearth-production-analytics)

Handles search logging, ratings, and feedback.

**Deployment**:
```bash
# Package and deploy
zip -r analytics.zip production_analytics.py
aws lambda update-function-code \
  --function-name hearth-production-analytics \
  --zip-file fileb://analytics.zip
```

---

## Production UI Deployment

**Critical**: Production UI is hosted on EC2/nginx, NOT S3.

### Deploy to Production

```bash
./deploy_production_ui.sh
```

**What it does**:
- Copies ui/production.html to EC2 instance (i-044e6ddd7ab8353f9)
- Deploys to `/var/www/html/index.html`
- Nginx serves at http://54.226.26.203/

**Manual Deployment** (if script fails):
```bash
# SSH to EC2
ssh -i your-key.pem ec2-user@54.226.26.203

# Copy file
scp -i your-key.pem ui/production.html ec2-user@54.226.26.203:/var/www/html/index.html

# Restart nginx (if needed)
sudo systemctl restart nginx
```

**DO NOT** deploy production UI to S3. It will not work.

---

## Internal Testing UI Deployment

The internal testing UI is deployed to S3.

```bash
# Deploy to S3
aws s3 cp ui/testing.html s3://your-testing-bucket/index.html --cache-control "max-age=0"
```

**Features**:
- Index selection (listings-v2 only - "listings" removed)
- Analytics view
- Direct search API testing

---

## Data Upload

### Full Data Upload

Upload property listings from Zillow JSON data:

```bash
python3 upload_listings.py slc_listings.json
```

**What it does**:
- Reads Zillow JSON data
- Extracts fields (livingArea, lotSize, price, etc.)
- Generates embeddings via Claude Vision API
- Classifies architecture styles (2-tier)
- Uploads to OpenSearch listings-v2 index
- Handles errors and retries

**Process**:
1. Validates JSON structure
2. Extracts property fields
3. Calls Claude Vision API for image analysis
4. Generates text embedding
5. Generates image embedding
6. Classifies architecture style
7. Uploads to OpenSearch

**Time**: ~30-60 seconds per property (3,902 properties = ~2 hours)

### Partial Data Upload

Upload specific batches:

```bash
# Upload first 100 properties
python3 upload_listings.py slc_listings.json --limit 100
```

### Fix Specific Fields

Fix livingArea field for existing properties:

```bash
python3 fix_living_area.py slc_listings.json 50
```

**Parameters**:
- `slc_listings.json`: Source Zillow data
- `50`: Batch size (requests per batch)

**Uses CRUD API** to update properties without regenerating embeddings.

---

## Environment Variables

### Search Lambda (hearth-search-v2)

```bash
OS_HOST=your-opensearch-endpoint.us-east-1.es.amazonaws.com
OS_INDEX=listings-v2  # CRITICAL: Must be listings-v2
BEDROCK_MODEL=us.anthropic.claude-3-haiku-20240307-v1:0
CLIP_MODEL=openai/clip-vit-base-patch32
```

### CRUD Lambda (hearth-crud-listings)

```bash
OS_HOST=your-opensearch-endpoint.us-east-1.es.amazonaws.com
OS_INDEX=listings-v2
BEDROCK_MODEL=us.anthropic.claude-3-haiku-20240307-v1:0
```

### Analytics Lambda (hearth-production-analytics)

```bash
DYNAMODB_REGION=us-east-1
SEARCH_LOGS_TABLE=SearchQueryLogs
QUALITY_FEEDBACK_TABLE=SearchQualityFeedback
RATINGS_TABLE=PropertyRatings
```

---

## Verification

### Verify Lambda Deployment

```bash
# Check Lambda exists and configuration
aws lambda get-function-configuration --function-name hearth-search-v2

# Check environment variables
aws lambda get-function-configuration --function-name hearth-search-v2 \
  --query 'Environment.Variables' --output json

# Test search
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=modern+homes"
```

### Verify Production UI

```bash
# Check if accessible
curl -I http://54.226.26.203/

# Should return: HTTP/1.1 200 OK
```

Open in browser: http://54.226.26.203/

### Verify Data Upload

```bash
# Check index document count
aws opensearch describe-domain --domain-name hearth-search | grep listings-v2

# Search for a property
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=modern"
```

### Verify CRUD API

```bash
# Test update endpoint
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/12345?index=listings-v2" \
  -H "Content-Type: application/json" \
  -d '{"updates": {"price": 500000}, "options": {"preserve_embeddings": true}}'
```

---

## Troubleshooting

### Lambda Deployment Fails

**Error**: "No such file or directory: deployment.zip"
**Fix**: Ensure you're in the project root directory

**Error**: "Function not found: hearth-search-v2"
**Fix**: Create Lambda function first via AWS Console

**Error**: "Insufficient permissions"
**Fix**: Ensure IAM role has Lambda:UpdateFunctionCode permission

### Production UI Not Updating

**Issue**: Changes not visible after deployment
**Cause**: Deployed to S3 instead of EC2

**Fix**:
```bash
# Use correct deployment script
./deploy_production_ui.sh

# NOT: aws s3 cp ui/production.html s3://...
```

**Issue**: UI shows old version
**Fix**: Clear browser cache, check EC2 file was updated

### Search Returning No Results

**Issue**: All searches return empty results
**Cause**: Lambda using wrong index

**Fix**:
```bash
# Update Lambda environment variable
aws lambda update-function-configuration \
  --function-name hearth-search-v2 \
  --environment 'Variables={OS_INDEX=listings-v2,OS_HOST=your-endpoint,...}'
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more issues.

---

## Deployment Checklist

Before deploying to production:

- [ ] Backup current Lambda code
- [ ] Test changes locally/staging
- [ ] Verify OS_INDEX=listings-v2 in deploy_lambda.sh
- [ ] Check all environment variables correct
- [ ] Run deployment script
- [ ] Verify Lambda updated (check timestamp)
- [ ] Test search functionality
- [ ] Check CloudWatch logs for errors
- [ ] Test CRUD operations (if updated)
- [ ] Test Production UI (if updated)
- [ ] Monitor for 15 minutes post-deployment

---

## Rollback Procedure

If deployment causes issues:

### Rollback Lambda

```bash
# List versions
aws lambda list-versions-by-function --function-name hearth-search-v2

# Rollback to previous version
aws lambda update-alias \
  --function-name hearth-search-v2 \
  --name prod \
  --function-version <previous-version>
```

### Rollback UI

```bash
# Restore from backup
scp -i your-key.pem backup/production.html ec2-user@54.226.26.203:/var/www/html/index.html
```

---

## Production Deployment Flow

```
1. Code Changes
    ↓
2. Test Locally
    ↓
3. Update deploy_lambda.sh (verify OS_INDEX=listings-v2)
    ↓
4. Run ./deploy_lambda.sh
    ↓
5. Verify Lambda Updated
    ↓
6. Test Search API
    ↓
7. Check CloudWatch Logs
    ↓
8. Monitor for Issues
    ↓
9. (If Issues) Rollback
```

---

## Quick Commands Reference

```bash
# Deploy search Lambda
./deploy_lambda.sh

# Deploy production UI
./deploy_production_ui.sh

# Upload data
python3 upload_listings.py slc_listings.json

# Fix livingArea field
python3 fix_living_area.py slc_listings.json 50

# Test search
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=test"

# Check Lambda config
aws lambda get-function-configuration --function-name hearth-search-v2

# View Lambda logs
aws logs tail /aws/lambda/hearth-search-v2 --follow
```
