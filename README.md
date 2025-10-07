# 🏠 Hearth Search Backend

**AI-Powered Multimodal Real Estate Search Engine**

Hearth Search is a sophisticated backend system that enables natural language search across real estate listings using **image recognition**, **semantic text matching**, and **keyword search**. Built on AWS serverless architecture, it combines multiple AI models to deliver highly relevant property search results.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Lambda Functions](#lambda-functions)
- [Setup & Deployment](#setup--deployment)
- [Usage Examples](#usage-examples)
- [API Reference](#api-reference)
- [Development Tools](#development-tools)
- [Cost Estimates](#cost-estimates)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

Hearth Search allows users to search for properties using natural language queries like:
- *"Show me a white house with a pool under 500k"*
- *"3 bedroom modern home with hardwood floors"*
- *"Luxury condo with mountain views"*

The system analyzes both **property images** (using computer vision) and **text descriptions** (using NLP) to return the most relevant results, ranked using advanced fusion algorithms.

### How It Works

```
┌─────────────────┐
│  User Query     │ "White house with pool under 500k"
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Lambda: hearth-search                              │
│  ┌──────────────────────────────────────────────┐  │
│  │ 1. Parse query with Claude LLM               │  │
│  │    → Extract: features, filters, must-haves  │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │ 2. Run 3 parallel searches in OpenSearch:    │  │
│  │    • BM25 (keyword matching)                 │  │
│  │    • kNN text (semantic similarity)          │  │
│  │    • kNN image (visual similarity)           │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │ 3. Fuse results with RRF algorithm           │  │
│  │    → Boost listings matching "must-haves"    │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Ranked Results │ [House1, House2, House3...]
└─────────────────┘
```

### Data Pipeline

```
┌──────────────┐
│ Zillow Data  │ (JSON files with listings)
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  Lambda: hearth-upload                               │
│  ┌────────────────────────────────────────────────┐ │
│  │ 1. Extract listing data (address, price, etc) │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ 2. Download property images (max 20)          │ │
│  │    → Deduplicate using MD5 hashing            │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ 3. Generate embeddings:                        │ │
│  │    • Text → Titan Text Embeddings (1024-dim)  │ │
│  │    • Images → Titan Image Embeddings          │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ 4. Extract features:                           │ │
│  │    • Visual labels via Rekognition             │ │
│  │    • Property features via Claude LLM          │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ 5. Index to OpenSearch                         │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────┐
│  OpenSearch Index  │ (Searchable vector database)
└────────────────────┘
```

---

## 🏗️ Architecture

### AWS Services Used

| Service | Purpose |
|---------|---------|
| **AWS Lambda** | Serverless compute for upload and search functions |
| **Amazon OpenSearch** | Vector database with kNN search capabilities |
| **Amazon Bedrock** | AI models (Titan Embeddings, Claude 3 Haiku) |
| **AWS Rekognition** | Image label detection |
| **EC2** (optional) | Hosting demo Flask UI |

### Data Flow

1. **Ingestion**: Zillow JSON → Upload Lambda → OpenSearch
2. **Search**: User Query → Search Lambda → OpenSearch → Ranked Results
3. **UI** (optional): Browser → Flask/EC2 → Search Lambda → Results

---

## ✨ Features

### 🔍 Search Capabilities

- **Natural Language Queries**: Ask questions like you would to a human agent
- **Image Recognition**: Search by visual features (e.g., "white exterior", "pool", "hardwood floors")
- **Semantic Search**: Understands meaning, not just keywords ("spacious" matches "large", "roomy")
- **Keyword Matching**: Traditional BM25 search for exact terms
- **Hybrid Ranking**: Combines all search methods using Reciprocal Rank Fusion (RRF)
- **Tag Boosting**: Prioritizes listings matching critical features

### 🎛️ Filters

- Price range (min/max)
- Bedrooms (minimum)
- Bathrooms (minimum)
- Custom filters via LLM extraction

### 🤖 AI Models

- **Claude 3 Haiku**: Query parsing, feature extraction
- **Titan Text Embeddings v2**: 1024-dimensional text vectors
- **Titan Image Embeddings**: 1024-dimensional image vectors
- **AWS Rekognition**: Visual label detection (Pool, Patio, Furniture, etc.)

---

## 🛠️ Technology Stack

- **Language**: Python 3.11
- **Vector Database**: Amazon OpenSearch 2.x
- **Search Algorithm**: HNSW (Hierarchical Navigable Small World)
- **Similarity Metric**: Cosine similarity
- **Frameworks**:
  - Backend: AWS Lambda
  - UI (demo): Flask
- **Libraries**: `boto3`, `requests`, `opensearch-py`

---

## 📁 Project Structure

```
hearth_backend_new/
├── README.md                      # This file
├── TECHNICAL_DOCUMENTATION.md     # Detailed technical docs for frontend integration
├── requirements.txt               # Python dependencies
│
├── Lambda Functions (Core Backend)
├── common.py                      # Shared utilities (OpenSearch, Bedrock, embeddings)
├── upload_listings.py             # Lambda: Index Zillow listings
├── search.py                      # Lambda: Search listings
│
├── Data Ingestion Scripts
├── upload_all_listings.sh         # Batch upload all listings
├── watch_upload.sh                # Monitor upload progress
│
├── Utility Scripts
├── test_search.py                 # CLI tool for testing searches
├── debug_index.py                 # Direct OpenSearch query tool
├── recreate_index.py              # Recreate OpenSearch index
├── delete_index.py                # Delete OpenSearch index
│
├── EC2 Demo UI (Optional)
├── deploy_ec2.sh                  # Deploy Flask UI to EC2
├── ec2_setup.sh                   # EC2 instance setup script
├── app.py                         # Flask web application
├── templates/
│   └── index.html                 # Web UI
├── run_ui.sh                      # Run Flask locally
│
└── IAM Policies
    ├── lambda-invoke-policy.json  # Policy for EC2 to invoke Lambda
    └── ec2-trust-policy.json      # Trust policy for EC2 role
```

---

## 🔧 Lambda Functions

### 1️⃣ `hearth-upload` (upload_listings.py)

**Purpose**: Index Zillow property listings into OpenSearch with embeddings and visual features.

**Triggers**:
- Manual invocation with JSON payload
- Self-invokes for batch processing (handles large datasets)

**What It Does**:

1. **Receives** array of Zillow listing objects
2. **Extracts** property data (address, price, beds, baths, description)
3. **Generates fallback description** if missing from Zillow data
4. **Downloads property images** (up to 20, deduplicated by MD5 hash)
5. **Creates embeddings**:
   - Text description → 1024-dim vector (Titan Text Embeddings)
   - Each image → 1024-dim vector (Titan Image Embeddings)
   - Average all image vectors → single `vector_image`
6. **Extracts features**:
   - Visual tags from images (AWS Rekognition)
   - Property features from description (Claude LLM)
7. **Indexes to OpenSearch** via bulk API
8. **Self-invokes** for remaining batches if dataset is large

**Input Format**:
```json
{
  "listings": [
    {
      "zpid": "12345678",
      "price": 450000,
      "beds": 3,
      "baths": 2,
      "address": "123 Main St",
      "city": "Salt Lake City",
      "state": "UT",
      "zip_code": "84101",
      "description": "Beautiful home with pool",
      "imgSrc": "https://photos.zillowstatic.com/...",
      "hdpData": {
        "homeInfo": {
          "description": "...",
          "hiResImageLink": "..."
        }
      }
    }
  ],
  "start_offset": 0  // Optional: for batch processing
}
```

**Output**:
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Indexed 10 documents\"}"
}
```

**Environment Variables**:
- `OS_HOST`: OpenSearch endpoint
- `OS_INDEX`: Index name (default: "listings")
- `AWS_REGION`: AWS region for Bedrock/Rekognition
- `MAX_IMAGES`: Max images to process per listing (default: 20)
- `USE_REKOGNITION`: Enable image labeling (default: "true")
- `TEXT_MODEL_ID`: Bedrock text model (default: "amazon.titan-embed-text-v2:0")
- `IMAGE_MODEL_ID`: Bedrock image model (default: "amazon.titan-embed-image-v1")
- `LLM_MODEL_ID`: Claude model (default: "anthropic.claude-3-haiku-20240307-v1:0")

**Deployment**:
```bash
# Package dependencies
cd hearth_backend_new
mkdir -p build
pip install -r requirements.txt -t build/
cp common.py upload_listings.py build/
cd build && zip -r ../upload.zip . && cd ..

# Deploy to Lambda
aws lambda update-function-code \
  --function-name hearth-upload \
  --zip-file fileb://upload.zip \
  --region us-east-1
```

---

### 2️⃣ `hearth-search` (search.py)

**Purpose**: Search indexed listings using natural language queries with hybrid multimodal search.

**Triggers**:
- API Gateway
- Direct Lambda invocation
- Flask UI (via boto3)

**What It Does**:

1. **Parses query** using Claude LLM to extract:
   - Must-have features (e.g., "pool", "white exterior")
   - Hard filters (price range, beds, baths)
   - Search terms for keyword matching
2. **Generates text embedding** for semantic search
3. **Runs 3 parallel searches** in OpenSearch:
   - **BM25**: Keyword matching on description/features
   - **kNN Text**: Semantic similarity on text embeddings
   - **kNN Image**: Visual similarity on image embeddings
4. **Fuses results** using Reciprocal Rank Fusion (RRF):
   - Combines scores from all 3 search methods
   - Formula: `score = Σ(1 / (60 + rank))`
5. **Boosts listings** matching must-have features (+0.5 per match)
6. **Applies filters** (price, beds, baths)
7. **Returns ranked results** with metadata

**Input Format**:
```json
{
  "q": "white house with pool under 500k",
  "size": 20,
  "filters": {
    "price_min": 200000,
    "price_max": 500000,
    "beds_min": 3,
    "baths_min": 2
  }
}
```

**Output**:
```json
{
  "statusCode": 200,
  "body": "{
    \"total\": 42,
    \"query\": \"white house with pool under 500k\",
    \"must_have\": [\"pool\", \"white exterior\"],
    \"results\": [
      {
        \"id\": \"12345678\",
        \"address\": \"123 Main St\",
        \"city\": \"Salt Lake City\",
        \"state\": \"UT\",
        \"zip_code\": \"84101\",
        \"price\": 475000,
        \"beds\": 4,
        \"baths\": 3,
        \"description\": \"Beautiful white house with pool...\",
        \"score\": 0.87,
        \"boosted\": true,
        \"feature_tags\": [\"pool\", \"hardwood floors\", \"granite countertops\"],
        \"image_tags\": [\"House\", \"Building\", \"Swimming Pool\", \"Patio\"]
      }
    ]
  }"
}
```

**Environment Variables**:
- `OS_HOST`: OpenSearch endpoint
- `OS_INDEX`: Index name
- `AWS_REGION`: AWS region for Bedrock
- `TEXT_MODEL_ID`: Bedrock text embedding model
- `LLM_MODEL_ID`: Claude model for query parsing

**Deployment**:
```bash
# Package and deploy
cd hearth_backend_new
mkdir -p build
pip install -r requirements.txt -t build/
cp common.py search.py build/
cd build && zip -r ../search.zip . && cd ..

aws lambda update-function-code \
  --function-name hearth-search \
  --zip-file fileb://search.zip \
  --region us-east-1
```

---

## 🚀 Setup & Deployment

### Prerequisites

1. **AWS Account** with access to:
   - Lambda
   - OpenSearch
   - Bedrock (with model access approved)
   - Rekognition
   - IAM

2. **AWS CLI** configured with credentials
   ```bash
   aws configure
   ```

3. **Python 3.11+** installed locally

### Step 1: Create OpenSearch Domain

```bash
# Create domain (can also use AWS Console)
aws opensearch create-domain \
  --domain-name hearth-search \
  --engine-version OpenSearch_2.11 \
  --cluster-config InstanceType=t3.small.search,InstanceCount=1 \
  --ebs-options EBSEnabled=true,VolumeType=gp3,VolumeSize=10 \
  --access-policies '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"AWS": "*"},
      "Action": "es:*",
      "Resource": "arn:aws:es:us-east-1:YOUR_ACCOUNT_ID:domain/hearth-search/*"
    }]
  }' \
  --region us-east-1

# Wait for domain to be active (takes ~10 minutes)
aws opensearch describe-domain --domain-name hearth-search --query 'DomainStatus.Processing'
```

Get the endpoint:
```bash
aws opensearch describe-domain \
  --domain-name hearth-search \
  --query 'DomainStatus.Endpoint' \
  --output text
```

### Step 2: Enable Bedrock Model Access

1. Go to AWS Console → Bedrock → Model access
2. Request access to:
   - Amazon Titan Text Embeddings v2
   - Amazon Titan Image Embeddings
   - Anthropic Claude 3 Haiku

### Step 3: Create Lambda Execution Role

```bash
# Create role with Lambda, OpenSearch, Bedrock, Rekognition permissions
aws iam create-role \
  --role-name hearth-lambda-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach policies
aws iam attach-role-policy \
  --role-name hearth-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam attach-role-policy \
  --role-name hearth-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonOpenSearchServiceFullAccess

aws iam attach-role-policy \
  --role-name hearth-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess

aws iam attach-role-policy \
  --role-name hearth-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonRekognitionReadOnlyAccess

# Allow Lambda self-invocation
aws iam put-role-policy \
  --role-name hearth-lambda-role \
  --policy-name lambda-invoke \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "*"
    }]
  }'
```

### Step 4: Deploy Lambda Functions

#### Upload Lambda

```bash
# Build package
mkdir -p build
pip install -r requirements.txt -t build/
cp common.py upload_listings.py build/
cd build && zip -r ../upload.zip . && cd ..

# Create function
aws lambda create-function \
  --function-name hearth-upload \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/hearth-lambda-role \
  --handler upload_listings.lambda_handler \
  --zip-file fileb://upload.zip \
  --timeout 900 \
  --memory-size 512 \
  --environment Variables="{
    OS_HOST=YOUR_OPENSEARCH_ENDPOINT,
    OS_INDEX=listings,
    AWS_REGION=us-east-1,
    MAX_IMAGES=20,
    USE_REKOGNITION=true
  }" \
  --region us-east-1
```

#### Search Lambda

```bash
# Build package
rm -rf build && mkdir -p build
pip install -r requirements.txt -t build/
cp common.py search.py build/
cd build && zip -r ../search.zip . && cd ..

# Create function
aws lambda create-function \
  --function-name hearth-search \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/hearth-lambda-role \
  --handler search.lambda_handler \
  --zip-file fileb://search.zip \
  --timeout 60 \
  --memory-size 512 \
  --environment Variables="{
    OS_HOST=YOUR_OPENSEARCH_ENDPOINT,
    OS_INDEX=listings,
    AWS_REGION=us-east-1
  }" \
  --region us-east-1
```

### Step 5: Initialize OpenSearch Index

```bash
# Run the recreate script
python3 recreate_index.py
```

Or manually invoke the upload Lambda with empty payload to trigger index creation.

### Step 6: Upload Data

```bash
# Batch upload all Zillow listings
./upload_all_listings.sh

# Monitor progress
./watch_upload.sh
```

---

## 📚 Usage Examples

### Example 1: Search from Command Line

```bash
# Simple search
python3 test_search.py

# Enter query when prompted:
> white house with pool under 500k
```

### Example 2: Direct Lambda Invocation

```bash
# Create payload
cat > search_payload.json << EOF
{
  "q": "modern 3 bedroom home with hardwood floors",
  "size": 10,
  "filters": {
    "price_max": 600000,
    "beds_min": 3
  }
}
EOF

# Invoke
aws lambda invoke \
  --function-name hearth-search \
  --payload file://search_payload.json \
  --region us-east-1 \
  response.json

# View results
cat response.json | jq .
```

### Example 3: Python SDK (boto3)

```python
import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-east-1')

payload = {
    "q": "luxury condo with mountain views",
    "size": 20,
    "filters": {
        "price_min": 300000,
        "beds_min": 2,
        "baths_min": 2
    }
}

response = lambda_client.invoke(
    FunctionName='hearth-search',
    Payload=json.dumps(payload)
)

result = json.loads(response['Payload'].read())
body = json.loads(result['body'])

print(f"Found {body['total']} results")
for listing in body['results']:
    print(f"{listing['address']} - ${listing['price']:,}")
```

### Example 4: React Frontend

```javascript
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";

const lambdaClient = new LambdaClient({ region: "us-east-1" });

async function searchProperties(query, filters = {}) {
  const payload = {
    q: query,
    size: 20,
    filters: filters
  };

  const command = new InvokeCommand({
    FunctionName: "hearth-search",
    Payload: JSON.stringify(payload)
  });

  const response = await lambdaClient.send(command);
  const result = JSON.parse(new TextDecoder().decode(response.Payload));
  const body = JSON.parse(result.body);

  return body;
}

// Usage in component
const handleSearch = async () => {
  const results = await searchProperties(
    "white house with pool",
    { price_max: 500000, beds_min: 3 }
  );

  console.log(`Found ${results.total} properties`);
  setListings(results.results);
};
```

### Example 5: Node.js/Express Backend Proxy

```javascript
const express = require('express');
const { LambdaClient, InvokeCommand } = require("@aws-sdk/client-lambda");

const app = express();
const lambda = new LambdaClient({ region: "us-east-1" });

app.use(express.json());

app.post('/api/search', async (req, res) => {
  try {
    const { query, filters } = req.body;

    const command = new InvokeCommand({
      FunctionName: "hearth-search",
      Payload: JSON.stringify({
        q: query,
        size: 20,
        filters: filters
      })
    });

    const response = await lambda.send(command);
    const result = JSON.parse(new TextDecoder().decode(response.Payload));
    const body = JSON.parse(result.body);

    res.json(body);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.listen(3000, () => console.log('Server running on port 3000'));
```

---

## 📖 API Reference

### Search API

**Endpoint**: Lambda function `hearth-search`

**Request**:
```typescript
{
  q: string;              // Natural language query (required)
  size?: number;          // Number of results (default: 20)
  filters?: {
    price_min?: number;   // Minimum price
    price_max?: number;   // Maximum price
    beds_min?: number;    // Minimum bedrooms
    baths_min?: number;   // Minimum bathrooms
  }
}
```

**Response**:
```typescript
{
  statusCode: 200,
  body: string; // JSON stringified:
  {
    total: number;           // Total matching documents
    query: string;           // Original query
    must_have: string[];     // Extracted must-have features
    results: Array<{
      id: string;            // Zillow property ID (zpid)
      address: string;
      city: string;
      state: string;
      zip_code: string;
      price: number;
      beds: number;
      baths: number;
      description: string;
      score: number;         // Relevance score (0-1+)
      boosted: boolean;      // True if matched must-haves
      feature_tags: string[];    // LLM-extracted features
      image_tags: string[];      // Rekognition visual labels
    }>
  }
}
```

### Upload API

**Endpoint**: Lambda function `hearth-upload`

**Request**:
```typescript
{
  listings: Array<{
    zpid: string;          // Zillow property ID (required)
    price?: number;
    beds?: number;
    baths?: number;
    address?: string;
    city?: string;
    state?: string;
    zip_code?: string;
    description?: string;
    imgSrc?: string;       // Image URL
    hdpData?: {            // Zillow nested data
      homeInfo?: {
        description?: string;
        hiResImageLink?: string;
      }
    }
  }>,
  start_offset?: number;   // For batch processing
}
```

**Response**:
```typescript
{
  statusCode: 200,
  body: string; // JSON stringified:
  {
    message: string;       // e.g., "Indexed 10 documents"
  }
}
```

---

## 🛠️ Development Tools

### 1. Test Search (`test_search.py`)

Interactive CLI tool for testing searches:

```bash
./test_search.py
# Enter query: white house with pool
# Enter filters (price_min,price_max,beds_min,baths_min): ,500000,3,2
```

### 2. Watch Upload Progress (`watch_upload.sh`)

Real-time progress monitoring:

```bash
./watch_upload.sh
# Shows: Processing batch 150/1588 (9%)
```

### 3. Debug Index (`debug_index.py`)

Direct OpenSearch queries for debugging:

```bash
python3 debug_index.py
```

### 4. Recreate Index (`recreate_index.py`)

Delete and recreate OpenSearch index (WARNING: deletes all data):

```bash
python3 recreate_index.py
```

---

## 💰 Cost Estimates

### Per-Search Costs

| Component | Cost | Notes |
|-----------|------|-------|
| Lambda execution | $0.000001 | 512MB, ~3s average |
| Bedrock Claude (query parse) | $0.00025 | ~1000 tokens |
| Bedrock Titan Text Embeddings | $0.0000001 | ~50 tokens |
| OpenSearch query | $0.00001 | t3.small instance |
| **Total per search** | **~$0.00026** | **0.026 cents** |

### Per-Listing Upload Costs

| Component | Cost | Notes |
|-----------|------|-------|
| Lambda execution | $0.000010 | 512MB, ~30s with images |
| Bedrock Claude (features) | $0.00025 | ~1000 tokens |
| Bedrock Titan Text | $0.0000001 | Description embedding |
| Bedrock Titan Image | $0.0001 × 20 | $0.002 for 20 images |
| Rekognition labels | $0.0001 × 20 | $0.002 for 20 images |
| OpenSearch indexing | $0.00001 | Bulk operation |
| **Total per listing** | **~$0.0043** | **0.43 cents** |

### Monthly Operating Costs

**Scenario: 10,000 searches/month, 1,000 listings indexed**

| Service | Cost |
|---------|------|
| OpenSearch (t3.small) | ~$45/month |
| Lambda executions | ~$0.10 |
| Bedrock API calls | ~$7 |
| Rekognition | ~$0.50 |
| **Total** | **~$53/month** |

*Costs are estimates and may vary by region and usage patterns.*

---

## 🔍 Troubleshooting

### Search returns 0 results

**Check 1**: Verify index has documents
```bash
python3 debug_index.py
# Should show total documents > 0
```

**Check 2**: Check CloudWatch logs
```bash
aws logs tail /aws/lambda/hearth-search --follow
```

**Check 3**: Verify embeddings are valid
```bash
# Query OpenSearch directly
curl -X GET "https://YOUR_OS_ENDPOINT/listings/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{"query": {"match_all": {}}, "size": 1}'

# Check if vector_text and vector_image fields exist
```

### Upload fails with "zero vector not supported"

**Cause**: Image or text embedding returned all zeros

**Fix**: Already handled in code - only valid (non-zero) vectors are indexed

**Verify**: Check upload logs for warnings:
```bash
aws logs tail /aws/lambda/hearth-upload --follow
```

### "Unable to locate credentials" error

**Cause**: Lambda execution role missing permissions

**Fix**: Ensure role has:
- `AmazonBedrockFullAccess`
- `AmazonOpenSearchServiceFullAccess`
- `AmazonRekognitionReadOnlyAccess`

### OpenSearch query parsing errors

**Check**: CloudWatch logs for error details
```bash
aws logs filter-pattern /aws/lambda/hearth-search --filter-pattern "ERROR"
```

**Common issues**:
- Invalid range filter (null values)
- Wrong kNN query syntax
- Missing index fields

---

## 📚 Additional Documentation

- **[TECHNICAL_DOCUMENTATION.md](./TECHNICAL_DOCUMENTATION.md)**: Comprehensive technical guide with architecture details, frontend integration examples, and advanced topics
- **[UI_README.md](./UI_README.md)**: Flask demo UI setup instructions

---

## 🤝 Support

For issues, questions, or contributions:
1. Check the troubleshooting section above
2. Review CloudWatch logs for detailed error messages
3. Consult the technical documentation
4. Contact the development team

---

## 📝 License

Internal project - Hearth Development Team

---

## 🎓 Key Concepts

### Reciprocal Rank Fusion (RRF)

RRF combines rankings from multiple search methods by:
1. Assigning each result a score based on its rank: `1 / (60 + rank)`
2. Summing scores across all search methods
3. Sorting by final combined score

**Example**:
- BM25 ranks: [A(1), B(2), C(3)]
- kNN Text ranks: [B(1), C(2), A(5)]
- kNN Image ranks: [C(1), A(2), B(10)]

Final scores:
- A: 1/61 + 1/65 + 1/62 = 0.048
- B: 1/62 + 1/61 + 1/70 = 0.046
- C: 1/63 + 1/62 + 1/61 = 0.048

### Tag Boosting

Listings matching "must-have" features get +0.5 score boost per match:
- Query: "white house with pool"
- Must-haves extracted: ["pool", "white exterior"]
- Listing with both → +1.0 boost
- This ensures critical features are prioritized

### Vector Embeddings

**Text embeddings** capture semantic meaning:
- "spacious living room" → [0.23, -0.45, 0.67, ...]
- "large family room" → [0.24, -0.43, 0.65, ...] (similar!)

**Image embeddings** capture visual features:
- White house image → [0.12, 0.89, -0.34, ...]
- Similar white houses have similar vectors

Both are 1024-dimensional vectors compared using cosine similarity.

---

**Built with ❤️ by the Hearth Team**
