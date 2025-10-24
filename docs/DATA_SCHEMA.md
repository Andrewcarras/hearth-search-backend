# Data Schema

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [ARCHITECTURE_STYLES.md](ARCHITECTURE_STYLES.md), [API.md](API.md)

Complete OpenSearch document schema and data ingestion pipeline documentation.

---

## Table of Contents

1. [OpenSearch Schema](#opensearch-schema)
2. [Field Descriptions](#field-descriptions)
3. [Data Ingestion](#data-ingestion)
4. [Embedding Generation](#embedding-generation)
5. [Data Quality](#data-quality)

---

## OpenSearch Schema

### Complete Property Document

```json
{
  "zpid": "123456",
  "address": "123 Main St",
  "city": "Salt Lake City",
  "state": "UT",
  "zipcode": "84101",
  "latitude": 40.7608,
  "longitude": -111.8910,

  "price": 450000,
  "bedrooms": 3,
  "bathrooms": 2.5,
  "livingArea": 2100,
  "lotSize": 5000,
  "yearBuilt": 2015,
  "propertyType": "SINGLE_FAMILY",

  "architecture_style": "mid_century_modern",
  "architecture_substyle": "mid_century_ranch",

  "property_features": [
    "granite countertops",
    "hardwood floors",
    "stainless steel appliances",
    "walk-in closet",
    "updated kitchen"
  ],

  "exterior_materials": [
    "brick",
    "vinyl siding"
  ],

  "interior_features": [
    "fireplace",
    "vaulted ceilings",
    "crown molding"
  ],

  "outdoor_amenities": [
    "pool",
    "deck",
    "fenced yard"
  ],

  "room_features": [
    "master suite",
    "bonus room",
    "office"
  ],

  "text_embedding": [0.123, -0.456, ...],
  "image_embedding": [0.789, -0.234, ...],

  "image_urls": [
    "https://photos.zillowstatic.com/...",
    "https://photos.zillowstatic.com/..."
  ],

  "listing_url": "https://www.zillow.com/homedetails/...",
  "description": "Beautiful mid-century modern ranch home...",
  "homeStatus": "FOR_SALE",
  "daysOnZillow": 14,

  "listingStatus": "for_sale",
  "soldDate": null,
  "listedDate": "2025-10-01"
}
```

---

## Field Descriptions

### Core Identification

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `zpid` | string | Zillow Property ID (unique) | "123456" |
| `address` | string | Street address | "123 Main St" |
| `city` | string | City name | "Salt Lake City" |
| `state` | string | State abbreviation | "UT" |
| `zipcode` | string | ZIP code | "84101" |
| `latitude` | float | Latitude coordinate | 40.7608 |
| `longitude` | float | Longitude coordinate | -111.8910 |

### Property Specs

| Field | Type | Description | Important Notes |
|-------|------|-------------|-----------------|
| `price` | number | Listing price (USD) | Current price |
| `bedrooms` | number | Number of bedrooms | Integer or decimal (studio = 0) |
| `bathrooms` | number | Number of bathrooms | Can be decimal (2.5 = 2 full + 1 half) |
| **`livingArea`** | **number** | **House square footage** | **HOUSE sqft, NOT lot size** |
| **`lotSize`** | **number** | **Lot size in square feet** | **LOT sqft, NOT house size** |
| `yearBuilt` | number | Year property built | 4-digit year |
| `propertyType` | string | Property type | SINGLE_FAMILY, CONDO, TOWNHOUSE, etc. |

**CRITICAL**: `livingArea` = house size, `lotSize` = land size. These were mixed up before 2025-10-24 fix.

### Architecture Styles

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `architecture_style` | string | Tier 1 broad category | "mid_century_modern", "craftsman", "victorian" |
| `architecture_substyle` | string | Tier 2 specific sub-style | "mid_century_ranch", "craftsman_bungalow" |

See [ARCHITECTURE_STYLES.md](ARCHITECTURE_STYLES.md) for complete style taxonomy.

### Custom Status Fields (Sales Pipeline Tracking)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `listingStatus` | string | **Custom status field** for your sales pipeline | "for_sale", "sold", "pending", "under_contract" |
| `soldDate` | string | Date property was marked sold (ISO format) | "2025-10-24" |
| `listedDate` | string | Date property was listed for sale (ISO format) | "2025-10-01" |

**Purpose**: These custom fields allow you to track property status independent of Zillow's original `homeStatus`. Use them to manage your own sales pipeline, mark properties as sold, or filter search results.

**Usage**:
```bash
# Mark property as sold
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2" \
  -d '{"updates": {"listingStatus": "sold", "soldDate": "2025-10-24"}, "options": {"preserve_embeddings": true}}'

# Mark property as for sale
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2" \
  -d '{"updates": {"listingStatus": "for_sale", "listedDate": "2025-10-01"}, "options": {"preserve_embeddings": true}}'
```

**Status Values**:
- `for_sale` - Available for purchase
- `sold` - Property sold
- `pending` - Sale pending
- `under_contract` - Under contract with buyer
- `off_market` - Temporarily off market
- `coming_soon` - Will be listed soon

### Tag Fields (BM25 Search)

| Field | Type | Description | Examples |
|-------|------|-------------|----------|
| `property_features` | array[string] | Interior features & materials | ["granite countertops", "hardwood floors"] |
| `exterior_materials` | array[string] | Exterior building materials | ["brick", "vinyl siding", "stucco"] |
| `interior_features` | array[string] | Interior architectural features | ["fireplace", "vaulted ceilings"] |
| `outdoor_amenities` | array[string] | Outdoor features | ["pool", "deck", "patio"] |
| `room_features` | array[string] | Room-specific features | ["master suite", "bonus room"] |

These fields are used for BM25 tag-based search.

### Embedding Fields

| Field | Type | Dimensions | Description |
|-------|------|------------|-------------|
| `text_embedding` | knn_vector | 1024 | Claude text embedding for semantic search |
| `image_embedding` | knn_vector | 512 | CLIP image embedding for visual search |

Generated during data ingestion via Claude Vision API and CLIP model.

### Media & Metadata

| Field | Type | Description |
|-------|------|-------------|
| `image_urls` | array[string] | Property photo URLs |
| `listing_url` | string | Zillow listing URL |
| `description` | string | Property description text |
| `homeStatus` | string | Listing status (FOR_SALE, SOLD, etc.) |
| `daysOnZillow` | number | Days listing has been active |

---

## Data Ingestion

### Source Data

**File**: Zillow JSON export (e.g., `slc_listings.json`)

**Example Source Document**:
```json
{
  "zpid": "123456",
  "streetAddress": "123 Main St",
  "city": "Salt Lake City",
  "state": "UT",
  "price": 450000,
  "bedrooms": 3,
  "bathrooms": 2.5,
  "livingArea": 2100,
  "lotSize": 5000,
  "livingAreaValue": 2100,
  "lotAreaValue": 5000,
  "imgSrc": "https://photos.zillowstatic.com/...",
  "detailUrl": "/homedetails/...",
  ...
}
```

### Ingestion Script

**File**: [upload_listings.py](../upload_listings.py)

**Usage**:
```bash
python3 upload_listings.py slc_listings.json
```

**Process**:
1. Read Zillow JSON file
2. For each property:
   - Extract core fields (zpid, address, price, etc.)
   - Extract specs (bedrooms, bathrooms, **livingArea**, **lotSize**)
   - Download property images
   - Generate text embedding via Claude Vision API
   - Generate image embedding via CLIP
   - Classify architecture style (2-tier)
   - Extract property features as tags
   - Upload to OpenSearch listings-v2 index
3. Log progress and errors

### Field Extraction Logic

**Critical Fix (2025-10-24)**: livingArea vs lotSize

**Before (INCORRECT)**:
```python
acreage = _num(lst.get("lotSize") or lst.get("acreage"))
# ...
"livingArea": float(acreage)  # WRONG! Lot size mapped to livingArea
```

**After (CORRECT)**:
```python
living_area = _num(lst.get("livingArea") or lst.get("livingAreaValue"))  # House sqft
lot_size = _num(lst.get("lotSize") or lst.get("lotAreaValue"))  # Lot sqft
# ...
"livingArea": float(living_area),  # House square footage
"lotSize": float(lot_size)  # Lot size
```

**Result**: Properties showing correct house sqft (e.g., 2,100) instead of lot size (e.g., 47,916).

---

## Embedding Generation

### Text Embedding (Claude Vision API)

**Model**: `us.anthropic.claude-3-haiku-20240307-v1:0`
**Dimensions**: 1024
**Used For**: Semantic search, architectural style understanding

**Input**:
```python
description = f"""
Property: {address}
Type: {propertyType}
Size: {bedrooms} bed, {bathrooms} bath, {livingArea} sqft
Style: {architecture_style}
Features: {', '.join(property_features)}
Exterior: {', '.join(exterior_materials)}
Year Built: {yearBuilt}
"""
```

**API Call**:
```python
response = bedrock.invoke_model(
    modelId="us.anthropic.claude-3-haiku-20240307-v1:0",
    body=json.dumps({
        "prompt": f"Generate semantic embedding for: {description}",
        "return_embedding": True,
        "max_tokens": 1
    })
)

text_embedding = response["embedding"]  # 1024-dim vector
```

**Cost**: ~$0.00025 per property

### Image Embedding (CLIP)

**Model**: `openai/clip-vit-base-patch32`
**Dimensions**: 512
**Used For**: Visual style search, appearance matching

**Process**:
```python
from transformers import CLIPProcessor, CLIPModel

model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

# Load first property image
image = Image.open(requests.get(image_url, stream=True).raw)

# Generate embedding
inputs = processor(images=image, return_tensors="pt")
image_embedding = model.get_image_features(**inputs)
```

**Cost**: Free (local inference)

### Architecture Classification

**Process**:
1. Send property images to Claude Vision API
2. Provide list of supported Tier 1 + Tier 2 styles
3. Claude returns classification

**Prompt**:
```python
prompt = """
Analyze these property images and classify the architectural style.

Return JSON with:
- tier1_style: broad category from {tier1_styles}
- tier2_style: specific sub-style from {tier2_styles}
- confidence: 0-1
- reasoning: brief explanation

Tier 1 Styles: modern, craftsman, victorian, colonial, ranch, ...
Tier 2 Styles: mid_century_modern, craftsman_bungalow, victorian_queen_anne, ...
"""
```

**Response**:
```json
{
  "tier1_style": "mid_century_modern",
  "tier2_style": "mid_century_ranch",
  "confidence": 0.92,
  "reasoning": "Low-pitched roof, horizontal emphasis, large windows, post-and-beam construction"
}
```

---

## Data Quality

### Current Stats (2025-10-24)

- **Total Properties**: 3,902
- **Complete Embeddings**: 3,902 (100%)
- **Architecture Classified**: ~2,800 (72%)
- **livingArea Fixed**: 3,153 (81%)

### Data Quality Issues Found

#### Issue 1: livingArea vs lotSize Swap (FIXED 2025-10-24)

**Problem**: livingArea field contained lot size instead of house size
**Example**: Property showing 47,916 sqft (lot) instead of 2,800 sqft (house)
**Cause**: upload_listings.py extracting from wrong field
**Fix**:
- Updated upload_listings.py:209-213
- Ran fix_living_area.py on all 3,902 properties
- 3,153 updated, 0 failures, 749 skipped (no data)

#### Issue 2: Missing Architecture Styles

**Problem**: ~1,100 properties without architecture_style
**Cause**: Batch update process ongoing
**Status**: In progress, ~2,800 properties completed
**Timeline**: Est. completion end of October 2025

### Data Validation

**Required Fields**:
- zpid (must be unique)
- address, city, state
- price > 0
- bedrooms >= 0
- bathrooms > 0

**Optional But Important**:
- livingArea (house sqft)
- lotSize (lot sqft)
- architecture_style
- property_features (tags)

**Embedding Requirements**:
- text_embedding: 1024 dimensions
- image_embedding: 512 dimensions
- Both required for full search functionality

---

## OpenSearch Mapping

### Index Configuration

**Index Name**: `listings-v2`

**Mapping** (simplified):
```json
{
  "mappings": {
    "properties": {
      "zpid": {"type": "keyword"},
      "address": {"type": "text"},
      "city": {"type": "keyword"},
      "state": {"type": "keyword"},
      "price": {"type": "integer"},
      "bedrooms": {"type": "integer"},
      "bathrooms": {"type": "float"},
      "livingArea": {"type": "float"},
      "lotSize": {"type": "float"},
      "propertyType": {"type": "keyword"},
      "architecture_style": {"type": "keyword"},
      "architecture_substyle": {"type": "keyword"},
      "property_features": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
      "exterior_materials": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
      "text_embedding": {
        "type": "knn_vector",
        "dimension": 1024,
        "method": {
          "name": "hnsw",
          "engine": "nmslib"
        }
      },
      "image_embedding": {
        "type": "knn_vector",
        "dimension": 512,
        "method": {
          "name": "hnsw",
          "engine": "nmslib"
        }
      }
    }
  }
}
```

---

## Updating Existing Properties

### Update Single Property

**Script**: [fix_living_area.py](../fix_living_area.py)

**Example**:
```bash
# Update livingArea for all properties
python3 fix_living_area.py slc_listings.json 50
```

**Uses CRUD API**:
```python
url = f"https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}?index=listings-v2"
payload = {
    "updates": {
        "livingArea": 2100,
        "lotSize": 5000
    },
    "options": {
        "preserve_embeddings": True  # Don't regenerate embeddings
    }
}
requests.patch(url, json=payload)
```

### Batch Update Architecture Styles

**Script**: [update_architecture_fast.py](../update_architecture_fast.py)

**Usage**:
```bash
python3 update_architecture_fast.py
```

**Process**:
- Fetches properties without architecture_style
- Calls Claude Vision API for classification
- Updates via CRUD API
- Batch size: 50 properties at a time

---

## See Also

- [API.md](API.md) - CRUD API for updating properties
- [ARCHITECTURE_STYLES.md](ARCHITECTURE_STYLES.md) - Architecture classification details
- [DEPLOYMENT.md](DEPLOYMENT.md) - Data upload procedures
- [upload_listings.py](../upload_listings.py) - Data ingestion script
