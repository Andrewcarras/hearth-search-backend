# Hearth Real Estate Search - Complete System Architecture

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Components](#core-components)
3. [Data Schemas](#data-schemas)
4. [Complete End-to-End Examples](#complete-end-to-end-examples)
5. [Key Algorithms](#key-algorithms)
6. [Cost Analysis](#cost-analysis)
7. [Performance Characteristics](#performance-characteristics)

---

## System Overview

Hearth is a **multimodal semantic search engine** for real estate listings. It combines:
- **Traditional keyword search** (BM25 full-text)
- **Semantic text search** (vector embeddings on descriptions)
- **Visual search** (vector embeddings on property photos)
- **Computer vision analysis** (automated feature extraction from images)
- **Natural language query parsing** (LLM-based intent extraction)

The system is built on AWS using:
- **AWS Lambda** for serverless compute
- **Amazon OpenSearch** for search indexing and vector similarity
- **Amazon Bedrock** for embeddings (Titan models) and vision (Claude Haiku)
- **Amazon S3** for complete listing data storage
- **Amazon DynamoDB** for caching (embeddings, vision analysis, geolocation, S3 data)
- **Google Places API** for location enrichment

---

## Core Components

### 1. common.py - Shared Infrastructure Layer

**Purpose**: Central utilities, AWS clients, and core processing functions used by all modules.

#### Key Global Configuration
```python
# AWS Configuration
AWS_REGION = "us-east-1"
OS_HOST = "search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com"
OS_INDEX = "listings-v2"  # Default index (multi-vector schema)

# Processing Limits
MAX_IMAGES = 0  # 0 = unlimited, process all available images
EMBEDDING_IMAGE_WIDTH = 576  # Resize images to 576px for embeddings (cost optimization)
USE_REKOGNITION = False  # Disabled (Claude Haiku is cheaper and better)

# Caching Tables
VISION_CACHE_TABLE = "hearth-vision-cache"  # Unified cache for embeddings + vision analysis
TEXT_CACHE_TABLE = "hearth-text-embeddings"  # Text embedding cache
```

#### Embedding Generation Functions

**embed_text(text: str) → List[float]**
- Generates 1024-dimensional vector from text using **Amazon Titan Text Embeddings v2**
- Used for: Property descriptions, user search queries
- Cost: ~$0.0001 per call
- Returns: `[0.023, -0.041, 0.115, ...]` (1024 floats)

**embed_image_bytes(img_bytes: bytes) → List[float]**
- Generates 1024-dimensional vector from image using **Amazon Titan Image Embeddings v1**
- Automatically resizes images to EMBEDDING_IMAGE_WIDTH (576px) before processing
- Cost: $0.00006 per image
- Returns: `[0.012, -0.089, 0.201, ...]` (1024 floats)
- **Cached in DynamoDB** (`hearth-vision-cache` table with unified embedding + analysis storage)

#### Vision Analysis Function

**detect_labels(img_bytes: bytes, image_url: str) → Dict[str, Any]**

Uses **Claude 3 Haiku Vision** to perform comprehensive image analysis. This is a single API call that extracts ALL visual information about a property image.

**Input**: Raw image bytes
**Output**: Complete analysis dictionary
```python
{
  "image_type": "exterior",  # or "interior", "unknown"
  "features": [
    "swimming_pool",
    "attached_garage",
    "covered_patio",
    "landscaped_yard"
  ],
  "materials": [
    "brick",
    "granite_countertops",
    "hardwood_floors"
  ],
  "visual_features": [
    "modern_design",
    "open_floor_plan",
    "mountain_views"
  ],
  "architecture_style": "modern",  # Only for exterior images
  "exterior_color": "white",       # Only for exterior images
  "confidence": "high"
}
```

**Caching Strategy** (Unified hearth-vision-cache):
- First checks DynamoDB cache by `image_url`
- If cache hit: Returns cached embedding + analysis + hash (saves $0.00031)
- If cache miss: Generates embedding AND vision analysis (atomic operation)
- Stores complete data in single DynamoDB item:
  ```python
  {
    "image_url": "https://...",
    "embedding": "[0.012, ...]",  # 1024-dim vector
    "analysis": {...},             # Complete vision analysis
    "image_hash": "a3f2d8...",    # MD5 hash for deduplication
    "created_at": "2025-10-15T...",
    "model_version": "titan-v1",
    "analysis_version": "haiku-20250314"
  }
  ```
- Cache hit rate: ~90% during re-indexing, higher for duplicate images

**Cost Optimization**:
- Claude 3 Haiku: $0.00025 per image (~500 input tokens, 100 output tokens)
- Replaces old approach that used separate calls:
  - AWS Rekognition: $0.001 per image (4x more expensive)
  - Claude for architecture: $0.0015 per listing (now done during vision analysis)
  - Total savings: ~$0.0024 per image

#### Query Parsing Function

**extract_query_constraints(query_text: str) → Dict[str, Any]**

Uses **Claude LLM** to parse natural language queries into structured search constraints.

**Example 1: Simple Query**
```python
Input: "3 bedroom house with pool"

Output: {
  "must_have": ["pool"],
  "nice_to_have": [],
  "hard_filters": {
    "beds_min": 3
  },
  "architecture_style": None,
  "proximity": None,
  "query_type": "specific_feature"  # Used for adaptive scoring
}
```

**Example 2: Complex Query**
```python
Input: "modern white brick house with granite countertops and mountain views under $500k"

Output: {
  "must_have": [
    "white_exterior",
    "brick_exterior",
    "granite_countertops",
    "mountain_views"
  ],
  "nice_to_have": [],
  "hard_filters": {
    "price_max": 500000
  },
  "architecture_style": "modern",
  "proximity": None,
  "query_type": "color"  # Detected color keywords → triggers adaptive scoring
}
```

**Example 3: Location Query**
```python
Input: "homes near grocery stores and schools"

Output: {
  "must_have": [],
  "nice_to_have": [],
  "hard_filters": {},
  "architecture_style": None,
  "proximity": {
    "poi_type": "grocery_store",
    "mentioned_pois": ["grocery_store", "school"]
  },
  "query_type": "general"
}
```

**Query Type Classification**:
The `query_type` field is critical for adaptive scoring (explained later):
- `"color"`: White, gray, blue, beige, brown exterior/interior
- `"material"`: Brick, stone, wood, granite, marble, hardwood
- `"visual_style"`: Architecture style, views, visual characteristics
- `"specific_feature"`: Pool, garage, fireplace, specific amenities
- `"room_type"`: Kitchen, bathroom, master bedroom
- `"general"`: Vague or general query

#### OpenSearch Index Management

**create_index_if_needed() → None**

Creates OpenSearch index with schema detection. Supports two schema versions:

**Legacy Schema** (index name: `listings`)
```python
{
  "mappings": {
    "properties": {
      "zpid": {"type": "keyword"},
      "description": {"type": "text"},
      "price": {"type": "integer"},
      "bedrooms": {"type": "float"},
      "bathrooms": {"type": "float"},
      "geo": {"type": "geo_point"},
      "vector_text": {
        "type": "knn_vector",
        "dimension": 1024,
        "method": {
          "name": "hnsw",
          "engine": "nmslib",
          "parameters": {"ef_construction": 512, "m": 16}
        }
      },
      "vector_image": {  # SINGLE averaged vector
        "type": "knn_vector",
        "dimension": 1024,
        "method": {...}
      },
      "image_tags": {"type": "keyword"},
      "feature_tags": {"type": "keyword"},
      "architecture_style": {"type": "keyword"},
      "has_valid_embeddings": {"type": "boolean"}
    }
  }
}
```

**Multi-Vector Schema** (index name: `listings-v2`)
```python
{
  "mappings": {
    "properties": {
      # ... same fields as legacy ...

      "image_vectors": {  # NEW: Nested array of image vectors
        "type": "nested",
        "properties": {
          "image_url": {"type": "keyword"},
          "image_type": {"type": "keyword"},  # exterior/interior
          "vector": {
            "type": "knn_vector",
            "dimension": 1024,
            "method": {
              "name": "hnsw",
              "engine": "nmslib",
              "parameters": {"ef_construction": 512, "m": 16}
            }
          }
        }
      }
    }
  }
}
```

**Why Multi-Vector Schema?**

Problem with averaging:
```
House has 30 images:
- 1 pool photo (embedding: [0.5, 0.8, ...])
- 29 interior photos (embeddings: [-0.2, 0.1, ...])

Averaged vector ≈ [-0.15, 0.13, ...]  # Pool signal is DILUTED
```

Solution with nested vectors:
```
Store ALL 30 vectors separately
Query: "house with pool"
OpenSearch searches each vector independently
Uses score_mode: "max" → BEST matching image wins
Pool photo scores high → Listing ranks well
```

**Race Condition Handling**:
```python
try:
    os_client.indices.create(index=OS_INDEX, body=body)
    logger.info(f"✅ Successfully created index {OS_INDEX}")
except Exception as e:
    if "resource_already_exists_exception" in str(e):
        # Parallel threads may try to create simultaneously
        logger.info(f"Index {OS_INDEX} already exists (created by parallel thread)")
    else:
        raise
```

**bulk_upsert(actions: List[Dict]) → None**

Robust bulk indexing with retry logic and error handling.

```python
def bulk_upsert(actions):
    """
    Index multiple documents with exponential backoff retry.

    Handles:
    - Rate limiting (429)
    - Server errors (502, 503, 504)
    - Chunk splitting if batch too large
    """

    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Prepare bulk request
            bulk_body = []
            for action in actions:
                bulk_body.append({"index": {"_index": OS_INDEX, "_id": action["_id"]}})
                bulk_body.append(action["_source"])

            # Execute bulk index
            response = os_client.bulk(body=bulk_body, refresh=True)

            # Check for errors in response
            if response.get("errors"):
                # Log but don't fail entire batch
                for item in response["items"]:
                    if "error" in item.get("index", {}):
                        logger.error(f"Failed to index {item['index']['_id']}: {item['index']['error']}")

            return

        except Exception as e:
            if "429" in str(e):  # Rate limited
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                logger.warning(f"Rate limited, retrying in {wait_time}s...")
                time.sleep(wait_time)
            elif any(code in str(e) for code in ["502", "503", "504"]):
                # Server error, retry
                time.sleep(2 ** attempt)
            else:
                raise  # Unrecoverable error

    raise Exception("Max retries exceeded")
```

---

### 2. upload_listings.py - Indexing Pipeline Lambda

**Purpose**: Transforms raw Zillow JSON into searchable OpenSearch documents with embeddings.

#### Handler Entry Point

**handler(event, context) → Dict**

Main Lambda entry point. Supports two invocation modes:

**Mode 1: From S3**
```python
event = {
    "bucket": "demo-hearth-data",
    "key": "slc_listings.json",
    "start": 0,
    "limit": 500
}
```

**Mode 2: Direct Data** (used for self-invocation)
```python
event = {
    "listings": [...],  # Complete array
    "start": 500,
    "limit": 500,
    "_invocation_count": 1,
    "_job_id": "abc123"
}
```

#### Processing Flow

**1. Load Listings**
```python
if "listings" in payload:
    # Subsequent invocation - use cached data from previous invocation
    all_listings = payload["listings"]
else:
    # First invocation - download from S3 once
    all_listings = _load_listings_from_s3(bucket, key)
```

**Why pass listings in payload?**
- Without optimization: 4 Lambda invocations = 4 S3 downloads of 12MB file
- With optimization: 1 S3 download, pass data through invocations
- Saves: 3 × 12MB downloads = 36MB transfer, ~2 seconds latency

**2. Process Batch**
```python
start = payload.get("start", 0)
limit = payload.get("limit", 500)
end = min(start + limit, total)

for i in range(start, end):
    # Stop if running out of time (15min Lambda limit)
    if context.get_remaining_time_in_millis() < 30000:  # 30s buffer
        break

    listing = all_listings[i]

    # Extract and process
    core = _extract_core_fields(listing)
    images = extract_zillow_images(listing, target_width=576)
    doc = _build_doc(core, images)

    # Add to batch
    actions.append({"_id": core["zpid"], "_source": doc})

    # Index in batches of 200
    if len(actions) >= 200:
        bulk_upsert(actions)
        actions.clear()

# Index remaining
if actions:
    bulk_upsert(actions)
```

**3. Self-Invocation Chain**
```python
next_start = start + processed
has_more = next_start < total

if has_more and invocation_count < 50:  # Safety limit
    next_payload = {
        "start": next_start,
        "limit": limit,
        "listings": all_listings,  # Pass data forward
        "_invocation_count": invocation_count + 1,
        "_job_id": job_id
    }

    lambda_client.invoke(
        FunctionName=context.invoked_function_arn,
        InvocationType="Event",  # Async
        Payload=json.dumps(next_payload)
    )
```

#### Field Extraction

**_extract_core_fields(lst: Dict) → Dict**

Zillow's JSON format is inconsistent. This function normalizes all variations.

**Example Input** (Zillow raw JSON):
```python
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
    "description": "Beautiful modern home with mountain views...",
    "responsivePhotos": [
        {"mixedSources": {"jpeg": [{"url": "https://..."}]}}
    ]
}
```

**Output** (normalized):
```python
{
    "zpid": "12345678",
    "description": "Beautiful modern home with mountain views...",
    "has_description": True,
    "price": 450000,
    "bedrooms": 3.0,
    "bathrooms": 2.5,
    "livingArea": None,  # Not present in this example
    "address": {
        "streetAddress": "123 Main St",
        "city": "Salt Lake City",
        "state": "UT",
        "zipcode": "84101"
    },
    "city": "Salt Lake City",  # Flat fields for filtering
    "state": "UT",
    "zip_code": "84101",
    "geo": {
        "lat": 40.7608,
        "lon": -111.8910
    }
}
```

**Fallback Description Generation**:
If description is missing:
```python
if not desc.strip():
    fallback_parts = []
    if addr:
        fallback_parts.append(f"Property at {addr}")
    if city and state:
        fallback_parts.append(f"in {city}, {state}")
    if beds:
        fallback_parts.append(f"{int(beds)} bedroom")
    if baths:
        fallback_parts.append(f"{baths} bath")
    if price > 0:
        fallback_parts.append(f"listed at ${price:,}")

    desc = " ".join(fallback_parts)

# Example output: "Property at 123 Main St in Salt Lake City, UT 3 bedroom 2.5 bath listed at $450,000"
```

#### Document Building

**_build_doc(base: Dict, image_urls: List[str]) → Dict**

This is the core processing function that enriches listings with AI-generated data.

**Step-by-Step Process**:

**1. Generate Text Embedding**
```python
vec_text = embed_text(base["description"])
# Returns: [0.023, -0.041, 0.115, ...] (1024 floats)
# Cost: $0.0001
```

**2. Process Images**
```python
image_vecs = []
image_vector_metadata = []  # For multi-vector schema
img_tags = set()
seen_hashes = set()  # For deduplication
style_from_vision = None
best_exterior_score = 0

for url in image_urls:
    # Check MAX_IMAGES limit (0 = unlimited)
    if MAX_IMAGES > 0 and count >= MAX_IMAGES:
        break

    # === OPTIMIZATION: Check embedding cache BEFORE downloading ===
    img_vec = None
    try:
        cached = dynamodb.get_item(
            TableName="hearth-image-cache",
            Key={"image_url": {"S": url}}
        )
        if "Item" in cached and "embedding" in cached["Item"]:
            img_vec = json.loads(cached["Item"]["embedding"]["S"])
            logger.debug("💾 Cache hit for image embedding")
    except:
        pass

    # Download image only if needed
    if img_vec is None:
        resp = requests.get(url, timeout=8)
        img_bytes = resp.content

        # Generate embedding
        img_vec = embed_image_bytes(img_bytes)

        # Cache for future use
        dynamodb.put_item(
            TableName="hearth-image-cache",
            Item={
                "image_url": {"S": url},
                "embedding": {"S": json.dumps(img_vec)},
                "created_at": {"N": str(int(time.time()))}
            }
        )
    else:
        # Need to download for deduplication check
        resp = requests.get(url, timeout=8)
        img_bytes = resp.content

    # === DEDUPLICATION: Skip duplicate images ===
    import hashlib
    img_hash = hashlib.md5(img_bytes).hexdigest()
    if img_hash in seen_hashes:
        continue  # Skip this image
    seen_hashes.add(img_hash)

    # NOW safe to add embedding
    image_vecs.append(img_vec)

    # === VISION ANALYSIS ===
    analysis = detect_labels(img_bytes, image_url=url)
    # Returns: {
    #   "image_type": "exterior",
    #   "features": ["pool", "garage"],
    #   "materials": ["brick"],
    #   "visual_features": ["modern_design"],
    #   "architecture_style": "modern",
    #   "exterior_color": "white",
    #   "confidence": "high"
    # }

    # Extract all features into tags
    for feature in analysis.get("features", []):
        img_tags.add(feature)  # "pool", "garage"

    for material in analysis.get("materials", []):
        img_tags.add(material)  # "brick"

    for visual in analysis.get("visual_features", []):
        img_tags.add(visual)  # "modern_design"

    # Add exterior color (both formats for compatibility)
    if analysis.get("exterior_color"):
        img_tags.add(f"{analysis['exterior_color']} exterior")
        img_tags.add(f"{analysis['exterior_color']}_exterior")
        # Example: "white exterior" and "white_exterior"

    # Track best exterior image for architecture style
    if analysis.get("image_type") == "exterior":
        exterior_score = 10 if analysis.get("architecture_style") else 5

        if exterior_score > best_exterior_score:
            best_exterior_score = exterior_score
            style_from_vision = analysis.get("architecture_style")

    # Store metadata for multi-vector schema
    if img_vec and analysis:
        image_vector_metadata.append({
            "image_url": url,
            "image_type": analysis.get("image_type", "unknown"),
            "vector": img_vec
        })
```

**3. Build Final Document**
```python
# Detect schema version
is_multi_vector = OS_INDEX.endswith("-v2")

doc = {
    **base,  # All core fields (zpid, price, address, etc.)
    "llm_profile": "",  # Legacy field, now always empty
    "feature_tags": [],  # Legacy field, now always empty
    "image_tags": sorted(img_tags),  # From vision analysis
    "images": image_urls,  # All URLs for frontend display
    "has_valid_embeddings": True,
    "status": "active",
    "indexed_at": int(time.time())
}

# Add text embedding
if vec_text:
    doc["vector_text"] = vec_text

# Add image vectors based on schema
if is_multi_vector:
    # Multi-vector: Store ALL vectors separately
    if image_vector_metadata:
        doc["image_vectors"] = image_vector_metadata
        # Example:
        # [
        #   {"image_url": "https://...", "image_type": "exterior", "vector": [...]},
        #   {"image_url": "https://...", "image_type": "interior", "vector": [...]}
        # ]
else:
    # Legacy: Average all vectors into one
    if image_vecs:
        vec_image = vec_mean(image_vecs, target_dim=1024)
        doc["vector_image"] = vec_image

# Add architecture style if detected
if style_from_vision:
    doc["architecture_style"] = style_from_vision

return doc
```

**Example Complete Document** (listings-v2):
```python
{
    "zpid": "12345678",
    "price": 450000,
    "bedrooms": 3.0,
    "bathrooms": 2.5,
    "description": "Beautiful modern home with mountain views...",
    "address": {
        "streetAddress": "123 Main St",
        "city": "Salt Lake City",
        "state": "UT",
        "zipcode": "84101"
    },
    "city": "Salt Lake City",
    "state": "UT",
    "zip_code": "84101",
    "geo": {"lat": 40.7608, "lon": -111.8910},

    "vector_text": [0.023, -0.041, ...],  # 1024-dim

    "image_vectors": [
        {
            "image_url": "https://.../exterior.jpg",
            "image_type": "exterior",
            "vector": [0.5, 0.8, ...]  # 1024-dim
        },
        {
            "image_url": "https://.../kitchen.jpg",
            "image_type": "interior",
            "vector": [-0.2, 0.1, ...]  # 1024-dim
        }
        # ... 20 more images
    ],

    "image_tags": [
        "attached_garage",
        "brick_exterior",
        "granite_countertops",
        "hardwood_floors",
        "modern_design",
        "mountain_views",
        "open_floor_plan",
        "swimming_pool",
        "white exterior",
        "white_exterior"
    ],

    "images": [
        "https://.../exterior.jpg",
        "https://.../kitchen.jpg",
        # ... 20 more URLs
    ],

    "architecture_style": "modern",
    "has_valid_embeddings": true,
    "status": "active",
    "indexed_at": 1678901234
}
```

---

### 3. search.py - Hybrid Search Engine Lambda

**Purpose**: Executes natural language property searches using Reciprocal Rank Fusion.

#### Handler Entry Point

**handler(event, context) → Dict**

Main search Lambda handler.

**Request Format**:
```python
{
    "q": "3 bedroom white brick house with pool under $500k",
    "size": 15,  # Number of results
    "index": "listings-v2",  # Optional, defaults to OS_INDEX
    "include_full_data": True,  # Merge S3 Zillow data
    "include_nearby_places": True,  # Add Google Places
    "filters": {  # Optional explicit filters
        "price_max": 500000,
        "beds_min": 3
    }
}
```

**Response Format**:
```python
{
    "ok": True,
    "results": [
        {
            "zpid": "12345678",
            "id": "12345678",
            "score": 2.456,  # RRF score with boosting
            "boosted": True,

            # All OpenSearch fields
            "price": 450000,
            "bedrooms": 3.0,
            "bathrooms": 2.5,
            "description": "...",
            "image_tags": ["white_exterior", "brick_exterior", "pool"],
            "architecture_style": "modern",
            "geo": {"lat": 40.7608, "lon": -111.8910},

            # S3 data (if include_full_data=true)
            "original_listing": {
                # 166+ Zillow fields
                "responsivePhotos": [...],
                "zestimate": 475000,
                "taxAssessedValue": 420000,
                # etc.
            },

            # Google Places (if include_nearby_places=true)
            "nearby_places": [
                {"name": "Whole Foods", "types": ["grocery_store"], "distance_meters": null},
                {"name": "Mountain View Elementary", "types": ["school"], "distance_meters": null}
            ]
        }
        # ... 14 more results
    ],
    "total": 15,
    "must_have": ["white_exterior", "brick_exterior", "pool"],
    "architecture_style": null
}
```

#### Search Pipeline

**Step 1: Parse Query**
```python
q = "3 bedroom white brick house with pool under $500k"

constraints = extract_query_constraints(q)
# Returns:
# {
#   "must_have": ["white_exterior", "brick_exterior", "pool"],
#   "nice_to_have": [],
#   "hard_filters": {"beds_min": 3, "price_max": 500000},
#   "architecture_style": null,
#   "proximity": null,
#   "query_type": "color"  # Triggers adaptive scoring
# }

must_tags = set(constraints["must_have"])
hard_filters = constraints["hard_filters"]
query_type = constraints["query_type"]
```

**Step 2: Expand Tags for Compatibility**
```python
# Image tags are stored in two formats: "white_exterior" and "white exterior"
# Ensure we match both

expanded_must_tags = set()
for tag in must_tags:
    expanded_must_tags.add(tag)  # "white_exterior"
    expanded_must_tags.add(tag.replace("_", " "))  # "white exterior"

# expanded_must_tags = {
#   "white_exterior", "white exterior",
#   "brick_exterior", "brick exterior",
#   "pool"
# }
```

**Step 3: Generate Query Embedding**
```python
q_vec = embed_text(q)
# Returns: [0.045, -0.023, 0.112, ...] (1024 floats)
```

**Step 4: Build Filters**
```python
filter_clauses = []

# Price filter
if "price_max" in hard_filters:
    filter_clauses.append({
        "range": {"price": {"lte": 500000}}
    })
else:
    # Default: exclude price=0 (sold/unlisted)
    filter_clauses.append({
        "range": {"price": {"gt": 0}}
    })

# Bedrooms filter
if "beds_min" in hard_filters:
    filter_clauses.append({
        "range": {"bedrooms": {"gte": 3}}
    })

# Require valid embeddings (for kNN search)
filter_clauses.append({
    "term": {"has_valid_embeddings": True}
})

# Final filter clause:
# [
#   {"range": {"price": {"lte": 500000}}},
#   {"range": {"bedrooms": {"gte": 3}}},
#   {"term": {"has_valid_embeddings": True}}
# ]
```

**Step 5: Execute 3 Parallel Searches**

**5a. BM25 Full-Text Search**
```python
bm25_query = {
    "query": {
        "bool": {
            "filter": filter_clauses,
            "should": [
                # Multi-match across text fields with boosting
                {
                    "multi_match": {
                        "query": "3 bedroom white brick house with pool under $500k",
                        "fields": [
                            "description^3",    # 3x weight
                            "llm_profile^2",    # 2x weight (always empty now)
                            "address^0.5",      # 0.5x weight
                            "city^0.3",
                            "state^0.2"
                        ],
                        "type": "best_fields"
                    }
                },
                # Tag boosts (soft matching)
                {
                    "terms": {
                        "feature_tags": ["white_exterior", "white exterior", "brick_exterior", "brick exterior", "pool"]
                    }
                },
                {
                    "terms": {
                        "image_tags": ["white_exterior", "white exterior", "brick_exterior", "brick exterior", "pool"]
                    }
                }
            ],
            "minimum_should_match": 1
        }
    },
    "size": 45  # size * 3 for RRF
}

bm25_hits = os_client.search(index="listings-v2", body=bm25_query)["hits"]["hits"]
# Returns: [
#   {"_id": "12345", "_score": 8.5, "_source": {...}},
#   {"_id": "67890", "_score": 7.2, "_source": {...}},
#   ...
# ]
```

**5b. kNN Text Similarity Search**
```python
knn_text_query = {
    "size": 45,
    "query": {
        "bool": {
            "must": [
                {
                    "knn": {
                        "vector_text": {
                            "vector": q_vec,  # [0.045, -0.023, ...]
                            "k": 100  # Find 100 nearest neighbors
                        }
                    }
                }
            ],
            "filter": filter_clauses
        }
    }
}

knn_text_hits = os_client.search(index="listings-v2", body=knn_text_query)["hits"]["hits"]
# Returns: [
#   {"_id": "23456", "_score": 0.92, "_source": {...}},  # High cosine similarity
#   {"_id": "34567", "_score": 0.88, "_source": {...}},
#   ...
# ]
```

**5c. kNN Image Similarity Search (Multi-Vector)**
```python
# For listings-v2 (multi-vector schema)
knn_image_query = {
    "size": 45,
    "query": {
        "bool": {
            "must": [
                {
                    "nested": {
                        "path": "image_vectors",
                        "score_mode": "max",  # BEST matching image wins!
                        "query": {
                            "knn": {
                                "image_vectors.vector": {
                                    "vector": q_vec,
                                    "k": 100
                                }
                            }
                        }
                    }
                }
            ],
            "filter": filter_clauses
        }
    }
}

knn_img_hits = os_client.search(index="listings-v2", body=knn_image_query)["hits"]["hits"]
# Returns: [
#   {"_id": "45678", "_score": 0.85, "_source": {...}},
#   {"_id": "56789", "_score": 0.79, "_source": {...}},
#   ...
# ]
```

**How Multi-Vector Search Works**:
```
Listing has 22 images with vectors:
- Image 1 (exterior): similarity = 0.45
- Image 2 (kitchen): similarity = 0.32
- Image 3 (pool): similarity = 0.91  ← BEST MATCH
- Image 4 (bedroom): similarity = 0.28
- ...
- Image 22 (backyard): similarity = 0.52

score_mode: "max" → Listing scores 0.91 (from pool image)

If we used average:
Average = (0.45 + 0.32 + 0.91 + ... + 0.52) / 22 ≈ 0.48
Pool signal would be DILUTED!
```

**Step 6: Calculate Adaptive RRF Weights**

This is a **critical innovation** that solves the "white house returns gray houses" problem.

```python
def calculate_adaptive_weights(must_have_tags, query_type):
    COLOR_KEYWORDS = ['white', 'gray', 'grey', 'blue', 'beige', 'brown', ...]
    MATERIAL_KEYWORDS = ['brick', 'stone', 'wood', 'granite', 'marble', ...]

    has_color = any(any(color in tag.lower() for color in COLOR_KEYWORDS) for tag in must_have_tags)
    has_material = any(any(mat in tag.lower() for mat in MATERIAL_KEYWORDS) for tag in must_have_tags)

    # Start balanced
    bm25_k = 60
    text_k = 60
    image_k = 60

    if has_color:
        bm25_k = 30      # BOOST BM25 (tags have exact color)
        image_k = 120    # DE-BOOST images (embeddings don't capture color)

    if has_material:
        bm25_k = int(bm25_k * 0.7)  # Further boost
        text_k = 45

    if query_type == "visual_style":
        image_k = 40     # BOOST images for architecture queries
        text_k = 45

    return [bm25_k, text_k, image_k]

# For our query: "white brick house with pool"
k_values = calculate_adaptive_weights(
    must_have_tags=["white_exterior", "brick_exterior", "pool"],
    query_type="color"
)
# Returns: [21, 45, 120]
#          ^^  ^^  ^^^
#          BM25 gets HIGHEST weight (lowest k)
#          Images get LOWEST weight (highest k)
```

**Why This Works**:
```
Problem: Image embeddings capture texture/structure but NOT color
- White house exterior embedding ≈ [0.5, 0.3, 0.2, ...]
- Gray house exterior embedding ≈ [0.48, 0.29, 0.21, ...]  ← Very similar!

Solution: Vision analysis extracts exact color tags
- White house → image_tags: ["white_exterior"]
- Gray house → image_tags: ["gray_exterior"]
- BM25 search on tags finds EXACT matches

Adaptive weights ensure BM25 (which uses tags) dominates the scoring
```

**Step 7: Reciprocal Rank Fusion (RRF)**

```python
def _rrf(bm25_hits, knn_text_hits, knn_img_hits, k_values=[21, 45, 120], top=45):
    """
    Combine 3 ranked lists using RRF algorithm.

    Formula: score = Σ(1 / (k + rank))
    Lower k = higher weight for that list
    """
    scores = {}

    # Process BM25 results (k=21, highest weight)
    for rank, hit in enumerate(bm25_hits, start=1):
        zpid = hit["_id"]
        scores.setdefault(zpid, {"doc": hit, "score": 0.0})
        scores[zpid]["score"] += 1.0 / (21 + rank)

    # Process kNN text results (k=45, medium weight)
    for rank, hit in enumerate(knn_text_hits, start=1):
        zpid = hit["_id"]
        scores.setdefault(zpid, {"doc": hit, "score": 0.0})
        scores[zpid]["score"] += 1.0 / (45 + rank)

    # Process kNN image results (k=120, lowest weight)
    for rank, hit in enumerate(knn_img_hits, start=1):
        zpid = hit["_id"]
        scores.setdefault(zpid, {"doc": hit, "score": 0.0})
        scores[zpid]["score"] += 1.0 / (120 + rank)

    # Sort by fused score
    fused = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return [x["doc"] for x in fused[:top]]

fused = _rrf(bm25_hits, knn_text_hits, knn_img_hits, k_values=[21, 45, 120], top=45)
# Returns top 45 fused results
```

**RRF Example**:
```
Listing zpid=12345:
- Appears at rank 2 in BM25 (score contribution: 1/(21+2) = 0.0435)
- Appears at rank 15 in kNN text (score contribution: 1/(45+15) = 0.0167)
- Appears at rank 8 in kNN image (score contribution: 1/(120+8) = 0.0078)
- Final RRF score: 0.0435 + 0.0167 + 0.0078 = 0.068

Listing zpid=67890:
- Appears at rank 1 in BM25 (score: 1/(21+1) = 0.0455)
- Doesn't appear in kNN text (score: 0)
- Appears at rank 50 in kNN image (score: 1/(120+50) = 0.0059)
- Final RRF score: 0.0455 + 0 + 0.0059 = 0.0514

Result: zpid=12345 ranks higher (0.068 > 0.0514)
```

**Step 8: Post-RRF Tag Boosting**

```python
final = []
for hit in fused:
    src = hit["_source"]
    tags = set(src.get("feature_tags", []) + src.get("image_tags", []))

    # Calculate boost based on tag match percentage
    boost = 1.0
    if expanded_must_tags:
        matched_tags = expanded_must_tags.intersection(tags)
        match_ratio = len(matched_tags) / len(expanded_must_tags)

        if match_ratio >= 1.0:    # All tags matched
            boost = 2.0
        elif match_ratio >= 0.75:  # 75% matched
            boost = 1.5
        elif match_ratio >= 0.50:  # 50% matched
            boost = 1.25

    result = {
        "zpid": hit["_id"],
        "score": hit["_score"] * boost,  # Apply boost
        "boosted": boost > 1.0,
        # ... all other fields
    }

    final.append(result)

# Example:
# Listing has tags: ["white_exterior", "brick_exterior", "pool", "garage"]
# Must have: ["white_exterior", "brick_exterior", "pool"]
# Match ratio: 3/3 = 100% → boost = 2.0
# Original score: 0.068 → Boosted score: 0.136
```

**Step 9: Enrich Results**

**9a. Merge S3 Data** (if `include_full_data=true`)
```python
def _fetch_listing_from_s3(zpid):
    # Check DynamoDB cache first (1-hour TTL)
    cached = dynamodb.get_item(
        TableName="hearth-s3-listing-cache",
        Key={"zpid": {"S": zpid}}
    )

    if cached and not_expired(cached):
        return json.loads(cached["Item"]["data"]["S"])

    # Cache miss - fetch from S3
    response = s3.get_object(
        Bucket="demo-hearth-data",
        Key=f"listings/{zpid}.json"
    )
    data = json.loads(response["Body"].read())

    # Cache for next time
    dynamodb.put_item(
        TableName="hearth-s3-listing-cache",
        Item={
            "zpid": {"S": zpid},
            "data": {"S": json.dumps(data)},
            "cached_at": {"N": str(int(time.time()))}
        }
    )

    return data

# Merge into result
for result in final:
    s3_data = _fetch_listing_from_s3(result["zpid"])
    result["original_listing"] = s3_data
    # Adds 166+ Zillow fields: responsivePhotos, zestimate, etc.
```

**9b. Add Nearby Places** (if `include_nearby_places=true`)
```python
def enrich_with_nearby_places(listing):
    lat = listing["geo"]["lat"]
    lon = listing["geo"]["lon"]

    # Round to 3 decimals (~111m precision) for cache hits
    location_key = f"{round(lat, 3)},{round(lon, 3)},1000"

    # Check DynamoDB cache
    cached = dynamodb.get_item(
        TableName="hearth-geolocation-cache",
        Key={"location_key": {"S": location_key}}
    )

    if cached:
        listing["nearby_places"] = json.loads(cached["Item"]["places"]["S"])
        return listing

    # Cache miss - call Google Places API (New)
    url = "https://places.googleapis.com/v1/places:searchNearby"
    payload = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": 1000.0  # 1km
            }
        },
        "maxResultCount": 10
    }

    response = requests.post(url, json=payload, headers={
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.types,places.location"
    })

    places = []
    for place in response.json().get("places", [])[:10]:
        places.append({
            "name": place["displayName"]["text"],
            "types": place["types"],
            "distance_meters": None
        })

    # Cache results
    dynamodb.put_item(
        TableName="hearth-geolocation-cache",
        Item={
            "location_key": {"S": location_key},
            "places": {"S": json.dumps(places)},
            "cached_at": {"N": str(int(time.time()))}
        }
    )

    listing["nearby_places"] = places
    return listing

# Example output:
# "nearby_places": [
#   {"name": "Whole Foods Market", "types": ["grocery_store", "food"], "distance_meters": null},
#   {"name": "Mountain View Elementary", "types": ["school", "education"], "distance_meters": null}
# ]
```

**Step 10: Return Results**
```python
# Sort final results by boosted score
final.sort(key=lambda x: x["score"], reverse=True)
results = final[:size]  # Take top 15

return {
    "statusCode": 200,
    "headers": cors_headers,
    "body": json.dumps({
        "ok": True,
        "results": results,
        "total": len(results),
        "must_have": list(must_tags)
    })
}
```

---

### 4. crud_listings.py - CRUD Operations Lambda

**Purpose**: Provides admin API for managing individual listings.

#### UPDATE Handler

**PATCH /listings/{zpid}**
```python
Request:
{
    "updates": {
        "price": 425000,  # Changed from $450k to $425k
        "status": "pending",
        "custom_notes": "Price reduced!"
    },
    "options": {
        "preserve_embeddings": true,  # Don't regenerate (expensive)
        "remove_fields": ["old_field"]
    }
}

Response:
{
    "ok": true,
    "zpid": "12345678",
    "updated_fields": ["price", "status", "custom_notes"],
    "removed_fields": ["old_field"]
}
```

**Implementation**:
```python
# Fetch existing document
response = os_client.get(index="listings-v2", id=zpid)
doc = response["_source"]

# Apply updates
for key, value in updates.items():
    doc[key] = value

# Remove fields
for field in remove_fields:
    if field in doc:
        del doc[field]

# Update timestamp
doc["updated_at"] = int(time.time())

# Re-index
os_client.index(index="listings-v2", id=zpid, body=doc)
```

#### CREATE Handler

**POST /listings**
```python
Request:
{
    "listing": {
        "zpid": "custom_abc123",  # Optional, auto-generated if not provided
        "price": 500000,
        "bedrooms": 4,
        "bathrooms": 3,
        "address": "456 Oak Ave",
        "city": "Salt Lake City",
        "state": "UT",
        "description": "Spacious family home...",
        "images": [
            "https://example.com/photo1.jpg",
            "https://example.com/photo2.jpg"
        ]
    },
    "options": {
        "process_images": true,  # Run vision analysis + embeddings
        "generate_embeddings": true,
        "source": "manual_entry"
    }
}

Response:
{
    "ok": true,
    "zpid": "custom_abc123",
    "indexed": true,
    "processing_cost": 0.0042,
    "images_processed": 2
}
```

**Implementation**:
```python
# Generate zpid if not provided
if not zpid:
    zpid = f"custom_{uuid.uuid4().hex[:12]}"

# Build base document
doc = {
    **listing_data,
    "source": "manual_entry",
    "created_at": int(time.time()),
    "indexed_at": int(time.time()),
    "status": "active",
    "searchable": True
}

# Generate text embedding
if doc.get("description"):
    vec_text = embed_text(doc["description"])
    doc["vector_text"] = vec_text

# Process images if requested
if process_images and doc.get("images"):
    image_vecs = []
    image_vector_metadata = []
    img_tags = set()

    for url in doc["images"][:10]:
        # Download image
        resp = requests.get(url, timeout=8)
        img_bytes = resp.content

        # Generate embedding
        img_vec = embed_image_bytes(img_bytes)
        image_vecs.append(img_vec)

        # Run vision analysis
        analysis = detect_labels(img_bytes, image_url=url)
        for feature in analysis.get("features", []):
            img_tags.add(feature)

        # Store metadata
        image_vector_metadata.append({
            "image_url": url,
            "image_type": analysis.get("image_type", "unknown"),
            "vector": img_vec
        })

    # Detect schema
    is_multi_vector = target_index.endswith("-v2")

    if is_multi_vector:
        doc["image_vectors"] = image_vector_metadata
    else:
        doc["vector_image"] = vec_mean(image_vecs, target_dim=1024)

    doc["image_tags"] = sorted(img_tags)

# Index to OpenSearch
os_client.index(index="listings-v2", id=zpid, body=doc)
```

#### DELETE Handler

**DELETE /listings/{zpid}?soft=true**
```python
# Soft delete (default): Mark as deleted
if soft_delete:
    response = os_client.get(index="listings-v2", id=zpid)
    doc = response["_source"]
    doc["status"] = "deleted"
    doc["deleted_at"] = int(time.time())
    os_client.index(index="listings-v2", id=zpid, body=doc)

# Hard delete: Remove from index
else:
    os_client.delete(index="listings-v2", id=zpid)

Response:
{
    "ok": true,
    "zpid": "12345678",
    "deleted": true,
    "soft_delete": true
}
```

---

### 5. index_local.py - Local Indexing Script

**Purpose**: Run indexing on your local machine instead of Lambda (for development/testing).

**Why Use This?**
- Lambda has 15-minute timeout (can't index large datasets in one run)
- Local script has no timeout
- 5-10x faster (no cold starts, direct S3 download)
- Better debugging (full stack traces, breakpoints)
- Full control (pause, resume, adjust parameters)

**Usage**:
```bash
# Index 50 listings to listings-v2 with unlimited images
python3 index_local.py \
    --bucket demo-hearth-data \
    --key slc_listings.json \
    --index listings-v2 \
    --limit 50 \
    --max-images 0 \
    --batch-size 5

# Output:
🚀 Starting OPTIMIZED local indexing...
======================================================================
Source: s3://demo-hearth-data/slc_listings.json
Target: OpenSearch index 'listings-v2' @ search-hearth-opensearch-...
Range: start=0, limit=50
Batch size: 5 listings in parallel
Max images per listing: 0 (unlimited)
======================================================================

📥 Loading listings from s3://demo-hearth-data/slc_listings.json...
✅ Loaded 1,588 listings from S3
📊 Processing range: [0:50] = 50 listings

🔧 Connecting to OpenSearch @ search-hearth-opensearch-...
✅ Connected to index 'listings-v2'

📦 BATCH [1-5] Processing 5 listings in parallel...
  ✅ [   1] zpid=12345678 completed
  ✅ [   2] zpid=12345679 completed
  ✅ [   3] zpid=12345680 completed
  ✅ [   4] zpid=12345681 completed
  ✅ [   5] zpid=12345682 completed

✅ BATCH COMPLETE in 42.3s | Verified: 5/5
📊 PROGRESS: 5/50 (10.0%) | Elapsed: 0h0m | ETA: ~0h6m | Rate: 7.1/min | Errors: 0

... continues for all batches ...

======================================================================
✅ INDEXING COMPLETE!
======================================================================
Source: s3://demo-hearth-data/slc_listings.json
Target: listings-v2
Range: 0 to 50 (50 listings)
✅ Verified in OpenSearch: 50 listings
❌ Errors: 0 listings
⏱️  Time taken: 0h 6m 32s
📊 Average: 7.8s per verified listing
```

**How It Works**:

**1. Parse Arguments**
```python
parser = argparse.ArgumentParser()
parser.add_argument('--bucket', required=True)
parser.add_argument('--key', required=True)
parser.add_argument('--start', type=int, default=0)
parser.add_argument('--limit', type=int, default=None)
parser.add_argument('--index', default='listings')
parser.add_argument('--batch-size', type=int, default=5)
parser.add_argument('--max-images', type=int, default=10)
args = parser.parse_args()
```

**2. Set Environment Variables**
```python
# CRITICAL: Set BEFORE importing common.py
# (common.py reads these at import time)
os.environ['OS_HOST'] = args.host
os.environ['OS_INDEX'] = args.index
os.environ['MAX_IMAGES'] = str(args.max_images)
```

**3. Load S3 Data Once**
```python
# Lambda approach: Re-download for each self-invocation
# Local approach: Download ONCE at startup

s3 = boto3.client('s3')
response = s3.get_object(Bucket=args.bucket, Key=args.key)
all_listings = json.loads(response['Body'].read())

# Apply start/limit
all_listings = all_listings[args.start:args.start+args.limit]

# Now have all data in memory
```

**4. Process in Parallel Batches**
```python
from concurrent.futures import ThreadPoolExecutor

batch_size = 5
for batch_start in range(0, len(all_listings), batch_size):
    batch = all_listings[batch_start:batch_start+batch_size]

    # Process batch in parallel
    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        futures = {
            executor.submit(process_single_listing, listing, os_client): idx
            for idx, listing in enumerate(batch)
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            print(f"✅ zpid={result['zpid']} completed")

def process_single_listing(listing_data, os_client):
    """Process one listing by calling upload_listings.handler()"""

    # Create payload for handler
    payload = {
        "listings": [listing_data],  # Single listing
        "start": 0,
        "limit": 1,
        "_invocation_count": 0,
        "_job_id": str(uuid.uuid4())
    }

    # Create mock Lambda context
    context = MockContext()

    # Call handler directly (no Lambda invoke!)
    result = handler(payload, context)

    # Verify in OpenSearch
    verified = os_client.get(index="listings-v2", id=listing_data["zpid"])["found"]

    return {"zpid": listing_data["zpid"], "verified": verified}
```

**5. Calculate Progress**
```python
total_verified = 0
start_time = time.time()

# After each batch
elapsed = int(time.time() - start_time)
percent = (total_verified / total_listings) * 100
rate = total_verified / elapsed if elapsed > 0 else 0
remaining = total_listings - total_verified
eta_secs = int(remaining / rate) if rate > 0 else 0

print(f"📊 PROGRESS: {total_verified}/{total_listings} ({percent:.1f}%) | "
      f"ETA: ~{eta_secs//3600}h{(eta_secs%3600)//60}m | "
      f"Rate: {rate*60:.1f}/min")
```

---

## Data Schemas

### OpenSearch Document Schema (listings-v2)

```python
{
    # === IDENTITY ===
    "zpid": "12345678",                    # Zillow Property ID (document _id)
    "source": "zillow_scrape",             # zillow_scrape | manual_entry | api

    # === PROPERTY DETAILS ===
    "price": 450000,                       # Integer
    "bedrooms": 3.0,                       # Float (allows 2.5, 3.5, etc.)
    "bathrooms": 2.5,                      # Float
    "livingArea": 2100.0,                  # Square feet (float)

    # === LOCATION ===
    "address": {
        "streetAddress": "123 Main St",
        "city": "Salt Lake City",
        "state": "UT",
        "zipcode": "84101"
    },
    "city": "Salt Lake City",              # Flat for filtering
    "state": "UT",
    "zip_code": "84101",
    "geo": {                                # Geo-point for distance queries
        "lat": 40.7608,
        "lon": -111.8910
    },

    # === TEXT DATA ===
    "description": "Beautiful modern home with mountain views...",
    "has_description": true,               # Quality flag
    "llm_profile": "",                     # Legacy (always empty now)

    # === EMBEDDINGS (EXCLUDED FROM RESPONSE) ===
    "vector_text": [0.023, -0.041, ...],  # 1024-dim text embedding
    "image_vectors": [                     # Multi-vector schema (listings-v2 only)
        {
            "image_url": "https://.../exterior1.jpg",
            "image_type": "exterior",
            "vector": [0.5, 0.8, ...]      # 1024-dim
        },
        {
            "image_url": "https://.../kitchen.jpg",
            "image_type": "interior",
            "vector": [-0.2, 0.1, ...]     # 1024-dim
        }
        # ... 20+ more images
    ],

    # === VISION-EXTRACTED FEATURES ===
    "image_tags": [                        # From Claude Haiku Vision
        "attached_garage",
        "brick_exterior",
        "granite_countertops",
        "hardwood_floors",
        "modern_design",
        "mountain_views",
        "open_floor_plan",
        "swimming_pool",
        "white exterior",                  # Space format
        "white_exterior"                   # Underscore format
    ],
    "architecture_style": "modern",        # From best exterior image
    "feature_tags": [],                    # Legacy (always empty now)

    # === IMAGES ===
    "images": [                            # All URLs for frontend display
        "https://photos.zillowstatic.com/...",
        "https://photos.zillowstatic.com/...",
        # ... 22 total
    ],

    # === METADATA ===
    "has_valid_embeddings": true,          # For filtering during search
    "status": "active",                    # active | sold | deleted | pending
    "indexed_at": 1678901234,             # Unix timestamp
    "updated_at": 1678905678,             # Unix timestamp (if updated)
    "created_at": 1678900000,             # Unix timestamp (for manual entries)

    # === CUSTOM FIELDS (via CRUD API) ===
    "custom_notes": "Any value",           # Flexible schema
    "agent_contact": "john@example.com"
}
```

### DynamoDB Cache Tables

**1. hearth-image-cache**
```python
{
    "image_url": "https://photos.zillowstatic.com/...",  # Partition key
    "embedding": "[0.5, 0.8, -0.2, ...]",                # JSON string (1024 floats)
    "created_at": 1678901234
}
```

**2. hearth-geolocation-cache**
```python
{
    "location_key": "40.761,-111.891,1000",  # Partition key (lat,lon,radius)
    "places": "[{\"name\": \"Whole Foods\", \"types\": [...]}]",  # JSON string
    "cached_at": 1678901234
}
```

**3. hearth-s3-listing-cache**
```python
{
    "zpid": "12345678",                      # Partition key
    "data": "{...}",                         # Complete Zillow JSON (166+ fields)
    "cached_at": 1678901234
}
```

### S3 Storage Structure

```
s3://demo-hearth-data/
├── slc_listings.json              # Source data (1,588 listings)
├── listings/                      # Individual listing JSONs
│   ├── 12345678.json             # Complete Zillow data
│   ├── 12345679.json
│   └── ...
└── ui/                            # Frontend files
    ├── ui_update.sh
    ├── search.html
    └── admin/
        └── index.html
```

---

## Complete End-to-End Examples

### Example 1: Uploading a Listing

**Scenario**: Index one listing from Zillow scrape data.

**Input Data** (slc_listings.json):
```python
{
    "zpid": 12778555,
    "price": 449900,
    "bedrooms": 3,
    "bathrooms": 2.5,
    "livingArea": 2100,
    "address": {
        "streetAddress": "1234 Alpine Dr",
        "city": "Sandy",
        "state": "UT",
        "zipcode": "84092"
    },
    "latitude": 40.5678,
    "longitude": -111.8543,
    "description": "Stunning modern home nestled in the foothills with breathtaking mountain views. Features an open-concept floor plan with hardwood floors, granite countertops, and a gourmet kitchen. Master suite with spa-like bathroom. Covered patio overlooks landscaped yard with mature trees. Close to hiking trails and top-rated schools.",
    "responsivePhotos": [
        {
            "mixedSources": {
                "jpeg": [
                    {"url": "https://photos.zillowstatic.com/fp/abc123-exterior.jpg"},
                    {"url": "https://photos.zillowstatic.com/fp/abc124-kitchen.jpg"},
                    {"url": "https://photos.zillowstatic.com/fp/abc125-living.jpg"},
                    {"url": "https://photos.zillowstatic.com/fp/abc126-master.jpg"},
                    {"url": "https://photos.zillowstatic.com/fp/abc127-bathroom.jpg"},
                    {"url": "https://photos.zillowstatic.com/fp/abc128-patio.jpg"}
                ]
            }
        }
    ]
}
```

**Step-by-Step Processing**:

**1. Extract Core Fields**
```python
core = _extract_core_fields(listing)

# Result:
{
    "zpid": "12778555",
    "description": "Stunning modern home nestled in the foothills...",
    "has_description": True,
    "price": 449900,
    "bedrooms": 3.0,
    "bathrooms": 2.5,
    "livingArea": 2100.0,
    "address": {
        "streetAddress": "1234 Alpine Dr",
        "city": "Sandy",
        "state": "UT",
        "zipcode": "84092"
    },
    "city": "Sandy",
    "state": "UT",
    "zip_code": "84092",
    "geo": {"lat": 40.5678, "lon": -111.8543}
}
```

**2. Extract Image URLs**
```python
images = extract_zillow_images(listing, target_width=576)

# Result:
[
    "https://photos.zillowstatic.com/fp/abc123-exterior.jpg",
    "https://photos.zillowstatic.com/fp/abc124-kitchen.jpg",
    "https://photos.zillowstatic.com/fp/abc125-living.jpg",
    "https://photos.zillowstatic.com/fp/abc126-master.jpg",
    "https://photos.zillowstatic.com/fp/abc127-bathroom.jpg",
    "https://photos.zillowstatic.com/fp/abc128-patio.jpg"
]
```

**3. Generate Text Embedding**
```python
vec_text = embed_text(core["description"])

# API Call to Bedrock:
{
    "model": "amazon.titan-embed-text-v2:0",
    "inputText": "Stunning modern home nestled in the foothills..."
}

# Response:
{
    "embedding": [0.023, -0.041, 0.115, -0.089, ...]  # 1024 floats
}

# Cost: $0.0001
```

**4. Process First Image (Exterior)**
```python
url = "https://photos.zillowstatic.com/fp/abc123-exterior.jpg"

# Check DynamoDB cache
cached = dynamodb.get_item(
    TableName="hearth-image-cache",
    Key={"image_url": {"S": url}}
)
# Result: Cache MISS (first time seeing this image)

# Download image
resp = requests.get(url)
img_bytes = resp.content  # 450KB JPEG

# Generate embedding
img_vec = embed_image_bytes(img_bytes)
# → Resizes to 576px, calls Bedrock Titan Image
# Cost: $0.00006
# Returns: [0.512, 0.834, -0.201, ...]

# Cache embedding
dynamodb.put_item(
    TableName="hearth-image-cache",
    Item={
        "image_url": {"S": url},
        "embedding": {"S": json.dumps(img_vec)},
        "created_at": {"N": "1678901234"}
    }
)

# Check for duplicates
img_hash = hashlib.md5(img_bytes).hexdigest()  # "a3f2c9..."
# Not in seen_hashes → Add to set

# Run vision analysis
analysis = detect_labels(img_bytes, image_url=url)

# API Call to Bedrock Claude Haiku:
{
    "model": "anthropic.claude-3-haiku-20240307-v1:0",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "data": "<base64>"}},
            {"type": "text", "text": "Analyze this real estate photo..."}
        ]
    }]
}

# Response:
{
    "image_type": "exterior",
    "features": ["landscaped_yard", "covered_patio", "mountain_views"],
    "materials": ["brick", "stone_accents"],
    "visual_features": ["modern_design", "two_story"],
    "architecture_style": "modern",
    "exterior_color": "gray",
    "confidence": "high"
}
# Cost: $0.00025

# Add to tags
img_tags.add("landscaped_yard")
img_tags.add("covered_patio")
img_tags.add("mountain_views")
img_tags.add("brick")
img_tags.add("stone_accents")
img_tags.add("modern_design")
img_tags.add("two_story")
img_tags.add("gray exterior")
img_tags.add("gray_exterior")

# Track as best exterior
style_from_vision = "modern"
best_exterior_score = 10

# Store metadata
image_vector_metadata.append({
    "image_url": url,
    "image_type": "exterior",
    "vector": img_vec
})
```

**5. Process Remaining Images**
```python
# Image 2: Kitchen (interior)
# Image 3: Living room (interior)
# Image 4: Master bedroom (interior)
# Image 5: Bathroom (interior)
# Image 6: Patio (exterior)

# Each follows same process:
# - Check cache → Download → Generate embedding → Cache
# - Dedup check
# - Vision analysis → Extract features/materials
# - Add to image_vector_metadata

# Final results after all 6 images:
image_tags = {
    "brick",
    "covered_patio",
    "gourmet_kitchen",
    "granite_countertops",
    "gray exterior",
    "gray_exterior",
    "hardwood_floors",
    "landscaped_yard",
    "master_suite",
    "modern_design",
    "mountain_views",
    "open_floor_plan",
    "spa_bathroom",
    "stone_accents",
    "two_story"
}

image_vector_metadata = [
    {"image_url": "...exterior.jpg", "image_type": "exterior", "vector": [...]},
    {"image_url": "...kitchen.jpg", "image_type": "interior", "vector": [...]},
    {"image_url": "...living.jpg", "image_type": "interior", "vector": [...]},
    {"image_url": "...master.jpg", "image_type": "interior", "vector": [...]},
    {"image_url": "...bathroom.jpg", "image_type": "interior", "vector": [...]},
    {"image_url": "...patio.jpg", "image_type": "exterior", "vector": [...]}
]

# Total cost: 6 × ($0.00006 + $0.00025) = $0.00186
```

**6. Build Final Document**
```python
doc = {
    # Core fields
    "zpid": "12778555",
    "price": 449900,
    "bedrooms": 3.0,
    "bathrooms": 2.5,
    "livingArea": 2100.0,
    "description": "Stunning modern home...",
    "address": {...},
    "city": "Sandy",
    "state": "UT",
    "zip_code": "84092",
    "geo": {"lat": 40.5678, "lon": -111.8543},

    # Embeddings
    "vector_text": [0.023, -0.041, ...],  # From step 3
    "image_vectors": image_vector_metadata,  # From step 5

    # Vision-extracted features
    "image_tags": sorted(image_tags),
    "architecture_style": "modern",

    # Images
    "images": [
        "https://photos.zillowstatic.com/fp/abc123-exterior.jpg",
        "https://photos.zillowstatic.com/fp/abc124-kitchen.jpg",
        "https://photos.zillowstatic.com/fp/abc125-living.jpg",
        "https://photos.zillowstatic.com/fp/abc126-master.jpg",
        "https://photos.zillowstatic.com/fp/abc127-bathroom.jpg",
        "https://photos.zillowstatic.com/fp/abc128-patio.jpg"
    ],

    # Metadata
    "has_valid_embeddings": True,
    "status": "active",
    "indexed_at": 1678901234,
    "llm_profile": "",
    "feature_tags": []
}
```

**7. Index to OpenSearch**
```python
os_client.index(
    index="listings-v2",
    id="12778555",
    body=doc,
    refresh=True
)

# Total processing cost: $0.0001 (text) + $0.00186 (images) = $0.00196
# Processing time: ~8 seconds
```

**8. Store Complete Data in S3**
```python
s3.put_object(
    Bucket="demo-hearth-data",
    Key="listings/12778555.json",
    Body=json.dumps(original_zillow_data)  # All 166+ fields
)
```

---

### Example 2: Searching for a Property

**Scenario**: User searches for "modern house with granite countertops and mountain views under $500k"

**Step-by-Step Search**:

**1. Parse Query**
```python
q = "modern house with granite countertops and mountain views under $500k"

constraints = extract_query_constraints(q)

# LLM analyzes query and returns:
{
    "must_have": ["granite_countertops", "mountain_views"],
    "nice_to_have": [],
    "hard_filters": {"price_max": 500000},
    "architecture_style": "modern",
    "proximity": None,
    "query_type": "material"  # Detected "granite" keyword
}

must_tags = {"granite_countertops", "mountain_views"}
architecture_style = "modern"
price_max = 500000
```

**2. Expand Tags**
```python
expanded_must_tags = set()
for tag in must_tags:
    expanded_must_tags.add(tag)
    expanded_must_tags.add(tag.replace("_", " "))

# Result:
expanded_must_tags = {
    "granite_countertops",
    "granite countertops",
    "mountain_views",
    "mountain views"
}
```

**3. Generate Query Embedding**
```python
q_vec = embed_text(q)
# Returns: [0.045, -0.023, 0.112, -0.067, ...]
# Cost: $0.0001
```

**4. Build Filters**
```python
filter_clauses = [
    {"range": {"price": {"lte": 500000}}},
    {"term": {"architecture_style": "modern"}},
    {"term": {"has_valid_embeddings": True}}
]
```

**5. Execute BM25 Search**
```python
bm25_query = {
    "size": 45,
    "query": {
        "bool": {
            "filter": filter_clauses,
            "should": [
                {
                    "multi_match": {
                        "query": q,
                        "fields": ["description^3", "address^0.5", "city^0.3"]
                    }
                },
                {
                    "terms": {
                        "image_tags": [
                            "granite_countertops", "granite countertops",
                            "mountain_views", "mountain views"
                        ]
                    }
                }
            ],
            "minimum_should_match": 1
        }
    }
}

bm25_hits = os_client.search(index="listings-v2", body=bm25_query)["hits"]["hits"]

# Returns (example):
[
    {"_id": "12778555", "_score": 9.2, "_source": {...}},  # Our listing from Example 1!
    {"_id": "12709904", "_score": 8.5, "_source": {...}},
    {"_id": "12764736", "_score": 7.8, "_source": {...}},
    # ... 42 more
]

# Why 12778555 scored high:
# - description contains "granite countertops" → High BM25 score
# - description contains "mountain views" → High BM25 score
# - image_tags contains both exact matches → Boost from terms query
# - architecture_style="modern" → Passed filter
# - price=449900 < 500000 → Passed filter
```

**6. Execute kNN Text Search**
```python
knn_text_query = {
    "size": 45,
    "query": {
        "bool": {
            "must": [{
                "knn": {
                    "vector_text": {
                        "vector": q_vec,
                        "k": 100
                    }
                }
            }],
            "filter": filter_clauses
        }
    }
}

knn_text_hits = os_client.search(index="listings-v2", body=knn_text_query)["hits"]["hits"]

# Returns (example):
[
    {"_id": "12764736", "_score": 0.94, "_source": {...}},  # Semantically similar description
    {"_id": "12778555", "_score": 0.91, "_source": {...}},  # Our listing again!
    {"_id": "12709904", "_score": 0.88, "_source": {...}},
    # ... 42 more
]

# Cosine similarity between query embedding and listing description embeddings
# Finds listings with similar semantic meaning, even without exact keyword matches
```

**7. Execute kNN Image Search (Multi-Vector)**
```python
knn_image_query = {
    "size": 45,
    "query": {
        "bool": {
            "must": [{
                "nested": {
                    "path": "image_vectors",
                    "score_mode": "max",  # Best matching image wins
                    "query": {
                        "knn": {
                            "image_vectors.vector": {
                                "vector": q_vec,
                                "k": 100
                            }
                        }
                    }
                }
            }],
            "filter": filter_clauses
        }
    }
}

knn_img_hits = os_client.search(index="listings-v2", body=knn_image_query)["hits"]["hits"]

# For listing 12778555:
# Searches all 6 image vectors:
# - exterior.jpg vector: similarity = 0.62
# - kitchen.jpg vector: similarity = 0.88  ← BEST (granite countertops visible)
# - living.jpg vector: similarity = 0.54
# - master.jpg vector: similarity = 0.48
# - bathroom.jpg vector: similarity = 0.71 (granite in bathroom)
# - patio.jpg vector: similarity = 0.79 (mountain views)
#
# score_mode="max" → Listing scores 0.88 (from kitchen image)

# Returns (example):
[
    {"_id": "12778555", "_score": 0.88, "_source": {...}},
    {"_id": "12709904", "_score": 0.82, "_source": {...}},
    {"_id": "12764736", "_score": 0.76, "_source": {...}},
    # ... 42 more
]
```

**8. Calculate Adaptive Weights**
```python
k_values = calculate_adaptive_weights(
    must_have_tags=["granite_countertops", "mountain_views"],
    query_type="material"
)

# Detected: MATERIAL keyword ("granite")
# Returns: [42, 45, 60]
#          ^^  ^^  ^^
#          BM25 boosted (material queries work well with tags)
#          Text moderate boost
#          Images balanced
```

**9. Reciprocal Rank Fusion**
```python
fused = _rrf(bm25_hits, knn_text_hits, knn_img_hits, k_values=[42, 45, 60], top=45)

# Listing 12778555 appears in all 3 result lists:
# - BM25: rank 1 → score contribution: 1/(42+1) = 0.0233
# - kNN text: rank 2 → score contribution: 1/(45+2) = 0.0213
# - kNN image: rank 1 → score contribution: 1/(60+1) = 0.0164
# Final RRF score: 0.0233 + 0.0213 + 0.0164 = 0.061

# Listing 12709904:
# - BM25: rank 2 → 1/(42+2) = 0.0227
# - kNN text: rank 3 → 1/(45+3) = 0.0208
# - kNN image: rank 2 → 1/(60+2) = 0.0161
# Final RRF score: 0.0227 + 0.0208 + 0.0161 = 0.0596

# 12778555 ranks higher!
```

**10. Post-RRF Tag Boosting**
```python
for hit in fused:
    src = hit["_source"]
    tags = set(src["image_tags"])

    # For listing 12778555:
    # tags = {"granite_countertops", "mountain_views", "hardwood_floors", ...}
    # expanded_must_tags = {"granite_countertops", "granite countertops",
    #                        "mountain_views", "mountain views"}

    matched_tags = expanded_must_tags.intersection(tags)
    # matched_tags = {"granite_countertops", "mountain_views"}

    match_ratio = len(matched_tags) / len({"granite_countertops", "mountain_views"})
    # match_ratio = 2/2 = 1.0 (100% match!)

    boost = 2.0  # 100% match → 2.0x boost

    final_score = 0.061 * 2.0 = 0.122

# Listing 12778555 now has final score: 0.122
```

**11. Enrich Results**
```python
# For top 15 results, enrich each:

# a) Fetch S3 data (if requested)
s3_data = _fetch_listing_from_s3("12778555")
# Checks DynamoDB cache first
# If miss, downloads from s3://demo-hearth-data/listings/12778555.json
# Returns all 166+ Zillow fields

result["original_listing"] = s3_data

# b) Add nearby places (if requested)
enrich_with_nearby_places(result)
# Uses geo coordinates: lat=40.5678, lon=-111.8543
# Rounds to: 40.568,-111.854,1000
# Checks DynamoDB cache
# If miss, calls Google Places API (New)
# Stores in cache for future queries

result["nearby_places"] = [
    {"name": "Smith's Food & Drug", "types": ["grocery_store", "food"]},
    {"name": "Sandy Creek Trail", "types": ["park", "point_of_interest"]},
    {"name": "Alta View Hospital", "types": ["hospital", "health"]}
]
```

**12. Return Results**
```python
{
    "ok": True,
    "results": [
        {
            "zpid": "12778555",
            "id": "12778555",
            "score": 0.122,
            "boosted": True,

            # OpenSearch fields
            "price": 449900,
            "bedrooms": 3.0,
            "bathrooms": 2.5,
            "description": "Stunning modern home...",
            "image_tags": ["granite_countertops", "mountain_views", ...],
            "architecture_style": "modern",
            "geo": {"lat": 40.5678, "lon": -111.8543},
            "images": ["https://.../exterior.jpg", "https://.../kitchen.jpg", ...],

            # S3 data
            "original_listing": {
                "responsivePhotos": [...],  # High-res images
                "zestimate": 475000,
                "taxAssessedValue": 420000,
                "yearBuilt": 2018,
                # ... 160+ more fields
            },

            # Google Places
            "nearby_places": [
                {"name": "Smith's Food & Drug", "types": ["grocery_store"]},
                {"name": "Sandy Creek Trail", "types": ["park"]},
                {"name": "Alta View Hospital", "types": ["hospital"]}
            ]
        },
        # ... 14 more results
    ],
    "total": 15,
    "must_have": ["granite_countertops", "mountain_views"],
    "architecture_style": "modern"
}

# Total search cost:
# - Query embedding: $0.0001
# - S3 fetches (15 listings, ~5 cache hits): 10 × $0.00001 = $0.0001
# - Google Places (15 locations, ~8 cache hits): 7 × $0.017 = $0.119
# Total: ~$0.12 per search
```

---

## Key Algorithms

### 1. Reciprocal Rank Fusion (RRF)

**Purpose**: Combine multiple ranked result lists into a single fused ranking.

**Why Use RRF?**
- Simple and effective (no training required)
- Works well when result lists have different scoring scales
- Emphasizes consensus (listings appearing in multiple lists rank higher)
- Robust to outliers

**Formula**:
```
For each document d:
    RRF_score(d) = Σ [ 1 / (k + rank_in_list_i) ]
                   i=1 to N

Where:
- N = number of result lists
- k = constant (controls weight, typically 60)
- rank_in_list_i = position of d in list i (1-indexed)
```

**Example**:
```
Document appears in 3 lists:
- BM25: rank 5 → contribution = 1/(60+5) = 0.0154
- kNN text: rank 12 → contribution = 1/(60+12) = 0.0139
- kNN image: rank 3 → contribution = 1/(60+3) = 0.0159
Final score: 0.0154 + 0.0139 + 0.0159 = 0.0452

Document appears in only 1 list:
- BM25: rank 1 → contribution = 1/(60+1) = 0.0164
- kNN text: not found → contribution = 0
- kNN image: not found → contribution = 0
Final score: 0.0164 + 0 + 0 = 0.0164

First document ranks higher (consensus across multiple strategies)
```

**Adaptive RRF (Our Innovation)**:
```
Standard RRF: Same k for all lists
Adaptive RRF: Different k per list based on query characteristics

Color query ("white house"):
k_values = [30, 60, 120]
           ^^^ BM25 (tags work best for color)
               ^^^ Text (moderate)
                   ^^^ Image (embeddings fail for color)

Material query ("brick house"):
k_values = [21, 45, 60]
           ^^^ BM25 further boosted
               ^^^ Text boosted
                   ^^^ Image moderate

Visual query ("modern architecture"):
k_values = [60, 45, 40]
           ^^^ BM25 balanced
               ^^^ Text boosted
                   ^^^ Image boosted (best for style)
```

### 2. Vector Similarity Search (kNN)

**Purpose**: Find listings with similar embeddings using cosine similarity.

**Cosine Similarity Formula**:
```
cos_sim(A, B) = (A · B) / (||A|| × ||B||)

Where:
- A, B = 1024-dimensional vectors
- A · B = dot product = Σ(a_i × b_i)
- ||A|| = magnitude = sqrt(Σ(a_i²))
- Result: -1 to 1 (1 = identical, 0 = orthogonal, -1 = opposite)
```

**Example**:
```
Query embedding: [0.5, 0.3, -0.2, 0.8, ...]
Listing 1 embedding: [0.48, 0.32, -0.18, 0.79, ...]
Listing 2 embedding: [-0.1, 0.6, 0.4, -0.2, ...]

cos_sim(query, listing1) = 0.97  ← Very similar
cos_sim(query, listing2) = 0.23  ← Somewhat similar

Listing 1 ranks higher
```

**OpenSearch HNSW Index**:
- Uses Hierarchical Navigable Small World (HNSW) algorithm
- Creates graph structure for fast approximate nearest neighbor search
- Parameters:
  - `ef_construction=512`: Build quality (higher = better recall, slower indexing)
  - `m=16`: Graph connectivity (higher = better recall, more memory)
- Search time: O(log N) instead of O(N) for brute force

### 3. Multi-Vector Max-Match

**Purpose**: Search multiple image vectors per listing and use best match.

**Problem with Averaging**:
```
Listing has 30 images:
Image 1: [0.8, 0.9, ...] (pool, high match)
Image 2-30: [0.1, 0.2, ...] (interiors, low match)

Averaged: [0.8 + 0.1×29]/30 = [0.13, ...]
Pool signal is LOST!
```

**Solution with Max-Match**:
```
OpenSearch nested query with score_mode="max":
- Searches each image vector independently
- Returns listing if ANY image matches well
- Listing scores 0.9 (from pool image)

Query: "house with pool"
Result: Pool photo matches → Listing ranks high ✓
```

**Implementation**:
```python
{
    "nested": {
        "path": "image_vectors",
        "score_mode": "max",  # KEY: Use best matching image
        "query": {
            "knn": {
                "image_vectors.vector": {
                    "vector": query_vec,
                    "k": 100
                }
            }
        }
    }
}
```

---

## Cost Analysis

### Per-Listing Indexing Cost (Unlimited Images)

Based on average 22.6 images per listing:

```
Text Embedding:
- Titan Text v2: $0.0001 per listing

Image Embeddings:
- Titan Image v1: $0.00006 × 22.6 = $0.0014

Vision Analysis:
- Claude 3 Haiku: $0.00025 × 22.6 = $0.0056
  - Input: ~500 tokens per image
  - Output: ~100 tokens per image
  - Rate: $0.25/1M input, $1.25/1M output

DynamoDB:
- Write operations: ~25 writes per listing = $0.000025
  - Image cache: 22.6 writes
  - Vision cache: 22.6 writes (combined with embedding)

S3:
- Storage: 50KB per listing = $0.0000012/month
- PUT operation: $0.000005

OpenSearch:
- Indexing: ~$0.0001 (estimate)

────────────────────────────────────
TOTAL: ~$0.0070 per listing
────────────────────────────────────

For 10,000 listings:
$0.0070 × 10,000 = $70

For 100,000 listings:
$0.0070 × 100,000 = $700
```

### Per-Search Cost

```
Query Embedding:
- Titan Text v2: $0.0001

S3 Fetches (15 results, assuming 33% cache hit rate):
- 10 fetches × $0.00001 = $0.0001

DynamoDB Reads:
- S3 cache checks: 15 reads × $0.00000025 = $0.000004
- Geolocation checks: 15 reads × $0.00000025 = $0.000004

Google Places API (assuming 50% cache hit rate):
- New locations: 7.5 × $0.017 = $0.128
  - Nearby Search (New): $0.017 per request
  - 10 places per request

OpenSearch:
- Query execution: ~$0.0001 (estimate)

────────────────────────────────────
TOTAL: ~$0.13 per search
────────────────────────────────────

For 1,000 searches:
$0.13 × 1,000 = $130

With 90% geolocation cache hit rate:
$0.13 - $0.115 + $0.0128 = $0.028 per search
1,000 searches = $28
```

### Cache Savings

**Image Embedding Cache** (90% hit rate during re-indexing):
```
Without cache:
10,000 listings × 22.6 images × $0.00006 = $135.60

With cache (90% hits):
10,000 listings × 22.6 images × 10% × $0.00006 = $13.56

Savings: $122 per re-index
```

**Vision Analysis Cache** (90% hit rate):
```
Without cache:
10,000 listings × 22.6 images × $0.00025 = $565

With cache (90% hits):
10,000 listings × 22.6 images × 10% × $0.00025 = $56.50

Savings: $508.50 per re-index
```

**Geolocation Cache** (after warm-up):
```
Unique locations in 10,000 listings: ~8,000
First-time cost: 8,000 × $0.017 = $136

Subsequent searches (90% hit rate):
1,000 searches × 15 results × 10% × $0.017 = $25.50

Without cache:
1,000 searches × 15 results × $0.017 = $255

Savings: $229.50 per 1,000 searches
```

---

## Performance Characteristics

### Indexing Performance

**Single Listing** (22.6 images average):
```
Breakdown:
- Download images: 2-3s (6 parallel requests)
- Generate embeddings: 1-2s (cached 90% of time)
- Vision analysis: 3-4s (cached 90% of time)
- Index to OpenSearch: 0.5s
- Store in S3: 0.2s

Total: ~8 seconds per listing (uncached)
       ~2 seconds per listing (cached)
```

**Batch Processing** (local script, 5 parallel):
```
50 listings in ~6 minutes = 7.2s per listing
- Includes OpenSearch verification
- Network latency
- Thread coordination

1,000 listings: ~2 hours
10,000 listings: ~20 hours
```

**Lambda Chain Processing**:
```
500 listings per invocation:
- Processing: ~12-13 minutes
- Self-invoke overhead: 1-2 seconds
- Total: ~13 minutes per batch

1,588 listings:
- 4 invocations × 13 minutes = ~52 minutes total
- BUT: Can't monitor progress
- Harder to debug failures
```

### Search Performance

**Latency Breakdown**:
```
Query parsing (LLM): 300-500ms
- Claude API call
- Cached in conversation context (not implemented yet)

Query embedding: 50-100ms
- Bedrock Titan API call

OpenSearch queries (parallel): 200-400ms
- BM25 search: 80-120ms
- kNN text search: 100-150ms
- kNN image search: 120-180ms
- Run in parallel, max determines total

RRF fusion: 10-20ms
- CPU-bound, fast

Tag boosting: 5-10ms

S3 enrichment (15 results, 33% cached):
- Cached: 10-20ms per listing
- Uncached: 100-200ms per listing
- Parallel fetching: ~300ms total

Google Places (15 locations, 50% cached):
- Cached: 10-20ms per location
- Uncached: 200-400ms per location
- Parallel fetching: ~600ms total

────────────────────────────────────
Total: 1.5-2.5 seconds typical
       0.8-1.2 seconds (high cache hit)
       2.5-4.0 seconds (low cache hit)
────────────────────────────────────
```

**Throughput**:
```
Single Lambda instance:
- ~1-2 requests/second
- Limited by external API calls (Google Places)

With caching warm:
- ~3-5 requests/second per instance

Auto-scaling:
- Lambda can scale to 1,000+ concurrent instances
- Sustained: 3,000-5,000 req/sec
- Burst: 10,000+ req/sec
```

### Storage Requirements

**OpenSearch** (per listing):
```
Document fields: ~2KB
- Text fields, metadata

Vectors:
- vector_text: 1024 floats × 4 bytes = 4KB
- image_vectors (22.6 images):
  - 22.6 × 1024 floats × 4 bytes = 92KB
  - Plus metadata: ~1KB
  - Total: 93KB

Total per listing: ~99KB
10,000 listings: 990MB
100,000 listings: 9.9GB
```

**S3** (per listing):
```
Complete Zillow JSON: 40-60KB average
10,000 listings: 500MB
100,000 listings: 5GB

Cost: $0.023/GB/month
100,000 listings: 5GB × $0.023 = $0.12/month
```

**DynamoDB**:
```
Image cache (per unique image):
- Embedding: 1024 floats × 8 bytes (JSON) = ~8KB
- Metadata: ~1KB
- Total: ~9KB

Vision cache (combined with embedding):
- Analysis JSON: ~2KB
- Total with embedding: ~11KB

Geolocation cache (per unique location):
- Places array: ~3KB

For 10,000 listings (22.6 images/listing, 50% unique):
- 113,000 unique images × 11KB = 1.24GB
- 8,000 unique locations × 3KB = 24MB
- Total: ~1.26GB

Cost: $0.25/GB/month (on-demand)
1.26GB × $0.25 = $0.32/month
```

---

This architecture provides a production-ready, cost-optimized search system that combines the best of keyword search, semantic search, and visual search to deliver highly relevant real estate results.
