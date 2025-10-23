# Data Availability Matrix - Where is Each Piece of Data Stored?

## Quick Answer Table

| Data Field | DynamoDB Cache | OpenSearch | S3 Images | Regenerate? |
|------------|----------------|------------|-----------|-------------|
| **Image URL** | ✅ (key) | ✅ (in image_vectors) | ❌ | N/A |
| **Image bytes** | ❌ | ❌ | ✅ | Download |
| **Image hash** | ✅ | ❌ | ❌ | Compute |
| **Image embedding (vector)** | ✅ | ✅ (in image_vectors) | ❌ | API call |
| **Image type** (exterior/interior) | ✅ | ✅ (in image_vectors) | ❌ | API call |
| **Features array** | ✅ | ❌ | ❌ | API call |
| **Architecture style** | ✅ | ❌ | ❌ | API call |
| **Exterior color** | ✅ | ❌ | ❌ | API call |
| **Materials array** | ✅ | ❌ | ❌ | API call |
| **Visual features** | ✅ | ❌ | ❌ | API call |
| **Confidence score** | ✅ | ❌ | ❌ | API call |
| **Raw LLM response** | ✅ | ❌ | ❌ | API call |
| **visual_features_text** | ❌ | ✅ | ❌ | Aggregate |
| **all_image_analyses** | ✅ (reconstruct) | ❌ | ❌ | Fetch from DB |

---

## Detailed Comparison

### DynamoDB Cache (`hearth-vision-cache`)

**Table:** `hearth-vision-cache`
**Primary Key:** `image_url` (string)
**Items:** ~30,000+ (one per unique image)

**Complete schema:**
```json
{
  // Identity
  "image_url": "https://photos.zillowstatic.com/fp/09af0951089569ae75c5e7c814afff6e-cc_ft_1536.jpg",
  "image_hash": "sha256:abc123def456...",

  // Embedding
  "embedding": "[0.123, 0.456, 0.789, ...]",  // 1024 floats
  "embedding_model": "amazon.titan-embed-image-v1",
  "embedding_cached_at": 1729123456,
  "embedding_cached_at_edt": "2024-10-16 18:30:56 EDT",

  // Analysis (FULL DETAILS)
  "analysis": {
    "image_type": "interior",
    "features": [
      "master bedroom",
      "king size bed",
      "gray bedding",
      "wood nightstands",
      "table lamps",
      "framed artwork",
      "curtains",
      "ceiling light fixture",
      "carpeted floors",
      "dresser",
      "tv",
      "window",
      "door"
    ],
    "architecture_style": null,
    "exterior_color": null,
    "materials": ["wood", "carpet"],
    "visual_features": ["natural light", "spacious"],
    "confidence": "high"
  },
  "analysis_llm_response": "{...}",  // Raw JSON from Claude
  "analysis_model": "anthropic.claude-3-haiku-20240307-v1:0",
  "analysis_cached_at": 1729123456,
  "analysis_cached_at_edt": "2024-10-16 18:30:56 EDT",

  // Metadata
  "cache_version": 1,
  "first_seen": 1729123456,
  "last_accessed": 1729567890,
  "access_count": 5,
  "image_size_bytes": 234567,

  // Cost tracking
  "cost_embedding": 0.0008,
  "cost_analysis": 0.00025,
  "cost_total": 0.00105,
  "cost_saved": 0.00525  // 5 cache hits × $0.00105
}
```

**Pros:**
- ✅ Has ALL analysis details
- ✅ Has raw LLM response (for debugging)
- ✅ Fast access (single DynamoDB read)
- ✅ No API calls needed
- ✅ 90%+ cache hit rate

**Cons:**
- ⚠️ Indexed by image URL, not zpid
- ⚠️ Need to fetch multiple items per property
- ❌ ~5-10% cache misses

---

### OpenSearch (`listings-v2`)

**Index:** `listings-v2`
**Document ID:** `zpid` (string)
**Documents:** ~1,588 (one per property)

**Complete schema (relevant fields):**
```json
{
  "zpid": "12345",
  "description": "Beautiful ranch home with modern updates...",

  // Aggregated visual features (TEXT)
  "visual_features_text": "Exterior: ranch style white exterior with vinyl siding, wood. Interior features: granite countertops, white cabinets, hardwood floors, stainless appliances, ceiling fan. Property includes: front porch, attached garage, natural light, well maintained.",

  // Image vectors (VECTORS + MINIMAL METADATA)
  "image_vectors": [
    {
      "image_url": "https://photos.zillowstatic.com/fp/.../exterior-1.jpg",
      "image_type": "exterior",
      "vector": [0.123, 0.456, ...]  // 1024 floats
    },
    {
      "image_url": "https://photos.zillowstatic.com/fp/.../kitchen-1.jpg",
      "image_type": "interior",
      "vector": [0.789, 0.012, ...]
    },
    // ... 18 more images
  ],

  // Text embedding (VECTOR)
  "vector_text": [0.234, 0.567, ...],  // Embedding of description + visual_features_text

  // Other fields
  "price": 450000,
  "bedrooms": 3,
  "architecture_style": "ranch"  // From best exterior image
}
```

**What's MISSING from image_vectors:**
```json
{
  "image_url": "https://...",
  "image_type": "exterior",
  "vector": [...],

  // ❌ NOT STORED:
  "features": ["front porch", "vinyl siding", "attached garage"],
  "architecture_style": "ranch",
  "exterior_color": "white",
  "materials": ["vinyl", "wood"],
  "visual_features": ["well maintained", "mature landscaping"],
  "confidence": "high"
}
```

**Pros:**
- ✅ Fast property-level access (single doc read)
- ✅ Has aggregated visual_features_text
- ✅ Has all image URLs (for DynamoDB lookup)

**Cons:**
- ❌ No per-image analysis details
- ❌ Can't reconstruct all_image_analyses from OpenSearch alone
- ❌ visual_features_text is aggregated (lost individual votes)

---

## Regeneration Strategies Comparison

### Strategy 1: DynamoDB Cache (RECOMMENDED)

**Data flow:**
```
OpenSearch (listings-v2)
  → Get image_vectors array (has URLs)
  → For each URL, fetch from DynamoDB cache
  → Reconstruct all_image_analyses
  → Re-run aggregation logic
  → Split into context fields
  → Update OpenSearch
```

**Coverage matrix:**

| Scenario | Coverage | Cost | Quality |
|----------|----------|------|---------|
| Full cache hit (90%) | 100% of images | $0.00 | ⭐⭐⭐⭐⭐ Exact |
| Partial cache hit | 90% of images | $0.00 | ⭐⭐⭐⭐ Very good |
| Cache miss (10%) | 0% of images | Skip or re-analyze | N/A |

**Total cost:** ~$0.18 (DynamoDB reads + OpenSearch updates)

**Pros:**
- ✅ Zero API cost
- ✅ Exact same quality as original
- ✅ Fast (parallel processing)
- ✅ 90%+ coverage

**Cons:**
- ⚠️ Cache misses require handling
- ⚠️ Need to fetch N items per property

---

### Strategy 2: Re-analyze from S3 Images

**Data flow:**
```
OpenSearch (listings-v2)
  → Get image_vectors array (has URLs)
  → For each URL, download image from S3
  → Call Claude Haiku Vision API
  → Get new analysis
  → Split into context fields
  → Update OpenSearch
```

**Coverage matrix:**

| Scenario | Coverage | Cost | Quality |
|----------|----------|------|---------|
| All images | 100% | $0.00025/image | ⭐⭐⭐⭐⭐ Exact |

**Total cost:** ~$8.20 (Bedrock API + OpenSearch updates)

**Pros:**
- ✅ 100% coverage
- ✅ Can improve analysis with updated prompts
- ✅ Refreshes cache

**Cons:**
- ❌ Expensive ($7.94 for API calls)
- ❌ Slow (rate limited)
- ❌ Redundant (90% already cached)

---

### Strategy 3: Parse Existing visual_features_text

**Data flow:**
```
OpenSearch (listings-v2)
  → Get visual_features_text
  → Parse text with regex
  → Extract exterior/interior sections
  → Split into context fields
  → Update OpenSearch
```

**Coverage matrix:**

| Scenario | Coverage | Cost | Quality |
|----------|----------|------|---------|
| All properties | 100% | $0.00 | ⭐⭐ Lossy |

**Total cost:** ~$0.16 (OpenSearch updates only)

**What can be recovered:**
```
Input:
  "Exterior: ranch style white exterior with vinyl siding, wood.
   Interior features: granite countertops, white cabinets, hardwood floors."

Parsing:
  ✅ Can extract: "ranch style white exterior with vinyl siding, wood"
  ✅ Can extract: "granite countertops, white cabinets, hardwood floors"

BUT:
  ❌ Lost: Individual image votes (3 white, 1 beige → chose white)
  ❌ Lost: Confidence scores
  ❌ Lost: Full features lists (only top 10 kept)
  ❌ Lost: Materials breakdowns
```

**Pros:**
- ✅ Zero cost
- ✅ 100% coverage
- ✅ Very fast

**Cons:**
- ❌ Lossy (can't recover lost details)
- ❌ Error-prone (parsing text)
- ❌ Lower quality results

---

## Data Loss Analysis

### What Gets Lost During Aggregation?

**Original analyses (in memory during upload):**
```python
all_image_analyses = [
  {
    "image_type": "exterior",
    "features": ["front porch", "vinyl siding", "attached garage", "driveway", "landscaping"],
    "architecture_style": "ranch",
    "exterior_color": "white",
    "materials": ["vinyl", "wood", "asphalt"],
    "visual_features": ["well maintained", "mature trees"],
    "confidence": "high"
  },
  {
    "image_type": "exterior",
    "features": ["front porch", "vinyl siding", "shutters"],
    "architecture_style": "ranch",
    "exterior_color": "white",
    "materials": ["vinyl", "wood"],
    "visual_features": ["curb appeal"],
    "confidence": "high"
  },
  {
    "image_type": "exterior",
    "features": ["backyard", "deck", "fence"],
    "architecture_style": null,
    "exterior_color": "beige",  // ← Minority vote
    "materials": ["wood"],
    "visual_features": ["private", "spacious"],
    "confidence": "medium"
  },
  {
    "image_type": "interior",
    "features": ["granite countertops", "white cabinets", "stainless appliances"],
    "architecture_style": null,
    "exterior_color": null,
    "materials": ["granite", "stainless steel"],
    "visual_features": ["modern", "bright"],
    "confidence": "high"
  },
  // ... 16 more images
]
```

**After aggregation (stored in OpenSearch):**
```python
visual_features_text = "Exterior: ranch style white exterior with vinyl siding, wood. Interior features: granite countertops, white cabinets, stainless appliances. Property includes: front porch, attached garage, well maintained, mature trees."
```

**What's LOST:**

1. **Vote counts:**
   - ❌ 2 images said "white", 1 said "beige"
   - ❌ 2 images had "ranch", 1 had no style
   - ✅ STORED in DynamoDB: Can recover

2. **Confidence scores:**
   - ❌ Image 1: high confidence
   - ❌ Image 2: high confidence
   - ❌ Image 3: medium confidence
   - ✅ STORED in DynamoDB: Can recover

3. **Full features lists:**
   - ❌ Image 1: 5 features
   - ❌ Image 2: 3 features
   - ❌ Image 3: 3 features
   - ✅ STORED in DynamoDB: Can recover

4. **Materials breakdown:**
   - ❌ Which materials came from which images
   - ✅ STORED in DynamoDB: Can recover

5. **Per-image context:**
   - ❌ Which features appeared together
   - ✅ STORED in DynamoDB: Can recover

**Summary:**
- ❌ Lost from OpenSearch (only has aggregated text)
- ✅ Recoverable from DynamoDB (has all original analyses)

---

## Final Recommendation

### Use DynamoDB Cache Approach

**Reasoning:**
1. **Quality:** Exact same as re-analyzing (⭐⭐⭐⭐⭐)
2. **Cost:** Essentially free ($0.18 vs $8.20)
3. **Speed:** Fast (30 min vs 3-4 hours)
4. **Coverage:** Excellent (90%+ cache hit rate)
5. **Risk:** Low (reversible, well-tested)

**Handles cache misses via:**
- Option A: Skip properties with cache misses (~10%)
- Option B: Re-analyze only missing images ($0.79 for 10%)
- Option C: Parse visual_features_text as fallback

**Implementation checklist:**
- [ ] Extract `split_visual_features()` to utils file
- [ ] Create migration script
- [ ] Update OpenSearch mappings
- [ ] Test on 10 sample properties
- [ ] Backup existing visual_features_text
- [ ] Execute migration on full dataset
- [ ] Verify results
- [ ] Update upload logic for future properties

**Expected outcome:**
- 1,427+ properties with full split fields (90%+)
- 161 properties needing Phase 2 handling (10%)
- Total cost: ~$0.18
- Total time: ~30 minutes
