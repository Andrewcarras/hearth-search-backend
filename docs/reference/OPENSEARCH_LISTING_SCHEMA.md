# OpenSearch Listing Document Schema

**Real Example from Production Index: `listings-v2`**

This document shows the actual structure of a listing document as stored in OpenSearch, using ZPID 12875925 as a real-world example.

---

## Document Overview

- **ZPID:** 12875925
- **Address:** 7161 S 2155 E, Cottonwood Heights, UT 84121
- **Total Fields:** 24
- **Has Embeddings:** Yes (text + 9 image vectors)
- **Image Count:** 9 photos
- **Total Tags:** 48 tags (aggregated from all images)

---

## Field Descriptions

### Core Property Data

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `zpid` | string | "12875925" | Zillow Property ID (unique identifier) |
| `address` | object | `{"streetAddress": "7161 S 2155 E", "city": "Cottonwood Heights", "state": "UT", "zipcode": "84121"}` | Structured address |
| `city` | string | "Cottonwood Heights" | City name (duplicate of address.city) |
| `state` | string | "UT" | State abbreviation |
| `zip_code` | string | "84121" | Postal code |
| `geo` | object | `{"lat": 40.62108, "lon": -111.829}` | Geographic coordinates |
| `price` | integer | 3100 | Listing price in USD |
| `bedrooms` | float | 3.0 | Number of bedrooms |
| `bathrooms` | float | 2.0 | Number of bathrooms |
| `livingArea` | float/null | null | Square footage (may be null) |
| `status` | string | "active" | Listing status |
| `indexed_at` | integer | 1760573124 | Unix timestamp of indexing |
| `updated_at` | integer | 1760719096 | Unix timestamp of last update |

### Text Content

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `description` | string | "Cozy fully renovated multi-level brick home..." | Full property description from Zillow |
| `has_description` | boolean | true | Whether description field is populated |
| `visual_features_text` | string | "Exterior: ranch style white exterior with vinyl siding. Interior features: white walls, hardwood floors..." | **LLM-generated** summary of visual features from images |
| `llm_profile` | string | "" | Additional LLM-generated profile (may be empty) |
| `architecture_style` | string | "ranch" | **LLM-extracted** architectural style |

### Tags & Features

| Field | Type | Count | Example Values | Description |
|-------|------|-------|----------------|-------------|
| `feature_tags` | array[string] | 0 | `[]` | Structured feature tags (currently empty for this property) |
| `image_tags` | array[string] | 48 | `["white exterior", "hardwood floors", "granite countertops", "brick fireplace", ...]` | **Auto-generated tags from ALL images combined** |

**Important:** `image_tags` is a FLAT array combining tags from all 9 images. This is why "white exterior" appears even though only 1 of 9 images is exterior.

### Images

| Field | Type | Count | Description |
|-------|------|-------|-------------|
| `images` | array[string] | 9 | Array of Zillow photo URLs (in original order) |
| `image_vectors` | array[object] | 9 | **Per-image embeddings with metadata** (see below) |

### Embeddings

| Field | Type | Dimensions | Description |
|-------|------|------------|-------------|
| `vector_text` | array[float] | 1024 | **Text embedding** of description using `amazon.titan-embed-image-v1` (multimodal TEXT input) |
| `has_valid_embeddings` | boolean | - | Whether embeddings are valid |

---

## Image Vectors Structure (Critical!)

Each property has a **nested array** of `image_vectors` with per-image metadata:

```json
{
  "image_vectors": [
    {
      "image_url": "https://photos.zillowstatic.com/fp/8d73b14774f857e3b87b77903abf6884-cc_ft_1536.jpg",
      "image_type": "exterior",
      "vector": [0.026994739, 0.017529052, ..., -0.0045123] // 1024 dimensions
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/8406942b3e9051a88f762bae26266ea5-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [0.017026367, 0.03263387, ..., 0.00234567] // 1024 dimensions
    }
    // ... 7 more images
  ]
}
```

### Image Vector Fields

- **`image_url`** (string): URL of the image
- **`image_type`** (string): One of:
  - `"exterior"` - Main exterior shot (usually first photo)
  - `"interior"` - Interior room photos
  - `"detail"` - Close-up details
  - `"floorplan"` - Floor plan diagrams
  - `"backyard"` - Outdoor/backyard photos
- **`vector`** (array[float]): 1024-dimensional embedding from `amazon.titan-embed-image-v1` (multimodal IMAGE input)

### Key Insights from Image Data

For ZPID 12875925:
- **9 total images**
- **1 exterior photo** (last in the array, index 8)
- **8 interior photos** (indices 0-7)
- **All images combined** contribute to the 48 tags in `image_tags[]`

**This explains the tagging issue:**
- Property has `"white_exterior"` tag in `image_tags[]`
- Tag comes from the 1 exterior photo (index 8)
- But when searching, we don't know WHICH image contributed which tag
- Interior photos (8 of 9) dominate the tag distribution

---

## Complete Real Document

```json
{
  "zpid": "12875925",
  "address": {
    "streetAddress": "7161 S 2155 E",
    "city": "Cottonwood Heights",
    "state": "UT",
    "zipcode": "84121"
  },
  "city": "Cottonwood Heights",
  "state": "UT",
  "zip_code": "84121",
  "geo": {
    "lat": 40.62108,
    "lon": -111.829
  },
  "price": 3100,
  "bedrooms": 3.0,
  "bathrooms": 2.0,
  "livingArea": null,
  "status": "active",
  "indexed_at": 1760573124,
  "updated_at": 1760719096,
  "description": "Cozy fully renovated multi-level brick home in Cottonwood Heights that has so much to offer:\n- Prime location! Amazingly close to canyons, freeways and ski resorts\n- Freshly painted light and white \n- Brand new beautiful flooring throughout \n- Cute quiet street\n- Central Air\n- Fully fenced backyard\n- Large master bedroom\n- 3 bedrooms\n- 2 bathrooms\n- Large storage/utility room\n- Washer/dryer hookups\n- Covered parking spot\n- Large back yard with storage shed in backyard\n- Amazing Mountain and city views \n\nRenter responsible for utilities\nRenter responsible for yard care/maintenance\nPets negotiable with pet rent / deposit\nNo smoking\n\nRenter responsible for utilities\nRenter responsible for yard care/maintenance\nPets negotiable with pet rent / deposit\nNo smoking",
  "has_description": true,
  "visual_features_text": "Exterior: ranch style white exterior with vinyl siding. Interior features: white walls, hardwood floors, ceiling fan, bright and airy, recessed lighting, large window, empty room, large windows, walk-in closet, white cabinets. Property includes: hardwood, wood, attached garage, front porch, white shelving, sliding closet doors, lots of natural light, modern finishes, newly renovated, window blinds, towel hooks, tile, wood furniture, storage trunks, wood beams.",
  "llm_profile": "",
  "architecture_style": "ranch",
  "has_valid_embeddings": true,
  "feature_tags": [],
  "image_tags": [
    "arched doorway",
    "attached garage",
    "bathroom",
    "brick",
    "brick fireplace",
    "bright and airy",
    "ceiling fan",
    "double vanity",
    "empty room",
    "fenced yard",
    "fireplace",
    "front porch",
    "gabled roof",
    "granite countertops",
    "hardwood",
    "hardwood floors",
    "landscaped yard",
    "large window",
    "large windows",
    "lots of natural light",
    "mature trees",
    "modern finishes",
    "mountain view",
    "newly renovated",
    "open floor plan",
    "recessed lighting",
    "sliding closet doors",
    "stainless steel appliances",
    "storage trunks",
    "tile",
    "tile floors",
    "towel hooks",
    "vanity",
    "vessel sink",
    "vinyl siding",
    "walk-in closet",
    "white cabinets",
    "white exterior",
    "white interior doors",
    "white shelving",
    "white walls",
    "white_exterior",
    "window blinds",
    "windows",
    "wood",
    "wood beams",
    "wood floors",
    "wood furniture"
  ],
  "images": [
    "https://photos.zillowstatic.com/fp/8d73b14774f857e3b87b77903abf6884-cc_ft_1536.jpg",
    "https://photos.zillowstatic.com/fp/8406942b3e9051a88f762bae26266ea5-cc_ft_1536.jpg",
    "https://photos.zillowstatic.com/fp/f01918999e0c5bbd3331b8f7220e8677-cc_ft_1536.jpg",
    "https://photos.zillowstatic.com/fp/f3ee58b5221cb549b83c263211301a92-cc_ft_1536.jpg",
    "https://photos.zillowstatic.com/fp/4865286b3e5f1d7ba76b097adb98749e-cc_ft_1536.jpg",
    "https://photos.zillowstatic.com/fp/3a72ff148fcdbe41d9ebc456984c22ff-cc_ft_1536.jpg",
    "https://photos.zillowstatic.com/fp/14d385784474cada75c666e6c0ddf98a-cc_ft_1536.jpg",
    "https://photos.zillowstatic.com/fp/f1e171f1fc6aff862bb1f43af27e5208-cc_ft_1536.jpg",
    "https://photos.zillowstatic.com/fp/5488c05dedc77c91265ab401766fff4d-cc_ft_1536.jpg"
  ],
  "image_vectors": [
    {
      "image_url": "https://photos.zillowstatic.com/fp/f3ee58b5221cb549b83c263211301a92-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [0.02179597, 0.0077138003, 0.00032935012, -0.015696686, -0.020899016, /* ... 1019 more values ... */]
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/8406942b3e9051a88f762bae26266ea5-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [0.017026367, 0.03263387, -0.013567886, 0.0063848877, 0.01143959, /* ... 1019 more values ... */]
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/4865286b3e5f1d7ba76b097adb98749e-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [0.0055482923, 0.046466947, -0.022886707, -0.049241096, 0.0018747159, /* ... 1019 more values ... */]
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/f01918999e0c5bbd3331b8f7220e8677-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [0.010479098, 0.030950924, -0.022107802, 0.0017465164, 0.0052174414, /* ... 1019 more values ... */]
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/3a72ff148fcdbe41d9ebc456984c22ff-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [0.0140536, 0.022378344, 0.014948734, -0.020588078, -0.0077429074, /* ... 1019 more values ... */]
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/f1e171f1fc6aff862bb1f43af27e5208-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [-0.022107, 0.008457941, -0.014409825, 0.0061308886, -0.010113728, /* ... 1019 more values ... */]
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/14d385784474cada75c666e6c0ddf98a-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [-0.02220001, -0.0009610148, -0.0070057414, 0.023200832, -0.0010406255, /* ... 1019 more values ... */]
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/5488c05dedc77c91265ab401766fff4d-cc_ft_1536.jpg",
      "image_type": "interior",
      "vector": [-0.0019251255, 0.024713239, 0.003962177, 0.004879969, 0.013968352, /* ... 1019 more values ... */]
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/8d73b14774f857e3b87b77903abf6884-cc_ft_1536.jpg",
      "image_type": "exterior",
      "vector": [0.026994739, 0.017529052, -0.010955657, -0.019720182, 0.009597155, /* ... 1019 more values ... */]
    }
  ],
  "vector_text": [
    -0.04876392,
    0.008845336,
    0.0015238725,
    -0.0005843421,
    -0.008295367,
    /* ... 1019 more float values ... */
  ]
}
```

---

## Key Takeaways for Search Improvements

### What We Have ✅

1. **`image_type` field exists!** This is CRITICAL for Phase 1 improvements
   - Can weight `"exterior"` photos 2.5x higher than `"interior"`
   - Already in the data, no reindexing needed

2. **Separate vectors per image** - Can validate tags against specific images

3. **LLM-generated `visual_features_text`** - Says "white exterior with vinyl siding"

4. **Description text** - Mentions "Freshly painted light and white"

### What's Missing ❌

1. **No per-image tags** - `image_tags` is flat array for ALL images combined

2. **Empty `feature_tags`** - Structured tags not populated

3. **No tag-to-image mapping** - Can't tell which image generated which tag

### Immediate Fix Available 🚀

Use **`image_type` weighting** in Phase 1:

```python
# When checking if "white_exterior" tag is valid:
exterior_photos = [v for v in image_vectors if v['image_type'] == 'exterior']
interior_photos = [v for v in image_vectors if v['image_type'] == 'interior']

# This property: 1 exterior, 8 interior
# If "white_exterior" tag only matches the 1 exterior photo, it's VALID
# If tag only matches the 8 interior photos, it's INVALID
```

This explains why the brown house problem exists and how to fix it without reindexing!
