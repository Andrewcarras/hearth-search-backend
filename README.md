# Hearth Real Estate Search System

Advanced multimodal AI-powered real estate search combining natural language processing, computer vision, and geolocation to find properties based on features, architecture style, and proximity to amenities.

---

## 🚀 Quick Start

**Live Demo:** http://54.227.66.148/
**Search API:** https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search
**Current Index:** `listings-v2` (multi-vector image search enabled)
**Status:** ✅ Production Ready - 3,904 listings from Salt Lake City, UT

### Try It Now

```bash
# Search for properties with granite countertops
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "granite countertops", "limit": 5, "index": "listings-v2"}'
```

**Example Queries:**
- "3 bedroom homes under $500k"
- "modern homes with pool and garage"
- "craftsman style houses with hardwood floors"
- "blue homes with vaulted ceilings"
- "homes near a school"

---

## 📚 Documentation

### **For Developers**
- **[API Integration Guide](docs/API_INTEGRATION.md)** - Complete API reference with code examples (JavaScript, Python, React, cURL)

### **For System Architects**
- **[Backend Architecture](docs/BACKEND_ARCHITECTURE.md)** - System architecture, data flow, hybrid search algorithm, cost analysis
- **[Code Reference](docs/CODE_REFERENCE.md)** - Detailed function documentation for all Python files

### **For Operations**
- **[AWS Deployment Guide](AWS_DEPLOYMENT_GUIDE.md)** - How to deploy and configure AWS resources
- **[Indexing Guide](INDEXING_GUIDE.md)** - How to index listings (local script or Lambda)

---

## 🎯 What Makes Hearth Unique

### 1. **Multimodal AI Search**
- **Natural Language Understanding** - "Show me modern homes with granite countertops" → structured filters
- **Visual Search** - Find properties by photo features (vaulted ceilings, blue exterior, pool)
- **Hybrid Ranking** - Combines BM25 keyword search + kNN semantic search + kNN visual search

### 2. **Cost-Optimized AI**
- **Claude Haiku Vision** - 75% cheaper than AWS Rekognition for image analysis
- **DynamoDB Caching** - 90% cost savings on re-indexing ($0.90 vs $8.89)
- **On-Demand Geolocation** - 100x cheaper than filtering all listings ($0.26 vs $27 per search)

### 3. **Complete Data Integration**
- Returns ALL Zillow fields (price history, tax history, schools, photos at all resolutions)
- Enriches with AI-detected features and nearby places
- Single API call - no multiple roundtrips needed

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                           │
│  http://54.227.66.148/ (Property search with modal details)     │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP POST
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (HTTP API)                       │
│  https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod    │
└───────────────────────────┬──────────────────────────────────────┘
                            │ Invokes
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LAMBDA: hearth-search                         │
│  • Parse query (Claude Haiku)                                   │
│  • Generate embeddings (Bedrock Titan)                          │
│  • Hybrid search (BM25 + kNN text + kNN image multi-vector)     │
│  • RRF fusion with adaptive k-values                            │
│  • Enrich with nearby places (Google Places API)                │
└───────────────────┬─────────────────────────────────────────────┘
                    │ Query
                    ▼
        ┌───────────────────────┐
        │   OPENSEARCH CLUSTER  │
        │   3,904 documents     │
        │   • Multi-vector kNN  │
        │   • BM25 text index   │
        │   • Filters/facets    │
        └───────────────────────┘
                    ▲
                    │ Index
┌───────────────────┴─────────────────────────────────────────────┐
│               INDEXING PIPELINE                                  │
│                                                                  │
│  ┌──────────────┐      ┌─────────────────────────────┐         │
│  │ S3 Listings  │  →   │ index_local.py (Recommended)│         │
│  │ 3,904 props  │      │ OR Lambda: upload-listings  │         │
│  └──────────────┘      └──────────┬──────────────────┘         │
│                                   │                             │
│                                   ▼                             │
│                    ┌──────────────────────────┐                 │
│                    │ For each listing:        │                 │
│                    │ • Text embedding         │                 │
│                    │ • Image embeddings (ALL) │                 │
│                    │ • Vision AI analysis     │                 │
│                    │ • Architecture style     │                 │
│                    │ • Parallel processing    │                 │
│                    └──────────┬───────────────┘                 │
│                               │                                 │
│                               ▼                                 │
│                    ┌──────────────────────────┐                 │
│                    │ Unified DynamoDB Caches  │                 │
│                    │ • hearth-vision-cache    │                 │
│                    │ • hearth-text-embeddings │                 │
│                    │ (90%+ hit rate)          │                 │
│                    └──────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
```

**Key Technologies:**
- **OpenSearch 2.11** - Multi-vector kNN search with HNSW algorithm
- **Amazon Bedrock** - Titan embeddings (1024-dim) + Claude Haiku for vision/NLP
- **DynamoDB** - Unified caching (embeddings + vision + geolocation)
- **Google Places API** - On-demand nearby places enrichment
- **Python 3.13** - Lambda runtime with optimized parallel processing

See [docs/BACKEND_ARCHITECTURE.md](docs/BACKEND_ARCHITECTURE.md) for detailed architecture.

---

## ⚡ Features

### Natural Language Understanding
```python
Query: "3 bedroom modern home with pool under $500k"

Parsed Constraints:
{
  "must_have": ["pool"],
  "hard_filters": {"beds_min": 3, "price_max": 500000},
  "architecture_style": "modern"
}
```

### Hybrid Search Algorithm
1. **BM25 Search** - Keyword matching on descriptions with field boosting
2. **kNN Text Search** - Semantic similarity on text embeddings (cosine)
3. **kNN Image Search** - Visual similarity on image embeddings (cosine)
4. **RRF Fusion** - Combines rankings from all 3 searches
5. **Tag Boosting** - Properties matching all required features rank higher

### Computer Vision Features
- **Architecture Classification** - 25+ styles (modern, craftsman, colonial, etc.)
- **Visual Feature Detection** - Granite countertops, vaulted ceilings, hardwood floors, pools, etc.
- **Exterior Analysis** - Colors, materials, structural elements (porch, garage, fence)
- **Cost** - $0.00025 per image (Claude Haiku Vision)

### Geolocation Enrichment
- **On-Demand** - Each listing shows its own nearby places
- **Cached** - DynamoDB cache by rounded coordinates (~95% hit rate)
- **Places Detected** - Grocery stores, gyms, parks, schools, restaurants, hospitals
- **Cost** - $0.017 per cache miss, $0 per cache hit

---

## 🔧 Setup

### Prerequisites
- AWS Account with credentials configured
- Python 3.11+
- Access to Amazon Bedrock models (Titan + Claude)
- Google Places API key (optional, for geolocation)

### Environment Variables

Lambda functions require:

```bash
# OpenSearch
OS_HOST=search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com
OS_INDEX=listings-v2  # Use listings-v2 for multi-vector image search

# Bedrock Models
TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0
IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1
LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0

# Image Processing
MAX_IMAGES=0  # 0 = unlimited (process all images per listing)
EMBEDDING_IMAGE_WIDTH=576  # Optimize cost vs quality

# Self-Invocation (upload Lambda only)
MAX_INVOCATIONS=50

# Google Places API (search Lambda only)
GOOGLE_PLACES_API_KEY=your-api-key-here  # Optional
```

### Local Development

```bash
# Install dependencies
pip install boto3 opensearch-py requests requests-aws4auth pytz

# Set AWS credentials
export AWS_PROFILE=default
export AWS_REGION=us-east-1

# Run local indexing (recommended - much faster than Lambda)
python3 index_local.py --file slc_listings.json --index listings-v2

# Test search locally
python3 -c "from common import embed_text; print(f'Embedding dimension: {len(embed_text(\"test\"))}')"

# Verify OpenSearch connection
python3 -c "from common import os_client; print(os_client.info())"
```

See [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md) for production deployment.

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| **Search Latency** | 2-5s (fully indexed), 60-120s (partial index) |
| **Indexing Speed** | 50-60 listings/min (local, parallel) |
| **Indexing Time** | ~65 minutes for 3,904 listings (cold cache) |
| **Cache Hit Rate** | 90%+ (vision), 95%+ (geolocation) |
| **Dataset Size** | 3,904 listings (Salt Lake City, UT) |
| **Images per Listing** | Unlimited (avg ~10 images at 576px) |
| **Vector Dimensions** | 1024 (Titan embeddings) |
| **Success Rate** | 99%+ (with exponential backoff retries) |
| **Concurrent Processing** | 20 listings in parallel, 10 images per listing |

---

## 💰 Cost Analysis

### Monthly Operational Costs

| Service | Configuration | Monthly Cost |
|---------|--------------|--------------|
| OpenSearch | t3.small.search (1 instance) | $33.84 |
| EC2 (UI) | t2.micro | $8.76 |
| Lambda | hearth-search (100 req/day) | $1.50 |
| Lambda | hearth-upload-listings | $10.00/month |
| DynamoDB | 3 tables (on-demand) | $5.00 |
| Bedrock | Titan + Claude (100 searches/day) | $3.00 |
| Google Places | ~50 cache misses/day | $25.50 |
| S3 | Storage + transfers | $0.50 |
| **TOTAL** | | **~$88/month** |

### One-Time Indexing Costs

**Full re-index (3,904 listings, ~39,040 images):**
- Text embeddings: 3,904 × $0.0001 = $0.39
- Image embeddings: 39,040 × $0.0008 = $31.23
- Claude Haiku Vision: 39,040 × $0.00025 = $9.76
- S3 data transfer: 26 GB × $0.09/GB = $2.34
- **Total: ~$43.72** (first run, cold cache)

**With unified caching (90%+ hit rate on re-index):**
- Text: 390 × $0.0001 = $0.04
- Images: 3,904 × $0.0008 = $3.12
- Vision: 3,904 × $0.00025 = $0.98
- S3 data transfer: ~$0.23
- **Total: ~$4.37** (90% savings!)

**Per-listing cost:** $0.0112 (first run), $0.0011 (cached)

---

## 📁 Project Structure

```
hearth_backend_new/
├── common.py                  # Shared utilities (embeddings, caching, OpenSearch)
├── search.py                  # Search Lambda handler
├── upload_listings.py         # Indexing Lambda handler
├── index_local.py            # Local indexing script (recommended)
│
├── docs/                      # Comprehensive documentation
│   ├── API_INTEGRATION.md     # API reference with code examples
│   ├── BACKEND_ARCHITECTURE.md # System architecture and data flow
│   └── CODE_REFERENCE.md      # Function-level documentation
│
├── scripts/                   # Utility scripts
│   └── index_listings.sh     # Bash wrapper for local indexing
│
├── AWS_DEPLOYMENT_GUIDE.md   # AWS setup and deployment
├── INDEXING_GUIDE.md         # Indexing instructions
└── README.md                 # This file
```

---

## 🔍 Usage Examples

### Search API

```bash
# Basic search
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "granite countertops", "limit": 10, "index": "listings-v2"}'

# Search with filters
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "modern homes with pool",
    "limit": 15,
    "index": "listings-v2",
    "filters": {
      "price_max": 600000,
      "beds_min": 3,
      "baths_min": 2
    }
  }'

# Search with boost mode enabled (better visual style matching)
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "craftsman style home", "limit": 10, "index": "listings-v2", "boost_mode": true}'
```

### Python

```python
import requests

# Basic search
response = requests.post(
    "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search",
    json={
        "query": "vaulted ceilings",
        "limit": 10,
        "index": "listings-v2"
    }
)

data = response.json()
print(f"Found {data['total']} results in {data['took_ms']}ms")

for result in data["results"]:
    print(f"\n{result['address']['streetAddress']} - ${result['price']:,}")
    print(f"  Bedrooms: {result['bedrooms']} | Bathrooms: {result['bathrooms']}")
    print(f"  Features: {', '.join(result.get('image_tags', [])[:5])}")
    if "nearby_places" in result:
        print(f"  Nearby: {', '.join(p['name'] for p in result['nearby_places'][:3])}")
```

### JavaScript

```javascript
async function searchProperties(query, options = {}) {
  const response = await fetch(
    'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search',
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        query: query,
        limit: options.limit || 15,
        index: 'listings-v2',
        boost_mode: options.boostMode || false,
        filters: options.filters || {}
      })
    }
  );
  const data = await response.json();
  return data;
}

// Usage examples
const results = await searchProperties('blue homes with garage');
console.log(`Found ${results.total} properties in ${results.took_ms}ms`);
console.log(`Showing ${results.results.length} results`);

// With filters
const filtered = await searchProperties('modern homes', {
  limit: 20,
  boostMode: true,
  filters: { price_max: 500000, beds_min: 3 }
});
```

See [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md) for complete examples.

---

## 🚨 Troubleshooting

### Search returns 0 results

**Cause:** Listings still indexing or embeddings invalid

**Check:**
```bash
# Count indexed listings in listings-v2
curl -X GET "https://search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com/listings-v2/_count" \
  --aws-sigv4 "aws:amz:us-east-1:es" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY"
```

**Fix:** Wait for indexing to complete or check [INDEXING_GUIDE.md](INDEXING_GUIDE.md)

### Search is slow (>30s) or timing out

**Cause:** Partial index or OpenSearch optimization needed

**Check:**
- Is indexing still in progress? (search slower on partial index)
- Lambda timeout in CloudWatch logs
- OpenSearch CPU/JVM metrics

**Fix:**
- Wait for indexing to complete (search speeds improve dramatically)
- Increase Lambda timeout: `aws lambda update-function-configuration --function-name hearth-search --timeout 300`
- Increase OpenSearch client timeout in `common.py`

### Indexing stuck or looping

**Cause:** Self-invocation issue or DynamoDB job conflict

**Fix:**
```bash
# Stop all invocations
aws lambda put-function-concurrency \
  --function-name hearth-upload-listings \
  --reserved-concurrent-executions 0 \
  --region us-east-1

# Use local indexing instead (faster and more reliable)
python3 index_local.py --file slc_listings.json --index listings-v2 --batch-size 20
```

### Bedrock throttling errors

**Cause:** Too many concurrent API calls to Bedrock

**Symptoms:**
```
ThrottlingException: Too many requests, please wait before trying again
```

**Fix:**
- Reduce `BEDROCK_SEMAPHORE` value in `upload_listings.py` (currently 10)
- Built-in exponential backoff retry will handle occasional throttling
- For very low limits, reduce to 5 or 8 concurrent calls

See [docs/BACKEND_ARCHITECTURE.md#troubleshooting](docs/BACKEND_ARCHITECTURE.md#troubleshooting) for more.

---

## 📖 Additional Resources

- **Live Demo:** http://54.227.66.148/
- **API Endpoint:** https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search
- **API Status:** ✅ Fully operational
- **Current Index:** `listings-v2` (multi-vector, 3,904 listings)
- **Dataset:** Salt Lake City, UT (Zillow)
- **OpenSearch:** search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com
- **Support:** Check documentation or review Lambda logs in CloudWatch

**Next Steps:**
1. Read [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md) to integrate the API
2. Review [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) to understand the system
3. Follow [INDEXING_GUIDE.md](INDEXING_GUIDE.md) to index your own listings
4. Check [admin_ui/](admin_ui/) for management tools

---

## 📝 License

Proprietary - Hearth Real Estate Search System
