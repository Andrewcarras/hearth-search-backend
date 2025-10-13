# AWS Deployment Guide - Step by Step

This guide will help you manually rebuild the entire AWS infrastructure from scratch.

## Current Working System (As of 2025-10-13)

✅ **Live Deployment:**
- **UI**: http://34.228.111.56/ (EC2 t2.micro with nginx)
- **API**: https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search
- **OpenSearch**: 1,358+ listings indexed (85.5% complete, indexing in progress)
- **Region**: us-east-1

✅ **What You Have:**
- Code files: `upload_listings.py`, `search.py`, `common.py`, `index_local.py`
- Requirements: `requirements.txt`
- S3 data: `s3://demo-hearth-data/murray_listings.json`
- Lambda functions: `hearth-search`, `hearth-upload-listings`
- OpenSearch domain: `hearth-opensearch`
- DynamoDB tables: `hearth-image-cache`, `hearth-indexing-jobs`

## Deployment Overview

If you need to rebuild from scratch, deploy in this order:

---

## Pre-Deployment Checklist

Before starting, gather:
- [ ] AWS Account ID
- [ ] AWS Region (was: `us-east-1`)
- [ ] Google Places API Key (for geolocation features)
- [ ] AWS CLI configured with credentials

---

## Deployment Order

Deploy in this order to avoid dependency issues:

1. IAM Role (Lambda needs permissions)
2. S3 Bucket (Lambda needs data)
3. DynamoDB Tables (Lambda needs caching)
4. OpenSearch Domain (Lambda needs search engine)
5. Lambda Functions (upload + search)
6. API Gateway (search endpoint)
7. EC2 Instance (optional UI server)

---

## 1. Create IAM Role for Lambda

### Purpose
Lambda functions need permissions to access S3, Bedrock, OpenSearch, DynamoDB, etc.

### Step-by-Step

#### 1.1 Create Role via AWS Console

1. Go to **IAM Console** → **Roles** → **Create role**
2. **Trusted entity type:** AWS service
3. **Use case:** Lambda
4. Click **Next**

#### 1.2 Attach Policies

Attach these AWS managed policies:
- ✅ `AWSLambdaBasicExecutionRole` (CloudWatch Logs)
- ✅ `AmazonS3ReadOnlyAccess` (Read from S3)
- ✅ `AmazonDynamoDBFullAccess` (Cache tables)

#### 1.3 Create Custom Inline Policy for Bedrock & OpenSearch

Policy Name: `BedrockOpenSearchAccess`

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-image-v1",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
      ]
    },
    {
      "Sid": "OpenSearchAccess",
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPut",
        "es:ESHttpPost",
        "es:ESHttpDelete",
        "es:ESHttpHead"
      ],
      "Resource": "arn:aws:es:us-east-1:YOUR_ACCOUNT_ID:domain/hearth-opensearch/*"
    },
    {
      "Sid": "LambdaSelfInvoke",
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:function:hearth-*"
    }
  ]
}
```

Replace `YOUR_ACCOUNT_ID` with your AWS account ID.

#### 1.4 Name the Role

- **Role name:** `RealEstateListingsLambdaRole`
- Click **Create role**

**Save the ARN:** `arn:aws:iam::YOUR_ACCOUNT_ID:role/RealEstateListingsLambdaRole`

---

## 2. Create S3 Bucket (if deleted)

### Purpose
Store listing data (murray_listings.json) and individual listing JSONs.

### Step-by-Step

#### 2.1 Create Bucket

```bash
aws s3 mb s3://demo-hearth-data --region us-east-1
```

OR via Console:
1. Go to **S3 Console** → **Create bucket**
2. **Bucket name:** `demo-hearth-data`
3. **Region:** `us-east-1`
4. **Block all public access:** YES (keep default)
5. Click **Create bucket**

#### 2.2 Upload Listings Data (if you have it)

```bash
# Upload main listings file
aws s3 cp murray_listings.json s3://demo-hearth-data/murray_listings.json

# If you have individual listing JSONs
aws s3 sync ./listings/ s3://demo-hearth-data/listings/
```

**Cost:** $0.023/GB/month (~$0.01/month for 279MB)

---

## 3. Create DynamoDB Tables

### Purpose
Cache image analysis, geolocation results, and S3 listing data.

### Tables Needed

1. **hearth-image-cache** - Cache Bedrock/Rekognition results
2. **hearth-geolocation-cache** - Cache Google Places results
3. **hearth-s3-listing-cache** - Cache listing JSONs from S3

### Step-by-Step (for each table)

#### 3.1 Via AWS CLI

```bash
# 1. Image Cache Table
aws dynamodb create-table \
  --table-name hearth-image-cache \
  --attribute-definitions AttributeName=image_hash,AttributeType=S \
  --key-schema AttributeName=image_hash,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# 2. Geolocation Cache Table
aws dynamodb create-table \
  --table-name hearth-geolocation-cache \
  --attribute-definitions AttributeName=location_key,AttributeType=S \
  --key-schema AttributeName=location_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# 3. S3 Listing Cache Table (with TTL)
aws dynamodb create-table \
  --table-name hearth-s3-listing-cache \
  --attribute-definitions AttributeName=zpid,AttributeType=S \
  --key-schema AttributeName=zpid,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# Enable TTL on S3 cache (1 hour expiration)
aws dynamodb update-time-to-live \
  --table-name hearth-s3-listing-cache \
  --time-to-live-specification Enabled=true,AttributeName=ttl \
  --region us-east-1
```

#### 3.2 Via AWS Console

For each table:
1. Go to **DynamoDB Console** → **Tables** → **Create table**
2. Fill in:
   - **Table name:** (see above)
   - **Partition key:** (see above)
   - **Key type:** String
3. **Table settings:** On-demand (no provisioned capacity needed)
4. Click **Create table**

**Cost:** Pay-per-request (~$0.25 per million requests, minimal for this app)

---

## 4. Create OpenSearch Domain

### Purpose
Vector search engine for semantic property search.

### Configuration

**IMPORTANT:** Use t3.small.search (smallest instance that supports kNN)

### Step-by-Step

#### 4.1 Via AWS Console (Recommended)

1. Go to **OpenSearch Service Console** → **Domains** → **Create domain**

2. **Deployment type:**
   - ✅ **Development and testing** (single node, cheaper)

3. **Domain name:** `hearth-opensearch`

4. **Engine options:**
   - **Version:** OpenSearch 3.1 (or latest 3.x)

5. **Data nodes:**
   - **Instance type:** `t3.small.search` (MINIMUM for kNN)
   - **Number of nodes:** 1
   - **EBS storage:** 10 GB (gp3)
   - **EBS IOPS:** 3000
   - **Throughput:** 125 MB/s

6. **Network:**
   - **Public access** (easier for development)

7. **Fine-grained access control:**
   - **Disable** (simpler setup)

8. **Access policy:**
   - **Domain access policy:** Configure access policy

Click **Edit** on access policy and use:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:role/RealEstateListingsLambdaRole"
      },
      "Action": "es:*",
      "Resource": "arn:aws:es:us-east-1:YOUR_ACCOUNT_ID:domain/hearth-opensearch/*"
    }
  ]
}
```

9. **Advanced options:**
   - Leave defaults

10. Click **Create**

**Wait time:** 10-15 minutes for domain to become active.

#### 4.2 Get Domain Endpoint

After creation:
1. Go to domain → **General information**
2. Copy **Domain endpoint** (e.g., `search-hearth-opensearch-xxx.us-east-1.es.amazonaws.com`)
3. **Save this endpoint** - you'll need it for Lambda environment variables

**Cost:** $0.036/hour = ~$26/month for t3.small.search

#### 4.3 Test Connection (Optional)

```bash
curl https://YOUR-OPENSEARCH-ENDPOINT:443
```

Should return OpenSearch version info.

---

## 5. Deploy Lambda Functions

### Functions to Create

1. **hearth-upload-listings** - Indexes listings to OpenSearch
2. **hearth-search** - Searches listings via API

### Prerequisites

Package the code with dependencies:

```bash
cd /Users/andrewcarras/hearth_backend_new

# Create deployment package directory
mkdir -p /tmp/lambda_package
cd /tmp/lambda_package

# Install dependencies
pip3 install -r /Users/andrewcarras/hearth_backend_new/requirements.txt --target .

# Copy Lambda code
cp /Users/andrewcarras/hearth_backend_new/upload_listings.py .
cp /Users/andrewcarras/hearth_backend_new/search.py .
cp /Users/andrewcarras/hearth_backend_new/common.py .

# Create ZIP
zip -r lambda.zip .
```

### 5.1 Deploy hearth-upload-listings

#### Via AWS Console

1. Go to **Lambda Console** → **Create function**
2. **Function name:** `hearth-upload-listings`
3. **Runtime:** Python 3.11 (or latest 3.x)
4. **Architecture:** x86_64
5. **Execution role:** Use existing role → `RealEstateListingsLambdaRole`
6. Click **Create function**

7. **Upload code:**
   - **Code source** → **Upload from** → **.zip file**
   - Upload `/tmp/lambda_package/lambda.zip`

8. **Configure:**
   - **Handler:** `upload_listings.handler`
   - **Memory:** 3008 MB (maximum)
   - **Timeout:** 15 minutes (900 seconds)
   - **Ephemeral storage:** 512 MB (default)

9. **Environment variables:**
   Click **Configuration** → **Environment variables** → **Edit**

```
AWS_REGION = us-east-1
OS_ENDPOINT = search-hearth-opensearch-xxx.us-east-1.es.amazonaws.com
OS_INDEX = listings
MAX_IMAGES = 10
EMBEDDING_IMAGE_WIDTH = 576
LOG_LEVEL = INFO
```

10. Click **Save**

#### Via AWS CLI

```bash
# Create function
aws lambda create-function \
  --function-name hearth-upload-listings \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/RealEstateListingsLambdaRole \
  --handler upload_listings.handler \
  --zip-file fileb:///tmp/lambda_package/lambda.zip \
  --timeout 900 \
  --memory-size 3008 \
  --environment Variables='{
    AWS_REGION=us-east-1,
    OS_ENDPOINT=search-hearth-opensearch-xxx.us-east-1.es.amazonaws.com,
    OS_INDEX=listings,
    MAX_IMAGES=10,
    EMBEDDING_IMAGE_WIDTH=576,
    LOG_LEVEL=INFO
  }' \
  --region us-east-1
```

### 5.2 Deploy hearth-search

Same process as above, but:
- **Function name:** `hearth-search`
- **Handler:** `search.handler`
- **Memory:** 1024 MB (less needed)
- **Timeout:** 1 minute (60 seconds)
- **Environment variables:**

```
AWS_REGION = us-east-1
OS_ENDPOINT = search-hearth-opensearch-xxx.us-east-1.es.amazonaws.com
OS_INDEX = listings
GOOGLE_PLACES_API_KEY = YOUR_GOOGLE_API_KEY
LOG_LEVEL = INFO
```

---

## 6. Create API Gateway

### Purpose
HTTP endpoint to call hearth-search Lambda function.

### Step-by-Step

#### 6.1 Create REST API

1. Go to **API Gateway Console** → **Create API**
2. Choose **REST API** (not private)
3. Click **Build**
4. **API name:** `hearth-api`
5. **Endpoint type:** Regional
6. Click **Create API**

#### 6.2 Create Resource

1. **Actions** → **Create Resource**
2. **Resource Name:** `search`
3. **Resource Path:** `/search`
4. ✅ Enable CORS
5. Click **Create Resource**

#### 6.3 Create POST Method

1. Select `/search` resource
2. **Actions** → **Create Method** → **POST**
3. **Integration type:** Lambda Function
4. ✅ Use Lambda Proxy integration
5. **Lambda Function:** `hearth-search`
6. Click **Save**
7. Click **OK** to grant API Gateway permissions

#### 6.4 Enable CORS

1. Select `/search` resource
2. **Actions** → **Enable CORS**
3. Keep defaults
4. Click **Enable CORS**

#### 6.5 Deploy API

1. **Actions** → **Deploy API**
2. **Deployment stage:** [New Stage]
3. **Stage name:** `prod`
4. Click **Deploy**

5. **Copy Invoke URL:**
   Example: `https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod`

**Your search endpoint:** `https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod/search`

**Cost:** $3.50 per million requests (minimal for dev)

---

## 7. Deploy EC2 for UI (Optional)

### Purpose
Host the property search web interface.

### Step-by-Step

#### 7.1 Launch EC2 Instance

1. Go to **EC2 Console** → **Launch Instance**
2. **Name:** `hearth-ui`
3. **AMI:** Amazon Linux 2023
4. **Instance type:** t2.micro (free tier eligible)
5. **Key pair:** Create or select existing
6. **Network settings:**
   - ✅ Allow HTTP traffic from the internet
   - ✅ Allow HTTPS traffic from the internet
7. **Configure storage:** 8 GB gp3 (default)
8. Click **Launch instance**

#### 7.2 Wait for Running State

Wait ~2 minutes, then get **Public IPv4 address** (e.g., `3.87.169.144`)

#### 7.3 Deploy UI

SSH into instance:

```bash
ssh -i your-key.pem ec2-user@YOUR_EC2_IP
```

Run deployment script:

```bash
# Download UI setup script
curl -o setup_ui.sh https://demo-hearth-data.s3.amazonaws.com/ui/setup.sh

# Make executable
chmod +x setup_ui.sh

# Run (replace with YOUR API Gateway URL)
./setup_ui.sh https://YOUR_API_GATEWAY_URL.execute-api.us-east-1.amazonaws.com/prod
```

**Access UI:** `http://YOUR_EC2_IP`

**Cost:** $0.0116/hour = ~$8.50/month (t2.micro)

---

## 8. Test the System

### 8.1 Test Indexing

Via AWS Console:
1. Go to **Lambda** → `hearth-upload-listings`
2. Click **Test**
3. **Event JSON:**

```json
{
  "bucket": "demo-hearth-data",
  "key": "murray_listings.json",
  "start": 0,
  "limit": 10
}
```

4. Click **Test**
5. Check CloudWatch Logs for success

Via AWS CLI:

```bash
aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type Event \
  --payload '{"bucket":"demo-hearth-data","key":"murray_listings.json","start":0,"limit":10}' \
  --region us-east-1 \
  response.json
```

### 8.2 Test Search

```bash
curl -X POST https://YOUR_API_GATEWAY_URL/prod/search \
  -H "Content-Type: application/json" \
  -d '{"q":"3 bedroom house with pool","size":5}'
```

Should return JSON with property results.

---

## Cost Summary

### Monthly Costs (if running 24/7)

| Service | Cost |
|---------|------|
| OpenSearch (t3.small.search) | $26.00 |
| EC2 (t2.micro) | $8.50 |
| S3 Storage | $0.01 |
| DynamoDB | $1.00 |
| API Gateway | $0.10 |
| **TOTAL** | **~$35.50/month** |

### Per-Operation Costs

| Operation | Cost |
|-----------|------|
| Index 1 listing | $0.003-0.005 |
| Search (with geolocation) | $0.17 |
| Search (without geolocation) | $0.0005 |

---

## Troubleshooting

### Lambda Can't Connect to OpenSearch

**Check:**
1. OpenSearch domain is active (green)
2. Access policy allows Lambda role
3. OS_ENDPOINT environment variable is correct (no https://)

### Lambda Timeout

**Check:**
1. Memory is 3008 MB for upload function
2. Timeout is 900 seconds (15 minutes)
3. Not processing too many listings at once (limit to 150-500)

### Search Returns No Results

**Check:**
1. OpenSearch index exists: `curl https://OS_ENDPOINT/listings`
2. Documents were indexed successfully (check CloudWatch Logs)
3. Documents have `has_valid_embeddings: true`

### High Bedrock Costs

**Likely cause:** Infinite loop in self-invocation
**Fix:** Check `upload_listings.py` lines 520-540 for self-invoke logic
**Prevention:** Add max batch count or always use `limit` parameter

---

## Post-Deployment Checklist

- [ ] IAM Role created with all permissions
- [ ] S3 bucket created with listing data
- [ ] DynamoDB tables created (3 tables)
- [ ] OpenSearch domain active and accessible
- [ ] Lambda functions deployed with correct code
- [ ] Environment variables set on both Lambdas
- [ ] API Gateway deployed with /search endpoint
- [ ] EC2 instance running (optional)
- [ ] Test indexing with 10 listings
- [ ] Test search returns results
- [ ] UI displays properties (if EC2 deployed)

---

## Next Steps After Deployment

1. **Test with small batch first** (10-50 listings)
2. **Monitor CloudWatch Logs** for any errors
3. **Check OpenSearch cluster health**
4. **Verify cost metrics** in AWS Cost Explorer
5. **Set up billing alerts** (recommended: $10, $25, $50 thresholds)
6. **Index full dataset** only after testing succeeds

---

## Quick Reference

### Important ARNs (fill in after creation)

```
IAM Role: arn:aws:iam::YOUR_ACCOUNT_ID:role/RealEstateListingsLambdaRole
OpenSearch: arn:aws:es:us-east-1:YOUR_ACCOUNT_ID:domain/hearth-opensearch
Lambda Upload: arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:function:hearth-upload-listings
Lambda Search: arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:function:hearth-search
S3 Bucket: arn:aws:s3:::demo-hearth-data
```

### Important Endpoints

```
OpenSearch: search-hearth-opensearch-xxx.us-east-1.es.amazonaws.com
API Gateway: https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod
EC2 UI: http://YOUR_EC2_IP
```

---

This guide should get you back up and running with the same architecture. Deploy step-by-step and test each component before moving to the next.
