# Hearth Backend - Technical Documentation

**Version:** 1.0
**Last Updated:** October 7, 2025
**Author:** AI-Assisted Development

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [How It Works](#how-it-works)
3. [API Reference](#api-reference)
4. [Frontend Integration Guide](#frontend-integration-guide)
5. [Data Pipeline](#data-pipeline)
6. [Search Algorithm](#search-algorithm)
7. [Cost Analysis](#cost-analysis)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### System Diagram

```
┌─────────────────┐
│   Zillow Data   │
│   (S3 Bucket)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  hearth-upload-listings Lambda                  │
│  ├─ Extract property details                    │
│  ├─ Generate text embeddings (Bedrock Titan)    │
│  ├─ Process images (up to 20 per listing)       │
│  │  ├─ Deduplicate by hash                      │
│  │  ├─ Generate image embeddings (Bedrock)      │
│  │  └─ Extract visual labels (Rekognition)      │
│  └─ Index to OpenSearch                         │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │  OpenSearch   │
         │  ├─ BM25      │
         │  ├─ kNN Text  │
         │  └─ kNN Image │
         └───────┬───────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│  hearth-search Lambda                           │
│  ├─ Parse query with Claude LLM                 │
│  ├─ Generate query embedding                    │
│  ├─ Execute 3 parallel searches:                │
│  │  ├─ BM25 (keyword matching)                  │
│  │  ├─ kNN text (semantic similarity)           │
│  │  └─ kNN image (visual similarity)            │
│  ├─ Fuse results with RRF algorithm             │
│  └─ Return ranked results                       │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │   Frontend    │
         │  (Your App)   │
         └───────────────┘
```

### AWS Services Used

| Service | Purpose | Monthly Cost (Est.) |
|---------|---------|---------------------|
| **Lambda** | Serverless compute for upload & search | ~$5-10 |
| **OpenSearch** | Vector database with kNN search | ~$100-150 |
| **Bedrock** | AI models (Titan embeddings, Claude LLM) | ~$20-50 |
| **Rekognition** | Image label detection | ~$10-20 |
| **S3** | Store property data & images | ~$5 |
| **EC2** (optional) | Host demo UI | ~$7.50 (t3.micro) |

**Total:** ~$150-250/month for production workload

---

## How It Works

### 1. Data Ingestion Pipeline

**Input:** Zillow property JSON data in S3

**Process:**

```python
# 1. Extract core fields from messy Zillow JSON
{
  "zpid": "12345678",
  "address": "123 Main St",
  "price": 450000,
  "beds": 3,
  "baths": 2,
  "description": "Beautiful modern home...",
  "images": ["url1", "url2", ...]
}

# 2. Generate text embedding (1024-dim vector)
text_embedding = bedrock.embed_text(description + llm_profile)

# 3. Process images (deduplicated)
for image_url in images[:20]:
    image_bytes = download(image_url)
    hash = md5(image_bytes)

    if hash not in seen:
        # Generate image embedding
        image_embedding = bedrock.embed_image(image_bytes)

        # Extract visual labels
        labels = rekognition.detect_labels(image_bytes)
        # Returns: ["white", "brick", "pool", "modern", ...]

# 4. Average image embeddings
avg_image_embedding = mean(all_image_embeddings)

# 5. Index to OpenSearch
opensearch.index({
  "zpid": "12345678",
  "address": "123 Main St",
  "vector_text": [0.123, 0.456, ...],    # 1024 dims
  "vector_image": [0.789, 0.012, ...],   # 1024 dims
  "feature_tags": ["pool", "garage"],     # From LLM
  "image_tags": ["white", "brick"],       # From Rekognition
  "has_valid_embeddings": true
})
```

**Key Features:**
- **Duplicate image detection** using MD5 hashing (saves ~40% API calls)
- **Fallback descriptions** generated from address/beds/baths when missing
- **Robust error handling** - continues processing even if some images fail
- **Self-invocation** for large batches (Lambda timeout handling)

### 2. Search Pipeline

**Input:** Natural language query from user

**Process:**

```python
# Step 1: Parse query with Claude LLM
query = "3 bedroom house with pool under 500k"

llm_response = claude.parse_query(query)
# Returns:
{
  "must_have": ["pool"],           # Tags that MUST be present
  "nice_to_have": [],              # Optional tags
  "hard_filters": {
    "beds_min": 3,
    "price_max": 500000
  }
}

# Step 2: Generate query embedding
query_vector = bedrock.embed_text(query)

# Step 3: Execute 3 parallel searches
results = await asyncio.gather(
    # A. BM25 - Traditional keyword search
    opensearch.search({
      "query": {
        "bool": {
          "must": {
            "multi_match": {
              "query": query,
              "fields": ["description^3", "llm_profile^2", "address^0.5"]
            }
          },
          "filter": [
            {"range": {"beds": {"gte": 3}}},
            {"range": {"price": {"lte": 500000}}},
            {"term": {"has_valid_embeddings": true}}
          ]
        }
      }
    }),

    # B. kNN Text - Semantic similarity on descriptions
    opensearch.knn_search({
      "knn": {
        "vector_text": {
          "vector": query_vector,
          "k": 100
        }
      },
      "filter": [...same filters...]
    }),

    # C. kNN Image - Visual similarity on photos
    opensearch.knn_search({
      "knn": {
        "vector_image": {
          "vector": query_vector,  # Same vector!
          "k": 100
        }
      },
      "filter": [...same filters...]
    })
)

# Step 4: Fuse results with Reciprocal Rank Fusion (RRF)
# RRF formula: score = sum(1 / (k + rank)) for each list
# k = 60 (constant)

fused_results = []
for doc_id in all_unique_docs:
    score = 0
    for result_list in [bm25, knn_text, knn_image]:
        rank = result_list.index(doc_id) + 1  # 1-indexed
        score += 1 / (60 + rank)
    fused_results.append((doc_id, score))

# Step 5: Boost results with all must-have tags
for result in fused_results:
    tags = result.feature_tags + result.image_tags
    if "pool" in tags:  # Has all must-have tags
        result.score *= 1.5  # 50% boost

# Step 6: Sort and return top N
return sorted(fused_results, key=lambda x: x.score, reverse=True)[:20]
```

**Why This Works:**

1. **BM25** catches exact keyword matches ("pool" in description)
2. **kNN Text** finds semantic matches (e.g., "swimming area" → pool)
3. **kNN Image** finds visual matches (actual pool photos)
4. **RRF** democratically combines all 3 approaches
5. **Tag boosting** ensures required features appear first

---

## API Reference

### Search Endpoint

**Function:** `hearth-search` (AWS Lambda)

#### Request Format

```json
{
  "q": "3 bedroom house with pool under 500k",
  "size": 20,
  "filters": {
    "price_min": 200000,
    "price_max": 500000,
    "beds_min": 3,
    "baths_min": 2,
    "acreage_min": 0.25,
    "acreage_max": 5.0
  }
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | ✅ | Natural language search query |
| `size` | integer | ❌ | Number of results (default: 30, max: 100) |
| `filters` | object | ❌ | Explicit numeric filters |
| `filters.price_min` | integer | ❌ | Minimum price in dollars |
| `filters.price_max` | integer | ❌ | Maximum price in dollars |
| `filters.beds_min` | integer | ❌ | Minimum bedrooms |
| `filters.baths_min` | number | ❌ | Minimum bathrooms (can be decimal) |
| `filters.acreage_min` | number | ❌ | Minimum lot size in sqft |
| `filters.acreage_max` | number | ❌ | Maximum lot size in sqft |

#### Response Format

```json
{
  "ok": true,
  "results": [
    {
      "id": "12345678",
      "score": 11.98,
      "boosted": true,
      "address": "2203 E Carriage Ln S #55",
      "city": "Salt Lake City",
      "state": "UT",
      "zip_code": "84117",
      "price": 385900,
      "beds": 3,
      "baths": 2,
      "acreage": 435,
      "description": "Beautiful home...",
      "llm_profile": "Modern 3-bedroom home...",
      "feature_tags": ["pool", "garage", "granite_counters"],
      "image_tags": ["white", "brick", "modern"]
    }
  ],
  "total": 10,
  "must_have": ["pool"]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Request success status |
| `results` | array | List of matching properties |
| `results[].id` | string | Zillow property ID (zpid) |
| `results[].score` | number | Relevance score (higher = better match) |
| `results[].boosted` | boolean | True if property has all must-have tags |
| `results[].address` | string | Street address |
| `results[].city` | string | City name |
| `results[].state` | string | State code (e.g., "UT") |
| `results[].zip_code` | string | ZIP code |
| `results[].price` | integer | Price in dollars (null if not listed) |
| `results[].beds` | number | Number of bedrooms |
| `results[].baths` | number | Number of bathrooms |
| `results[].acreage` | number | Lot size in square feet |
| `results[].description` | string | Property description |
| `results[].llm_profile` | string | AI-generated summary |
| `results[].feature_tags` | array | Tags from text (LLM-extracted) |
| `results[].image_tags` | array | Tags from images (Rekognition) |
| `total` | integer | Total number of results returned |
| `must_have` | array | Tags extracted as required by LLM |

---

## Frontend Integration Guide

### Option 1: Direct Lambda Invoke (AWS SDK)

**Best for:** Applications already using AWS SDK

```javascript
// React/Next.js example
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";

const client = new LambdaClient({ region: "us-east-1" });

async function searchProperties(query, filters = {}) {
  const payload = {
    q: query,
    size: 20,
    ...(Object.keys(filters).length > 0 && { filters })
  };

  const command = new InvokeCommand({
    FunctionName: "hearth-search",
    Payload: JSON.stringify(payload)
  });

  const response = await client.send(command);
  const result = JSON.parse(new TextDecoder().decode(response.Payload));
  const body = JSON.parse(result.body);

  return body;
}

// Usage
const results = await searchProperties(
  "3 bedroom house with pool",
  { price_max: 500000, beds_min: 3 }
);

console.log(`Found ${results.total} properties`);
console.log(`Must-have tags: ${results.must_have.join(", ")}`);

results.results.forEach(property => {
  console.log(`${property.address} - $${property.price.toLocaleString()}`);
  console.log(`  Beds: ${property.beds}, Baths: ${property.baths}`);
  console.log(`  Score: ${property.score} ${property.boosted ? "⭐" : ""}`);
});
```

### Option 2: API Gateway REST API

**Best for:** Public-facing applications, mobile apps

**Setup API Gateway:**

```bash
# Create REST API
aws apigateway create-rest-api \
  --name "hearth-search-api" \
  --region us-east-1

# Create /search resource and POST method
# Integrate with hearth-search Lambda
# Deploy to stage (e.g., "prod")
```

**Frontend code:**

```javascript
// React/Next.js with fetch
async function searchProperties(query, filters = {}) {
  const response = await fetch('https://your-api-id.execute-api.us-east-1.amazonaws.com/prod/search', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      q: query,
      size: 20,
      filters
    })
  });

  const data = await response.json();
  return data;
}

// Usage in React component
function SearchPage() {
  const [results, setResults] = useState([]);
  const [query, setQuery] = useState("");

  const handleSearch = async () => {
    const data = await searchProperties(query);
    setResults(data.results);
  };

  return (
    <div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search properties..."
      />
      <button onClick={handleSearch}>Search</button>

      {results.map(property => (
        <PropertyCard key={property.id} property={property} />
      ))}
    </div>
  );
}
```

### Option 3: Backend Proxy (Recommended for Production)

**Best for:** Security, rate limiting, caching

**Node.js/Express example:**

```javascript
// server.js
const express = require('express');
const { LambdaClient, InvokeCommand } = require("@aws-sdk/client-lambda");

const app = express();
const lambda = new LambdaClient({ region: "us-east-1" });

app.use(express.json());

app.post('/api/search', async (req, res) => {
  try {
    const { q, size = 20, filters = {} } = req.body;

    // Validate input
    if (!q || q.trim().length === 0) {
      return res.status(400).json({ error: 'Query required' });
    }

    // Rate limiting (example)
    // await rateLimiter.check(req.ip);

    // Invoke Lambda
    const command = new InvokeCommand({
      FunctionName: "hearth-search",
      Payload: JSON.stringify({ q, size, filters })
    });

    const response = await lambda.send(command);
    const result = JSON.parse(new TextDecoder().decode(response.Payload));
    const body = JSON.parse(result.body);

    // Optional: Cache results
    // await cache.set(`search:${q}`, body, 3600);

    res.json(body);
  } catch (error) {
    console.error('Search error:', error);
    res.status(500).json({ error: 'Search failed' });
  }
});

app.listen(3000);
```

**Frontend:**

```javascript
// Simple fetch to your backend
async function searchProperties(query, filters = {}) {
  const response = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q: query, filters })
  });

  return await response.json();
}
```

### Full React Component Example

```jsx
import React, { useState } from 'react';

function PropertySearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    priceMin: '',
    priceMax: '',
    bedsMin: '',
    bathsMin: ''
  });

  const handleSearch = async () => {
    setLoading(true);

    // Build filters object (only include non-empty values)
    const activeFilters = {};
    if (filters.priceMin) activeFilters.price_min = parseInt(filters.priceMin);
    if (filters.priceMax) activeFilters.price_max = parseInt(filters.priceMax);
    if (filters.bedsMin) activeFilters.beds_min = parseInt(filters.bedsMin);
    if (filters.bathsMin) activeFilters.baths_min = parseFloat(filters.bathsMin);

    try {
      const data = await searchProperties(query, activeFilters);
      setResults(data.results);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="property-search">
      <div className="search-box">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Try: 3 bedroom house with pool under 500k"
          onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
        />

        <div className="filters">
          <input
            type="number"
            placeholder="Min Price"
            value={filters.priceMin}
            onChange={(e) => setFilters({...filters, priceMin: e.target.value})}
          />
          <input
            type="number"
            placeholder="Max Price"
            value={filters.priceMax}
            onChange={(e) => setFilters({...filters, priceMax: e.target.value})}
          />
          <input
            type="number"
            placeholder="Min Beds"
            value={filters.bedsMin}
            onChange={(e) => setFilters({...filters, bedsMin: e.target.value})}
          />
          <input
            type="number"
            placeholder="Min Baths"
            value={filters.bathsMin}
            onChange={(e) => setFilters({...filters, bathsMin: e.target.value})}
          />
        </div>

        <button onClick={handleSearch} disabled={loading}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {results.length > 0 && (
        <div className="results">
          <h2>Found {results.length} properties</h2>

          {results.map(property => (
            <div key={property.id} className="property-card">
              <h3>{property.address}</h3>
              <p>{property.city}, {property.state} {property.zip_code}</p>

              <div className="details">
                <span>${property.price?.toLocaleString() || 'N/A'}</span>
                <span>{property.beds} beds</span>
                <span>{property.baths} baths</span>
              </div>

              {property.boosted && <span className="badge">Best Match ⭐</span>}

              <p className="description">
                {property.description?.substring(0, 200)}...
              </p>

              <div className="tags">
                {property.feature_tags?.map(tag => (
                  <span key={tag} className="tag">{tag}</span>
                ))}
              </div>

              <a
                href={`https://www.zillow.com/homedetails/${property.id}_zpid/`}
                target="_blank"
                rel="noopener noreferrer"
              >
                View on Zillow →
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

## Data Pipeline

### Upload Process (Detailed)

**Trigger:** Upload batch of 10 listings at a time

```python
# upload_listings.py - handler function

def handler(event, context):
    # 1. Load listings from S3 or event payload
    listings = load_listings(event)

    # 2. Ensure OpenSearch index exists with correct mapping
    create_index_if_needed()

    # 3. Process each listing in batch
    actions = []
    for listing in listings[:10]:  # Batch of 10
        # Extract core fields
        core = extract_core_fields(listing)

        # Build full document with embeddings
        doc = build_document(core, listing.images)

        actions.append({
            "_id": core["zpid"],
            "_source": doc
        })

    # 4. Bulk index to OpenSearch
    bulk_upsert(actions)

    # 5. Self-invoke for next batch if needed
    if len(listings) > 10:
        lambda_client.invoke(
            FunctionName=context.function_name,
            InvocationType='Event',  # Async
            Payload=json.dumps({
                "start": event["start"] + 10,
                "limit": 10
            })
        )
```

**Image Processing Pipeline:**

```python
def build_document(core, image_urls):
    # Deduplicate images by hash
    seen_hashes = set()
    image_vectors = []
    image_tags = set()

    for url in image_urls[:20]:  # Max 20 images
        # Download image
        image_bytes = requests.get(url).content

        # Check for duplicates
        img_hash = hashlib.md5(image_bytes).hexdigest()
        if img_hash in seen_hashes:
            continue
        seen_hashes.add(img_hash)

        # Generate embedding (1024-dim vector)
        try:
            vector = bedrock.invoke_model(
                modelId="amazon.titan-embed-image-v1",
                body=json.dumps({"inputImage": base64_encode(image_bytes)})
            )
            image_vectors.append(vector)
        except Exception as e:
            logger.warning(f"Image embedding failed: {e}")

        # Extract visual labels
        try:
            labels = rekognition.detect_labels(Image={"Bytes": image_bytes})
            for label in labels["Labels"]:
                if label["Confidence"] > 80:  # High confidence only
                    image_tags.add(label["Name"].lower())
        except Exception as e:
            logger.warning(f"Label detection failed: {e}")

    # Average all image vectors
    avg_image_vector = mean(image_vectors) if image_vectors else None

    return {
        **core,
        "vector_text": text_embedding,
        "vector_image": avg_image_vector,
        "image_tags": sorted(image_tags),
        "has_valid_embeddings": avg_image_vector is not None
    }
```

---

## Search Algorithm

### Reciprocal Rank Fusion (RRF)

RRF is a simple but effective algorithm for combining ranked lists from different retrieval methods.

**Formula:**

```
For each document d:
  RRF_score(d) = Σ (1 / (k + rank_i(d)))

Where:
  - rank_i(d) = position of document d in result list i (1-indexed)
  - k = constant (we use 60)
  - Σ = sum across all result lists
```

**Example:**

```python
# Document appears in multiple lists:
doc_123 in BM25 results at position 3
doc_123 in kNN_text results at position 1
doc_123 in kNN_image results at position 5

# RRF score calculation:
score = 1/(60+3) + 1/(60+1) + 1/(60+5)
      = 1/63 + 1/61 + 1/65
      = 0.0159 + 0.0164 + 0.0154
      = 0.0477

# Documents appearing high in multiple lists get higher scores!
```

**Why RRF Works:**

1. **No score normalization needed** - Works directly with ranks
2. **Equal weighting** - All search strategies contribute equally
3. **Handles missing documents** - If doc only in 1 list, still gets score
4. **Simple & effective** - Beats complex ML fusion in many cases

### Tag Boosting

After RRF fusion, we apply a final boost for must-have tags:

```python
must_have_tags = ["pool", "garage"]

for result in results:
    all_tags = result.feature_tags + result.image_tags

    if all(tag in all_tags for tag in must_have_tags):
        result.score *= 1.5  # 50% boost
        result.boosted = True
```

This ensures properties with all required features appear first.

---

## Cost Analysis

### Per-Search Costs

**Breakdown for 1 search query:**

| Component | Cost | Notes |
|-----------|------|-------|
| Lambda invocation | $0.0000002 | 1 request |
| Lambda compute | $0.0000167 | 1s @ 1GB RAM |
| Bedrock text embedding | $0.0001 | 1 embedding (query) |
| Claude LLM parsing | $0.00025 | ~1000 tokens |
| OpenSearch queries | $0.00002 | 3 parallel searches |
| **Total per search** | **$0.00044** | **~450 searches per $1** |

### Per-Upload Costs (With Images)

**Breakdown for 1 property with 20 images:**

| Component | Cost | Notes |
|-----------|------|-------|
| Lambda invocation | $0.0000002 | 1 request |
| Lambda compute | $0.0133 | 60s @ 2GB RAM |
| Bedrock text embedding | $0.0001 | 1 text embedding |
| Bedrock image embeddings | $0.0120 | 12 images (after dedup) @ $0.001 each |
| Rekognition labels | $0.0120 | 12 images @ $0.001 each |
| Claude LLM | $0.0005 | Feature extraction |
| OpenSearch indexing | $0.00001 | Bulk index operation |
| **Total per property** | **$0.0379** | **~$60 for 1,588 listings** |

### Monthly Operating Costs (Production)

**Assumptions:** 10,000 searches/month, 1,588 properties indexed once

| Service | Monthly Cost |
|---------|--------------|
| Lambda (searches) | $4.40 |
| Lambda (uploads) | $0.02 (one-time) |
| OpenSearch t3.small.search | $35.00 |
| OpenSearch storage (10GB) | $1.00 |
| Bedrock embeddings | $15.00 |
| Rekognition | $12.00 (one-time) |
| Claude LLM | $8.00 |
| S3 storage | $5.00 |
| **Total Monthly** | **~$80** |

**To reduce costs:**
- Use smaller OpenSearch instance (t2.small: $18/month)
- Reduce MAX_IMAGES to 10 (cuts image costs in half)
- Set USE_REKOGNITION=false (saves $12 one-time + ongoing)
- Cache search results in Redis/CloudFront

---

## Troubleshooting

### Common Issues

#### 1. Search returns 0 results

**Causes:**
- Index is empty (upload not complete)
- All documents filtered out by `has_valid_embeddings` flag
- Query filters too restrictive

**Debug:**
```bash
# Check document count
aws lambda invoke \
  --function-name hearth-debug \
  --region us-east-1 \
  debug_output.json

# Check if filtering is issue - search with no filters
curl -X POST http://your-api/search \
  -H "Content-Type: application/json" \
  -d '{"q":"house","size":100}'
```

#### 2. Image recognition not working

**Symptoms:** `image_tags` array is empty in results

**Causes:**
- `USE_REKOGNITION=false` in Lambda environment
- `MAX_IMAGES=0` in Lambda environment
- Image download failures (broken URLs)

**Fix:**
```bash
# Check Lambda config
aws lambda get-function-configuration \
  --function-name hearth-upload-listings \
  | jq '.Environment.Variables'

# Should show:
# "USE_REKOGNITION": "true"
# "MAX_IMAGES": "20"

# Update if needed
aws lambda update-function-configuration \
  --function-name hearth-upload-listings \
  --environment "Variables={...,MAX_IMAGES=20,USE_REKOGNITION=true}"
```

#### 3. Upload Lambda timing out

**Symptoms:** CloudWatch shows timeout after 900s

**Causes:**
- Processing too many images per listing
- Bedrock API throttling
- Network issues downloading images

**Solutions:**
- Reduce `MAX_IMAGES` to 10
- Increase batch size from 10 to 5
- Add exponential backoff for Bedrock calls

#### 4. High costs

**Symptoms:** AWS bill higher than expected

**Causes:**
- Re-uploading same data multiple times
- Too many images per listing
- OpenSearch instance too large

**Solutions:**
```bash
# 1. Check if you're re-indexing unnecessarily
# Stop duplicate uploads

# 2. Reduce image processing
aws lambda update-function-configuration \
  --function-name hearth-upload-listings \
  --environment "Variables={...,MAX_IMAGES=6}"

# 3. Downsize OpenSearch
# t3.small.search → t2.small.search saves $17/month

# 4. Disable Rekognition if not needed
aws lambda update-function-configuration \
  --function-name hearth-upload-listings \
  --environment "Variables={...,USE_REKOGNITION=false}"
```

#### 5. EC2 UI "Unable to locate credentials"

**Cause:** EC2 instance missing IAM role

**Fix:**
```bash
# Attach IAM role
aws ec2 associate-iam-instance-profile \
  --instance-id i-XXXXX \
  --iam-instance-profile Name=hearth-ui-instance-profile

# Restart instance
aws ec2 reboot-instances --instance-ids i-XXXXX
```

---

## Performance Optimization

### Caching Strategy

```javascript
// Node.js backend with Redis cache
const redis = require('redis');
const client = redis.createClient();

app.post('/api/search', async (req, res) => {
  const { q, filters } = req.body;
  const cacheKey = `search:${q}:${JSON.stringify(filters)}`;

  // Check cache first
  const cached = await client.get(cacheKey);
  if (cached) {
    return res.json(JSON.parse(cached));
  }

  // Call Lambda
  const results = await searchLambda(q, filters);

  // Cache for 1 hour
  await client.setEx(cacheKey, 3600, JSON.stringify(results));

  res.json(results);
});
```

### Pagination

```javascript
// Add offset parameter
const payload = {
  q: query,
  size: 20,
  from: page * 20  // Add this
};

// Backend needs to pass this to OpenSearch
opensearch.search({
  from: payload.from,
  size: payload.size,
  query: {...}
});
```

### Debouncing Search Input

```javascript
// React hook for debounced search
import { useState, useEffect } from 'react';

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// Usage
function SearchBox() {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, 500);  // 500ms delay

  useEffect(() => {
    if (debouncedQuery) {
      performSearch(debouncedQuery);
    }
  }, [debouncedQuery]);

  return <input value={query} onChange={(e) => setQuery(e.target.value)} />;
}
```

---

## Appendix

### Environment Variables Reference

**hearth-upload-listings Lambda:**

| Variable | Value | Description |
|----------|-------|-------------|
| `OS_HOST` | `search-xxx.us-east-1.es.amazonaws.com` | OpenSearch endpoint |
| `OS_INDEX` | `listings` | Index name |
| `TEXT_DIM` | `1024` | Text embedding dimensions |
| `IMAGE_DIM` | `1024` | Image embedding dimensions |
| `MAX_IMAGES` | `20` | Max images to process per listing |
| `USE_REKOGNITION` | `true` | Enable image label detection |
| `TEXT_EMBED_MODEL` | `amazon.titan-embed-text-v2:0` | Text embedding model |
| `IMAGE_EMBED_MODEL` | `amazon.titan-embed-image-v1` | Image embedding model |
| `LLM_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` | LLM for parsing |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

**hearth-search Lambda:**

Same as above (uses shared `common.py`)

### Useful Commands

```bash
# Check upload progress
tail -f upload_progress.log

# Monitor with progress bar
./watch_upload.sh

# Test search from CLI
python3 test_search.py "3 bedroom house with pool"

# Check Lambda logs
aws logs tail /aws/lambda/hearth-search --since 10m --follow

# Count indexed documents
aws lambda invoke \
  --function-name hearth-debug \
  --region us-east-1 \
  output.json && cat output.json | jq
```

---

## Support

For issues or questions:
1. Check CloudWatch Logs: `/aws/lambda/hearth-search` and `/aws/lambda/hearth-upload-listings`
2. Review OpenSearch dashboard for index health
3. Test individual components (embeddings, Rekognition) in isolation

**Demo URL:** http://54.234.160.86

**Repository:** Contact your development team for access

---

*Last updated: October 7, 2025*
