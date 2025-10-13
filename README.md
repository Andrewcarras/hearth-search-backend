# Hearth Real Estate Search System

Advanced multimodal AI-powered real estate search combining natural language processing, computer vision, and geolocation to find properties based on features, architecture style, and proximity to amenities.

---

## 🚀 Quick Start

**Live Demo:** http://34.228.111.56/
**Search API:** https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search
**Status:** ✅ 1,358+ of 1,588 listings indexed (85.5%)

### Try It Now

```bash
# Search for properties with granite countertops
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"q": "granite countertops", "size": 5}'
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
│  http://34.228.111.56/ (Property search with modal details)     │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP POST
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (HTTP API)                       │
│  https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod    │
└───────────────────────────┬──────────────────────────────────────┘
                            │ Invokes
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LAMBDA: hearth-search                         │
│  • Parse query (Claude Haiku)                                   │
│  • Generate embeddings (Bedrock Titan)                          │
│  • Hybrid search (BM25 + kNN text + kNN image)                  │
│  • RRF fusion                                                   │
│  • Enrich with nearby places (Google Places API)                │
└───────────────────┬─────────────────────────────────────────────┘
                    │ Query
                    ▼
        ┌───────────────────────┐
        │   OPENSEARCH CLUSTER  │
        │   1,358+ documents    │
        │   • kNN vectors       │
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
│  │ 1,588 props  │      │ OR Lambda: upload-listings  │         │
│  └──────────────┘      └──────────┬──────────────────┘         │
│                                   │                             │
│                                   ▼                             │
│                    ┌──────────────────────────┐                 │
│                    │ For each listing:        │                 │
│                    │ • Text embedding         │                 │
│                    │ • Image embeddings (10x) │                 │
│                    │ • Vision AI analysis     │                 │
│                    │ • Architecture style     │                 │
│                    └──────────┬───────────────┘                 │
│                               │                                 │
│                               ▼                                 │
│                    ┌─────────────────┐                          │
│                    │ DynamoDB Cache  │                          │
│                    │ (90% cost save) │                          │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

**Key Technologies:**
- **OpenSearch** - Hybrid search (BM25 + kNN with HNSW)
- **Amazon Bedrock** - Titan embeddings (1024-dim) + Claude for NLP
- **DynamoDB** - Caching layer (embeddings, vision, geolocation)
- **Google Places API** - Nearby places enrichment
- **Python 3.11** - Lambda runtime

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
OS_INDEX=listings

# Bedrock Models
TEXT_EMBED_MODEL=amazon.titan-embed-text-v2:0
IMAGE_EMBED_MODEL=amazon.titan-embed-image-v1
LLM_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0

# Image Processing
MAX_IMAGES=10
EMBEDDING_IMAGE_WIDTH=576

# Self-Invocation (upload Lambda only)
MAX_INVOCATIONS=50

# Google Places API (search Lambda only)
GOOGLE_PLACES_API_KEY=your-api-key-here  # Optional
```

### Local Development

```bash
# Install dependencies
pip install boto3 opensearch-py requests requests-aws4auth

# Set AWS credentials
export AWS_PROFILE=default

# Run local indexing (recommended)
python index_local.py

# Test search locally
python -c "from common import embed_text; print(len(embed_text('test')))"
```

See [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md) for production deployment.

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| **Search Latency** | 500-800ms (warm), 2-3s (cold start) |
| **Indexing Speed** | 30-40 seconds per listing |
| **Cache Hit Rate** | 90% (embeddings), 95% (geolocation) |
| **Dataset Size** | 1,588 listings (Murray, UT) |
| **Images per Listing** | Up to 10 (576px for embeddings) |
| **Vector Dimensions** | 1024 (Titan embeddings) |
| **Success Rate** | 99.9% (with retries) |

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

**Full re-index (1,588 listings):**
- Text embeddings: 1,588 × $0.0001 = $0.16
- Image embeddings: 15,880 × $0.0003 = $4.76
- Claude Vision: 15,880 × $0.00025 = $3.97
- **Total: ~$8.89** (without caching)

**With DynamoDB caching (90% hit rate):**
- Text: 159 × $0.0001 = $0.02
- Images: 1,588 × $0.0003 = $0.48
- Vision: 1,588 × $0.00025 = $0.40
- **Total: ~$0.90** (90% savings!)

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
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"q": "granite countertops", "size": 10}'

# Search with filters
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{
    "q": "modern homes with pool",
    "size": 15,
    "filters": {
      "price_max": 600000,
      "beds_min": 3,
      "baths_min": 2
    }
  }'
```

### Python

```python
import requests

response = requests.post(
    "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search",
    json={"q": "vaulted ceilings", "size": 10}
)

data = response.json()
for result in data["results"]:
    print(f"{result['address']['streetAddress']} - ${result['price']:,}")
    print(f"  Features: {', '.join(result['image_tags'][:5])}")
    if "nearby_places" in result:
        print(f"  Nearby: {', '.join(p['name'] for p in result['nearby_places'][:3])}")
```

### JavaScript

```javascript
async function searchProperties(query) {
  const response = await fetch(
    'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search',
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({q: query, size: 15})
    }
  );
  const data = await response.json();
  return data.results;
}

// Usage
const results = await searchProperties('blue homes with garage');
console.log(`Found ${results.length} properties`);
```

See [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md) for complete examples.

---

## 🚨 Troubleshooting

### Search returns 0 results

**Cause:** Listings still indexing or embeddings invalid

**Check:**
```bash
# Count indexed listings
curl https://search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com/listings/_count
```

**Fix:** Wait for indexing to complete or check [INDEXING_GUIDE.md](INDEXING_GUIDE.md)

### Search is slow (>2s)

**Cause:** OpenSearch cold start or Lambda cold start

**Check:**
- CloudWatch metrics for OpenSearch CPU/JVM
- Lambda cold start logs

**Fix:** Use Lambda provisioned concurrency or scale up OpenSearch cluster

### Indexing stuck or looping

**Cause:** Self-invocation issue or DynamoDB job conflict

**Fix:**
```bash
# Stop all invocations
aws lambda put-function-concurrency \
  --function-name hearth-upload-listings \
  --reserved-concurrent-executions 0 \
  --region us-east-1

# Use local indexing instead
python index_local.py
```

See [docs/BACKEND_ARCHITECTURE.md#troubleshooting](docs/BACKEND_ARCHITECTURE.md#troubleshooting) for more.

---

## 📖 Additional Resources

- **Live Demo:** http://34.228.111.56/
- **API Status:** ✅ Fully operational
- **Dataset:** 1,588 listings from Murray, UT (Zillow)
- **Support:** Check documentation or review Lambda logs

**Next Steps:**
1. Read [docs/API_INTEGRATION.md](docs/API_INTEGRATION.md) to integrate the API
2. Review [docs/BACKEND_ARCHITECTURE.md](docs/BACKEND_ARCHITECTURE.md) to understand the system
3. Follow [INDEXING_GUIDE.md](INDEXING_GUIDE.md) to index your own listings

---

## 📝 License

Proprietary - Hearth Real Estate Search System
