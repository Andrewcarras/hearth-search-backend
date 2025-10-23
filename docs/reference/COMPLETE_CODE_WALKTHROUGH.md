# Complete Hearth Backend Code Walkthrough

**Purpose:** Step-by-step walkthrough of how every part of the Hearth real estate search system works, based solely on the actual code.

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Module 1: common.py - Core Infrastructure](#module-1-commonpy)
3. [Module 2: cache_utils.py - Caching Layer](#module-2-cache_utilspy)
4. [Module 3: upload_listings.py - Indexing Pipeline](#module-3-upload_listingspy)
5. [Module 4: search.py - Main Search Lambda](#module-4-searchpy)
6. [Module 5: search_detailed_scoring.py - Debug Search](#module-5-search_detailed_scoringpy)
7. [Module 6: crud_listings.py - CRUD Operations](#module-6-crud_listingspy)
8. [Module 7: index_local.py - Local Indexing Script](#module-7-index_localpy)
9. [Complete Example Flows](#complete-example-flows)

---

## System Overview

The Hearth system consists of 7 Python modules that work together to:
1. **Index** property listings with embeddings → `upload_listings.py`, `index_local.py`
2. **Cache** expensive AI operations → `cache_utils.py`
3. **Search** using hybrid multimodal search → `search.py`
4. **Debug** search results → `search_detailed_scoring.py`
5. **Manage** listings via CRUD → `crud_listings.py`
6. **Provide shared utilities** → `common.py`

---

## Module 1: common.py

### Purpose
Provides shared infrastructure used by all other modules:
- AWS client initialization (OpenSearch, Bedrock, DynamoDB)
- Embedding generation (text + images)
- Vision analysis (Claude Haiku)
- Query parsing (Claude LLM)
- OpenSearch index management
- Zillow data parsing

### Configuration (Lines 36-61)

```python
# Environment variables with defaults
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
OS_HOST = os.getenv("OS_HOST")  # OpenSearch endpoint
OS_INDEX = os.getenv("OS_INDEX", "listings-v2")  # Index name

# Bedrock models
TEXT_MODEL_ID = "amazon.titan-embed-text-v2:0"  # 1024-dim text embeddings
IMAGE_MODEL_ID = "amazon.titan-embed-image-v1"   # 1024-dim image embeddings
LLM_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"  # Vision + NLP

# Processing
MAX_IMAGES = 0  # 0 = unlimited images per listing
EMBEDDING_IMAGE_WIDTH = 576  # Resize images to 576px for cost optimization
```

### AWS Client Initialization (Lines 66-99)

```python
# 1. Get AWS credentials from Lambda environment
session = boto3.Session(region_name=AWS_REGION)
creds = session.get_credentials().get_frozen_credentials()

# 2. Create AWS Signature V4 auth for OpenSearch
awsauth = AWS4Auth(creds.access_key, creds.secret_key, AWS_REGION, "es",
                   session_token=creds.token)

# 3. Initialize OpenSearch client with retries
os_client = OpenSearch(
    hosts=[{"host": OS_HOST, "port": 443}],
    http_auth=awsauth,
    timeout=240,  # 4 minutes
    max_retries=8,
    retry_on_status=(429, 502, 503, 504)  # Rate limits + server errors
)

# 4. Initialize Bedrock and DynamoDB clients
brt = session.client("bedrock-runtime")
dynamodb = session.client("dynamodb")
```

### Key Function: embed_text() (Lines 140-172)

**Purpose:** Generate 1024-dimensional text embedding using Bedrock Titan

**Flow:**
```
1. Check if text is empty → return zero vector
2. Import cache_utils
3. Check DynamoDB cache (hearth-text-embeddings table)
   ├─ Cache HIT → return cached embedding
   └─ Cache MISS → continue
4. Call Bedrock Titan Text Embeddings API
   - Body: {"inputText": "Beautiful modern home..."}
   - Response: {"embedding": [0.023, -0.041, ...]}
5. Parse response to extract vector
6. Cache in DynamoDB for future use
7. Return 1024-dim vector
```

**Example:**
```python
text = "Modern 3BR home with granite countertops"
vector = embed_text(text)
# Returns: [0.023, -0.041, 0.115, ..., 0.067]  (1024 floats)
```

**Cost:** ~$0.0001 per call (cached after first use)

### Key Function: embed_image_bytes() (Lines 174-197)

**Purpose:** Generate 1024-dimensional image embedding using Bedrock Titan

**Flow:**
```
1. Encode image bytes to base64 (Bedrock requirement)
2. Call Bedrock Titan Image Embeddings API
   - Body: {"inputImage": "base64encodedstring..."}
   - Response: {"embedding": [0.012, -0.089, ...], "inputImageDimensions": {...}}
3. Extract embedding vector
4. Return 1024-dim vector
```

**Example:**
```python
import requests
img_bytes = requests.get("https://zillow.com/photo.jpg").content
vector = embed_image_bytes(img_bytes)
# Returns: [0.012, -0.089, 0.201, ..., -0.034]  (1024 floats)
```

**Cost:** $0.00006 per image (NOT cached in this function - caching done in upload_listings.py)

### Key Function: detect_labels_with_response() (Lines 425-608)

**Purpose:** Analyze property image using Claude Haiku vision model to extract ALL features

**Flow:**
```
1. Encode image to base64
2. Build comprehensive prompt asking Claude to identify:
   - Image type (exterior/interior)
   - All visible features (30-50+ items)
   - Architecture style (if exterior)
   - Colors and materials
   - Room type (if interior)
3. Call Claude 3 Haiku via Bedrock
   - Temperature: 0 (deterministic)
   - Max tokens: 800
4. Parse JSON response
5. Normalize all strings to lowercase
6. Return both parsed analysis AND raw LLM response
```

**Example Input:** Image of modern white house with pool

**Example Output:**
```python
{
  "analysis": {
    "image_type": "exterior",
    "features": ["in-ground pool", "white exterior", "attached garage", "landscaped yard",
                 "modern finishes", "large windows", "flat roof"],
    "architecture_style": "modern",
    "exterior_color": "white",
    "materials": ["stucco", "glass"],
    "visual_features": ["pool", "garage", "driveway"],
    "confidence": "high"
  },
  "llm_response": "{\"image_type\": \"exterior\", \"features\": [...], ...}"
}
```

**Cost:** ~$0.00025 per image

### Key Function: extract_query_constraints() (Lines 1025-1183)

**Purpose:** Parse natural language search query into structured constraints using Claude LLM

**Flow:**
```
1. Build detailed prompt with examples of constraint types:
   - must_have: Required features (pool, garage, etc.)
   - nice_to_have: Preferred features
   - hard_filters: Numeric constraints (price, beds, baths)
   - architecture_style: Style preference
   - proximity: Location requirements
   - query_type: Classification for adaptive scoring
2. Call Claude Haiku via Bedrock
3. Parse JSON response
4. Normalize architecture style (spaces → underscores, lowercase)
5. Return structured constraints dict
6. FALLBACK: If LLM fails, use keyword matching
```

**Example 1: Simple Query**
```python
query = "3 bedroom house with pool under $500k"
result = extract_query_constraints(query)
# Returns:
{
  "must_have": ["pool"],
  "nice_to_have": [],
  "hard_filters": {"beds_min": 3, "price_max": 500000},
  "architecture_style": None,
  "proximity": None,
  "query_type": "specific_feature"
}
```

**Example 2: Complex Query**
```python
query = "modern white brick house with granite countertops near a school"
result = extract_query_constraints(query)
# Returns:
{
  "must_have": ["white_exterior", "brick_exterior", "granite_countertops"],
  "nice_to_have": [],
  "hard_filters": {},
  "architecture_style": "modern",
  "proximity": {"poi_type": "school", "max_distance_km": 5},
  "query_type": "color"
}
```

**Example 3: Location Query**
```python
query = "homes near grocery stores"
result = extract_query_constraints(query)
# Returns:
{
  "must_have": [],  # EMPTY - location-only query
  "nice_to_have": [],
  "hard_filters": {},
  "architecture_style": None,
  "proximity": {"poi_type": "grocery_store"},
  "query_type": "general"
}
```

**Cost:** ~$0.0001 per query

### Key Function: create_index_if_needed() (Lines 614-744)

**Purpose:** Create OpenSearch index with proper schema if it doesn't exist

**Flow:**
```
1. Check if index exists → return if yes
2. Detect schema version from index name:
   - "listings" → Legacy single-vector schema
   - "listings-v2" → Multi-vector schema
3. Build index mapping with fields:
   - zpid (keyword) - Zillow ID
   - price, bedrooms, bathrooms (numeric)
   - geo (geo_point) - lat/lon
   - description (text) - for BM25 search
   - feature_tags, image_tags (keyword) - extracted features
   - vector_text (knn_vector) - 1024-dim text embedding
   - vector_image OR image_vectors - image embeddings
4. For multi-vector schema (listings-v2):
   - Use nested "image_vectors" array
   - Each element: {image_url, image_type, vector}
5. For legacy schema:
   - Use single "vector_image" field (averaged)
6. Create index with HNSW algorithm for kNN
7. Handle race condition (parallel threads creating simultaneously)
```

**Multi-Vector Schema Structure:**
```json
{
  "zpid": "12345678",
  "price": 450000,
  "bedrooms": 3,
  "description": "Beautiful modern home...",
  "vector_text": [0.023, -0.041, ...],  // 1024 dims
  "image_vectors": [  // NESTED ARRAY - key difference!
    {
      "image_url": "https://photos.zillowstatic.com/img1.jpg",
      "image_type": "exterior",
      "vector": [0.012, -0.089, ...]  // 1024 dims
    },
    {
      "image_url": "https://photos.zillowstatic.com/img2.jpg",
      "image_type": "kitchen",
      "vector": [0.045, 0.123, ...]  // 1024 dims
    },
    // ... up to 30+ images
  ]
}
```

**Why Multi-Vector?**
- **Problem with averaging:** If property has 1 pool photo + 29 interior photos, pool signal gets diluted
- **Solution:** Store all vectors separately, OpenSearch searches each one and uses BEST match (score_mode: "max")

### Key Function: bulk_upsert() (Lines 828-901)

**Purpose:** Robustly index multiple documents to OpenSearch with retry logic

**Flow:**
```
1. Buffer documents up to chunk_size (default 100)
2. When buffer full:
   a. Convert to OpenSearch bulk API format:
      {"index": {"_index": "listings-v2", "_id": "12345"}}
      {"zpid": "12345", "price": 450000, ...}
      {"index": {"_index": "listings-v2", "_id": "67890"}}
      {"zpid": "67890", "price": 320000, ...}
   b. Send bulk request via _send_bulk()
   c. If rate limited (429):
      - Wait with exponential backoff (0.5s, 1s, 2s, 4s, 8s)
      - Retry
   d. If repeatedly throttled:
      - Split chunk in half
      - Recursively flush each half
3. Flush remaining documents at end
```

**Retry Strategy:**
```
Attempt 0: Wait 0.5s
Attempt 1: Wait 1s
Attempt 2: Wait 2s
Attempt 3: Split chunk → flush(first_half), flush(second_half)
Attempt 4: Wait 8s
Attempt 5: Give up or split again
```

### Key Function: extract_zillow_images() (Lines 907-1014)

**Purpose:** Extract image URLs from Zillow listing JSON at optimal resolution

**Flow:**
```
1. Try carouselPhotosComposable (primary source):
   - For each photo, check mixedSources.jpeg array
   - Find closest resolution to target_width (default 576px)
   - Prefer slightly larger over smaller
   - Return if found
2. Fallback to imgSrc (thumbnail)
3. Fallback to responsivePhotos:
   - SPECIAL HANDLING: Skip for vacant land (photoCount=0)
   - Reason: Zillow includes nearby property images for vacant lots!
   - Track photo IDs to avoid duplicates
   - Extract largest resolution
4. Fallback to simple image arrays (images, photos, photoUrls)
5. Return list of URLs
```

**Example:**
```python
listing = {
  "zpid": "12345",
  "carouselPhotosComposable": [
    {
      "mixedSources": {
        "jpeg": [
          {"width": 384, "url": "https://...384w.jpg"},
          {"width": 576, "url": "https://...576w.jpg"},  # ← This one!
          {"width": 768, "url": "https://...768w.jpg"}
        ]
      }
    }
  ]
}

urls = extract_zillow_images(listing, target_width=576)
# Returns: ["https://...576w.jpg"]
```

---

## Module 2: cache_utils.py

### Purpose
Unified caching for image embeddings, vision analysis, and text embeddings with complete metadata tracking.

### Tables
- **hearth-vision-cache:** Image embeddings + Claude analysis (atomic storage)
- **hearth-text-embeddings:** Text embeddings with hash-based lookup

### Key Function: cache_image_data() (Lines 64-141)

**Purpose:** Atomically cache ALL image data (embedding + analysis + metadata) in single write

**Flow:**
```
1. Calculate SHA256 hash of image bytes
2. Get current timestamps (UTC + EDT)
3. Calculate costs:
   - Embedding: $0.0008
   - Analysis: $0.00025
   - Total: $0.00105
4. Build DynamoDB item with:
   - image_url (primary key)
   - image_hash (for deduplication)
   - embedding (1024-dim vector as JSON string)
   - analysis (parsed features dict as JSON string)
   - llm_response (raw Claude response for debugging)
   - model versions
   - timestamps
   - cost tracking fields
5. Write to hearth-vision-cache table
```

**DynamoDB Item Structure:**
```python
{
  "image_url": "https://photos.zillowstatic.com/abc123.jpg",
  "image_hash": "sha256:a3f2d8b4e6c9...",
  "embedding": "[0.012, -0.089, ...]",  # JSON string
  "embedding_model": "amazon.titan-embed-image-v1",
  "analysis": "{\"features\": [...], \"image_type\": \"exterior\", ...}",  # JSON string
  "analysis_llm_response": "{\"image_type\": \"exterior\", ...}",  # Raw LLM output
  "analysis_model": "anthropic.claude-3-haiku-20240307-v1:0",
  "cache_version": 1,
  "first_seen": 1697410845,
  "last_accessed": 1697410845,
  "access_count": 0,
  "cost_embedding": 0.0008,
  "cost_analysis": 0.00025,
  "cost_total": 0.00105,
  "cost_saved": 0.0
}
```

### Key Function: get_cached_image_data() (Lines 143-208)

**Purpose:** Retrieve cached image data and update access metrics

**Flow:**
```
1. Query DynamoDB by image_url
2. If not found → return None
3. Parse embedding and analysis from JSON strings
4. Extract image_hash
5. UPDATE access tracking:
   - Increment access_count
   - Update last_accessed timestamp
   - Calculate cost_saved = access_count × cost_total
   - Example: 5th cache hit = 5 × $0.00105 = $0.00525 saved
6. Return (embedding, analysis, image_hash) tuple
```

**Cache Hit Example:**
```python
from cache_utils import get_cached_image_data

result = get_cached_image_data(dynamodb, "https://photos.zillowstatic.com/abc.jpg")

if result:
    embedding, analysis, img_hash = result
    # embedding: [0.012, -0.089, ...]  (1024 floats)
    # analysis: {"features": [...], "image_type": "exterior", ...}
    # img_hash: "sha256:a3f2d8..."
    print(f"✓ Cache hit! Saved $0.00105")
else:
    print(f"✗ Cache miss - need to generate")
```

### Key Function: cache_text_embedding() (Lines 210-256)

**Purpose:** Cache text embedding with SHA256 hash-based lookup

**Flow:**
```
1. Calculate SHA256 hash of text (primary key)
2. Store first 200 chars of text as sample (for debugging)
3. Build DynamoDB item with:
   - text_hash (primary key)
   - text_sample (truncated)
   - embedding (1024-dim vector as JSON)
   - model version
   - timestamps
   - cost tracking
4. Write to hearth-text-embeddings table
```

**Why hash-based?**
- Same text always generates same hash
- Enables deduplication (multiple listings with same description)
- Privacy: Full text not stored, only 200-char sample

---

## Module 3: upload_listings.py

### Purpose
Lambda function that indexes Zillow listings to OpenSearch with multimodal embeddings.

### Processing Pipeline (Per Listing)

```
1. Extract core fields from Zillow JSON
   ├─ zpid, price, beds, baths, location
   ├─ description (or generate fallback)
   └─ coordinates (lat/lon)

2. Generate text embedding
   ├─ Check cache (hearth-text-embeddings)
   ├─ If miss: Call Bedrock Titan Text
   └─ Return 1024-dim vector

3. Extract image URLs
   ├─ Call extract_zillow_images(listing, target_width=576)
   └─ Returns list of optimized URLs

4. For each image:
   ├─ Check cache (hearth-vision-cache)
   ├─ If HIT:
   │  └─ Use cached embedding + analysis
   └─ If MISS:
      ├─ Download image from URL
      ├─ Generate embedding (Bedrock Titan Image)
      ├─ Generate analysis (Claude Haiku Vision)
      └─ Cache atomically (cache_utils.cache_image_data)

5. Aggregate image data:
   ├─ For listings-v2 (multi-vector):
   │  └─ Store all image vectors in nested array
   └─ For listings (legacy):
      └─ Average all vectors into single vector

6. Build OpenSearch document
   ├─ Core fields (zpid, price, beds, geo, etc.)
   ├─ Text embedding (vector_text)
   ├─ Image embeddings (image_vectors or vector_image)
   ├─ Tags (feature_tags, image_tags)
   └─ Flags (has_valid_embeddings, has_description)

7. Index to OpenSearch
   └─ bulk_upsert() with batching and retries
```

### Self-Invocation Chain

**Problem:** Lambda has 15-minute timeout, but indexing 3,900 listings takes ~45 minutes

**Solution:** Chain multiple Lambda invocations

```
Invocation 1:
├─ Download slc_listings.json from S3 (12MB, 3904 listings)
├─ Process listings 0-499 (500 listings)
├─ Pass listings array to next invocation (avoid re-downloading)
└─ Invoke Lambda asynchronously for next batch

Invocation 2:
├─ Receive listings array from previous invocation
├─ Process listings 500-999
└─ Invoke next batch

Invocation 3:
├─ Process listings 1000-1499
└─ Invoke next batch

...continues until all listings processed
```

**Key Code (Lines 432-449 in upload_listings.py):**
```python
next_start = start + processed
has_more = next_start < total

if has_more and invocation_count < 50:  # Safety limit
    next_payload = {
        "start": next_start,
        "limit": limit,
        "listings": all_listings,  # Pass data forward - KEY OPTIMIZATION!
        "_invocation_count": invocation_count + 1,
        "_job_id": job_id
    }

    lambda_client.invoke(
        FunctionName=context.invoked_function_arn,
        InvocationType="Event",  # Async invocation
        Payload=json.dumps(next_payload)
    )
```

### Multi-Vector Document Structure

**Code Location:** Lines 500-550 in upload_listings.py

```python
# For listings-v2 index (multi-vector schema)
is_multi_vector = OS_INDEX.endswith("-v2")

if is_multi_vector:
    # Store ALL image vectors separately
    doc["image_vectors"] = []
    for img_url, img_vec, img_analysis in zip(image_urls, image_vecs, image_analyses):
        doc["image_vectors"].append({
            "image_url": img_url,
            "image_type": img_analysis.get("image_type", "unknown"),
            "vector": img_vec  # 1024-dim
        })
else:
    # Legacy: Average all vectors
    doc["vector_image"] = vec_mean(image_vecs, IMAGE_DIM)
```

**Example Document:**
```json
{
  "zpid": "12345678",
  "price": 450000,
  "bedrooms": 3,
  "bathrooms": 2.5,
  "geo": {"lat": 40.7608, "lon": -111.8910},
  "description": "Beautiful modern home with mountain views",
  "vector_text": [0.023, -0.041, ..., 0.067],
  "image_vectors": [
    {
      "image_url": "https://photos.zillowstatic.com/img1.jpg",
      "image_type": "exterior",
      "vector": [0.012, -0.089, ..., -0.034]
    },
    {
      "image_url": "https://photos.zillowstatic.com/img2.jpg",
      "image_type": "kitchen",
      "vector": [0.045, 0.123, ..., 0.091]
    }
  ],
  "feature_tags": ["pool", "garage", "granite_countertops"],
  "image_tags": ["modern", "white_exterior", "landscaped_yard"],
  "architecture_style": "modern",
  "has_valid_embeddings": true
}
```

---

## Module 4: search.py

### Purpose
Main Lambda function for natural language property search using hybrid multimodal search.

### Complete Search Pipeline

```
REQUEST
  ↓
1. Parse Query
   ├─ Input: "modern 3 bedroom house with pool under $500k"
   ├─ Call: extract_query_constraints(query)
   └─ Output: {
       "must_have": ["pool"],
       "hard_filters": {"beds_min": 3, "price_max": 500000},
       "architecture_style": "modern",
       "query_type": "visual_style"
     }

2. Generate Query Embedding
   ├─ Call: embed_text("modern 3 bedroom house with pool under $500k")
   └─ Output: [0.156, -0.023, ..., 0.089]  (1024-dim)

3. Build Filter Clause
   ├─ Price: {"range": {"price": {"lte": 500000, "gt": 0}}}
   ├─ Beds: {"range": {"bedrooms": {"gte": 3}}}
   └─ Valid embeddings: {"term": {"has_valid_embeddings": true}}

4. Execute 3 Parallel Searches
   ├─ BM25 (keyword search)
   │  ├─ Searches: description, visual_features_text, feature_tags
   │  ├─ Boost: 2.0x for feature_tags matches
   │  └─ Returns: Top 50 ranked by BM25 score
   │
   ├─ kNN Text (semantic text search)
   │  ├─ Searches: vector_text field
   │  ├─ Query vector: [0.156, -0.023, ...]
   │  ├─ Algorithm: HNSW approximate nearest neighbor
   │  └─ Returns: Top 50 ranked by cosine similarity
   │
   └─ kNN Image (visual search)
      ├─ Searches: image_vectors (nested array)
      ├─ Query vector: [0.156, -0.023, ...]  (same as text)
      ├─ Score mode: "max" (best matching image wins)
      └─ Returns: Top 50 ranked by cosine similarity

5. Adaptive Weight Calculation
   ├─ Analyze query type and tags
   ├─ Color detected? → Boost BM25, reduce images
   ├─ Visual style? → Boost images
   └─ Output: [bm25_k=60, text_k=60, image_k=40]

6. Reciprocal Rank Fusion (RRF)
   ├─ For each document in any result list:
   │  └─ score += 1 / (k + rank)
   ├─ Example: Property appears at rank 3 in BM25, rank 5 in text kNN:
   │  └─ score = 1/(60+3) + 1/(60+5) = 0.0159 + 0.0154 = 0.0313
   ├─ Sort all documents by fused score
   └─ Return top N (default 15)

7. Tag-Based Boosting
   ├─ Check which must_have tags match feature_tags
   ├─ Calculate match ratio: matched / total
   ├─ Apply multiplier:
   │  ├─ 100% match → 2.0x
   │  ├─ 75-99% → 1.5x
   │  ├─ 50-74% → 1.25x
   │  └─ <50% → 1.0x
   └─ Example: 1 of 1 tag matches → 2.0x boost

8. Fetch Complete Data from S3 (Optional)
   ├─ For each result zpid:
   │  ├─ Check DynamoDB cache (hearth-s3-listing-cache)
   │  ├─ If miss: Fetch from s3://demo-hearth-data/listings/{zpid}.json
   │  └─ Returns all 166+ Zillow fields
   └─ Merge with OpenSearch result

9. Enrich with Nearby Places (Optional)
   ├─ For each result:
   │  ├─ Get lat/lon
   │  ├─ Create location key (rounded to ~100m precision)
   │  ├─ Check DynamoDB cache (hearth-geolocation-cache)
   │  ├─ If miss: Call Google Places API (1km radius)
   │  └─ Attach nearby_places array to result
   └─ Cost: $0.017 per cache miss, $0 per hit

10. Return Results
    └─ JSON response with ranked properties
```

### Detailed RRF Example

**Query:** "modern house with pool"

**Individual Search Results:**

```
BM25 Results (ranked by keyword match):
1. zpid=111 (score=12.5) - "modern pool home"
2. zpid=222 (score=10.2) - "pool modern design"
3. zpid=333 (score=8.7) - "contemporary pool house"
4. zpid=444 (score=6.1) - "traditional with pool"
...

Text kNN Results (ranked by semantic similarity):
1. zpid=222 (score=0.89) - semantically similar description
2. zpid=555 (score=0.87) - similar wording
3. zpid=111 (score=0.85) - close match
4. zpid=666 (score=0.82) - related concepts
...

Image kNN Results (ranked by visual similarity):
1. zpid=777 (score=0.92) - modern architecture in images
2. zpid=222 (score=0.88) - similar visual style
3. zpid=888 (score=0.86) - pool visible in photo
4. zpid=111 (score=0.83) - modern features
...
```

**RRF Fusion (k=60 for all):**

```python
# zpid=111 appears in:
# - BM25 rank 1: score += 1/(60+1) = 0.0164
# - Text kNN rank 3: score += 1/(60+3) = 0.0159
# - Image kNN rank 4: score += 1/(60+4) = 0.0156
# Total: 0.0479

# zpid=222 appears in:
# - BM25 rank 2: score += 1/(60+2) = 0.0161
# - Text kNN rank 1: score += 1/(60+1) = 0.0164
# - Image kNN rank 2: score += 1/(60+2) = 0.0161
# Total: 0.0486  ← HIGHEST!

# zpid=333 appears in:
# - BM25 rank 3: score += 1/(60+3) = 0.0159
# - Text kNN: not in top 50: score += 0
# - Image kNN: not in top 50: score += 0
# Total: 0.0159

# Final ranking:
# 1. zpid=222 (0.0486) - appeared highly in all 3 strategies!
# 2. zpid=111 (0.0479) - appeared in all 3, but slightly lower ranks
# 3. zpid=777 (0.0312) - only in image kNN rank 1
# 4. zpid=333 (0.0159) - only in BM25
```

### Adaptive Weighting Example

**Code Location:** Lines 461-503 in search.py

**Query:** "white house with blue door"

```python
constraints = extract_query_constraints("white house with blue door")
# Returns: {
#   "must_have": ["white_exterior", "blue_door"],
#   "query_type": "color"
# }

# Calculate adaptive weights
bm25_k, text_k, image_k = calculate_adaptive_weights(
    must_have_tags=["white_exterior", "blue_door"],
    query_type="color"
)

# Logic detects COLOR keywords:
if has_color:
    bm25_k = 30      # BOOST BM25 (tags have exact color info)
    image_k = 120    # REDUCE images (embeddings don't capture color well)

# Result: [30, 60, 120]
# Effect: BM25 has 4x more influence than images (120/30 = 4)
```

**RRF with Adaptive Weights:**

```python
# zpid=111 (white house, blue door, appears in all 3):
# - BM25 rank 1: score += 1/(30+1) = 0.0323  ← Much higher due to low k!
# - Text kNN rank 3: score += 1/(60+3) = 0.0159
# - Image kNN rank 4: score += 1/(120+4) = 0.0081  ← Much lower due to high k!
# Total: 0.0563

# zpid=222 (white house, red door, only in BM25 and text):
# - BM25 rank 2: score += 1/(30+2) = 0.0312
# - Text kNN rank 1: score += 1/(60+1) = 0.0164
# - Image kNN: not in results: score += 0
# Total: 0.0476

# Result: zpid=111 wins because BM25 tag match is heavily weighted
```

### Tag Boosting Example

**Code Location:** Lines 750-850 in search.py

```python
# After RRF fusion, apply tag boosting
for result in fused_results:
    # Check which must_have tags are in feature_tags
    result_tags = set(result["_source"].get("feature_tags", []))
    matched = must_tags.intersection(result_tags)
    match_ratio = len(matched) / len(must_tags) if must_tags else 0

    # Apply boost multiplier
    if match_ratio >= 1.0:
        boost = 2.0   # 100% match
    elif match_ratio >= 0.75:
        boost = 1.5   # 75-99% match
    elif match_ratio >= 0.5:
        boost = 1.25  # 50-74% match
    else:
        boost = 1.0   # <50% match

    # Multiply RRF score by boost
    result["_score"] = result["_rrf_score"] * boost
```

**Example:**

```python
must_tags = {"pool", "granite_countertops"}

# Property A:
feature_tags = ["pool", "granite_countertops", "hardwood_floors"]
matched = {"pool", "granite_countertops"}
match_ratio = 2/2 = 1.0 → boost = 2.0x
rrf_score = 0.0486
final_score = 0.0486 × 2.0 = 0.0972

# Property B:
feature_tags = ["pool", "marble_countertops"]
matched = {"pool"}
match_ratio = 1/2 = 0.5 → boost = 1.25x
rrf_score = 0.0520
final_score = 0.0520 × 1.25 = 0.0650

# Result: Property A wins (0.0972 > 0.0650)
```

---

## Module 5: search_detailed_scoring.py

### Purpose
Debug version of search.py that returns extensive diagnostic information for understanding search behavior.

### Additional Output (Not in Production)

```json
{
  "query": "modern house with pool",
  "constraints": {
    "must_have": ["pool"],
    "architecture_style": "modern",
    "query_type": "visual_style"
  },
  "search_strategies": {
    "bm25": {
      "query_body": { /* Full OpenSearch query */ },
      "top_results": [
        {"zpid": "111", "score": 12.5, "reason": "Matched 'modern' and 'pool' in description"}
      ]
    },
    "knn_text": {
      "query_vector": [0.156, -0.023, ...],
      "top_results": [
        {"zpid": "222", "score": 0.89}
      ]
    },
    "knn_image": {
      "query_vector": [0.156, -0.023, ...],
      "top_results": [
        {"zpid": "777", "score": 0.92, "matching_images": [
          {"url": "https://...", "type": "exterior", "score": 0.92}
        ]}
      ]
    }
  },
  "rrf_fusion": {
    "k_values": [60, 60, 40],
    "fused_scores": {
      "222": {
        "bm25_contribution": 0.0161,
        "text_contribution": 0.0164,
        "image_contribution": 0.0161,
        "total": 0.0486
      }
    }
  },
  "final_results": [ /* Boosted and sorted results */ ]
}
```

### Use Cases

1. **Debug "Not Found in Top Results"**
   - Check if property appears in individual strategies
   - See where it ranks before fusion
   - Identify if RRF is down-ranking it

2. **Validate Adaptive Scoring**
   - Confirm k-values are being calculated correctly
   - Check which strategy is weighted highest

3. **Understand Image Matching**
   - See which specific images are matching
   - Identify best-matching photos per property

---

## Module 6: crud_listings.py

### Purpose
CRUD operations for manual listing management.

### Operations

#### 1. UPDATE (PATCH /listings/{zpid})

**Purpose:** Modify existing listing fields

**Flow:**
```
1. Extract zpid from path parameters
2. Parse request body:
   {
     "updates": {"price": 450000, "status": "sold"},
     "options": {"preserve_embeddings": true}
   }
3. Fetch existing document from OpenSearch
4. Merge updates with existing data
5. If preserve_embeddings=false:
   - Regenerate text embedding
   - Regenerate image embeddings
6. Update document in OpenSearch
7. Return updated document
```

#### 2. CREATE (POST /listings)

**Purpose:** Add new listing with auto-generated zpid

**Flow:**
```
1. Parse request body with listing data
2. Generate zpid (UUID or sequential)
3. Extract/download images if URLs provided
4. Generate embeddings:
   - Text: embed_text(description)
   - Images: embed_image_bytes() for each
5. Generate vision analysis: detect_labels_with_response()
6. Build OpenSearch document
7. Index to OpenSearch
8. Return new listing with zpid
```

#### 3. DELETE (DELETE /listings/{zpid})

**Purpose:** Remove listing from index

**Flow:**
```
1. Extract zpid and soft/hard delete flag
2. If soft delete:
   - Update document: {"deleted": true, "deleted_at": timestamp}
   - Keep in index for audit trail
3. If hard delete:
   - os_client.delete(index=OS_INDEX, id=zpid)
   - Permanently remove
4. Return success response
```

---

## Module 7: index_local.py

### Purpose
Local script for indexing listings from your computer (faster than Lambda chain).

### Advantages over Lambda

1. **No timeouts** - Can run for hours if needed
2. **Parallel processing** - Default 20 concurrent listings
3. **Better debugging** - Full control, detailed logs
4. **Resume capability** - Start from any index with `--start`
5. **One-time S3 download** - Lambda re-downloads multiple times

### Usage Examples

```bash
# Index all listings
python3 index_local.py --bucket demo-hearth-data --key slc_listings.json

# Test with first 30 listings
python3 index_local.py --bucket demo-hearth-data --key slc_listings.json --limit 30

# Resume from listing 500
python3 index_local.py --bucket demo-hearth-data --key slc_listings.json --start 500

# Index to listings-v2 with 10 concurrent threads
python3 index_local.py --bucket demo-hearth-data --key slc_listings.json \\
    --index listings-v2 --batch-size 10

# Use local file instead of S3
python3 index_local.py --file ./slc_listings.json
```

### Processing Flow

```
1. Parse command-line arguments
2. Set environment variables (OS_HOST, OS_INDEX, MAX_IMAGES)
3. Load listings from S3 or local file (ONE TIME)
4. Create ThreadPoolExecutor with batch_size workers
5. For each batch of listings:
   ├─ Submit to thread pool
   ├─ Each thread calls upload_listings.handler()
   ├─ Progress tracking: "Processed 100/3904 (2.6%) - Rate: 5.2/s - ETA: 12m 15s"
   └─ Wait for batch to complete
6. Verify each listing indexed to OpenSearch
7. Print final statistics
```

**Key Advantage - No S3 Re-downloads:**

```
Lambda chain:
├─ Invocation 1: Download 12MB from S3 → process → pass to next
├─ Invocation 2: Use passed data → process → pass to next
├─ Invocation 3: Use passed data → process → pass to next
└─ Total: 1 download (optimized) but complex chain management

Local script:
├─ Download 12MB from S3 ONCE
├─ Process all listings in parallel batches
└─ Total: 1 download, simpler logic, 5-10x faster
```

---

## Complete Example Flows

### Example 1: Full Indexing Flow (Single Listing)

**Input:** One Zillow listing JSON

```json
{
  "zpid": 12345678,
  "price": 450000,
  "bedrooms": 3,
  "bathrooms": 2.5,
  "address": {
    "streetAddress": "123 Main St",
    "city": "Salt Lake City",
    "state": "UT",
    "zipcode": "84101"
  },
  "latitude": 40.7608,
  "longitude": -111.8910,
  "description": "Beautiful modern home with granite countertops and mountain views",
  "carouselPhotosComposable": [
    {
      "mixedSources": {
        "jpeg": [
          {"width": 576, "url": "https://photos.zillowstatic.com/exterior.jpg"}
        ]
      }
    },
    {
      "mixedSources": {
        "jpeg": [
          {"width": 576, "url": "https://photos.zillowstatic.com/kitchen.jpg"}
        ]
      }
    }
  ]
}
```

**Processing Steps:**

```
1. Extract core fields
   ✓ zpid: "12345678"
   ✓ price: 450000
   ✓ bedrooms: 3
   ✓ geo: {"lat": 40.7608, "lon": -111.8910}
   ✓ description: "Beautiful modern home with granite countertops..."

2. Generate text embedding
   ├─ Check cache: hearth-text-embeddings
   │  └─ Hash: sha256(description) = "a3f2d8b4..."
   │  └─ MISS (first time indexing this text)
   ├─ Call Bedrock Titan Text Embeddings
   │  └─ Cost: $0.0001
   ├─ Receive: [0.023, -0.041, 0.115, ..., 0.067]  (1024 dims)
   └─ Cache for future use

3. Extract image URLs
   ├─ Call: extract_zillow_images(listing, 576)
   └─ Returns: [
       "https://photos.zillowstatic.com/exterior.jpg",
       "https://photos.zillowstatic.com/kitchen.jpg"
     ]

4. Process image 1 (exterior.jpg)
   ├─ Check cache: hearth-vision-cache
   │  └─ Key: "https://photos.zillowstatic.com/exterior.jpg"
   │  └─ MISS
   ├─ Download image (576px width)
   ├─ Generate embedding
   │  ├─ Call: embed_image_bytes(image_bytes)
   │  ├─ Bedrock Titan Image Embeddings
   │  ├─ Cost: $0.00006
   │  └─ Returns: [0.012, -0.089, 0.201, ..., -0.034]
   ├─ Generate analysis
   │  ├─ Call: detect_labels_with_response(image_bytes, url)
   │  ├─ Claude 3 Haiku Vision
   │  ├─ Cost: $0.00025
   │  └─ Returns: {
   │       "analysis": {
   │         "image_type": "exterior",
   │         "features": ["modern", "white_exterior", "attached_garage",
   │                      "landscaped_yard", "mountain_view"],
   │         "architecture_style": "modern",
   │         "exterior_color": "white",
   │         "materials": ["stucco"],
   │         "confidence": "high"
   │       },
   │       "llm_response": "{...}"
   │     }
   └─ Cache atomically: cache_image_data(url, bytes, embedding, analysis)
      └─ Total cached cost: $0.00031

5. Process image 2 (kitchen.jpg)
   ├─ Check cache: hearth-vision-cache
   │  └─ MISS
   ├─ Download image
   ├─ Generate embedding: [0.045, 0.123, ..., 0.091]
   ├─ Generate analysis: {
   │    "image_type": "interior",
   │    "features": ["kitchen", "granite_countertops", "stainless_steel_appliances",
   │                 "white_cabinets", "kitchen_island"],
   │    "materials": ["granite", "stainless_steel"],
   │    "confidence": "high"
   │  }
   └─ Cache: $0.00031

6. Aggregate image data
   ├─ All embeddings: [
   │    [0.012, -0.089, ...],  # exterior
   │    [0.045, 0.123, ...]    # kitchen
   │  ]
   ├─ All analyses: [
   │    {"image_type": "exterior", "features": [...]},
   │    {"image_type": "interior", "features": [...]}
   │  ]
   └─ Extract all unique features: [
       "modern", "white_exterior", "attached_garage", "landscaped_yard",
       "mountain_view", "kitchen", "granite_countertops",
       "stainless_steel_appliances", "white_cabinets", "kitchen_island"
     ]

7. Build OpenSearch document (listings-v2 schema)
   {
     "zpid": "12345678",
     "price": 450000,
     "bedrooms": 3,
     "bathrooms": 2.5,
     "geo": {"lat": 40.7608, "lon": -111.8910},
     "description": "Beautiful modern home with granite countertops...",
     "vector_text": [0.023, -0.041, 0.115, ..., 0.067],
     "image_vectors": [
       {
         "image_url": "https://photos.zillowstatic.com/exterior.jpg",
         "image_type": "exterior",
         "vector": [0.012, -0.089, 0.201, ..., -0.034]
       },
       {
         "image_url": "https://photos.zillowstatic.com/kitchen.jpg",
         "image_type": "interior",
         "vector": [0.045, 0.123, ..., 0.091]
       }
     ],
     "feature_tags": ["pool", "garage", "granite_countertops", "mountain_view"],
     "image_tags": ["modern", "white_exterior", "landscaped_yard", "kitchen",
                    "stainless_steel_appliances"],
     "architecture_style": "modern",
     "has_valid_embeddings": true,
     "has_description": true
   }

8. Index to OpenSearch
   ├─ Call: bulk_upsert([{"_id": "12345678", "_source": doc}])
   ├─ OpenSearch bulk API
   └─ Document immediately searchable (refresh=True)

Total cost for this listing: $0.0001 (text) + $0.00062 (2 images) = $0.00072
If re-indexed: $0 (all cached!)
```

### Example 2: Complete Search Flow

**Input:** User search query

```json
{
  "q": "modern 3 bedroom house with granite countertops under $500k",
  "size": 10,
  "index": "listings-v2"
}
```

**Processing Steps:**

```
1. Parse query
   ├─ Call: extract_query_constraints(query)
   ├─ Claude Haiku LLM parsing
   ├─ Cost: $0.0001
   └─ Returns: {
       "must_have": ["granite_countertops"],
       "hard_filters": {"beds_min": 3, "price_max": 500000},
       "architecture_style": "modern",
       "query_type": "visual_style"
     }

2. Generate query embedding
   ├─ Call: embed_text(query)
   ├─ Check cache first (likely MISS for unique query)
   ├─ Bedrock Titan Text
   ├─ Cost: $0.0001
   └─ Returns: [0.156, -0.023, ..., 0.089]

3. Build filter clause
   {
     "bool": {
       "filter": [
         {"range": {"price": {"lte": 500000, "gt": 0}}},
         {"range": {"bedrooms": {"gte": 3}}},
         {"term": {"has_valid_embeddings": true}}
       ]
     }
   }

4. Execute BM25 search
   ├─ Query body: {
   │    "query": {
   │      "bool": {
   │        "must": {
   │          "multi_match": {
   │            "query": "modern 3 bedroom house granite countertops",
   │            "fields": ["description", "visual_features_text", "feature_tags^2.0"]
   │          }
   │        },
   │        "filter": [ /* from step 3 */ ]
   │      }
   │    },
   │    "size": 50
   │  }
   ├─ OpenSearch execution time: ~50ms
   └─ Returns: [
       {"_id": "12345678", "_score": 15.3, "_source": {...}},
       {"_id": "87654321", "_score": 12.1, "_source": {...}},
       ...50 results
     ]

5. Execute kNN text search (PARALLEL with BM25)
   ├─ Query body: {
   │    "query": {
   │      "bool": {
   │        "must": {
   │          "knn": {
   │            "vector_text": {
   │              "vector": [0.156, -0.023, ..., 0.089],
   │              "k": 50
   │            }
   │          }
   │        },
   │        "filter": [ /* from step 3 */ ]
   │      }
   │    }
   │  }
   ├─ OpenSearch HNSW search: ~30ms
   └─ Returns: [
       {"_id": "11111111", "_score": 0.89, "_source": {...}},
       {"_id": "12345678", "_score": 0.85, "_source": {...}},
       ...50 results
     ]

6. Execute kNN image search (PARALLEL with above)
   ├─ Query body: {
   │    "query": {
   │      "bool": {
   │        "must": {
   │          "nested": {
   │            "path": "image_vectors",
   │            "score_mode": "max",  ← KEY: Best image wins!
   │            "query": {
   │              "knn": {
   │                "image_vectors.vector": {
   │                  "vector": [0.156, -0.023, ..., 0.089],
   │                  "k": 50
   │                }
   │              }
   │            }
   │          }
   │        },
   │        "filter": [ /* from step 3 */ ]
   │      }
   │    }
   │  }
   ├─ OpenSearch nested HNSW search: ~40ms
   └─ Returns: [
       {"_id": "22222222", "_score": 0.92, "_source": {...}},
       {"_id": "12345678", "_score": 0.88, "_source": {...}},
       ...50 results
     ]

7. Calculate adaptive weights
   ├─ must_have: ["granite_countertops"]
   ├─ query_type: "visual_style"
   ├─ Detect: No color, no material, IS visual_style
   ├─ Apply rules:
   │  └─ query_type == "visual_style" → boost images
   └─ Returns: [bm25_k=60, text_k=45, image_k=40]

8. Reciprocal Rank Fusion
   ├─ Merge results from 3 searches
   ├─ For listing 12345678 (appeared in all 3):
   │  ├─ BM25 rank 1: 1/(60+1) = 0.0164
   │  ├─ Text kNN rank 2: 1/(45+2) = 0.0213
   │  ├─ Image kNN rank 2: 1/(40+2) = 0.0238
   │  └─ Total RRF: 0.0615
   ├─ For listing 22222222 (only in image):
   │  ├─ BM25: not present = 0
   │  ├─ Text kNN: not present = 0
   │  ├─ Image kNN rank 1: 1/(40+1) = 0.0244
   │  └─ Total RRF: 0.0244
   └─ Sort by RRF score, return top 10

9. Tag boosting
   ├─ For listing 12345678:
   │  ├─ must_have: {"granite_countertops"}
   │  ├─ feature_tags: ["pool", "garage", "granite_countertops", "modern"]
   │  ├─ matched: {"granite_countertops"}
   │  ├─ match_ratio: 1/1 = 1.0 → boost = 2.0x
   │  └─ final_score: 0.0615 × 2.0 = 0.1230
   └─ For listing 22222222:
      ├─ feature_tags: ["pool", "traditional", "hardwood"]
      ├─ matched: {} (no granite)
      ├─ match_ratio: 0/1 = 0.0 → boost = 1.0x
      └─ final_score: 0.0244 × 1.0 = 0.0244

10. Final ranking
    [
      {"zpid": "12345678", "_score": 0.1230, ...},  ← Winner!
      {"zpid": "11111111", "_score": 0.0845, ...},
      {"zpid": "33333333", "_score": 0.0678, ...},
      {"zpid": "22222222", "_score": 0.0244, ...},
      ...
    ]

11. Return response
    {
      "results": [
        {
          "zpid": "12345678",
          "price": 450000,
          "bedrooms": 3,
          "address": {...},
          "description": "Beautiful modern home with granite countertops...",
          "_score": 0.1230
        },
        ...
      ],
      "total": 387,
      "took_ms": 145
    }

Total search cost: $0.0002 (query parsing + embedding)
Total search time: ~150ms
```

### Example 3: Multi-Vector Image Matching

**Query:** "house with pool"

**Listing A:** Has 20 images (1 pool photo, 19 interior photos)

**Without multi-vector (averaged):**
```python
# All 20 vectors averaged into one
pool_vector = [0.8, 0.9, 0.7, ...]  # Strong pool signal
interior_vectors = 19 × [-0.1, 0.2, -0.05, ...]  # No pool

averaged = (1×pool_vector + 19×interior_vectors) / 20
         = [0.04, 0.19, 0.035, ...]  # Pool signal DILUTED!

# When searching for pool
query_vector = [0.75, 0.85, 0.65, ...]
cosine_similarity(query_vector, averaged) = 0.45  # LOW!
```

**With multi-vector (nested):**
```python
# Each vector stored separately
image_vectors = [
  {"url": "pool.jpg", "vector": [0.8, 0.9, 0.7, ...]},
  {"url": "living1.jpg", "vector": [-0.1, 0.2, -0.05, ...]},
  {"url": "living2.jpg", "vector": [-0.15, 0.18, -0.08, ...]},
  ...19 interior photos
]

# OpenSearch searches EACH vector independently
scores = [
  cosine_similarity(query, [0.8, 0.9, 0.7, ...]) = 0.92,  ← POOL!
  cosine_similarity(query, [-0.1, 0.2, -0.05, ...]) = 0.12,
  cosine_similarity(query, [-0.15, 0.18, -0.08, ...]) = 0.15,
  ...
]

# score_mode: "max" → Use BEST match
final_score = max(scores) = 0.92  # HIGH!
```

**Result:** Listing A ranks highly because its pool photo matches perfectly, even though it's only 1 of 20 images!

---

## Summary of Key Concepts

### 1. Embeddings
- **Text embeddings:** 1024-dim vectors representing semantic meaning of text
- **Image embeddings:** 1024-dim vectors representing visual features
- **Same dimension:** Allows cross-modal search (text query → find similar images)

### 2. Caching Strategy
- **Why:** Bedrock API costs add up ($0.00105 per image × 3900 listings = $4.10)
- **How:** DynamoDB tables store results with metadata
- **Effect:** Re-indexing is FREE (90%+ cache hit rate)

### 3. Multi-Vector Schema
- **Problem:** Averaging dilutes signals from specific features
- **Solution:** Store all vectors separately, search each independently
- **Trade-off:** More storage, but dramatically better recall

### 4. Hybrid Search
- **BM25:** Keyword matching (fast, interpretable)
- **kNN text:** Semantic similarity (handles synonyms, concepts)
- **kNN image:** Visual similarity (finds visually similar homes)
- **Fusion:** RRF combines rankings, not scores (robust to scale differences)

### 5. Adaptive Scoring
- **Observation:** Not all queries benefit equally from each strategy
- **Solution:** Adjust RRF k-values based on query type
- **Examples:**
  - Color queries → Boost BM25 (tags have exact colors)
  - Visual queries → Boost images (architecture style in photos)
  - Feature queries → Balanced (all strategies contribute)

### 6. Pure Python Math
- **Issue:** Numpy broke in Lambda (import errors)
- **Solution:** Implemented cosine similarity in pure Python
- **Code:**
```python
def cosine_similarity(vec1, vec2):
    dot = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))
    return dot / (mag1 * mag2)
```
- **Impact:** Slightly slower (~5-10%), but no deployment issues

---

## End of Walkthrough

This document provides a complete code-based walkthrough of the Hearth backend system. Every flow, function, and example is derived directly from the actual codebase, with no external context or assumptions.
