# Visual Features Regeneration - Quick Reference

## TL;DR

**Question:** Can we split `visual_features_text` into context fields without re-analyzing images?

**Answer:** YES - Use DynamoDB cache. Cost: ~$0.16, Time: ~30 min, Coverage: 90%+

---

## Data Availability

| Location | Has Analysis? | Coverage | Cost to Access |
|----------|---------------|----------|----------------|
| **DynamoDB cache** | ✅ Full details | 90%+ | $0.00 |
| **OpenSearch** | ❌ Only aggregated text | 100% | $0.00 |
| **S3 images** | ❌ Would need re-analysis | 100% | ~$7.94 |

**Winner:** DynamoDB cache (hearth-vision-cache table)

---

## Code Locations

### 1. Where Analysis is Generated

**File:** `/Users/andrewcarras/hearth_backend_new/common.py`
**Function:** `detect_labels_with_response()`
**Lines:** 468-650

```python
def detect_labels_with_response(img_bytes: bytes, image_url: str = "") -> Dict[str, Any]:
    """
    Returns:
    {
        "analysis": {
            "features": ["front porch", "vinyl siding", ...],
            "image_type": "exterior" or "interior",
            "architecture_style": "ranch" or null,
            "exterior_color": "white" or null,
            "materials": ["vinyl", "wood"],
            "visual_features": ["natural light", ...],
            "confidence": "high"/"medium"/"low"
        },
        "llm_response": "raw JSON from Claude"
    }
    """
```

### 2. Where Analysis is Cached

**File:** `/Users/andrewcarras/hearth_backend_new/cache_utils.py`
**Function:** `cache_image_data()`
**Lines:** 64-141

```python
def cache_image_data(
    dynamodb_client,
    image_url: str,
    image_bytes: bytes,
    embedding: List[float],
    analysis: Dict[str, Any],  # ← Full analysis stored here
    llm_response: str,
    embedding_model: str,
    analysis_model: str
)
```

**DynamoDB Table:** `hearth-vision-cache`
**Primary Key:** `image_url` (string)

### 3. Where Analysis is Retrieved

**File:** `/Users/andrewcarras/hearth_backend_new/cache_utils.py`
**Function:** `get_cached_image_data()`
**Lines:** 143-207

```python
def get_cached_image_data(dynamodb_client, image_url: str) -> Optional[Tuple]:
    """
    Returns: (embedding, analysis, image_hash) or None

    analysis = {
        "image_type": "exterior",
        "features": [...],
        "architecture_style": "ranch",
        "exterior_color": "white",
        "materials": [...],
        "visual_features": [...],
        "confidence": "high"
    }
    """
```

### 4. Where Aggregation Happens

**File:** `/Users/andrewcarras/hearth_backend_new/upload_listings.py`
**Lines:** 492-596

**Key Steps:**
1. Collect `all_image_analyses` (line 388, 443)
2. Separate by type (lines 502-503)
3. Majority voting for exterior (lines 506-570)
4. Collect interior features (lines 572-576)
5. Build text (line 595)

```python
# Line 492-596: Aggregation logic
visual_features_text = ""
if all_image_analyses:
    exterior_analyses = [a for a in all_image_analyses if a.get("image_type") == "exterior"]
    interior_analyses = [a for a in all_image_analyses if a.get("image_type") == "interior"]

    # Majority voting
    exterior_styles = [a["architecture_style"] for a in exterior_analyses if a.get("architecture_style")]
    primary_style = Counter(exterior_styles).most_common(1)[0][0]

    # Build text
    visual_features_text = ". ".join(description_parts) + "."
```

### 5. Where Data is Stored to OpenSearch

**File:** `/Users/andrewcarras/hearth_backend_new/upload_listings.py`
**Lines:** 664-687

```python
# Line 664-666: Store aggregated text
if visual_features_text:
    doc["visual_features_text"] = visual_features_text

# Line 678-681: Store image vectors (NO analysis details)
if is_multi_vector:
    if image_vector_metadata and len(image_vector_metadata) > 0:
        doc["image_vectors"] = image_vector_metadata  # Only: url, type, vector
```

---

## Regeneration Code Template

### Extract Reusable Function

**New file:** `/Users/andrewcarras/hearth_backend_new/visual_features_utils.py`

```python
from typing import List, Dict
from collections import Counter

def split_visual_features(all_image_analyses: List[Dict]) -> Dict[str, str]:
    """
    Split image analyses into context-specific fields.

    This is the EXACT same logic as upload_listings.py lines 492-596,
    extracted for reuse in migration scripts.

    Args:
        all_image_analyses: List of analysis dicts from DynamoDB cache

    Returns:
        {
            "exterior": "ranch style white exterior with vinyl siding",
            "interior": "granite countertops, white cabinets, hardwood floors",
            "amenities": "front porch, attached garage"
        }
    """
    # Copy logic from upload_listings.py lines 492-596
    # (See full implementation in VISUAL_FEATURES_REGENERATION_INVESTIGATION.md)
    ...
```

### Migration Script

**New file:** `/Users/andrewcarras/hearth_backend_new/regenerate_visual_features.py`

```python
#!/usr/bin/env python3
import boto3
from opensearchpy import OpenSearch
from cache_utils import get_cached_image_data
from visual_features_utils import split_visual_features

dynamodb = boto3.client('dynamodb', region_name='us-east-1')
os_client = OpenSearch(...)

def regenerate_property(zpid: str, image_vectors: List[Dict]) -> Dict:
    """Regenerate split features for one property."""

    # Step 1: Reconstruct all_image_analyses from cache
    all_image_analyses = []
    for img_vec in image_vectors:
        cached = get_cached_image_data(dynamodb, img_vec["image_url"])
        if cached:
            _, analysis, _ = cached
            all_image_analyses.append(analysis)

    if not all_image_analyses:
        return {"status": "skip", "reason": "no_cached_analyses"}

    # Step 2: Split into context fields
    split = split_visual_features(all_image_analyses)

    # Step 3: Update OpenSearch
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
```

---

## Testing Strategy

### 1. Dry Run (Test 1 Property)

```bash
# Test regeneration for one property
python3 -c "
from regenerate_visual_features import regenerate_property
from opensearchpy import OpenSearch

os_client = OpenSearch(...)
resp = os_client.get(index='listings-v2', id='12345')

result = regenerate_property(
    zpid='12345',
    image_vectors=resp['_source']['image_vectors']
)

print(f'Result: {result}')
"
```

### 2. Verify Cache Coverage

```bash
# Check how many properties have full cache coverage
python3 -c "
import boto3
from opensearchpy import OpenSearch

dynamodb = boto3.client('dynamodb', region_name='us-east-1')
os_client = OpenSearch(...)

# Sample 100 properties
resp = os_client.search(
    index='listings-v2',
    body={'size': 100, '_source': ['zpid', 'image_vectors']}
)

full_coverage = 0
partial_coverage = 0
no_coverage = 0

for hit in resp['hits']['hits']:
    image_vectors = hit['_source'].get('image_vectors', [])
    cached_count = 0

    for img_vec in image_vectors:
        try:
            resp = dynamodb.get_item(
                TableName='hearth-vision-cache',
                Key={'image_url': {'S': img_vec['image_url']}}
            )
            if 'Item' in resp:
                cached_count += 1
        except:
            pass

    if cached_count == len(image_vectors):
        full_coverage += 1
    elif cached_count > 0:
        partial_coverage += 1
    else:
        no_coverage += 1

print(f'Full coverage: {full_coverage}/100 ({full_coverage}%)')
print(f'Partial coverage: {partial_coverage}/100')
print(f'No coverage: {no_coverage}/100')
"
```

### 3. Compare Before/After

```bash
# Get original visual_features_text
python3 -c "
from opensearchpy import OpenSearch
os_client = OpenSearch(...)

resp = os_client.get(index='listings-v2', id='12345')
print('BEFORE:')
print(resp['_source']['visual_features_text'])
"

# Run regeneration
python regenerate_visual_features.py --zpid 12345 --dry-run

# Check result
python3 -c "
from opensearchpy import OpenSearch
os_client = OpenSearch(...)

resp = os_client.get(index='listings-v2', id='12345')
print('AFTER:')
print(f\"Exterior: {resp['_source']['exterior_visual_features']}\")
print(f\"Interior: {resp['_source']['interior_visual_features']}\")
print(f\"Amenities: {resp['_source']['amenities_visual_features']}\")
"
```

---

## Rollback Plan

### If Migration Fails

```python
# Revert to original state
def rollback_property(zpid: str):
    """Remove split fields, keep original visual_features_text."""
    os_client.update(
        index="listings-v2",
        id=zpid,
        body={
            "script": {
                "source": """
                    ctx._source.remove('exterior_visual_features');
                    ctx._source.remove('interior_visual_features');
                    ctx._source.remove('amenities_visual_features');
                """
            }
        }
    )
```

### Backup Strategy

```bash
# Before migration, backup all visual_features_text
python3 -c "
from opensearchpy import OpenSearch
import json

os_client = OpenSearch(...)

resp = os_client.search(
    index='listings-v2',
    body={
        'size': 10000,
        '_source': ['zpid', 'visual_features_text']
    },
    scroll='5m'
)

backup = {}
for hit in resp['hits']['hits']:
    backup[hit['_source']['zpid']] = hit['_source']['visual_features_text']

with open('visual_features_backup.json', 'w') as f:
    json.dump(backup, f, indent=2)

print(f'Backed up {len(backup)} properties')
"
```

---

## Monitoring

### Track Migration Progress

```python
def get_migration_stats():
    """Check how many properties have been migrated."""

    resp = os_client.search(
        index="listings-v2",
        body={
            "size": 0,
            "aggs": {
                "has_exterior": {
                    "filter": {"exists": {"field": "exterior_visual_features"}}
                },
                "has_interior": {
                    "filter": {"exists": {"field": "interior_visual_features"}}
                },
                "has_amenities": {
                    "filter": {"exists": {"field": "amenities_visual_features"}}
                }
            }
        }
    )

    total = resp["hits"]["total"]["value"]
    has_exterior = resp["aggregations"]["has_exterior"]["doc_count"]
    has_interior = resp["aggregations"]["has_interior"]["doc_count"]
    has_amenities = resp["aggregations"]["has_amenities"]["doc_count"]

    print(f"Total properties: {total}")
    print(f"Has exterior_visual_features: {has_exterior} ({has_exterior/total*100:.1f}%)")
    print(f"Has interior_visual_features: {has_interior} ({has_interior/total*100:.1f}%)")
    print(f"Has amenities_visual_features: {has_amenities} ({has_amenities/total*100:.1f}%)")
```

---

## Execution Plan

### Phase 1: Preparation (30 min)

1. Extract `split_visual_features()` to `visual_features_utils.py`
2. Create `regenerate_visual_features.py` migration script
3. Update OpenSearch mappings in `common.py`
4. Test on 1-5 properties

### Phase 2: Dry Run (15 min)

1. Run migration in dry-run mode on 100 properties
2. Verify cache coverage
3. Check output quality
4. Backup all `visual_features_text` values

### Phase 3: Execute (30 min)

1. Run migration on full dataset (1,588 properties)
2. Monitor progress every 5 minutes
3. Check for errors

### Phase 4: Verification (15 min)

1. Verify all properties have new fields
2. Spot-check 10 random properties
3. Compare before/after search quality
4. Run search tests

### Phase 5: Update Upload Logic (30 min)

1. Modify `upload_listings.py` to generate split fields
2. Test on new property upload
3. Deploy updated Lambda

**Total time:** ~2 hours

**Total cost:** ~$0.16

---

## Success Criteria

✅ 90%+ properties have all three new fields
✅ New fields match quality of original `visual_features_text`
✅ No data loss or corruption
✅ Search quality improves for context queries
✅ Future uploads generate split fields automatically
