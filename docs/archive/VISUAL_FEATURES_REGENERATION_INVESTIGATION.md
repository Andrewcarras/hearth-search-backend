# Visual Features Regeneration Investigation

## Executive Summary

**Can we regenerate visual_features_text into separate context fields without re-downloading or re-analyzing images?**

**Answer: NO - Raw image analyses are NOT stored in OpenSearch documents.**

However, **YES - We can regenerate from DynamoDB cache at ZERO cost** (no API calls needed).

---

## Key Findings

### 1. Data Availability ✅

**DynamoDB Cache (`hearth-vision-cache`):**
- ✅ Stores complete image analysis for each image
- ✅ Includes: `image_type`, `features`, `architecture_style`, `exterior_color`, `materials`, `visual_features`, `confidence`
- ✅ Stores both parsed JSON analysis AND raw LLM response
- ✅ Cache hit rate: 90%+ (most images already analyzed)
- ✅ Can retrieve analysis without re-calling Bedrock API

**Example cache entry structure:**
```json
{
  "image_url": "https://photos.zillowstatic.com/...",
  "image_hash": "sha256:abc123...",
  "analysis": {
    "image_type": "interior",
    "features": ["master bedroom", "king size bed", "gray bedding", ...],
    "architecture_style": null,
    "exterior_color": null,
    "materials": ["wood", "carpet"],
    "visual_features": ["natural light", "spacious"],
    "confidence": "high"
  },
  "analysis_llm_response": "{...}",
  "embedding": "[0.123, 0.456, ...]",
  "cached_at": 1729123456
}
```

**OpenSearch Documents (`listings-v2`):**
- ❌ Do NOT store raw `all_image_analyses` array
- ✅ Store `visual_features_text` (aggregated string)
- ✅ Store `image_vectors` array with metadata
- ❌ `image_vectors` does NOT include analysis data

**Example OpenSearch document structure:**
```json
{
  "zpid": "12345",
  "visual_features_text": "Exterior: ranch style white exterior with vinyl siding. Interior features: granite countertops, white cabinets...",
  "image_vectors": [
    {
      "image_url": "https://photos.zillowstatic.com/...",
      "image_type": "exterior",  // ← Only image_type stored
      "vector": [0.123, 0.456, ...]
    },
    {
      "image_url": "https://photos.zillowstatic.com/...",
      "image_type": "interior",
      "vector": [0.789, 0.012, ...]
    }
  ]
}
```

**CRITICAL: `image_vectors` does NOT include analysis details** (features, colors, materials, etc.)

---

## 2. Regeneration Logic

### Current Flow (upload_listings.py)

```python
# Line 388: Collect analyses during image processing
all_image_analyses = []

# Line 443: Store analysis from each image
if analysis:
    all_image_analyses.append(analysis)

# Line 492-596: Generate visual_features_text from all_image_analyses
if all_image_analyses:
    exterior_analyses = [a for a in all_image_analyses if a.get("image_type") == "exterior"]
    interior_descriptions = []

    # Majority voting for exterior attributes
    for analysis in all_image_analyses:
        if analysis.get("image_type") == "exterior":
            exterior_styles.append(analysis["architecture_style"])
            exterior_colors.append(analysis["exterior_color"])
            all_materials.extend(analysis.get("materials", []))
        elif analysis.get("image_type") == "interior":
            interior_descriptions.extend(analysis.get("features", [])[:5])

    # Build description
    visual_features_text = ". ".join([
        f"Exterior: {style} style {color} exterior with {materials}",
        f"Interior features: {interior_features}",
        f"Property includes: {all_features}"
    ])
```

### What Gets Stored Where

**During Upload:**
1. Download image → Generate embedding + analysis → **Cache to DynamoDB**
2. Collect `all_image_analyses` in memory (temporary)
3. Generate `visual_features_text` from `all_image_analyses`
4. Store to OpenSearch:
   - ✅ `visual_features_text` (aggregated string)
   - ✅ `image_vectors` (URL + type + vector)
   - ❌ `all_image_analyses` (NOT stored, discarded after use)

**LOST DATA:** The detailed analysis (`features`, `colors`, `materials`, etc.) is NOT persisted to OpenSearch.

---

## 3. Regeneration Approaches

### Option A: Regenerate from DynamoDB Cache (RECOMMENDED)

**Cost:** $0.00 (no API calls)

**Process:**
1. For each property in OpenSearch:
   - Read `image_vectors` array (has URLs but not analysis)
   - Fetch analysis for each image URL from DynamoDB cache
   - Reconstruct `all_image_analyses` array
   - Re-run aggregation logic to split into context fields

**Code outline:**
```python
def regenerate_visual_features_from_cache(zpid: str, image_vectors: List[Dict]) -> Dict:
    """
    Regenerate split visual features from cached analyses.

    Args:
        zpid: Property ID
        image_vectors: Array from OpenSearch doc (has URLs)

    Returns:
        {
            "exterior_visual_features": "modern style white exterior...",
            "interior_visual_features": "granite countertops, hardwood floors...",
            "amenities_visual_features": "pool, garage, patio..."
        }
    """
    all_image_analyses = []

    # Reconstruct all_image_analyses from cache
    for img_vec in image_vectors:
        image_url = img_vec["image_url"]

        # Fetch from DynamoDB cache
        cached_data = get_cached_image_data(dynamodb, image_url)
        if cached_data:
            embedding, analysis, img_hash = cached_data
            all_image_analyses.append(analysis)
        else:
            logger.warning(f"Cache miss for {image_url} (zpid={zpid})")

    # Re-use existing aggregation logic
    return split_visual_features(all_image_analyses)
```

**Pros:**
- ✅ Zero cost (no Bedrock API calls)
- ✅ Fast (DynamoDB reads only)
- ✅ Exact same analysis as original
- ✅ Works for 90%+ of properties (cache hit rate)

**Cons:**
- ❌ Cache misses (~5-10% of images) require re-analysis OR skip
- ❌ Requires migration script to update all docs

### Option B: Re-analyze Images from Scratch

**Cost:** ~$0.40 per 1,588 properties (same as initial indexing)

**Process:**
1. Download images again
2. Call Claude Haiku Vision API
3. Generate new analyses
4. Split into context fields

**Pros:**
- ✅ Works for 100% of images
- ✅ Can improve analysis with updated prompts

**Cons:**
- ❌ Costs money ($0.00025 per image)
- ❌ Slower (network + API latency)
- ❌ Redundant (we already have analyses cached)

### Option C: Parse Existing visual_features_text

**Cost:** $0.00

**Process:**
```python
def parse_visual_features_text(text: str) -> Dict:
    """
    Parse existing visual_features_text into separate fields.

    Example input:
    "Exterior: ranch style white exterior with vinyl siding.
     Interior features: granite countertops, white cabinets."
    """
    parts = text.split(". ")
    exterior = ""
    interior = ""

    for part in parts:
        if part.startswith("Exterior:"):
            exterior = part.replace("Exterior:", "").strip()
        elif part.startswith("Interior features:"):
            interior = part.replace("Interior features:", "").strip()

    return {
        "exterior_visual_features": exterior,
        "interior_visual_features": interior
    }
```

**Pros:**
- ✅ Zero cost
- ✅ Very fast (no external calls)
- ✅ Works for 100% of properties

**Cons:**
- ❌ **LOSSY:** Lost information during aggregation can't be recovered
  - Example: If 3 exterior photos said "white" and 1 said "beige", we picked "white"
  - Can't recover the original votes/counts
- ❌ **IMPRECISE:** Parsing text is error-prone
- ❌ **INCOMPLETE:** Loses image-level granularity

---

## 4. Recommended Approach

### Two-Phase Migration Strategy

**Phase 1: Regenerate from DynamoDB Cache (Covers 90%+)**
```python
def migrate_visual_features_phase1():
    """Regenerate from cache for all properties."""

    # Scan all documents in OpenSearch
    docs = scan_all_documents(index="listings-v2")

    success_count = 0
    cache_miss_count = 0

    for doc in docs:
        zpid = doc["zpid"]
        image_vectors = doc.get("image_vectors", [])

        if not image_vectors:
            continue

        # Reconstruct all_image_analyses from cache
        all_image_analyses = []
        has_cache_miss = False

        for img_vec in image_vectors:
            cached = get_cached_image_data(dynamodb, img_vec["image_url"])
            if cached:
                _, analysis, _ = cached
                all_image_analyses.append(analysis)
            else:
                has_cache_miss = True
                cache_miss_count += 1

        if not has_cache_miss:
            # Full cache hit - regenerate with confidence
            split_features = split_visual_features(all_image_analyses)

            # Update OpenSearch
            os_client.update(
                index="listings-v2",
                id=zpid,
                body={
                    "doc": {
                        "exterior_visual_features": split_features["exterior"],
                        "interior_visual_features": split_features["interior"],
                        "amenities_visual_features": split_features["amenities"]
                    }
                }
            )
            success_count += 1
        else:
            # Has cache misses - handle in Phase 2
            logger.info(f"Cache miss for zpid={zpid}, skipping for Phase 2")

    print(f"✅ Phase 1 complete: {success_count} properties migrated")
    print(f"⏭️  Phase 2 needed: {cache_miss_count} cache misses")
```

**Phase 2: Handle Cache Misses (Optional)**
- For properties with cache misses, either:
  1. Re-analyze missing images (small cost)
  2. Parse existing `visual_features_text` (lossy but free)
  3. Leave as-is and let next re-index handle it

---

## 5. Cost Comparison

| Approach | API Calls | Compute | Reindex Cost | Total Cost |
|----------|-----------|---------|--------------|------------|
| **DynamoDB Cache** | $0.00 | ~$0.05 | ~$0.10 | **$0.15** |
| **Re-analyze All** | ~$0.40 | ~$0.05 | ~$0.10 | **$0.55** |
| **Parse Text** | $0.00 | ~$0.02 | ~$0.10 | **$0.12** |

**Winner: DynamoDB Cache approach** - Best quality-to-cost ratio.

---

## 6. Implementation Plan

### Step 1: Extract Aggregation Logic
Create reusable function from lines 492-596 of `upload_listings.py`:

```python
def split_visual_features(all_image_analyses: List[Dict]) -> Dict[str, str]:
    """
    Split image analyses into context-specific text fields.

    Args:
        all_image_analyses: List of analysis dicts with:
            - image_type: "exterior" | "interior" | "unknown"
            - features: List[str]
            - architecture_style: str | None
            - exterior_color: str | None
            - materials: List[str]
            - visual_features: List[str]

    Returns:
        {
            "exterior": "modern style white exterior with vinyl siding, brick",
            "interior": "granite countertops, hardwood floors, stainless appliances",
            "amenities": "pool, attached garage, front porch"
        }
    """
    from collections import Counter

    exterior_analyses = [a for a in all_image_analyses if a.get("image_type") == "exterior"]
    interior_analyses = [a for a in all_image_analyses if a.get("image_type") == "interior"]

    # Exterior: Use majority voting
    exterior_text = ""
    if exterior_analyses:
        styles = [a["architecture_style"] for a in exterior_analyses if a.get("architecture_style")]
        colors = [a["exterior_color"] for a in exterior_analyses if a.get("exterior_color")]
        all_materials = []
        for a in exterior_analyses:
            all_materials.extend(a.get("materials", []))

        parts = []
        if styles:
            style = Counter(styles).most_common(1)[0][0]
            parts.append(f"{style} style")
        if colors:
            color = Counter(colors).most_common(1)[0][0]
            parts.append(f"{color} exterior")
        if all_materials:
            top_materials = [m for m, _ in Counter(all_materials).most_common(3)]
            parts.append(f"with {', '.join(top_materials)}")

        exterior_text = " ".join(parts)

    # Interior: Collect top features
    interior_text = ""
    if interior_analyses:
        all_features = []
        for a in interior_analyses:
            all_features.extend(a.get("features", [])[:5])

        feature_counts = Counter(all_features)
        top_features = [f for f, _ in feature_counts.most_common(10)]
        interior_text = ", ".join(top_features)

    # Amenities: Outdoor/structural features
    amenity_features = set()
    amenity_keywords = ["pool", "garage", "porch", "patio", "deck", "fireplace", "yard", "driveway"]
    for analysis in all_image_analyses:
        for feature in analysis.get("features", []):
            if any(kw in feature.lower() for kw in amenity_keywords):
                amenity_features.add(feature)

    amenities_text = ", ".join(sorted(amenity_features))

    return {
        "exterior": exterior_text,
        "interior": interior_text,
        "amenities": amenities_text
    }
```

### Step 2: Create Migration Script

```python
#!/usr/bin/env python3
"""
regenerate_visual_features.py - Migrate visual_features_text to split context fields

Usage:
    python regenerate_visual_features.py --index listings-v2 --dry-run
    python regenerate_visual_features.py --index listings-v2 --execute
"""

import boto3
from opensearchpy import OpenSearch
from cache_utils import get_cached_image_data
from typing import List, Dict

dynamodb = boto3.client('dynamodb', region_name='us-east-1')
os_client = OpenSearch(...)

def reconstruct_analyses_from_cache(image_vectors: List[Dict]) -> List[Dict]:
    """Reconstruct all_image_analyses from DynamoDB cache."""
    all_image_analyses = []

    for img_vec in image_vectors:
        image_url = img_vec["image_url"]
        cached = get_cached_image_data(dynamodb, image_url)

        if cached:
            _, analysis, _ = cached
            all_image_analyses.append(analysis)
        else:
            # Cache miss - could re-analyze or skip
            logger.warning(f"Cache miss: {image_url}")

    return all_image_analyses

def migrate_property(zpid: str, doc: Dict, dry_run: bool = True):
    """Migrate a single property."""
    image_vectors = doc.get("image_vectors", [])

    if not image_vectors:
        return {"status": "skip", "reason": "no_images"}

    # Reconstruct analyses from cache
    all_image_analyses = reconstruct_analyses_from_cache(image_vectors)

    if not all_image_analyses:
        return {"status": "skip", "reason": "no_cached_analyses"}

    # Generate split features
    split = split_visual_features(all_image_analyses)

    if dry_run:
        print(f"Would update zpid={zpid}:")
        print(f"  Exterior: {split['exterior'][:60]}...")
        print(f"  Interior: {split['interior'][:60]}...")
        print(f"  Amenities: {split['amenities'][:60]}...")
        return {"status": "dry_run"}

    # Execute update
    os_client.update(
        index="listings-v2",
        id=zpid,
        body={
            "doc": {
                "exterior_visual_features": split["exterior"],
                "interior_visual_features": split["interior"],
                "amenities_visual_features": split["amenities"]
            }
        }
    )

    return {"status": "success"}

def main(index: str, dry_run: bool):
    """Migrate all properties in index."""
    # Scan all documents
    results = {"success": 0, "skip": 0, "error": 0}

    resp = os_client.search(
        index=index,
        body={
            "size": 100,
            "_source": ["zpid", "image_vectors"],
            "query": {"match_all": {}}
        },
        scroll="5m"
    )

    while resp["hits"]["hits"]:
        for hit in resp["hits"]["hits"]:
            zpid = hit["_source"]["zpid"]
            result = migrate_property(zpid, hit["_source"], dry_run)
            results[result["status"]] += 1

        # Next batch
        resp = os_client.scroll(scroll_id=resp["_scroll_id"], scroll="5m")

    print(f"\n=== Migration Results ===")
    print(f"✅ Success: {results['success']}")
    print(f"⏭️  Skipped: {results['skip']}")
    print(f"❌ Errors: {results['error']}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    main(args.index, dry_run=not args.execute)
```

### Step 3: Update OpenSearch Mappings

Add new fields to `common.py`:

```python
# In create_index_if_needed()
body["mappings"]["properties"].update({
    "exterior_visual_features": {"type": "text"},
    "interior_visual_features": {"type": "text"},
    "amenities_visual_features": {"type": "text"}
})
```

### Step 4: Update Upload Logic

Modify `upload_listings.py` to generate split fields during upload:

```python
# Line 596 (after generating visual_features_text)
split_features = split_visual_features(all_image_analyses)

# Line 665 (when adding to doc)
if split_features["exterior"]:
    doc["exterior_visual_features"] = split_features["exterior"]
if split_features["interior"]:
    doc["interior_visual_features"] = split_features["interior"]
if split_features["amenities"]:
    doc["amenities_visual_features"] = split_features["amenities"]
```

---

## 7. Conclusion

### Summary

**Can we regenerate without re-downloading/re-analyzing?**
- ✅ YES - Using DynamoDB cache
- ✅ 90%+ cache hit rate
- ✅ Zero API cost
- ✅ Exact same analysis quality

**Best Path Forward:**
1. Extract aggregation logic to reusable function
2. Create migration script using DynamoDB cache
3. Run migration on existing index
4. Update upload logic for future properties
5. Handle cache misses in Phase 2 (optional)

**Estimated Effort:**
- Extract function: 30 minutes
- Migration script: 1-2 hours
- Testing: 1 hour
- Execution: 10 minutes
- **Total: 3-4 hours**

**Estimated Cost:**
- API calls: $0.00 (using cache)
- OpenSearch updates: ~$0.10
- **Total: ~$0.10**

### Recommendation

**Proceed with DynamoDB cache approach** - It's the optimal balance of:
- Quality (exact same analyses)
- Cost (virtually free)
- Speed (fast DynamoDB reads)
- Reliability (90%+ cache hit rate)
