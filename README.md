# Hearth - AI-Powered Multimodal Real Estate Search

An advanced real estate search system that combines natural language processing, computer vision, and semantic search to enable intuitive property discovery.

## 🚀 Quick Start for Frontend Developers

**Production API Endpoint:** `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`

```javascript
// Search for homes
const response = await fetch(
  'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search',
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q: "homes with a pool", size: 20 })
  }
);
const data = await response.json();
console.log(data.results); // Array of matching homes
```

**📚 Documentation:**
- **[Quick Start Guide](docs/QUICKSTART.md)** - Get started in 1 minute
- **[Complete API Documentation](docs/API.md)** - Full reference with examples
- **[API Configuration](docs/api-gateway-config.json)** - Technical details

## Features

### 🏠 Natural Language Search
- Ask questions like "Show me modern homes with a balcony near a school"
- Automatic extraction of filters, features, and constraints
- Context-aware query understanding

### 🎨 Architecture Style Recognition
- Automatic classification of 25+ architectural styles
- Vision-based analysis using Claude 3 Sonnet
- Styles include: modern, craftsman, victorian, ranch, colonial, mid-century modern, and more

### 👁️ Visual Feature Detection
- Identifies structural elements: balconies, porches, fences, decks
- Detects exterior colors and materials
- Recognizes garage types, windows, and landscaping features

### 📍 Proximity-Based Search
- Find homes near schools, gyms, grocery stores, parks
- Support for drive-time constraints
- Geocoding with OpenStreetMap Nominatim

### 🔍 Hybrid Search
- BM25 text search for keyword matching
- Semantic vector search (text + image embeddings)
- Reciprocal Rank Fusion (RRF) for optimal result ranking

## Architecture

```
User Query → Claude LLM Parser → OpenSearch
                                      ↓
                         Hybrid Search (BM25 + 2x kNN)
                                      ↓
                            RRF Fusion + Boosting
                                      ↓
                                  Results
```

### Components

- **common.py**: Shared utilities, embeddings, LLM interactions
- **search.py**: Search Lambda handler with hybrid query execution
- **upload_listings.py**: Indexing Lambda with vision analysis
- **requirements.txt**: Python dependencies

### AWS Services

- **AWS Lambda**: Serverless compute for search and indexing
- **Amazon OpenSearch**: Vector database with kNN search
- **Amazon Bedrock**: LLM (Claude) and embedding models
- **Amazon S3**: Listing data storage

## Setup

### Prerequisites

- AWS Account with configured credentials
- Python 3.11+
- Access to Amazon Bedrock models

### Environment Variables

```bash
# OpenSearch
OS_HOST=search-xyz.us-east-1.es.amazonaws.com
OS_INDEX=listings
AWS_REGION=us-east-1

# Bedrock Models
TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0
IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1
LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0

# Cost Optimization
USE_REKOGNITION=false  # Disabled to reduce costs
MAX_IMAGES=3           # Limit images processed per property
```

### Deployment

```bash
# Install dependencies
pip install -r requirements.txt -t build/

# Copy source files
cp common.py search.py upload_listings.py build/

# Create deployment packages
cd build && zip -r ../search.zip . && cd ..

# Deploy to Lambda
aws lambda update-function-code \
  --function-name hearth-search \
  --zip-file fileb://search.zip
```

## Usage

### Search API

```python
# Query
POST /search
{
  "q": "Show me modern homes with a pool near a school",
  "size": 30
}

# Response
{
  "ok": true,
  "results": [...],
  "total": 30,
  "must_have": ["pool"],
  "architecture_style": "modern",
  "proximity": {"poi_type": "school"}
}
```

### Example Queries

```
"Show me modern homes with a balcony"
"Find craftsman style houses with a garage"
"Show me homes near an elementary school"
"Find colonial homes with a white fence"
"Show me homes within 10 minutes from downtown"
```

### Indexing New Listings

```bash
# Upload from S3
aws lambda invoke \
  --function-name hearth-upload-listings \
  --payload '{"bucket": "demo-hearth-data", "key": "murray_listings.json"}' \
  response.json
```

## Cost Optimization

### Rekognition Disabled
- Previous cost: ~$200/day for 1600 listings
- Current cost: $0 (using Claude Vision only)
- Claude Vision: ~$0.003 per image (only best exterior photo)

### Image Processing
- Reduced from 6 images/property to 1-3
- Vision analysis on best exterior image only
- 83% reduction in processing costs

### Best Practices
1. Set `USE_REKOGNITION=false` to avoid Rekognition costs
2. Limit `MAX_IMAGES=3` to reduce embedding costs
3. Claude Vision provides better analysis at lower cost

## Performance

- **Search latency**: ~200-400ms
- **Indexing speed**: ~15-20 seconds per listing
- **Vector dimensions**: 1024-dim (text + image)
- **Index size**: ~1MB per 1000 listings

## Documentation

### For Frontend Developers
- **[Quick Start Guide](docs/QUICKSTART.md)** - 1-minute integration guide
- **[API Documentation](docs/API.md)** - Complete REST API reference
- **[API Configuration](docs/api-gateway-config.json)** - Gateway setup details

### For Backend Developers
- [Deployment Guide](docs/DEPLOYMENT_SUMMARY.md) - AWS deployment instructions
- [Implementation Details](docs/IMPLEMENTATION_SUMMARY.md) - Technical architecture
- [Technical Deep Dive](docs/TECHNICAL_DOCUMENTATION.md) - Detailed system design

## Development

### Local Testing

```bash
# Test query parsing
python scripts/test_query_parsing.py

# Upload test listings
./scripts/upload_all_listings.sh
```

### Monitoring

```bash
# Watch search logs
aws logs tail /aws/lambda/hearth-search --follow

# Watch upload logs
aws logs tail /aws/lambda/hearth-upload-listings --follow
```

## License

Proprietary - All rights reserved

## Support

For issues or questions, contact the development team.
