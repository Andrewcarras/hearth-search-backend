# Hearth Real Estate Search System

Advanced multimodal real estate search combining natural language processing, computer vision, and geolocation to find properties based on features, architecture style, and proximity to amenities.

## Quick Start

**Live UI**: http://3.87.169.144/
**API Endpoint**: https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search

**Search Examples**:
- "3 bedroom homes under $500k"
- "modern homes with pool and garage"
- "craftsman style houses with hardwood floors"
- "homes near a gym" *(requires Google Maps API key)*

## System Architecture

### Core Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Search Lambda** | Natural language search | BM25 + kNN hybrid search |
| **Upload Lambda** | Index listings with vision analysis | Claude Vision + Rekognition |
| **OpenSearch** | Vector database | 1024-dim embeddings, geo-distance |
| **EC2 UI** | Web interface | Flask (54.163.59.108) |
| **API Gateway** | Production endpoint | REST API |

### Search Pipeline

```
User Query
    ↓
Claude LLM Parser (extract features, filters, proximity)
    ↓
OpenSearch Hybrid Search (BM25 + kNN text + kNN image)
    ↓
RRF Fusion + Tag Boosting
    ↓
Filtered Results
```

## Features

### 1. Natural Language Understanding
- Parses complex queries into structured filters
- Example: "modern 3 bed homes with pool near gym" → `{architecture: "modern", beds_min: 3, must_have: ["pool"], proximity: {poi_type: "gym"}}`

### 2. Hybrid Search (BM25 + kNN)
- **BM25**: Keyword matching on descriptions
- **kNN Text**: Semantic similarity on text embeddings
- **kNN Image**: Visual similarity on image embeddings
- **RRF**: Fuses results from all three searches

### 3. Computer Vision
- Architecture style classification (25+ styles)
- Visual feature detection (balcony, porch, fence, etc.)
- Exterior color identification
- Uses Claude 3 Sonnet + Rekognition

### 4. Geolocation (Google Maps Places API)
- Find homes near specific businesses/amenities
- Accurate POI geocoding (gyms, schools, restaurants, etc.)
- Distance-based filtering (km or drive time)

## Setup

### Prerequisites

- AWS Account with credentials configured
- Python 3.11+
- Access to Amazon Bedrock models
- Google Maps API key (optional, for geo queries)

### Environment Variables

Lambda functions require these environment variables:

```bash
# OpenSearch
OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com
OS_INDEX=listings

# Bedrock Models
TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0
IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1
LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0

# Google Maps (optional but recommended)
GOOGLE_MAPS_API_KEY=<your-key>
```

### Google Maps API Setup

**Required for**: "homes near X" queries

1. Get API key: https://console.cloud.google.com/apis/credentials
2. Enable "Places API"
3. Restrict key to Places API only
4. Add to Lambda:
   ```bash
   ./add_google_maps_key.sh YOUR_API_KEY
   ```

**Cost**: Free tier ($200/month) covers typical usage

See [GOOGLE_MAPS_SETUP.md](GOOGLE_MAPS_SETUP.md) for detailed instructions.

## Core Files

### Production Code
- **search.py** - Search Lambda handler (hybrid search)
- **upload_listings.py** - Indexing Lambda handler (vision analysis)
- **common.py** - Shared utilities (embeddings, LLM, geocoding)

### Scripts
- **add_google_maps_key.sh** - Add Google Maps API key to Lambda
- **monitor_reindex.sh** - Check re-indexing progress

### Documentation
- **README.md** - This file
- **docs/API.md** - Complete API reference
- **docs/EXAMPLE_QUERIES.md** - 100 test queries
- **docs/TECHNICAL_DOCUMENTATION.md** - Architecture deep dive
- **GOOGLE_MAPS_SETUP.md** - Google Maps configuration

## API Usage

### Search Endpoint

```bash
POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search
Content-Type: application/json

{
  "q": "3 bedroom homes with pool under $500k",
  "size": 20
}
```

**Response**:
```json
{
  "ok": true,
  "total": 15,
  "must_have": ["pool"],
  "results": [
    {
      "id": "12345",
      "address": "123 Main St",
      "city": "Salt Lake City",
      "state": "UT",
      "price": 450000,
      "beds": 3,
      "baths": 2,
      "feature_tags": ["pool", "garage", "backyard"],
      "architecture_style": "modern",
      "geo": {"lat": 40.7608, "lon": -111.891}
    }
  ]
}
```

See [docs/API.md](docs/API.md) for complete reference.

## Deployment

### Deploy Search Lambda

```bash
# Create package directory
mkdir -p /tmp/lambda_package && cd /tmp/lambda_package

# Install dependencies
pip install opensearchpy requests requests-aws4auth -t .

# Add code
cp ~/hearth_backend_new/{search.py,common.py} .

# Package
zip -r search_deployment.zip .

# Deploy
aws lambda update-function-code \
  --function-name hearth-search \
  --zip-file fileb://search_deployment.zip \
  --region us-east-1
```

### Deploy Upload Lambda

Similar process, use `upload_listings.py` instead of `search.py`.

### Trigger Re-indexing

```bash
aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type Event \
  --payload '{"bucket": "demo-hearth-data", "key": "murray_listings.json", "start": 0, "limit": 100}' \
  response.json
```

The Lambda self-invokes to process all listings in batches.

## Monitoring

### Check Search Logs
```bash
aws logs tail /aws/lambda/hearth-search --follow
```

### Check Re-indexing Progress
```bash
./monitor_reindex.sh
```

### Test Search
```bash
curl -X POST http://54.163.59.108/search \
  -H "Content-Type: application/json" \
  -d '{"q": "modern homes", "size": 5}'
```

## Performance

- **Search latency**: 500-800ms average
- **Indexing speed**: ~100 listings per 13 minutes
- **Vector dimensions**: 1024-dim (Titan embeddings)
- **Database size**: ~1588 listings

## Cost Estimate

**Monthly operational costs**:
- OpenSearch: ~$50 (t3.small.search)
- Lambda: ~$2 (within free tier)
- Bedrock: ~$5 (Claude + embeddings)
- EC2: ~$10 (t3.micro UI)
- Google Maps: $0 (within free tier)

**Total**: ~$67/month

**One-time indexing cost**: ~$15 (Rekognition + Claude Vision)

## Troubleshooting

### No Results for "Homes Near X" Queries

**Cause**: Google Maps API key not configured

**Fix**:
```bash
./add_google_maps_key.sh YOUR_KEY
```

### Re-indexing Appears Stuck

**Check progress**:
```bash
./monitor_reindex.sh
```

**Check logs**:
```bash
aws logs tail /aws/lambda/hearth-upload-listings --since 10m
```

### Search Returns 0 Results

1. Verify listings are indexed:
   ```bash
   curl https://search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com/listings/_count
   ```

2. Check search logs for errors:
   ```bash
   aws logs tail /aws/lambda/hearth-search --since 5m
   ```

## Documentation

- **[API Reference](docs/API.md)** - Complete API documentation
- **[Example Queries](docs/EXAMPLE_QUERIES.md)** - 100 test queries
- **[Technical Documentation](docs/TECHNICAL_DOCUMENTATION.md)** - Architecture details
- **[Google Maps Setup](GOOGLE_MAPS_SETUP.md)** - Geo-location configuration

## License

Proprietary - Hearth Real Estate Search System
