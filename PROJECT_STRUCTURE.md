# Project Structure

Clean, organized structure with only essential files.

## Root Directory

```
hearth_backend_new/
├── README.md                      # Main documentation
├── GOOGLE_MAPS_SETUP.md          # Google Maps API setup guide
├── PROJECT_STRUCTURE.md          # This file
│
├── search.py                      # Search Lambda handler
├── upload_listings.py            # Upload/indexing Lambda handler
├── common.py                      # Shared utilities
├── requirements.txt              # Python dependencies
│
├── add_google_maps_key.sh       # Add Google Maps API key
├── monitor_reindex.sh           # Monitor re-indexing progress
│
├── docs/                        # Documentation
└── scripts/                     # Deployment & utility scripts
```

## Core Code Files

| File | Purpose | Size |
|------|---------|------|
| **search.py** | Search Lambda handler | ~400 lines |
| **upload_listings.py** | Indexing Lambda handler | ~500 lines |
| **common.py** | Shared utilities (embeddings, LLM, geocoding) | ~1000 lines |

### search.py
- BM25 + kNN hybrid search
- RRF fusion algorithm
- Query constraint extraction
- Tag-based boosting

### upload_listings.py
- Batch processing with self-invocation
- Vision analysis (Claude + Rekognition)
- Text/image embedding generation
- OpenSearch bulk indexing

### common.py
- Bedrock client (Claude LLM, Titan embeddings)
- OpenSearch client configuration
- Google Maps Places API integration
- LLM query parsing
- Architecture style classification

## Documentation

| File | Purpose |
|------|---------|
| **README.md** | Main documentation with setup, API usage, deployment |
| **docs/API.md** | Complete API reference with examples |
| **docs/EXAMPLE_QUERIES.md** | 100 test queries by category |
| **docs/TECHNICAL_DOCUMENTATION.md** | Detailed architecture and implementation |
| **docs/REINDEX_STATUS.md** | Re-indexing guide and troubleshooting |
| **docs/REKOGNITION_COST_ANALYSIS.md** | Cost analysis and optimization |
| **docs/EC2_UI_UPDATE.md** | EC2 instance setup and configuration |
| **GOOGLE_MAPS_SETUP.md** | Google Maps API configuration guide |

## Scripts

| File | Purpose |
|------|---------|
| **add_google_maps_key.sh** | Add Google Maps API key to Lambda |
| **monitor_reindex.sh** | Check re-indexing progress |
| **scripts/deploy_ec2.sh** | Deploy new EC2 instance |
| **scripts/ec2_setup.sh** | Configure EC2 instance |
| **scripts/run_ui.sh** | Start UI web server |
| **scripts/test_query_parsing.py** | Test LLM query parsing |
| **scripts/update_ec2_ui.sh** | Update UI on EC2 |
| **scripts/upload_all_listings.sh** | Trigger full re-index |

## Dependencies

### Python Packages (requirements.txt)
- `opensearchpy` - OpenSearch client
- `requests` - HTTP client
- `requests-aws4auth` - AWS authentication for requests
- `boto3` - AWS SDK (included in Lambda)
- `botocore` - AWS core (included in Lambda)

### AWS Services
- **Lambda** - Serverless compute
- **OpenSearch** - Vector database
- **Bedrock** - Claude LLM and Titan embeddings
- **Rekognition** - Image analysis (optional)
- **S3** - Listing data storage
- **EC2** - UI web server
- **API Gateway** - REST API endpoint

### External APIs
- **Google Maps Places API** - POI geocoding (optional but recommended)

## Configuration

### Lambda Environment Variables

Both Lambda functions use:
```bash
OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com
OS_INDEX=listings
TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0
IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1
LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
GOOGLE_MAPS_API_KEY=<your-key>  # Optional
```

### OpenSearch Index

**Name**: `listings`
**Shards**: 1
**Replicas**: 0
**Documents**: ~1,588 listings

**Fields**:
- `zpid` (keyword) - Zillow property ID
- `description` (text) - Property description
- `vector_text` (knn_vector, 1024-dim) - Text embedding
- `vector_image` (knn_vector, 1024-dim) - Image embedding
- `feature_tags` (keyword[]) - Property features
- `image_tags` (keyword[]) - Visual features
- `architecture_style` (keyword) - Architecture classification
- `geo` (geo_point) - Latitude/longitude
- `price`, `beds`, `baths`, `acreage` (numeric)

## Deployment

### Lambda Packages

Create deployment packages with:
```bash
mkdir -p /tmp/lambda_package && cd /tmp/lambda_package
pip install opensearchpy requests requests-aws4auth -t .
cp ~/hearth_backend_new/{search.py,common.py} .
zip -r search_deployment.zip .
```

Deploy with:
```bash
aws lambda update-function-code \
  --function-name hearth-search \
  --zip-file fileb://search_deployment.zip \
  --region us-east-1
```

### EC2 UI

**Instance**: i-0fe9543d2f7726bf5
**IP**: 54.163.59.108
**Type**: t3.micro

UI code is in `/opt/hearth-ui/app.py` on the EC2 instance.

## File Sizes

- Total project: ~50KB (code only, excluding .venv)
- Lambda deployment package: ~16MB (with dependencies)
- OpenSearch index: ~150MB (1,588 listings with embeddings)

## Development Workflow

1. **Make changes** to `search.py`, `upload_listings.py`, or `common.py`
2. **Test locally** (if possible with AWS credentials)
3. **Package** code into deployment zip
4. **Deploy** to Lambda
5. **Test** via UI or API
6. **Monitor** CloudWatch logs

## Removed Files

During cleanup, removed:
- All deployment packages (*.zip)
- Response JSON files (response*.json)
- Duplicate/outdated documentation
- Temporary scripts
- Deployment artifacts

## Maintenance

### Regular Tasks
- Monitor re-indexing progress
- Check CloudWatch logs for errors
- Update Google Maps API key if needed
- Refresh EC2 instance periodically

### Occasional Tasks
- Full re-index when data changes
- Update Lambda code for new features
- Adjust OpenSearch instance size if needed
- Review costs monthly

## Support

For issues:
1. Check CloudWatch logs
2. Review relevant documentation
3. Test API endpoints directly
4. Verify environment variables
