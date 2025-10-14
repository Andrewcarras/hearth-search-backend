# Hearth Code Reference

Complete reference for all Python files in the project with detailed function documentation, parameters, and usage examples.

---

## Table of Contents

1. [common.py](#commonpy) - Shared utilities (embeddings, caching, OpenSearch)
2. [search.py](#searchpy) - Search Lambda handler
3. [upload_listings.py](#upload_listingspy) - Indexing Lambda handler
4. [index_local.py](#index_localpy) - Local indexing script

---

## common.py

**Purpose:** Shared utility functions for embeddings, caching, OpenSearch, and query parsing

**Dependencies:**
- `boto3` - AWS SDK
- `opensearchpy` - OpenSearch client
- `requests` - HTTP client
- `requests_aws4auth` - AWS request signing

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for all services |
| `OS_HOST` | Required | OpenSearch domain endpoint (no https://) |
| `OS_INDEX` | `listings` | OpenSearch index name |
| `TEXT_EMBED_MODEL` | `amazon.titan-embed-text-v2:0` | Bedrock text embedding model |
| `IMAGE_EMBED_MODEL` | `amazon.titan-embed-image-v1` | Bedrock image embedding model |
| `LLM_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` | Claude model for query parsing and vision analysis |
| `TEXT_DIM` | `1024` | Text embedding dimension |
| `IMAGE_DIM` | `1024` | Image embedding dimension |
| `MAX_IMAGES` | `6` | Max images to process per listing |
| `EMBEDDING_IMAGE_WIDTH` | `576` | Target image width for embeddings (cost optimization) |
| `LOG_LEVEL` | `INFO` | Logging level |

---

### AWS Clients

#### `os_client` (OpenSearch)
```python
os_client = OpenSearch(
    hosts=[{"host": OS_HOST, "port": 443}],
    http_auth=awsauth,
    use_ssl=True,
    timeout=60,
    max_retries=8,
    retry_on_timeout=True,
    retry_on_status=(429, 502, 503, 504)
)
```
**Configuration:**
- 60s timeout for bulk operations
- Auto-retry on rate limits and server errors
- Uses AWS Signature V4 authentication

#### `brt` (Bedrock Runtime)
```python
brt = session.client("bedrock-runtime", config=Config(
    read_timeout=30,
    retries={"max_attempts": 2}
))
```
**Usage:** Invoke AI models (Titan embeddings, Claude)

#### `dynamodb` (DynamoDB)
```python
dynamodb = session.client("dynamodb")
```
**Tables:**
- `hearth-image-cache` - Embeddings and vision analysis cache

---

### Embedding Functions

#### `embed_text(text: str) -> List[float]`
Generate text embedding with DynamoDB caching.

**Parameters:**
- `text` (str) - Input text to embed (description, query, etc.)

**Returns:**
- `List[float]` - 1024-dimensional embedding vector

**Algorithm:**
1. Check DynamoDB cache (key: `text:{MD5 hash}`)
2. If cache miss:
   - Invoke Bedrock Titan Text v2
   - Parse response
   - Cache result
3. Return vector

**Example:**
```python
from common import embed_text

# Generate embedding for listing description
description = "Beautiful 3 bedroom home with granite countertops"
vector = embed_text(description)
# Returns: [0.123, -0.456, 0.789, ..., 0.234]  (1024 floats)

# For search query
query = "modern home with pool"
query_vector = embed_text(query)
```

**Cost:** ~$0.0001 per call (cache miss), $0 per cache hit

**Cache Key Format:**
```
text:{MD5}
Example: text:a3f5e92c4b8d1a6f7e9c2b4d8a1f6e3c
```

---

#### `embed_image_from_url(url: str) -> List[float]`
Download image and generate embedding with DynamoDB caching.

**Parameters:**
- `url` (str) - Image URL (typically from Zillow CDN)

**Returns:**
- `List[float]` - 1024-dimensional embedding vector

**Algorithm:**
1. Check DynamoDB cache (key: `url`)
2. If cache miss:
   - Download image bytes (timeout: 15s)
   - Base64 encode
   - Invoke Bedrock Titan Image
   - Parse response
   - Cache result
3. Return vector

**Example:**
```python
from common import embed_image_from_url

# Generate embedding for property photo
image_url = "https://photos.zillowstatic.com/fp/abc123-cc_ft_1536.jpg"
vector = embed_image_from_url(image_url)
# Returns: [0.234, -0.567, 0.890, ..., 0.345]  (1024 floats)
```

**Cost:** ~$0.0003 per call (cache miss), $0 per cache hit

---

#### `embed_image_bytes(img_bytes: bytes) -> List[float]`
Generate embedding from raw image bytes (no caching).

**Parameters:**
- `img_bytes` (bytes) - Raw image data (JPEG, PNG, etc.)

**Returns:**
- `List[float]` - 1024-dimensional embedding vector

**Example:**
```python
from common import embed_image_bytes
import requests

# Download and embed image
response = requests.get(image_url)
vector = embed_image_bytes(response.content)
```

**Use Case:** When you already have image bytes and don't need caching

---

#### `vec_mean(vectors: List[List[float]], target_dim: int) -> List[float]`
Compute element-wise mean of multiple vectors.

**Parameters:**
- `vectors` (List[List[float]]) - List of embedding vectors
- `target_dim` (int) - Dimension for zero vector fallback

**Returns:**
- `List[float]` - Mean vector

**Algorithm:**
```python
# For each dimension:
mean[i] = sum(vec[i] for vec in vectors) / len(vectors)
```

**Example:**
```python
from common import vec_mean

# Average embeddings from 5 property photos
image_vectors = [
    embed_image_from_url(url1),  # [0.1, 0.2, ...]
    embed_image_from_url(url2),  # [0.3, 0.4, ...]
    embed_image_from_url(url3),  # [0.2, 0.5, ...]
]
avg_vector = vec_mean(image_vectors, target_dim=1024)
# Returns: [0.2, 0.367, ...]  (element-wise mean)
```

**Use Case:** Combine multiple image embeddings into single property vector

---

### Vision AI Functions

#### `detect_labels(img_bytes: bytes, image_url: str = "", max_labels: int = 15) -> List[str]`
Detect visual features using Claude 3 Haiku Vision.

**Parameters:**
- `img_bytes` (bytes) - Raw image data
- `image_url` (str, optional) - URL for caching
- `max_labels` (int) - Maximum labels to return

**Returns:**
- `List[str]` - Lowercase feature labels

**Algorithm:**
1. Check DynamoDB cache (if `image_url` provided)
2. If cache miss:
   - Base64 encode image
   - Invoke Claude Haiku with vision prompt
   - Parse comma-separated labels
   - Cache result
3. Return labels

**Prompt Strategy:**
- Focuses on buyer search terms
- Prioritizes specific features (e.g., "3-car garage" not "garage")
- Categorizes: exterior, interior, materials, amenities

**Example:**
```python
from common import detect_labels
import requests

# Analyze property photo
image_url = "https://photos.zillowstatic.com/fp/abc123.jpg"
img_bytes = requests.get(image_url).content

labels = detect_labels(img_bytes, image_url=image_url)
# Returns: [
#   "granite countertops",
#   "stainless steel appliances",
#   "hardwood floors",
#   "vaulted ceilings",
#   "large windows"
# ]
```

**Cost:** ~$0.00025 per call (75% cheaper than Rekognition)

**Cache Duration:** Permanent (images don't change)

---

#### `classify_architecture_style_vision(image_bytes: bytes) -> Dict[str, Any]`
Classify architecture style using Claude 3 Sonnet Vision.

**Parameters:**
- `image_bytes` (bytes) - Raw image data (preferably exterior photo)

**Returns:**
- `Dict[str, Any]` - Classification result with keys:
  - `primary_style` (str) - Main architecture style
  - `secondary_styles` (List[str]) - Additional applicable styles
  - `exterior_color` (str) - Primary exterior color
  - `roof_type` (str) - Roof style
  - `materials` (List[str]) - Visible materials
  - `visual_features` (List[str]) - Structural features
  - `confidence` (str) - "high", "medium", or "low"

**Example:**
```python
from common import classify_architecture_style_vision

# Classify home exterior
style_data = classify_architecture_style_vision(img_bytes)
# Returns: {
#   "primary_style": "craftsman",
#   "secondary_styles": ["bungalow"],
#   "exterior_color": "blue",
#   "roof_type": "gabled",
#   "materials": ["brick", "siding"],
#   "visual_features": ["front_porch", "2_car_garage", "white_fence"],
#   "confidence": "high"
# }
```

**Supported Styles:**
- modern, contemporary, craftsman, victorian, colonial
- ranch, mediterranean, tudor, cape_cod, farmhouse
- mid_century_modern, traditional, transitional, industrial
- spanish, french_country, greek_revival, bungalow, cottage
- split_level, dutch_colonial, georgian, italianate, prairie
- art_deco, southwestern

**Cost:** ~$0.003 per call (not cached)

---

### OpenSearch Functions

#### `create_index_if_needed() -> None`
Create OpenSearch index with proper mappings if it doesn't exist.

**Algorithm:**
1. Check if index exists: `os_client.indices.exists(index=OS_INDEX)`
2. If not exists:
   - Define mappings (text, keyword, numeric, geo, kNN vectors)
   - Create index: `os_client.indices.create(index=OS_INDEX, body=...)`

**Mappings:**
- **Text fields:** `description` (BM25 search), `llm_profile` (reserved, unused)
- **Keyword fields:** `zpid`, `city`, `state`, `feature_tags`, `image_tags`
- **Numeric fields:** `price`, `bedrooms`, `bathrooms`, `livingArea`
- **Geo field:** `geo` (lat/lon for radius search)
- **kNN vectors:** `vector_text`, `vector_image` (1024-dim, HNSW, cosine similarity)

**Example:**
```python
from common import create_index_if_needed

# Ensure index exists before indexing
create_index_if_needed()
# Index now exists with correct mappings
```

---

#### `upsert_listing(doc_id: str, body: Dict[str, Any]) -> None`
Insert or update a single listing in OpenSearch.

**Parameters:**
- `doc_id` (str) - Document ID (typically zpid)
- `body` (Dict[str, Any]) - Document fields

**Example:**
```python
from common import upsert_listing

# Index single listing
upsert_listing(
    doc_id="12345",
    body={
        "zpid": "12345",
        "price": 450000,
        "bedrooms": 3,
        "description": "Beautiful home",
        "vector_text": [0.1, 0.2, ...],  # 1024 floats
        "has_valid_embeddings": True
    }
)
```

**Note:** Use `bulk_upsert()` for multiple documents (much faster)

---

#### `bulk_upsert(actions: Iterable[Dict[str, Any]], initial_chunk: int = 100, max_retries: int = 6) -> None`
Robustly index multiple documents with automatic chunking and retry.

**Parameters:**
- `actions` (Iterable[Dict]) - Iterator of documents, each with:
  - `_id` (str) - Document ID
  - `_source` (Dict) - Document fields
- `initial_chunk` (int) - Initial batch size (auto-reduces if throttled)
- `max_retries` (int) - Max retry attempts per chunk

**Algorithm:**
1. Buffer documents up to `initial_chunk` size
2. Convert to OpenSearch bulk format:
   ```json
   {"index": {"_index": "listings", "_id": "12345"}}
   {"price": 450000, "bedrooms": 3, ...}
   ```
3. Send bulk request with `refresh=true`
4. If rate limited (429):
   - Exponential backoff: 0.5s, 1s, 2s, 4s, 8s
   - After 3 retries: split chunk in half and retry each half
5. Log errors for failed documents
6. Continue until all documents indexed

**Example:**
```python
from common import bulk_upsert

# Index 100 listings
actions = []
for listing in listings:
    actions.append({
        "_id": listing["zpid"],
        "_source": {
            "zpid": listing["zpid"],
            "price": listing["price"],
            "bedrooms": listing["bedrooms"],
            "vector_text": listing["vector_text"],
            "has_valid_embeddings": True
        }
    })

# Bulk index with automatic retry/chunking
bulk_upsert(actions, initial_chunk=200)
```

**Performance:**
- 200 docs/batch = ~2-3 seconds
- Auto-splits to 100, 50, 25... if throttled
- 99.9% success rate with retries

---

### Query Understanding Functions

#### `extract_query_constraints(query_text: str) -> Dict[str, Any]`
Parse natural language query using Claude Haiku LLM.

**Parameters:**
- `query_text` (str) - User's search query

**Returns:**
- `Dict[str, Any]` with keys:
  - `must_have` (List[str]) - Required feature tags
  - `nice_to_have` (List[str]) - Preferred features
  - `hard_filters` (Dict) - Numeric constraints
  - `architecture_style` (str or None) - Architecture style
  - `proximity` (Dict or None) - Location-based requirement

**Example:**
```python
from common import extract_query_constraints

# Parse natural language query
query = "3 bedroom modern home with pool under $500k near a school"
constraints = extract_query_constraints(query)
# Returns: {
#   "must_have": ["pool"],
#   "nice_to_have": [],
#   "hard_filters": {
#     "beds_min": 3,
#     "price_max": 500000
#   },
#   "architecture_style": "modern",
#   "proximity": {
#     "poi_type": "school",
#     "max_distance_km": 5
#   }
# }
```

**Supported Constraints:**

**must_have tags:**
- Structural: `balcony`, `porch`, `deck`, `patio`, `fence`, `pool`, `garage`
- Exterior: `white_exterior`, `blue_exterior`, `brick_exterior`, `stone_exterior`
- Interior: `kitchen_island`, `fireplace`, `open_floorplan`, `hardwood_floors`
- Outdoor: `backyard`, `fenced_yard`, `large_yard`

**hard_filters:**
- `price_min`, `price_max` - Price range in USD
- `beds_min` - Minimum bedrooms
- `baths_min` - Minimum bathrooms
- `acreage_min`, `acreage_max` - Lot size range

**proximity:**
- `poi_type` - "school", "grocery_store", "gym", "park", "hospital", etc.
- `max_distance_km` - Distance in kilometers
- `max_drive_time_min` - Drive time in minutes

**Fallback:** If LLM fails, uses simple keyword matching

---

### Zillow Data Parsing

#### `extract_zillow_images(listing: Dict[str, Any], target_width: int = 576) -> List[str]`
Extract image URLs at optimal resolution for embeddings.

**Parameters:**
- `listing` (Dict) - Raw Zillow listing JSON
- `target_width` (int) - Target image width in pixels (default 576 for cost optimization)

**Returns:**
- `List[str]` - Image URLs at target resolution

**Algorithm:**
1. Try `carouselPhotosComposable` (deduplicated, high quality)
2. Try `mixedSources.jpeg` array (multiple resolutions)
3. Find closest match to `target_width` (prefer slightly larger)
4. Fallback to `imgSrc` or `responsivePhotos`
5. Return unique URLs

**Example:**
```python
from common import extract_zillow_images

# Extract images from Zillow listing
images = extract_zillow_images(zillow_listing, target_width=576)
# Returns: [
#   "https://photos.zillowstatic.com/fp/abc-w576.jpg",
#   "https://photos.zillowstatic.com/fp/def-w576.jpg",
#   ...
# ]

# For high-res UI display
images_hires = extract_zillow_images(zillow_listing, target_width=1536)
```

**Cost Optimization:**
- 576px images: ~$0.0003 per embedding
- 1536px images: ~$0.0012 per embedding (4x more expensive!)
- Recommended: Use 576px for embeddings, store full URLs for UI

---

## search.py

**Purpose:** Lambda handler for natural language property search

**Entry Point:** `handler(event, context)`

---

### Lambda Handler

#### `handler(event: Dict, context: Any) -> Dict`
AWS Lambda handler for search requests.

**Input Event:**
```json
{
  "body": "{\"q\": \"3 bedroom home with pool\", \"size\": 15, \"filters\": {\"price_max\": 500000}}"
}
```

**Or direct invocation:**
```json
{
  "q": "3 bedroom home with pool",
  "size": 15,
  "filters": {"price_max": 500000}
}
```

**Parameters (in payload):**
- `q` (str, required) - Search query
- `size` (int, optional) - Max results (default 15)
- `filters` (Dict, optional) - Explicit filters
  - `price_min`, `price_max` (int)
  - `beds_min` (int)
  - `baths_min` (int)
  - `acreage_min`, `acreage_max` (float)

**Returns:**
```json
{
  "statusCode": 200,
  "headers": {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS"
  },
  "body": "{\"ok\": true, \"results\": [...], \"total\": 15, \"must_have\": [...]}"
}
```

**Response Body:**
```json
{
  "ok": true,
  "results": [
    {
      "zpid": "12345",
      "price": 450000,
      "bedrooms": 3,
      "bathrooms": 2.5,
      "address": {
        "streetAddress": "123 Main St",
        "city": "Murray",
        "state": "UT",
        "zipcode": "84107"
      },
      "description": "...",
      "images": ["url1", "url2", ...],
      "image_tags": ["granite_counters", "pool"],
      "architecture_style": "modern",
      "nearby_places": [
        {"name": "Whole Foods", "types": ["grocery_store"], "distance_meters": null},
        {"name": "Murray Park", "types": ["park"], "distance_meters": null}
      ],
      "score": 0.045,
      "boosted": true
    }
  ],
  "total": 15,
  "must_have": ["pool"]
}
```

**Example Usage:**
```bash
# cURL
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{
    "q": "modern home with granite countertops",
    "size": 15,
    "filters": {"price_max": 600000, "beds_min": 3}
  }'
```

```python
# Python
import requests

response = requests.post(
    "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search",
    json={
        "q": "modern home with granite countertops",
        "size": 15,
        "filters": {"price_max": 600000, "beds_min": 3}
    }
)
data = response.json()
results = data["results"]
```

---

### Helper Functions

#### `enrich_with_nearby_places(listing: Dict[str, Any]) -> Dict[str, Any]`
Enrich listing with nearby places from Google Places API.

**Parameters:**
- `listing` (Dict) - Listing with `latitude` and `longitude` fields

**Returns:**
- `Dict` - Listing with added `nearby_places` array

**Algorithm:**
1. Extract coordinates from listing
2. Create cache key (rounded lat/lon)
3. Check DynamoDB cache
4. If cache miss:
   - Call Google Places API (1km radius, max 10 results)
   - Parse response
   - Cache result
5. Add `nearby_places` to listing

**Example:**
```python
from search import enrich_with_nearby_places

listing = {
    "zpid": "12345",
    "latitude": 40.6643,
    "longitude": -111.8893,
    # ... other fields
}

enriched = enrich_with_nearby_places(listing)
# enriched now has:
# {
#   ...
#   "nearby_places": [
#     {"name": "Whole Foods Market", "types": ["grocery_store", "food"], "distance_meters": null},
#     {"name": "Murray City Park", "types": ["park"], "distance_meters": null}
#   ]
# }
```

**Cost:** ~$0.017 per cache miss, $0 per cache hit

---

#### `_rrf(*ranked_lists: List[List[Dict]], k: int = 60, top: int = 50) -> List[Dict]`
Reciprocal Rank Fusion - Combine multiple ranked result lists.

**Parameters:**
- `*ranked_lists` - Variable number of result lists
- `k` (int) - RRF constant (default 60)
- `top` (int) - Number of results to return

**Algorithm:**
```
For each document:
  score = Σ (1 / (k + rank)) across all lists
```

**Example:**
```python
# BM25 results
bm25_hits = [
    {"_id": "123", "_score": 10.5},
    {"_id": "456", "_score": 8.2},
    {"_id": "789", "_score": 7.1}
]

# kNN text results
knn_text_hits = [
    {"_id": "456", "_score": 0.95},
    {"_id": "123", "_score": 0.92},
    {"_id": "999", "_score": 0.88}
]

# kNN image results
knn_img_hits = [
    {"_id": "123", "_score": 0.89},
    {"_id": "789", "_score": 0.85}
]

# Fuse results
from search import _rrf
fused = _rrf(bm25_hits, knn_text_hits, knn_img_hits, top=10)
# zpid=123 appears in all 3 lists → highest RRF score
# zpid=456 appears in 2 lists → medium score
# zpid=789 appears in 2 lists → medium score
# zpid=999 appears in 1 list → lowest score
```

---

## upload_listings.py

**Purpose:** Lambda handler for indexing listings to OpenSearch

**Entry Point:** `handler(event, context)`

---

### Lambda Handler

#### `handler(event: Dict, context: Any) -> Dict`
AWS Lambda handler for indexing listings.

**Input Payload:**
```json
{
  "bucket": "demo-hearth-data",
  "key": "murray_listings.json",
  "start": 0,
  "limit": 50
}
```

**Or direct listing array:**
```json
{
  "listings": [...],
  "start": 0,
  "limit": 50
}
```

**Special Operations:**
```json
{
  "operation": "delete_index"
}
```

**Parameters:**
- `bucket` (str) - S3 bucket name
- `key` (str) - S3 object key
- `start` (int) - Start index in listings array
- `limit` (int) - Max listings to process
- `listings` (List) - Direct listing array (alternative to S3)
- `operation` (str) - Special operation ("delete_index")
- `_invocation_count` (int) - Internal counter for loop detection
- `_job_id` (str) - Job ID for idempotency

**Returns:**
```json
{
  "statusCode": 200,
  "body": "{\"ok\": true, \"index\": \"listings\", \"batch\": {...}, \"next_start\": 50, \"total\": 1588, \"has_more\": true, \"zpid\": \"12345\"}"
}
```

**Example:**
```bash
# Index first 50 listings from S3
aws lambda invoke \
  --function-name hearth-upload-listings \
  --invocation-type Event \
  --payload '{"bucket":"demo-hearth-data","key":"murray_listings.json","start":0,"limit":50}' \
  --region us-east-1 \
  response.json
```

**Self-Invocation:**
- Lambda automatically invokes itself for next batch if more listings remain
- Increments `_invocation_count` to prevent infinite loops
- Max 50 invocations (configurable via `MAX_INVOCATIONS` env var)

---

### Helper Functions

#### `_extract_core_fields(lst: Dict[str, Any]) -> Dict[str, Any]`
Extract and normalize core fields from Zillow JSON.

**Parameters:**
- `lst` (Dict) - Raw Zillow listing

**Returns:**
- `Dict` - Normalized fields:
  - `zpid` (str)
  - `description` (str)
  - `has_description` (bool)
  - `price` (int or None)
  - `bedrooms` (float or None)
  - `bathrooms` (float or None)
  - `livingArea` (float or None)
  - `address` (Dict) - Nested object
  - `city`, `state`, `zip_code` (str)
  - `geo` (Dict or None) - `{"lat": ..., "lon": ...}`

**Handles Variations:**
- Multiple field names (`price` vs `listPrice` vs `unformattedPrice`)
- Nested vs flat address structures
- Missing descriptions (generates fallback)

**Example:**
```python
from upload_listings import _extract_core_fields

zillow_listing = {
    "zpid": "12345",
    "price": 450000,
    "bedrooms": 3,
    "bathrooms": 2.5,
    "address": {
        "streetAddress": "123 Main St",
        "city": "Murray",
        "state": "UT",
        "zipcode": "84107"
    },
    "latitude": 40.6643,
    "longitude": -111.8893,
    "description": "Beautiful home..."
}

core = _extract_core_fields(zillow_listing)
# Returns normalized fields with consistent structure
```

---

#### `_build_doc(base: Dict[str, Any], image_urls: List[str]) -> Dict[str, Any]`
Build complete OpenSearch document with embeddings.

**Parameters:**
- `base` (Dict) - Core fields from `_extract_core_fields()`
- `image_urls` (List[str]) - Image URLs from `extract_zillow_images()`

**Returns:**
- `Dict` - Complete document with:
  - All base fields
  - `image_tags` (List[str]) - Visual features from Claude Vision
  - `architecture_style` (str or None) - Architecture style from vision analysis
  - `vector_text` (List[float]) - Text embedding (1024-dim)
  - `vector_image` (List[float]) - Image embedding (1024-dim)
  - `has_valid_embeddings` (bool)
  - `images` (List[str]) - All image URLs

**Processing Steps:**
1. Generate text embedding (with caching)
2. Process up to `MAX_IMAGES` images:
   - Generate image embedding (with caching)
   - Detect visual features with Claude Vision (with caching)
   - Score for architecture classification
3. Classify architecture style (best exterior image)
4. Average image embeddings
5. Validate embeddings (non-zero check)
6. Combine all fields into document

**Example:**
```python
from upload_listings import _build_doc, _extract_core_fields
from common import extract_zillow_images

# Process listing
core = _extract_core_fields(zillow_listing)
images = extract_zillow_images(zillow_listing, target_width=576)
doc = _build_doc(core, images)

# doc now contains all fields ready for OpenSearch
```

**Performance:** 30-40 seconds per listing (with 90% cache hit rate)

---

## index_local.py

**Purpose:** Local indexing script - Run on your computer instead of Lambda

**Entry Point:** `if __name__ == '__main__': index_all_listings()`

---

### Main Function

#### `index_all_listings() -> None`
Index all 1,588 listings from S3 with verification.

**Algorithm:**
1. Connect to OpenSearch
2. Load all listings from S3
3. For each listing (sequential):
   - Create unique job ID (UUID)
   - Call `upload_listings.handler()` with 1 listing
   - Verify listing exists in OpenSearch
   - Print progress with ETA
4. Print final summary

**Features:**
- ✅ Full control (Ctrl+C to stop anytime)
- ✅ No Lambda timeouts
- ✅ Real-time progress tracking
- ✅ OpenSearch verification per listing
- ✅ Same DynamoDB caching as Lambda

**Usage:**
```bash
# Set AWS credentials first
export AWS_PROFILE=default

# Run indexing
python index_local.py

# Output:
# 🚀 Starting local indexing with OpenSearch verification...
# ============================================================
# Target: 1,588 listings from s3://demo-hearth-data/murray_listings.json
# Caching: DynamoDB (saves Bedrock costs)
# Verification: Each listing verified in OpenSearch
# Progress will be shown in real-time
# ============================================================
#
# 🔧 Connecting to OpenSearch...
# ✅ Connected to OpenSearch
#
# ✅ INDEXED [   1/1588] zpid=12345 |   0.1% | Elapsed: 0m35s | ETA: ~924m | Verified: 1, Errors: 0
# ✅ INDEXED [   2/1588] zpid=12346 |   0.1% | Elapsed: 1m10s | ETA: ~923m | Verified: 2, Errors: 0
# ...
```

**Progress Format:**
```
✅ INDEXED [1234/1588] zpid=12345 | 77.7% | Elapsed: 8h12m | ETA: ~2h | Verified: 1234, Errors: 5
```

**Stop & Resume:**
- Press Ctrl+C to stop anytime
- Progress is saved (DynamoDB cache + OpenSearch)
- Restart script to continue from where you left off

---

### Helper Functions

#### `get_opensearch_client() -> OpenSearch`
Create OpenSearch client for verification queries.

**Returns:**
- `OpenSearch` - Client instance

**Example:**
```python
from index_local import get_opensearch_client

client = get_opensearch_client()
# Use client for queries
```

---

#### `verify_listing_in_opensearch(zpid: str, os_client: OpenSearch) -> bool`
Verify that a listing exists in OpenSearch.

**Parameters:**
- `zpid` (str) - Zillow property ID
- `os_client` (OpenSearch) - OpenSearch client

**Returns:**
- `bool` - True if listing found, False otherwise

**Algorithm:**
```python
try:
    response = os_client.get(index="listings", id=zpid)
    return response.get('found', False)
except:
    return False  # Document not found
```

**Example:**
```python
from index_local import verify_listing_in_opensearch, get_opensearch_client

client = get_opensearch_client()
exists = verify_listing_in_opensearch("12345", client)
if exists:
    print("✅ Listing 12345 is indexed")
else:
    print("❌ Listing 12345 NOT found")
```

---

## Best Practices

### Caching
- Always use DynamoDB caching for embeddings and vision
- Check cache hit rate in CloudWatch logs
- Expected: 90% hit rate after first full index

### Error Handling
- All functions log warnings for non-fatal errors
- Failed documents skip gracefully (don't break batch)
- Use try/except with specific exception types

### Performance
- Use `bulk_upsert()` for multiple documents (10-100x faster than single upserts)
- Batch size: 200 for normal load, 100-150 for busy clusters
- Monitor OpenSearch CPU/JVM in CloudWatch

### Cost Optimization
- Use 576px images for embeddings (4x cheaper than 1536px)
- Enable DynamoDB caching (90% cost savings)
- Cache geolocation lookups (95% savings after warmup)

### Testing
```python
# Test text embedding
from common import embed_text
vec = embed_text("test query")
assert len(vec) == 1024
assert sum(abs(v) for v in vec) > 0  # Non-zero

# Test image embedding
from common import embed_image_from_url
vec = embed_image_from_url("https://example.com/image.jpg")
assert len(vec) == 1024

# Test search
import requests
response = requests.post(
    "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search",
    json={"q": "pool", "size": 5}
)
assert response.status_code == 200
data = response.json()
assert data["ok"] == True
assert len(data["results"]) > 0
```

---

## Troubleshooting

### Common Errors

**ImportError: No module named 'opensearchpy'**
```bash
pip install opensearchpy requests requests-aws4auth boto3
```

**OpenSearch connection timeout**
- Check `OS_HOST` environment variable
- Verify OpenSearch cluster is running
- Check security group allows Lambda/local access

**DynamoDB cache errors**
- Verify tables exist: `hearth-image-cache`, `hearth-geolocation-cache`
- Check IAM permissions for DynamoDB access
- Non-fatal - code continues without cache

**Bedrock throttling (429 errors)**
- Reduce concurrency (Lambda: set to 1)
- Add delays between requests
- Request quota increase in AWS console

**OpenSearch bulk indexing errors**
- Check cluster health: `GET /_cluster/health`
- Reduce batch size (200 → 100 → 50)
- Check CloudWatch for CPU/JVM pressure

---

## Related Documentation

- **API Integration:** [docs/API_INTEGRATION.md](API_INTEGRATION.md)
- **Backend Architecture:** [docs/BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md)
- **Deployment Guide:** [AWS_DEPLOYMENT_GUIDE.md](../AWS_DEPLOYMENT_GUIDE.md)
- **Indexing Guide:** [INDEXING_GUIDE.md](../INDEXING_GUIDE.md)
