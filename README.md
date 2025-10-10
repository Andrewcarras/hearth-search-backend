# Hearth Real Estate Search System

Advanced multimodal real estate search combining natural language processing, computer vision, and geolocation to find properties based on features, architecture style, and proximity to amenities.

## Quick Start

**Live UI**: http://50.17.10.169/ (Zillow-style UI with property cards)
**API Endpoint**: https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search
**API Docs**: [docs/API.md](docs/API.md)

**Search Examples**:
- "3 bedroom homes under $500k"
- "modern homes with pool and garage"
- "craftsman style houses with hardwood floors"
- "homes near a gym" *(requires Google Maps API key)*

## System Architecture

### Core Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Search Lambda** | Natural language search | BM25 + kNN hybrid search + on-demand geolocation |
| **Upload Lambda** | Index listings with vision analysis | Claude 3 Haiku Vision (cached) |
| **OpenSearch** | Search index (vectors, filters) | 1024-dim embeddings |
| **S3** | Complete Zillow listing storage | Individual JSON files per listing |
| **DynamoDB** | Caching layer | Image analysis + geolocation caches |
| **EC2 UI** | Web interface | Flask (50.17.10.169) |
| **API Gateway** | Production endpoint | REST API |

### Data Architecture (S3 + OpenSearch Hybrid)

**OpenSearch** stores only search-relevant fields (~20 fields per listing):
- Embeddings (vector_text, vector_image)
- Filters (price, beds, baths, geo)
- Tags (architecture_style, feature_tags, image_tags)

**S3** stores complete Zillow data (166+ fields per listing):
- All photos with all resolutions (responsivePhotos)
- Complete address objects, tax history, schools
- All original Zillow fields preserved
- Location: `s3://demo-hearth-data/listings/{zpid}.json`

**Why this architecture?**
- ✅ No OpenSearch mapping conflicts (only indexed fields in OS)
- ✅ Complete data always available (S3 never loses fields)
- ✅ Fast search (OpenSearch optimized for vectors)
- ✅ Scalable (S3 handles unlimited fields/complexity)

### Search Pipeline

```
User Query
    ↓
Claude LLM Parser (extract features, filters, proximity mentions)
    ↓
OpenSearch Hybrid Search (BM25 + kNN text + kNN image)
    ↓
RRF Fusion + Tag Boosting
    ↓
Fetch Complete Data from S3 (merge with OpenSearch results)
    ↓
On-Demand Geolocation Enrichment (Google Places API, cached)
    ↓
Filtered Results with Complete Zillow Data + nearby_places
```

## Features

### 1. Complete Zillow Data Returned (214 Fields)
- **All API responses include the complete original Zillow listing JSON from S3**
- Returns ALL 214 Zillow fields: photos, tax history, price history, schools, building permits, etc.
- Includes `responsivePhotos` (all resolutions), `taxHistory`, `priceHistory`, `schools`, `resoFacts`
- Hearth AI enrichments (architecture style, feature tags) are merged with original data
- Default page size: 15 results (2.9MB response, under 6MB Lambda limit)
- No data loss - everything from the source listing is preserved and accessible

### 2. Natural Language Understanding
- Parses complex queries into structured filters
- Example: "modern 3 bed homes with pool near gym" → `{architecture: "modern", beds_min: 3, must_have: ["pool"], proximity: {poi_type: "gym"}}`

### 3. Hybrid Search (BM25 + kNN)
- **BM25**: Keyword matching on descriptions
- **kNN Text**: Semantic similarity on text embeddings
- **kNN Image**: Visual similarity on image embeddings
- **RRF**: Fuses results from all three searches

### 4. Computer Vision (Claude 3 Haiku - Cost Optimized)
- Architecture style classification (25+ styles)
- Visual feature detection (flooring, materials, rooms, etc.)
- Exterior color identification
- **Cost**: $0.00025/image (75% cheaper than Rekognition)
- **DynamoDB caching** prevents re-analyzing same images

### 5. On-Demand Geolocation (Google Places API New)
- **Every result shows ITS OWN nearby places** (grocery stores, gyms, parks, restaurants, etc.)
- Proximity mentions in queries (e.g., "near a grocery store") are informational only
- Returns ALL matching homes, each enriched with nearby places from Google Places API (New v1)
- **DynamoDB caching** by rounded coordinates (~100m precision)
- **Cost**: ~$0.26 per search first time, $0 cached (100x cheaper than old approach)

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

# Google Places API New (for on-demand geolocation enrichment)
GOOGLE_PLACES_API_KEY=<your-key>
```

### Google Places API Setup (New API)

**What it does**: Enriches search results with nearby places for each listing

1. Get API key: https://console.cloud.google.com/apis/credentials
2. Enable "Places API (New)" in Google Cloud Console
3. Add to Lambda environment variable: `GOOGLE_PLACES_API_KEY`
4. Results now include `nearby_places` array with groceries, gyms, restaurants, etc.

**Cost**: ~$0.017 per listing first time, $0 cached (DynamoDB)

## Core Files

### Production Code
- **search.py** - Search Lambda handler (hybrid search + on-demand geolocation)
- **upload_listings.py** - Indexing Lambda handler (vision analysis with caching)
- **common.py** - Shared utilities (embeddings, LLM, vision, OpenSearch)
- **app.py** - Flask UI backend

### Scripts
- **scripts/deploy_ec2.sh** - Deploy UI to EC2
- **scripts/ec2_bootstrap_final.sh** - EC2 setup script
- **scripts/test_query_parsing.py** - Test LLM query parsing
- **scripts/upload_all_listings.sh** - Batch upload helper

### Documentation
- **README.md** - This file
- **docs/API.md** - Complete API reference
- **docs/EXAMPLE_QUERIES.md** - Example queries
- **docs/TECHNICAL_DOCUMENTATION.md** - Architecture deep dive
- **PROJECT_STRUCTURE.md** - Code organization

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

**Response** (15 results by default):
```json
{
  "ok": true,
  "total": 15,
  "must_have": ["pool"],
  "results": [
    {
      "id": "12345",

      // Complete Zillow data (214 fields from S3)
      "zpid": "12345",
      "address": {"streetAddress": "123 Main St", "city": "Salt Lake City", ...},
      "price": 450000,
      "bedrooms": 3,
      "bathrooms": 2,
      "responsivePhotos": [...],  // All photos, all resolutions
      "taxHistory": [...],
      "priceHistory": [...],
      "schools": [...],
      "resoFacts": {...},
      // ... 200+ more Zillow fields

      // Hearth enrichments (from OpenSearch)
      "feature_tags": ["pool", "garage", "backyard"],
      "image_tags": ["brick", "hardwood", "tile"],
      "architecture_style": "modern",
      "score": 0.95,
      "boosted": false,

      // On-demand geolocation (from Google Places API, cached)
      "nearby_places": [
        {"name": "Smith's Grocery", "types": ["grocery_store", "supermarket"]},
        {"name": "Gold's Gym", "types": ["gym", "fitness_center"]},
        ...
      ]
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

- **Search latency**: 500-800ms average (includes S3 fetch)
- **Indexing speed**: ~150 listings per batch (~5 minutes per batch)
- **Vector dimensions**: 1024-dim (Titan embeddings)
- **Dataset**: 1,588 Murray County, UT listings
- **Images processed**: 6 per listing @ 576px resolution (cost-optimized)

## Cost Estimate

**Monthly operational costs**:
- OpenSearch: ~$25-30 (t3.small.search, 10GB storage)
- S3: ~$0.05 (1,588 listing JSONs)
- Lambda: ~$2 (within free tier)
- EC2: ~$10 (t3.micro UI)
- Google Maps: $0 (within free tier)

**Total**: ~$37-42/month

**One-time re-indexing costs** (per full re-index):
- Bedrock Text Embeddings: ~$0.50 (1,588 descriptions)
- Bedrock Image Embeddings: ~$0.60 (6 images × 1,588 listings @ 576px)
- Claude Vision (architecture + features): ~$2.38 (6 images × 1,588 listings × $0.00025)
- DynamoDB writes (caching): ~$0.02
- **Total**: ~$3.50 per re-index (75% cheaper than before!)
- **Note**: Subsequent re-indexes cost ~$1.10 (cached images skip vision analysis)

## Troubleshooting

### "Homes Near X" Queries Return Results Without nearby_places

**Cause**: Google Places API key not configured

**Fix**: Add `GOOGLE_PLACES_API_KEY` to Lambda environment variables:
```bash
aws lambda update-function-configuration \
  --function-name hearth-search \
  --environment "Variables={..., GOOGLE_PLACES_API_KEY=YOUR_KEY}"
```

**Note**: Queries like "homes near a grocery store" will still return all matching homes. The API key just enables the `nearby_places` enrichment for each result.

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

**Most common cause:** Re-indexing still in progress or Bedrock throttling

1. Check if listings are indexed:
   ```bash
   curl https://search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com/listings/_count
   ```

2. Check for Bedrock throttling in upload logs:
   ```bash
   aws logs tail /aws/lambda/hearth-upload-listings --since 5m | grep ThrottlingException
   ```

   If you see "Too many requests" errors, Bedrock is being rate-limited. This is normal during re-indexing and will settle within 1-2 hours.

3. Check search logs for errors:
   ```bash
   aws logs tail /aws/lambda/hearth-search --since 5m
   ```

**Solution:** Wait for re-indexing to complete. Listings without embeddings (due to throttling) aren't searchable yet.

## Documentation

### 📚 **Complete Documentation Index**

**For Frontend Developers:**
- **[Frontend Integration Guide](docs/FRONTEND_INTEGRATION_GUIDE.md)** - **START HERE** - How to integrate the API into your UI

**For API Users:**
- **[API Reference](docs/API.md)** - Complete endpoint documentation with examples
- **[Example Queries](docs/EXAMPLE_QUERIES.md)** - Real-world search examples and use cases

**For System Architects & DevOps:**
- **[Complete System Documentation](docs/COMPLETE_SYSTEM_DOCUMENTATION.md)** - **COMPREHENSIVE GUIDE** - Full system architecture, AWS infrastructure, cost analysis, deployment, troubleshooting
- **[Technical Documentation](docs/TECHNICAL_DOCUMENTATION.md)** - Deep dive into search algorithms and data flow
- **[Project Structure](PROJECT_STRUCTURE.md)** - Codebase organization and file reference

**Quick Links by Topic:**
- **Architecture & Flow Diagrams**: [Complete System Documentation](docs/COMPLETE_SYSTEM_DOCUMENTATION.md#architecture-diagram)
- **AWS Infrastructure Setup**: [Complete System Documentation](docs/COMPLETE_SYSTEM_DOCUMENTATION.md#aws-infrastructure)
- **Cost Analysis**: [Complete System Documentation](docs/COMPLETE_SYSTEM_DOCUMENTATION.md#cost-analysis)
- **Deployment Guide**: [Complete System Documentation](docs/COMPLETE_SYSTEM_DOCUMENTATION.md#deployment-guide)
- **Troubleshooting**: [Complete System Documentation](docs/COMPLETE_SYSTEM_DOCUMENTATION.md#troubleshooting)
- **Performance Benchmarks**: [Complete System Documentation](docs/COMPLETE_SYSTEM_DOCUMENTATION.md#performance-benchmarks)

## License

Proprietary - Hearth Real Estate Search System
