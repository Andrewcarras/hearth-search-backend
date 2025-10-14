# Hearth Backend Architecture

## System Overview

Hearth is a **multimodal AI-powered real estate search engine** that combines:
- **Natural language search** - Understand queries like "3 bedroom home with pool near a school"
- **Semantic text search** - Find listings by meaning, not just keywords
- **Visual search** - Match properties by photo features (granite countertops, vaulted ceilings, etc.)
- **Hybrid ranking** - Fuse multiple search strategies for best results

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                                   │
│  http://34.228.111.56/  (React/Next.js frontend)                        │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ HTTP POST /search
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (HTTP API)                               │
│  https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search     │
│  - CORS enabled                                                          │
│  - Public access                                                         │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ Invokes
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LAMBDA: hearth-search                               │
│  Runtime: Python 3.11 | Memory: 3008 MB | Timeout: 30s                  │
│  Code: search.py + common.py                                             │
│                                                                           │
│  Processing Flow:                                                        │
│  1. Parse natural language query (Claude Haiku)                         │
│  2. Extract constraints (must_have tags, price range, etc.)             │
│  3. Generate query embedding (Bedrock Titan)                            │
│  4. Execute 3 parallel searches:                                        │
│     - BM25 keyword search                                               │
│     - kNN text similarity (cosine)                                      │
│     - kNN image similarity (cosine)                                     │
│  5. Fuse results with RRF algorithm                                     │
│  6. Enrich with nearby places (Google Places API)                       │
│  7. Return ranked results                                               │
└───────────────────┬──────────────────────┬──────────────────────────────┘
                    │                      │
                    │                      │ Query/Filter
                    │ Read                 ▼
                    │           ┌──────────────────────────┐
                    │           │   OPENSEARCH CLUSTER     │
                    │           │   (t3.small.search)      │
                    │           │                          │
                    │           │  Index: listings         │
                    │           │  - 1,358+ documents      │
                    │           │  - kNN vectors (1024-dim)│
                    │           │  - BM25 text index       │
                    │           │  - Geo-point fields      │
                    │           └──────────────────────────┘
                    │
                    │ Cache Read/Write
                    ▼
    ┌───────────────────────────────┐
    │  DYNAMODB TABLES              │
    │                               │
    │  1. hearth-image-cache        │
    │     - Image embeddings        │
    │     - Text embeddings         │
    │     - Vision analysis         │
    │     Key: image_url            │
    │                               │
    │  2. hearth-geolocation-cache  │
    │     - Nearby places           │
    │     Key: lat,lon,radius       │
    │                               │
    │  3. hearth-indexing-jobs      │
    │     - Job status tracking     │
    │     Key: job_id               │
    └───────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                        INDEXING PIPELINE                                 │
└─────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────┐
    │  S3 BUCKET       │
    │  demo-hearth-data│
    │                  │
    │  murray_listings │  1,588 Zillow listings (JSON)
    │  .json           │
    └────────┬─────────┘
             │ Read
             ▼
    ┌──────────────────┐         ┌────────────────────┐
    │ index_local.py   │   OR    │ LAMBDA:            │
    │ (Recommended)    │         │ hearth-upload-     │
    │                  │         │ listings           │
    │ - Runs on your   │         │                    │
    │   computer       │         │ Runtime: Python    │
    │ - Full control   │         │ Memory: 3008 MB    │
    │ - No timeouts    │         │ Timeout: 15m       │
    │ - Same caching   │         │ Self-invokes       │
    └────────┬─────────┘         └─────────┬──────────┘
             │                             │
             └─────────────┬───────────────┘
                           │ Process each listing
                           ▼
         ┌─────────────────────────────────────────┐
         │  LISTING PROCESSING PIPELINE            │
         │                                         │
         │  1. Extract core fields                 │
         │     (price, beds, baths, address, etc.) │
         │                                         │
         │  2. Generate text embedding             │
         │     ├─ Check DynamoDB cache             │
         │     ├─ Bedrock Titan (1024-dim)         │
         │     └─ Cache result                     │
         │                                         │
         │  3. Process images (up to 10)           │
         │     For each image:                     │
         │     ├─ Download from Zillow CDN         │
         │     ├─ Generate image embedding         │
         │     │  ├─ Check DynamoDB cache          │
         │     │  ├─ Bedrock Titan (1024-dim)      │
         │     │  └─ Cache result                  │
         │     └─ Detect visual features           │
         │        ├─ Check DynamoDB cache          │
         │        ├─ Claude Haiku Vision           │
         │        │  ($0.00025/image)               │
         │        └─ Cache result                  │
         │                                         │
         │  4. Average image embeddings            │
         │     (1 vector per property)             │
         │                                         │
         │  5. Validate embeddings                 │
         │     (non-zero check)                    │
         │                                         │
         │  6. Index to OpenSearch                 │
         │     (bulk upsert with retry)            │
         └─────────────────────────────────────────┘
                           │
                           ▼
                 ┌─────────────────┐
                 │  OPENSEARCH     │
                 │  1,358+ indexed │
                 │  ~30-40s/listing│
                 └─────────────────┘
```

---

## Core Components

### 1. Search Lambda (`search.py`)

**Purpose:** Handle natural language search queries and return ranked results

**Key Features:**
- Natural language understanding via Claude Haiku
- Hybrid search (BM25 + kNN text + kNN image)
- Reciprocal Rank Fusion (RRF) for result combination
- On-demand geolocation enrichment
- DynamoDB caching for performance

**Search Flow:**

```
User Query: "3 bedroom home with granite countertops under $500k"
     │
     ▼
┌─────────────────────────────────────────┐
│ 1. QUERY ANALYSIS (Claude Haiku)        │
│    Input: Raw query string              │
│    Output: Structured constraints       │
│    {                                    │
│      "must_have": ["granite_counters"], │
│      "hard_filters": {                  │
│        "beds_min": 3,                   │
│        "price_max": 500000              │
│      }                                  │
│    }                                    │
│    Cost: ~$0.0001 per query             │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. EMBEDDING GENERATION                 │
│    Input: Query text                    │
│    Output: 1024-dim vector              │
│    Model: Bedrock Titan Text v2         │
│    Cache: DynamoDB (by MD5 hash)        │
│    Cost: ~$0.0001 per query             │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. PARALLEL SEARCH EXECUTION            │
│                                         │
│    ┌─────────────────────────────┐     │
│    │ A) BM25 KEYWORD SEARCH      │     │
│    │ - Full-text on description  │     │
│    │ - Field boosting:           │     │
│    │   * description^3           │     │
│    │   * address^0.5             │     │
│    │   * city^0.3, state^0.2     │     │
│    │ - Tag matching (soft boost) │     │
│    │ - Returns: Top 45 results   │     │
│    └─────────────────────────────┘     │
│                                         │
│    ┌─────────────────────────────┐     │
│    │ B) kNN TEXT SIMILARITY      │     │
│    │ - Cosine similarity         │     │
│    │ - Field: vector_text        │     │
│    │ - k=100 nearest neighbors   │     │
│    │ - Returns: Top 45 results   │     │
│    └─────────────────────────────┘     │
│                                         │
│    ┌─────────────────────────────┐     │
│    │ C) kNN IMAGE SIMILARITY     │     │
│    │ - Cosine similarity         │     │
│    │ - Field: vector_image       │     │
│    │ - k=100 nearest neighbors   │     │
│    │ - Returns: Top 45 results   │     │
│    └─────────────────────────────┘     │
│                                         │
│    All 3 searches run with filters:    │
│    - price > 0                          │
│    - has_valid_embeddings = true        │
│    - Custom filters (beds, baths, etc.) │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 4. RECIPROCAL RANK FUSION (RRF)        │
│    Combines rankings from 3 searches:   │
│                                         │
│    For each document across all lists:  │
│    score = Σ (1 / (60 + rank))         │
│                                         │
│    Example:                             │
│    zpid=123 appears in:                 │
│    - BM25 at rank #2  → 1/(60+2) = 0.016│
│    - kNN text at #5   → 1/(60+5) = 0.015│
│    - kNN image at #10 → 1/(60+10)= 0.014│
│    Total score: 0.045                   │
│                                         │
│    Documents sorted by total score      │
│    Returns: Top 45 fused results        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 5. TAG BOOSTING                         │
│    For each result:                     │
│    - Check if all must_have tags present│
│    - If yes: boost score by 50%         │
│    - Ensures exact matches rank higher  │
│                                         │
│    Example:                             │
│    Query wants: ["granite_counters"]    │
│    Listing has: ["granite_counters",    │
│                  "pool", "hardwood"]    │
│    ✓ Boosted by 1.5x                    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 6. GEOLOCATION ENRICHMENT               │
│    For each result (if has coordinates):│
│    - Check DynamoDB cache               │
│    - If miss: Call Google Places API    │
│      (1km radius, max 10 places)        │
│    - Cache result by rounded lat/lon    │
│    - Add "nearby_places" array          │
│                                         │
│    Cost: ~$0.017 per cache miss         │
│          $0 per cache hit               │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 7. RETURN TOP 15 RESULTS                │
│    Each result contains:                │
│    - All OpenSearch fields              │
│    - nearby_places array                │
│    - boosted flag                       │
│    - Final score                        │
└─────────────────────────────────────────┘
```

**Performance Metrics:**
- Average latency: 500-800ms
- BM25 search: ~50ms
- kNN searches: ~100ms each
- RRF fusion: ~10ms
- Geolocation enrichment: ~30ms per listing (cached) or ~200ms (cache miss)

---

### 2. Upload Lambda (`upload_listings.py`)

**Purpose:** Index real estate listings into OpenSearch with multimodal embeddings

**Key Features:**
- Process listings from S3 or direct payload
- Generate text and image embeddings
- Classify architecture style with vision AI
- Batch processing with self-invocation
- DynamoDB caching to save 90% of costs
- Idempotency and loop protection

**Indexing Flow:**

```
S3: murray_listings.json (1,588 listings)
     │
     ▼
┌─────────────────────────────────────────┐
│ LAMBDA HANDLER                          │
│ - Check OpenSearch index exists         │
│ - Load batch (50 listings)              │
│ - Process each listing in sequence      │
└──────────────┬──────────────────────────┘
               │
               ▼ (For each listing)
┌─────────────────────────────────────────┐
│ 1. EXTRACT CORE FIELDS                  │
│    From Zillow JSON:                    │
│    - zpid (unique ID)                   │
│    - price, bedrooms, bathrooms         │
│    - address (nested object)            │
│    - city, state, zip_code              │
│    - geo coordinates (lat/lon)          │
│    - description text                   │
│                                         │
│    Handle variations:                   │
│    - Nested vs flat address             │
│    - Multiple possible field names      │
│    - Generate fallback description      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. TEXT EMBEDDING                       │
│    Input: description only              │
│                                         │
│    Cache Check:                         │
│    ├─ Key: text:{MD5 hash}              │
│    ├─ Table: hearth-image-cache         │
│    └─ Hit? Return cached vector         │
│                                         │
│    Cache Miss:                          │
│    ├─ Bedrock: Titan Text v2            │
│    ├─ Output: 1024-dim vector           │
│    ├─ Cost: ~$0.0001 per text           │
│    └─ Cache for next time               │
│                                         │
│    Result: [0.123, -0.456, ...]         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. IMAGE PROCESSING (up to 10 images)  │
│                                         │
│    For each image URL:                  │
│    ┌─────────────────────────────┐     │
│    │ A) Download from Zillow CDN │     │
│    │    - 576px width (optimized)│     │
│    │    - Dedupe by MD5 hash     │     │
│    └──────────┬──────────────────┘     │
│               │                         │
│               ▼                         │
│    ┌─────────────────────────────┐     │
│    │ B) Generate Embedding       │     │
│    │    Cache Check:             │     │
│    │    ├─ Key: image_url         │     │
│    │    ├─ Hit? Use cached        │     │
│    │    │                         │     │
│    │    Cache Miss:               │     │
│    │    ├─ Base64 encode          │     │
│    │    ├─ Bedrock: Titan Image   │     │
│    │    ├─ Output: 1024-dim       │     │
│    │    ├─ Cost: ~$0.0003/image   │     │
│    │    └─ Cache result           │     │
│    └──────────┬──────────────────┘     │
│               │                         │
│               ▼                         │
│    ┌─────────────────────────────┐     │
│    │ C) Detect Features          │     │
│    │    (Claude Haiku Vision)    │     │
│    │    Cache Check:             │     │
│    │    ├─ Key: image_url         │     │
│    │    ├─ Field: labels          │     │
│    │    ├─ Hit? Use cached        │     │
│    │    │                         │     │
│    │    Cache Miss:               │     │
│    │    ├─ Base64 encode          │     │
│    │    ├─ Invoke Claude Haiku    │     │
│    │    ├─ Parse comma-sep labels │     │
│    │    ├─ Cost: $0.00025/image   │     │
│    │    ├─ 75% cheaper than       │     │
│    │    │   Rekognition           │     │
│    │    └─ Cache result           │     │
│    │                             │     │
│    │    Detected features:        │     │
│    │    - granite countertops     │     │
│    │    - vaulted ceilings        │     │
│    │    - hardwood floors         │     │
│    │    - stainless steel         │     │
│    │    - blue exterior           │     │
│    │    - 2-car garage            │     │
│    └──────────┬──────────────────┘     │
│               │                         │
│               ▼                         │
│    ┌─────────────────────────────┐     │
│    │ D) Score for Architecture   │     │
│    │    Identify best exterior:   │     │
│    │    +3 pts: exterior keywords │     │
│    │    -2 pts: interior keywords │     │
│    │    Save best image for       │     │
│    │    style classification      │     │
│    └─────────────────────────────┘     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 4. ARCHITECTURE CLASSIFICATION          │
│    (Claude Sonnet Vision)               │
│                                         │
│    Input: Best exterior image           │
│    Output: {                            │
│      "primary_style": "craftsman",      │
│      "exterior_color": "blue",          │
│      "materials": ["brick", "siding"],  │
│      "visual_features": ["porch",       │
│                          "2_car_garage"]│
│    }                                    │
│                                         │
│    Cost: ~$0.003 per image              │
│    Only runs on 1 image per listing     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 5. COMPUTE AVERAGE IMAGE VECTOR         │
│    Input: List of image embeddings      │
│    Output: Single 1024-dim vector       │
│                                         │
│    Formula: mean(vectors)               │
│    vec[i] = Σ(all_vecs[i]) / count      │
│                                         │
│    This represents the "visual essence" │
│    of the entire property               │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 6. VALIDATE EMBEDDINGS                  │
│    Check vectors are non-zero:          │
│                                         │
│    has_valid_text = sum(abs(vec)) > 0   │
│    has_valid_image = sum(abs(vec)) > 0  │
│                                         │
│    has_valid_embeddings =               │
│      has_valid_text OR has_valid_image  │
│                                         │
│    ⚠️ Only listings with valid          │
│    embeddings appear in kNN searches    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 7. BUILD OPENSEARCH DOCUMENT            │
│    Combine all fields:                  │
│    {                                    │
│      "zpid": "12345",                   │
│      "price": 450000,                   │
│      "bedrooms": 3,                     │
│      "bathrooms": 2.5,                  │
│      "address": {...},                  │
│      "description": "...",              │
│      "image_tags": ["granite", "pool"], │
│      "architecture_style": "craftsman", │
│      "vector_text": [1024 floats],      │
│      "vector_image": [1024 floats],     │
│      "has_valid_embeddings": true,      │
│      "images": ["url1", "url2", ...]    │
│    }                                    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 8. BULK INDEX TO OPENSEARCH             │
│    Batch size: 200 documents            │
│    - Exponential backoff on 429/503     │
│    - Auto-split chunks if throttled     │
│    - Refresh: true (immediately search) │
│    - Retry: up to 6 attempts            │
│                                         │
│    Index time: ~30-40s per listing      │
│    (including all API calls + caching)  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 9. SELF-INVOKE FOR NEXT BATCH           │
│    If more listings remain:             │
│    - Increment invocation counter       │
│    - Set next_start = current + count   │
│    - Check safety limits:               │
│      * Max 50 invocations               │
│      * Start must advance               │
│      * Job idempotency check            │
│    - Async invoke next Lambda           │
│                                         │
│    Safety Features:                     │
│    - DynamoDB job tracking              │
│    - Duplicate invocation detection     │
│    - Timeout protection (~30s buffer)   │
└─────────────────────────────────────────┘
```

**Cost Optimization via DynamoDB Caching:**

```
WITHOUT CACHING (1,588 listings × 10 images):
  Text embeddings: 1,588 × $0.0001 = $0.16
  Image embeddings: 15,880 × $0.0003 = $4.76
  Vision analysis: 15,880 × $0.00025 = $3.97
  TOTAL: ~$8.89 per full re-index

WITH CACHING (90% hit rate):
  Text embeddings: 159 × $0.0001 = $0.02
  Image embeddings: 1,588 × $0.0003 = $0.48
  Vision analysis: 1,588 × $0.00025 = $0.40
  TOTAL: ~$0.90 per re-index (90% savings!)
```

---

### 3. Common Utilities (`common.py`)

**Purpose:** Shared functions used by both search and upload Lambda functions

**Key Modules:**

#### A) AWS Client Initialization
- OpenSearch client with retry logic
- Bedrock Runtime client for AI models
- DynamoDB client for caching
- AWS4Auth for OpenSearch authentication

#### B) Embedding Generation
```python
def embed_text(text: str) -> List[float]:
    """
    Generate 1024-dim text embedding using Bedrock Titan Text v2
    - Checks DynamoDB cache first (key: text:{MD5})
    - On cache miss: invoke Bedrock model
    - Cache result for 90% cost savings
    """

def embed_image_from_url(url: str) -> List[float]:
    """
    Generate 1024-dim image embedding using Bedrock Titan Image
    - Checks DynamoDB cache first (key: image_url)
    - Downloads image bytes
    - Base64 encodes for Bedrock
    - Cache result
    """
```

#### C) Vision AI Functions
```python
def detect_labels(img_bytes: bytes, image_url: str) -> List[str]:
    """
    Detect visual features using Claude 3 Haiku Vision
    - 75% cheaper than AWS Rekognition
    - Better context understanding
    - Returns: ["granite countertops", "vaulted ceiling", "pool"]
    - Cached in DynamoDB by URL
    """

def classify_architecture_style_vision(img_bytes: bytes) -> Dict:
    """
    Classify architecture style using Claude 3 Sonnet Vision
    - Analyzes exterior image
    - Returns: {
        "primary_style": "craftsman",
        "exterior_color": "blue",
        "materials": ["brick", "siding"],
        "visual_features": ["porch", "garage"]
      }
    """
```

#### D) OpenSearch Management
```python
def create_index_if_needed():
    """
    Create OpenSearch index with proper mappings
    - kNN vector fields (HNSW algorithm)
    - BM25 text fields
    - Keyword fields for exact filtering
    - Geo-point for location search
    """

def bulk_upsert(actions: List[Dict], chunk_size: int = 100):
    """
    Robustly index documents to OpenSearch
    - Automatic chunking
    - Exponential backoff on rate limits
    - Auto-split chunks if throttled
    - Error handling for individual docs
    """
```

#### E) Query Understanding
```python
def extract_query_constraints(query: str) -> Dict:
    """
    Parse natural language query using Claude Haiku
    Input: "3 bedroom modern home with pool under $500k"
    Output: {
      "must_have": ["pool"],
      "hard_filters": {
        "beds_min": 3,
        "price_max": 500000
      },
      "architecture_style": "modern"
    }
    """
```

---

## Data Flow

### Search Request Flow

```
1. User enters query: "homes with granite countertops"
   │
2. Frontend sends POST to API Gateway
   │
3. API Gateway invokes hearth-search Lambda
   │
4. Lambda parses query with Claude Haiku
   │  Output: {"must_have": ["granite_counters"]}
   │
5. Generate query embedding (Bedrock Titan)
   │  Cache check → Generate if needed
   │
6. Execute 3 parallel OpenSearch queries:
   │  ├─ BM25: "granite countertops" in description
   │  ├─ kNN text: Similar descriptions
   │  └─ kNN image: Similar property photos
   │
7. Fuse results with RRF algorithm
   │  Combine rankings from all 3 searches
   │
8. Boost listings with granite_counters tag
   │
9. Enrich each result with nearby places
   │  Cache check → Google Places API if needed
   │
10. Return top 15 results to frontend
    │
11. Frontend displays property cards with:
    - High-res images
    - Price, beds, baths
    - Nearby places
    - Click to view full listing modal
```

### Indexing Flow (Local Script)

```
1. User runs: python index_local.py
   │
2. Script connects to OpenSearch
   │
3. Load 1,588 listings from S3
   │
4. For each listing (sequential):
   │  ├─ Extract core fields
   │  ├─ Generate text embedding (cached 90%)
   │  ├─ Process up to 10 images:
   │  │  ├─ Download from Zillow CDN
   │  │  ├─ Generate embedding (cached)
   │  │  └─ Detect features with Claude Vision (cached)
   │  ├─ Classify architecture style
   │  ├─ Average image embeddings
   │  ├─ Validate embeddings
   │  └─ Index to OpenSearch
   │
5. Verify each listing in OpenSearch
   │  GET /listings/_doc/{zpid}
   │
6. Print progress:
   │  ✅ [1234/1588] zpid=123 | 77.7% | ETA: 8m
   │
7. Complete after ~12-16 hours
   │  (with 90% cache hit rate)
```

---

## OpenSearch Schema

### Index: `listings`

**Settings:**
```json
{
  "index": {
    "knn": true  // Enable k-nearest neighbors search
  }
}
```

**Field Mappings:**

| Field | Type | Purpose | Searchable |
|-------|------|---------|------------|
| `zpid` | keyword | Zillow Property ID (unique) | Exact match |
| `price` | long | Listing price in USD | Range filter |
| `bedrooms` | float | Number of bedrooms | Range filter |
| `bathrooms` | float | Number of bathrooms | Range filter |
| `livingArea` | float | Living area (sqft) | Range filter |
| `address` | nested | Nested address object for UI | No |
| `address.streetAddress` | text | Street address | Full-text |
| `address.city` | keyword | City name | Exact match |
| `address.state` | keyword | State code | Exact match |
| `address.zipcode` | keyword | ZIP code | Exact match |
| `city` | keyword | City (flat field for filters) | Exact match |
| `state` | keyword | State (flat field for filters) | Exact match |
| `zip_code` | keyword | ZIP code (flat field) | Exact match |
| `geo` | geo_point | Coordinates (lat/lon) | Geo-distance |
| `description` | text | Original description | BM25 search |
| `llm_profile` | text | Reserved (unused, always empty) | BM25 search |
| `feature_tags` | keyword | Extracted features (pool, etc.) | Exact match (array) |
| `image_tags` | keyword | Visual features from AI | Exact match (array) |
| `architecture_style` | keyword | Architecture style | Exact match |
| `images` | keyword | Image URLs (not searchable) | No |
| `vector_text` | knn_vector | Text embedding (1024-dim) | kNN similarity |
| `vector_image` | knn_vector | Image embedding (1024-dim) | kNN similarity |
| `has_valid_embeddings` | boolean | Quality flag | Filter |

**kNN Vector Configuration:**
```json
{
  "type": "knn_vector",
  "dimension": 1024,
  "method": {
    "name": "hnsw",              // Hierarchical Navigable Small World
    "engine": "lucene",
    "space_type": "cosinesimil"  // Cosine similarity metric
  }
}
```

**HNSW Algorithm:**
- Approximate nearest neighbor search
- Fast: O(log n) query time
- Memory-efficient graph structure
- 95%+ accuracy vs brute force
- Optimized for high-dimensional vectors (1024-dim)

---

## Hybrid Search Algorithm

### Reciprocal Rank Fusion (RRF)

**Problem:** How do we combine results from 3 different search strategies?
- BM25 returns documents sorted by keyword relevance
- kNN text returns documents sorted by semantic similarity
- kNN image returns documents sorted by visual similarity

**Solution:** RRF - A rank-based fusion algorithm

**Algorithm:**
```python
def rrf(ranked_lists, k=60):
    """
    For each document appearing in any list:
      score = Σ (1 / (k + rank))

    Where:
    - k = 60 (constant that controls score decay)
    - rank = position in each list (1-indexed)
    """
    scores = {}

    for list in ranked_lists:
        for rank, doc in enumerate(list, start=1):
            doc_id = doc["_id"]
            scores[doc_id] = scores.get(doc_id, 0) + (1 / (k + rank))

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

**Example:**

Listing zpid=123 appears in:
- BM25 results at rank #2
- kNN text at rank #5
- kNN image at rank #10

RRF score = 1/(60+2) + 1/(60+5) + 1/(60+10)
          = 1/62 + 1/65 + 1/70
          = 0.0161 + 0.0154 + 0.0143
          = **0.0458**

Listing zpid=456 appears in:
- BM25 results at rank #1
- kNN text: not present
- kNN image: not present

RRF score = 1/(60+1)
          = 1/61
          = **0.0164**

**Result:** zpid=123 ranks higher because it appears in all 3 searches, even though zpid=456 was #1 in BM25.

**Why RRF Works:**
- ✅ No normalization needed (rank-based)
- ✅ Works with different scoring functions
- ✅ Handles missing documents gracefully
- ✅ Gives credit for appearing in multiple lists
- ✅ Proven effective in information retrieval research

---

## Cost Analysis

### Per-Search Costs

**Search Lambda (`hearth-search`):**
- Lambda execution: $0.0000017 per 100ms (3008 MB)
- Claude Haiku (query parsing): $0.0001
- Bedrock Titan (text embedding): $0.0001
- OpenSearch query: Free (included in cluster)
- Google Places API (cache miss): $0.017 per listing × 15 = $0.26
- Google Places API (cache hit): $0
- **Total per search:** $0.0002 (cached) to $0.26 (cold cache)

**Indexing Lambda (`hearth-upload-listings`):**
- Lambda execution: $0.003 per listing (avg 30s × 3008 MB)
- Text embedding: $0.0001 (cached 90%) = $0.00001 avg
- Image embeddings (10 images): 10 × $0.0003 = $0.003 (cached 90%) = $0.0003 avg
- Claude Haiku Vision (10 images): 10 × $0.00025 = $0.0025 (cached 90%) = $0.00025 avg
- Claude Sonnet Vision (1 image): $0.003 (not cached)
- **Total per listing:** ~$0.0066 (with caching)
- **Total for 1,588 listings:** ~$10.48

### Monthly Costs (Current Usage)

| Service | Configuration | Monthly Cost |
|---------|--------------|--------------|
| OpenSearch | t3.small.search (1 instance) | $33.84 |
| EC2 (UI) | t2.micro (1 instance) | $8.76 |
| Lambda | hearth-search (100 requests/day) | $1.50 |
| Lambda | hearth-upload-listings (re-index 1x/month) | $10.00 |
| DynamoDB | 3 tables (on-demand) | $5.00 |
| Bedrock | Titan + Claude (100 searches/day) | $3.00 |
| Google Places | ~50 cache misses/day | $25.50 |
| S3 | 1 GB storage + transfers | $0.50 |
| **TOTAL** | | **$88.10/month** |

**Cost Optimization Strategies:**
1. ✅ DynamoDB caching → 90% savings on re-indexing
2. ✅ Claude Haiku Vision → 75% cheaper than Rekognition
3. ✅ Geolocation caching → 95% cache hit rate after warmup
4. ✅ Reduced page size (15 → 30 results) → Lower Google Places costs
5. ✅ Index refresh=true → No waiting for scheduled refresh

---

## Performance Metrics

### Search Latency Breakdown

| Operation | Avg Time | Max Time |
|-----------|----------|----------|
| API Gateway routing | 10ms | 20ms |
| Lambda cold start | 1500ms | 3000ms |
| Lambda warm execution | 500ms | 800ms |
| ├─ Query parsing (Claude) | 200ms | 400ms |
| ├─ Embedding generation | 100ms | 200ms |
| ├─ OpenSearch BM25 | 50ms | 150ms |
| ├─ OpenSearch kNN text | 100ms | 250ms |
| ├─ OpenSearch kNN image | 100ms | 250ms |
| ├─ RRF fusion | 10ms | 20ms |
| └─ Geolocation enrichment | 30ms (cached) | 200ms (miss) |
| **Total (warm)** | **500-800ms** | **1500ms** |
| **Total (cold)** | **2000-2300ms** | **4500ms** |

### Indexing Performance

| Metric | Value |
|--------|-------|
| Listings processed | 1,358 / 1,588 (85.5%) |
| Avg time per listing | 30-40 seconds |
| Cache hit rate | 90% (embeddings + vision) |
| OpenSearch bulk size | 200 documents |
| Retry attempts | Max 6 per chunk |
| Success rate | 99.9% |

### Cache Performance

| Cache Type | Table | Hit Rate | Savings |
|------------|-------|----------|---------|
| Text embeddings | hearth-image-cache | 90% | $0.14 per re-index |
| Image embeddings | hearth-image-cache | 90% | $4.28 per re-index |
| Vision analysis | hearth-image-cache | 90% | $3.57 per re-index |
| Geolocation | hearth-geolocation-cache | 95% | $24.00 per 100 searches |
| **Total Savings** | | | **~$32 per re-index + search cycle** |

---

## Deployment Architecture

### AWS Resources

```
Region: us-east-1

├─ Lambda Functions
│  ├─ hearth-search
│  │  ├─ Runtime: Python 3.11
│  │  ├─ Memory: 3008 MB
│  │  ├─ Timeout: 30s
│  │  ├─ Handler: search.handler
│  │  └─ Environment: OS_HOST, GOOGLE_PLACES_API_KEY
│  │
│  └─ hearth-upload-listings
│     ├─ Runtime: Python 3.11
│     ├─ Memory: 3008 MB
│     ├─ Timeout: 900s (15m)
│     ├─ Handler: upload_listings.handler
│     ├─ Concurrency: 1 (prevents loop)
│     └─ Environment: OS_HOST, MAX_IMAGES=10, MAX_INVOCATIONS=50
│
├─ API Gateway
│  └─ hearth-api (HTTP API)
│     ├─ Route: POST /search → hearth-search Lambda
│     ├─ CORS: Enabled (*)
│     └─ URL: https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod
│
├─ OpenSearch
│  └─ hearth-opensearch
│     ├─ Instance: t3.small.search
│     ├─ EBS: 20 GB gp3
│     ├─ Endpoint: search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a...
│     └─ Index: listings (1,358 docs)
│
├─ DynamoDB Tables
│  ├─ hearth-image-cache
│  │  ├─ Key: image_url (S)
│  │  ├─ Attributes: embedding (S), labels (S), cached_at (N)
│  │  └─ Billing: On-demand
│  │
│  ├─ hearth-geolocation-cache
│  │  ├─ Key: location_key (S)
│  │  ├─ Attributes: places (S), cached_at (N)
│  │  └─ Billing: On-demand
│  │
│  └─ hearth-indexing-jobs
│     ├─ Key: job_id (S)
│     ├─ Attributes: status (S), started_at (N), completed_at (N)
│     └─ Billing: On-demand
│
├─ S3 Buckets
│  └─ demo-hearth-data
│     ├─ murray_listings.json (1,588 listings)
│     ├─ listings/{zpid}.json (individual listing files)
│     └─ ui/ (frontend static files)
│
└─ EC2 Instances
   └─ UI Server (t2.micro)
      ├─ OS: Amazon Linux 2023
      ├─ Web Server: nginx
      ├─ URL: http://34.228.111.56/
      └─ Proxy: /api/search → API Gateway (CORS fix)
```

---

## Security

### Authentication & Authorization
- OpenSearch: AWS4Auth (IAM credentials)
- Lambda: Execution role with policies:
  - `AmazonOpenSearchServiceFullAccess`
  - `AmazonBedrockFullAccess`
  - `AmazonDynamoDBFullAccess`
  - `AmazonS3ReadOnlyAccess` (upload Lambda)
  - `AWSLambdaBasicExecutionRole`
- API Gateway: Public access (no auth required)
- EC2: IAM instance profile (for S3 access)

### Network Security
- OpenSearch: VPC endpoint (private) + public endpoint (IAM-secured)
- Lambda: Runs in VPC (optional) or public subnet
- API Gateway: Public endpoint with CORS
- EC2: Security group allows HTTP (port 80)

### Data Security
- Data at rest: EBS encrypted, S3 server-side encryption
- Data in transit: TLS 1.2+ for all API calls
- Secrets: Environment variables (Lambda), AWS Secrets Manager (optional)

---

## Monitoring & Logging

### CloudWatch Logs

**Lambda: hearth-search**
- Log group: `/aws/lambda/hearth-search`
- Logs: Query parsing, search execution, result count
- Alerts: Error rate > 5%, latency > 2s

**Lambda: hearth-upload-listings**
- Log group: `/aws/lambda/hearth-upload-listings`
- Logs: Batch progress, embedding generation, errors
- Alerts: Invocation count > 50, error rate > 10%

### CloudWatch Metrics

| Metric | Threshold | Alert |
|--------|-----------|-------|
| Lambda errors | > 10 in 5m | Email |
| Lambda duration | > 25s | Warning |
| OpenSearch CPU | > 80% | Email |
| OpenSearch JVM pressure | > 75% | Critical |
| DynamoDB throttles | > 5 in 5m | Email |

---

## Troubleshooting

### Common Issues

**Issue:** Search returns 0 results
- **Cause:** Listings still indexing or embeddings invalid
- **Check:** `GET /listings/_count?q=has_valid_embeddings:true`
- **Fix:** Wait for indexing to complete

**Issue:** Search is slow (>2s)
- **Cause:** OpenSearch cold start or high load
- **Check:** CloudWatch metrics for CPU/JVM
- **Fix:** Scale up cluster or reduce k value

**Issue:** Indexing fails with "Loop detected"
- **Cause:** Self-invocation stuck
- **Check:** DynamoDB job tracking table
- **Fix:** Set concurrency to 0, clear job table, restart

**Issue:** High Bedrock costs
- **Cause:** Cache not working or high re-indexing rate
- **Check:** DynamoDB cache hit rate
- **Fix:** Verify cache table exists, check code logs

**Issue:** Geolocation not working
- **Cause:** Google Places API key missing or invalid
- **Check:** Lambda environment variable `GOOGLE_PLACES_API_KEY`
- **Fix:** Set API key, enable Places API (New) in Google Cloud Console

---

## Future Improvements

### Performance
- [ ] Add Redis caching layer for faster embedding lookups
- [ ] Implement result caching for popular queries
- [ ] Use Lambda SnapStart for faster cold starts
- [ ] Batch Google Places API calls to reduce latency

### Features
- [ ] Add image similarity search (upload photo, find similar homes)
- [ ] Support price history and trend analysis
- [ ] Add user favorites and saved searches
- [ ] Implement real-time notifications for new listings

### Cost Optimization
- [ ] Use reserved capacity for OpenSearch (30% savings)
- [ ] Implement tiered caching (memory → DynamoDB → S3)
- [ ] Pre-compute popular search results
- [ ] Use Lambda provisioned concurrency for search (reduce cold starts)

### Quality
- [ ] Add A/B testing framework for search algorithm changes
- [ ] Implement relevance feedback (click tracking)
- [ ] Add search analytics dashboard
- [ ] Improve architecture classification with fine-tuned model

---

## Related Documentation

- **API Integration:** [docs/API_INTEGRATION.md](API_INTEGRATION.md)
- **Code Reference:** [docs/CODE_REFERENCE.md](CODE_REFERENCE.md) *(coming next)*
- **Deployment Guide:** [AWS_DEPLOYMENT_GUIDE.md](../AWS_DEPLOYMENT_GUIDE.md)
- **Indexing Guide:** [INDEXING_GUIDE.md](../INDEXING_GUIDE.md)
