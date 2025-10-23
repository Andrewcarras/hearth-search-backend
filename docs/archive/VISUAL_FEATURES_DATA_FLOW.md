# Visual Features Data Flow - Where is Analysis Data Stored?

## Data Flow During Upload

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         UPLOAD_LISTINGS.PY FLOW                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│  Property with       │
│  20 Image URLs       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  FOR EACH IMAGE:                                                             │
│                                                                              │
│  1. Check DynamoDB cache (hearth-vision-cache)                              │
│     - Key: image_url                                                         │
│     - Contains: embedding + analysis                                         │
│                                                                              │
│  2. If CACHE HIT:                                                           │
│     ✅ Return (embedding, analysis, hash)                                    │
│     📊 Cost: $0.00                                                           │
│                                                                              │
│  3. If CACHE MISS:                                                          │
│     📥 Download image                                                        │
│     🔮 Call Bedrock Titan Image Embedding → vector[1024]                    │
│     🤖 Call Claude Haiku Vision → analysis JSON                             │
│     💾 Cache both to DynamoDB atomically                                     │
│     📊 Cost: $0.00105 ($0.0008 + $0.00025)                                  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  MEMORY (TEMPORARY):                                                         │
│                                                                              │
│  all_image_analyses = [                    # ← ONLY EXISTS IN MEMORY!       │
│    {                                                                         │
│      "image_type": "exterior",                                              │
│      "features": ["front porch", "vinyl siding", ...],                      │
│      "architecture_style": "ranch",                                          │
│      "exterior_color": "white",                                             │
│      "materials": ["vinyl", "wood"],                                        │
│      "visual_features": ["natural light", ...],                             │
│      "confidence": "high"                                                    │
│    },                                                                        │
│    {                                                                         │
│      "image_type": "interior",                                              │
│      "features": ["granite countertops", "white cabinets", ...],            │
│      "architecture_style": null,                                            │
│      "exterior_color": null,                                                │
│      "materials": ["granite", "stainless steel"],                           │
│      "visual_features": ["modern", "bright"],                               │
│      "confidence": "high"                                                    │
│    },                                                                        │
│    ... (18 more analyses)                                                    │
│  ]                                                                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  AGGREGATION LOGIC (Lines 492-596):                                         │
│                                                                              │
│  # Separate by type                                                          │
│  exterior_analyses = [a for a in all_image_analyses                         │
│                       if a["image_type"] == "exterior"]                     │
│  interior_analyses = [a for a in all_image_analyses                         │
│                       if a["image_type"] == "interior"]                     │
│                                                                              │
│  # Majority voting for exterior                                             │
│  exterior_styles = [a["architecture_style"] for a in exterior_analyses]     │
│  primary_style = Counter(exterior_styles).most_common(1)[0][0]              │
│                                                                              │
│  exterior_colors = [a["exterior_color"] for a in exterior_analyses]         │
│  primary_color = Counter(exterior_colors).most_common(1)[0][0]              │
│                                                                              │
│  # Combine into text                                                         │
│  visual_features_text = (                                                    │
│    f"Exterior: {primary_style} style {primary_color} exterior. "            │
│    f"Interior features: {top_interior_features}. "                          │
│    f"Property includes: {all_features}."                                    │
│  )                                                                           │
│                                                                              │
│  ⚠️  CRITICAL: all_image_analyses DISCARDED after this step!                │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  OPENSEARCH DOCUMENT (listings-v2):                                         │
│                                                                              │
│  {                                                                           │
│    "zpid": "12345",                                                          │
│    "description": "Beautiful ranch home...",                                 │
│                                                                              │
│    "visual_features_text": "Exterior: ranch style white exterior with       │
│       vinyl siding, wood. Interior features: granite countertops,            │
│       white cabinets, hardwood floors. Property includes: ...",              │
│       └─► ✅ STORED (aggregated text)                                       │
│                                                                              │
│    "image_vectors": [                                                        │
│      {                                                                       │
│        "image_url": "https://...",                                          │
│        "image_type": "exterior",  ← Only type, NO analysis details!         │
│        "vector": [0.123, 0.456, ...]                                        │
│      },                                                                      │
│      {                                                                       │
│        "image_url": "https://...",                                          │
│        "image_type": "interior",  ← Only type, NO analysis details!         │
│        "vector": [0.789, 0.012, ...]                                        │
│      },                                                                      │
│      ... (18 more)                                                           │
│    ],                                                                        │
│    └─► ✅ STORED (URLs + types + vectors, NO features/colors/materials)     │
│                                                                              │
│    "vector_text": [0.234, 0.567, ...]  # Embedding of description + visual  │
│  }                                                                           │
│                                                                              │
│  ❌ all_image_analyses NOT STORED (only exists during upload)               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Storage Locations Summary

### ✅ DynamoDB (hearth-vision-cache)

**Stores:** Complete per-image data

```json
{
  "image_url": "https://photos.zillowstatic.com/...",
  "image_hash": "sha256:abc123...",
  "embedding": "[0.123, 0.456, ...]",  // ← 1024-dim vector
  "analysis": {                         // ← FULL ANALYSIS DATA
    "image_type": "exterior",
    "features": ["front porch", "vinyl siding", "attached garage"],
    "architecture_style": "ranch",
    "exterior_color": "white",
    "materials": ["vinyl", "wood"],
    "visual_features": ["natural light", "well maintained"],
    "confidence": "high"
  },
  "analysis_llm_response": "{...}",    // ← Raw LLM output
  "embedding_model": "amazon.titan-embed-image-v1",
  "analysis_model": "anthropic.claude-3-haiku-20240307-v1:0",
  "cached_at": 1729123456,
  "access_count": 5,
  "cost_saved": 0.00525
}
```

**Key:** `image_url` (primary key)

**Coverage:** 90%+ of all images (high cache hit rate)

**Regeneration:** ✅ Can reconstruct `all_image_analyses` from cache

---

### ✅ OpenSearch (listings-v2)

**Stores:** Aggregated property-level data

```json
{
  "zpid": "12345",
  "visual_features_text": "Exterior: ranch style white exterior...",
  "image_vectors": [
    {
      "image_url": "https://...",
      "image_type": "exterior",  // ← ONLY image_type
      "vector": [0.123, ...]
    }
  ]
}
```

**Missing:**
- ❌ Per-image `features` array
- ❌ Per-image `architecture_style`
- ❌ Per-image `exterior_color`
- ❌ Per-image `materials`
- ❌ Per-image `visual_features`
- ❌ Per-image `confidence`

**Regeneration:** ❌ Cannot reconstruct detailed analyses from OpenSearch alone

---

### ❌ Nowhere (Lost After Upload)

**Discarded:** `all_image_analyses` array

This array only exists in memory during upload, then discarded after:
1. Aggregating into `visual_features_text`
2. Indexing to OpenSearch

**Why lost?** Not needed for search (only aggregated text is searched).

**Can recover?** ✅ YES - From DynamoDB cache (90%+ coverage)

---

## Regeneration Strategy

### Data Sources

```
┌────────────────────────────────────────────────────────────────┐
│  REGENERATION OPTIONS                                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Option A: DynamoDB Cache (RECOMMENDED)                       │
│  ✅ Has full analysis per image                               │
│  ✅ Zero cost (no API calls)                                  │
│  ✅ 90%+ coverage                                              │
│  ⚠️  Requires fetching analyses for each image_url            │
│                                                                │
│  Option B: Re-analyze from Images                             │
│  ✅ 100% coverage                                              │
│  ❌ Costs ~$0.40 per 1,588 properties                         │
│  ❌ Slower (network + API latency)                            │
│                                                                │
│  Option C: Parse existing visual_features_text                │
│  ✅ Zero cost                                                  │
│  ✅ 100% coverage                                              │
│  ❌ LOSSY (can't recover lost details)                        │
│  ❌ ERROR-PRONE (text parsing)                                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Recommended Flow

```
┌───────────────────────────────────────────────────────────────────────────┐
│  REGENERATION PROCESS                                                     │
└───────────────────────────────────────────────────────────────────────────┘

1. Fetch property from OpenSearch
   ┌────────────────────────────────────┐
   │ {                                  │
   │   "zpid": "12345",                 │
   │   "image_vectors": [               │
   │     {"image_url": "https://..."},  │
   │     {"image_url": "https://..."}   │
   │   ]                                 │
   │ }                                  │
   └────────────────────────────────────┘
           │
           ▼
2. Reconstruct all_image_analyses from DynamoDB
   FOR EACH image_url IN image_vectors:
     cached = dynamodb.get_item(key=image_url)
     all_image_analyses.append(cached["analysis"])

   ┌────────────────────────────────────┐
   │ all_image_analyses = [             │
   │   {                                │
   │     "image_type": "exterior",      │
   │     "features": [...],             │
   │     "architecture_style": "ranch", │
   │     "exterior_color": "white",     │
   │     "materials": [...]             │
   │   },                               │
   │   {                                │
   │     "image_type": "interior",      │
   │     "features": [...],             │
   │     ...                            │
   │   }                                │
   │ ]                                  │
   └────────────────────────────────────┘
           │
           ▼
3. Re-run aggregation logic (extracted from upload_listings.py)
   split = split_visual_features(all_image_analyses)

   ┌────────────────────────────────────┐
   │ {                                  │
   │   "exterior": "ranch style white   │
   │                exterior with vinyl  │
   │                siding, wood",       │
   │   "interior": "granite countertops, │
   │                white cabinets,      │
   │                hardwood floors",    │
   │   "amenities": "front porch,        │
   │                 attached garage"    │
   │ }                                  │
   └────────────────────────────────────┘
           │
           ▼
4. Update OpenSearch document
   os_client.update(
     id=zpid,
     body={
       "doc": {
         "exterior_visual_features": split["exterior"],
         "interior_visual_features": split["interior"],
         "amenities_visual_features": split["amenities"]
       }
     }
   )
```

---

## Cost Analysis

### DynamoDB Cache Approach

```
Per Property (avg 20 images):
  DynamoDB reads: 20 × $0.00000025 = $0.000005
  OpenSearch update: 1 × $0.0001 = $0.0001
  Total: ~$0.0001 per property

For 1,588 properties:
  Total cost: ~$0.16

Time estimate: ~30 minutes (parallel processing)
```

### Re-analysis Approach

```
Per Property (avg 20 images):
  Download: 20 × (network time, no cost)
  Claude Haiku: 20 × $0.00025 = $0.005
  Total: ~$0.005 per property

For 1,588 properties:
  Total cost: ~$7.94

Time estimate: ~3-4 hours (rate limited)
```

### Parse Text Approach

```
Per Property:
  Parse text: $0 (local computation)
  OpenSearch update: $0.0001
  Total: ~$0.0001 per property

For 1,588 properties:
  Total cost: ~$0.16

Time estimate: ~10 minutes

⚠️  BUT: Lossy quality (can't recover lost details)
```

---

## Conclusion

**Best approach:** DynamoDB cache regeneration
- ✅ Same quality as re-analysis
- ✅ Same cost as parsing
- ✅ Covers 90%+ of properties
- ✅ Fast execution (~30 min)

**Implementation effort:** ~3-4 hours
**Cost:** ~$0.16 total
**Risk:** Low (non-destructive, can rollback)
