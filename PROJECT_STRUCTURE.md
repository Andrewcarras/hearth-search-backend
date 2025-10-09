# Project Structure

Clean, organized structure with only essential files for production deployment.

## Root Directory

```
hearth_backend_new/
├── README.md                      # Main documentation
├── PROJECT_STRUCTURE.md          # This file
│
├── search.py                      # Search Lambda handler
├── upload_listings.py            # Upload/indexing Lambda handler
├── common.py                      # Shared utilities
│
├── app.py                        # Flask UI application
├── templates/
│   └── index.html                # Zillow-style property cards UI
│
├── add_google_maps_key.sh       # Add Google Maps API key to Lambda
│
├── docs/                        # Documentation
│   ├── API.md                   # Complete API reference
│   ├── EXAMPLE_QUERIES.md       # 100+ test queries
│   └── TECHNICAL_DOCUMENTATION.md  # Architecture details
│
└── scripts/                     # Deployment scripts
    ├── deploy_ec2.sh            # Deploy new EC2 instance
    ├── ec2_bootstrap_final.sh   # EC2 setup script (embedded UI)
    ├── test_query_parsing.py   # Test LLM query parsing
    └── upload_all_listings.sh  # Trigger full re-index
```

## Core Code Files

| File | Purpose | Lines |
|------|---------|-------|
| **search.py** | Search Lambda handler with BM25 + kNN hybrid search | ~400 |
| **upload_listings.py** | Indexing Lambda with vision analysis | ~500 |
| **common.py** | Shared utilities (embeddings, LLM, geocoding, image extraction) | ~1000 |

### search.py
- BM25 + kNN hybrid search (text + image embeddings)
- Reciprocal Rank Fusion (RRF) algorithm
- LLM-based query constraint extraction
- Tag-based result boosting
- Returns complete original Zillow listing JSON + Hearth enrichments

### upload_listings.py
- Batch processing with automatic self-invocation
- Claude Vision architecture style classification
- Text/image embedding generation (Bedrock Titan)
- Optimized image resolution (576px for embeddings, cost-optimized)
- Stores complete original Zillow listing data
- OpenSearch bulk indexing with retry logic

### common.py
- Bedrock client (Claude LLM, Titan embeddings)
- OpenSearch client with AWS4Auth
- Google Maps Places API integration
- LLM query parsing and feature extraction
- Optimized image extraction (configurable resolution)
- Architecture style classification

## UI Files

| File | Purpose |
|------|---------|
| **app.py** | Flask web application for property search |
| **templates/index.html** | Zillow-style UI with property cards and modal carousel |

The UI displays:
- Property grid with image cards
- Click-to-view detail modal with image carousel
- Complete listing data (price, beds, baths, description, features)
- All images from `carouselPhotosComposable`

## Documentation

| File | Purpose |
|------|---------|
| **README.md** | Main documentation with setup, deployment, and API usage |
| **docs/API.md** | Complete API reference with TypeScript interfaces and examples |
| **docs/EXAMPLE_QUERIES.md** | 100+ test queries organized by category |
| **docs/TECHNICAL_DOCUMENTATION.md** | Detailed architecture, algorithms, and implementation |

## Scripts

| File | Purpose |
|------|---------|
| **add_google_maps_key.sh** | Add/update Google Maps API key in search Lambda |
| **scripts/deploy_ec2.sh** | Deploy new EC2 instance with UI |
| **scripts/ec2_bootstrap_final.sh** | EC2 setup script with embedded UI files |
| **scripts/test_query_parsing.py** | Test LLM query parsing locally |
| **scripts/upload_all_listings.sh** | Trigger full re-indexing from S3 |

## Configuration

### Lambda Environment Variables

**hearth-search**:
```bash
OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com
OS_INDEX=listings
TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0
IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1
LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
GOOGLE_MAPS_API_KEY=<your-key>  # Optional for "near" queries
```

**hearth-upload-listings**:
```bash
OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com
OS_INDEX=listings
TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0
IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1
LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
MAX_IMAGES=6                      # Max images to process per listing
EMBEDDING_IMAGE_WIDTH=576         # Target resolution for embeddings (cost optimization)
USE_REKOGNITION=false             # Set to true to enable Rekognition labels
```

### OpenSearch Index

**Name**: `listings`
**Shards**: 1
**Replicas**: 0
**Documents**: ~1,588 Murray, UT listings

**Key Fields**:
- `zpid` (keyword) - Zillow property ID
- `description` (text) - Property description
- `vector_text` (knn_vector, 1024-dim) - Text embedding
- `vector_image` (knn_vector, 1024-dim) - Image embedding (from 576px images)
- `feature_tags` (keyword[]) - Extracted features (pool, garage, etc.)
- `image_tags` (keyword[]) - Visual features from image analysis
- `architecture_style` (keyword) - AI-detected style
- `geo` (geo_point) - Latitude/longitude
- `price`, `beds`, `baths`, `acreage` (numeric)
- `original_listing` (object) - Complete Zillow JSON with all fields
- `images` (keyword[]) - Deduplicated high-res image URLs

## Image Resolution Strategy

**For Embeddings** (cost-optimized):
- Downloads **576px** images from Zillow
- Sufficient quality for vision models (Titan, Claude)
- ~70% cost savings vs 1536px images
- Configurable via `EMBEDDING_IMAGE_WIDTH` (384, 576, 768)

**For API Returns** (high-quality):
- Returns complete `carouselPhotosComposable` with all resolutions (192px - 1536px)
- Frontend can choose optimal resolution for each use case
- No data loss - full Zillow listing preserved

## AWS Infrastructure

### Lambda Functions
- **hearth-search**: 1024 MB, 900s timeout
- **hearth-upload-listings**: 3008 MB, 900s timeout

### EC2 UI
- **Instance**: i-0f8debd6dcad98aaf
- **IP**: http://50.17.10.169/
- **Type**: t3.micro
- **Location**: /opt/hearth-ui/

### API Gateway
- **Endpoint**: https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod
- **Routes**: `/search`, `/upload`

### S3 Storage
- **Bucket**: demo-hearth-data
- **Listings**: murray_listings.json (1,588 properties, 279 MB)

## Deployment

### Lambda Deployment

```bash
# Create deployment package
mkdir -p /tmp/lambda_package && cd /tmp/lambda_package
pip install opensearchpy requests requests-aws4auth anthropic -t .

# Deploy search Lambda
cp ~/hearth_backend_new/{search.py,common.py} .
zip -r search_full.zip .
aws lambda update-function-code \
  --function-name hearth-search \
  --zip-file fileb://search_full.zip \
  --region us-east-1

# Deploy upload Lambda
cp ~/hearth_backend_new/upload_listings.py .
zip -r upload_full.zip .
aws lambda update-function-code \
  --function-name hearth-upload-listings \
  --zip-file fileb://upload_full.zip \
  --region us-east-1
```

### EC2 UI Deployment

```bash
cd scripts
./deploy_ec2.sh
# Creates new EC2 instance with embedded UI files
# UI will be available at http://<new-ip>/
```

## Development Workflow

1. **Make changes** to Python files
2. **Test locally** if possible (with AWS credentials)
3. **Update Lambda** code via deployment package
4. **Test** via UI at http://50.17.10.169/ or API
5. **Monitor** CloudWatch logs for errors
6. **Commit** changes to GitHub

## Data Flow

1. **Upload**: Listings JSON → upload Lambda → Vision analysis → Embeddings → OpenSearch
2. **Search**: User query → search Lambda → LLM parsing → Hybrid search → RRF fusion → Results
3. **UI**: User search → Flask → API Gateway → Lambda → OpenSearch → Complete listing JSON

## File Sizes

- Total code: ~60KB (Python + HTML)
- Lambda package: ~45 MB (with dependencies)
- OpenSearch index: ~600 MB (1,588 listings with embeddings)
- UI instance: Embedded in EC2 bootstrap script (9.5 KB compressed)

## Cost Optimization

- Use 576px images for embeddings (not 1536px) - 70% savings
- Limit to 6 images per listing via `MAX_IMAGES`
- Disable Rekognition labels (`USE_REKOGNITION=false`) - saves ~$1/1000 images
- Single OpenSearch shard with 0 replicas

## Maintenance

### Regular Tasks
- Monitor re-indexing progress via CloudWatch logs
- Check API Gateway metrics for errors
- Review Lambda execution times and memory usage

### Occasional Tasks
- Full re-index when source data changes
- Update UI files via new EC2 deployment
- Adjust `EMBEDDING_IMAGE_WIDTH` if cost/quality tradeoff changes
- Update API documentation when adding features

## Support

For issues:
1. Check CloudWatch logs (`/aws/lambda/hearth-search`, `/aws/lambda/hearth-upload-listings`)
2. Verify environment variables in Lambda console
3. Test API directly via curl/Postman
4. Review OpenSearch cluster health
5. Check GitHub issues: https://github.com/Andrewcarras/hearth-search-backend/issues
