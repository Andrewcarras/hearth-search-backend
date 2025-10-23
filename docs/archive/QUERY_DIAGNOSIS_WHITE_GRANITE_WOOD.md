# Search Quality Diagnosis: "White houses with granite countertops and wood floors"

**Date:** October 22, 2025
**Query ID:** 718fe197-6640-4d00-94e4-123e09b33e91
**Status:** 🔴 CRITICAL ISSUE IDENTIFIED

---

## Executive Summary

**Problem:** Search results are poor despite properties having the exact features requested.

**Root Cause:** **feature_tags is empty** on all properties. Tag matching/boosting logic uses `feature_tags`, but visual features are only stored in `image_tags`. This means properties with perfect visual matches get **0% tag boost**.

**Impact:**
- Properties with all 3 requested features (white exterior, granite countertops, hardwood floors) rank poorly
- No feature-based filtering or prioritization
- Ranking relies purely on semantic similarity (RRF), which is less accurate than tag matching

---

## Diagnostic Results

### Query Details

**Original Query:** "White houses with granite countertops and wood floors"

**Required Features Extracted:**
1. `white exterior`
2. `granite countertops`
3. `hardwood floors`

**Expected Behavior:**
- Properties with all 3 features should get 2.0x boost
- Properties with 2/3 features should get 1.5x boost
- Properties with 1/3 features should get 1.25x boost
- Properties with 0/3 features should get no boost

---

### Sub-Query Analysis

**Issue #1: No Sub-Queries Generated** 🔴

The response shows:
```json
"sub_queries": null
```

**Expected:** With 3 features, multi-query mode should split into sub-queries like:
```json
[
  {"query": "white exterior house", "feature": "white_exterior", "weight": 2.0},
  {"query": "granite countertops kitchen", "feature": "granite_countertops", "weight": 1.0},
  {"query": "hardwood floors interior", "feature": "hardwood_floors", "weight": 1.0}
]
```

**Why This Matters:**
- Multi-query mode allows each feature to find its best matching images independently
- "white exterior" matches exterior photos
- "granite countertops" matches kitchen photos
- "hardwood floors" matches interior room photos
- Without sub-queries, all features compete in a single embedding

---

### Top Result Analysis

**Property:** 7502 S Lace Wood Dr #417, West Jordan, UT (ZPID: 2080387168)

**Score:** 0.030777 (very low!)

#### Tag Matching Results 🔴

```json
{
  "required_tags": ["hardwood floors", "white exterior", "granite countertops"],
  "matched_tags": [],
  "match_ratio": 0.0,
  "boost_factor": 1.0
}
```

**❌ 0% match despite having all features!**

#### Feature Tag Analysis

```json
{
  "feature_tags": [],           // ← EMPTY!
  "image_tags": 169,
  "image_tags_sample": [
    "granite",
    "granite countertops",      // ← HAS IT
    "hardwood",
    "hardwood floors",          // ← HAS IT
    "white exterior"            // ← HAS IT
  ]
}
```

**🔍 The Smoking Gun:**
- Property HAS all 3 required features in `image_tags`
- But `feature_tags` is EMPTY
- Tag matching only checks `feature_tags`
- Result: Perfect match gets 0% boost

---

### RRF Contribution Analysis

```json
{
  "bm25_rank": null,           // Not in BM25 top results
  "knn_text_rank": 11,         // 11th in text similarity
  "knn_image_rank": 9          // 9th in image similarity
}
```

**RRF Scores:**
- BM25: 0.000000 (rank null)
- kNN Text: 0.015152 (rank 11)
- kNN Image: 0.015625 (rank 9)
- **Total: 0.030777**

**Without tag boost:**
- Should have gotten 2.0x boost → score = 0.061554
- Would have ranked much higher with boost applied

---

## Root Cause Analysis

### Issue #1: feature_tags Not Populated 🔴 CRITICAL

**Current State:**
```python
# In OpenSearch index
{
  "zpid": "2080387168",
  "feature_tags": [],           # ← EMPTY
  "image_tags": [               # ← POPULATED
    "granite countertops",
    "hardwood floors",
    "white exterior",
    ...
  ]
}
```

**Tag Matching Logic (search.py):**
```python
# Lines 1671-1688
matched_tags = set()
for tag in expanded_must_tags:
    # Checks ONLY feature_tags
    if tag in feature_tags:
        matched_tags.add(tag)

match_ratio = len(matched_tags) / len(expanded_must_tags)
```

**Problem:**
- `feature_tags` is always empty
- `image_tags` is populated but never checked
- Match ratio always = 0%
- Boost always = 1.0x

---

### Issue #2: Sub-Queries Not Being Generated 🔴

**Current Behavior:**
```json
"debug_info": {
  "sub_queries": null,
  "query": null
}
```

**Expected Behavior:**
When `use_multi_query=true` and query has 2+ features, should generate sub-queries.

**Possible Causes:**
1. LLM query splitting is failing silently
2. `must_tags` not being extracted from query
3. Sub-query generation code not running
4. Debug info not being returned

**Location to Check:** [search.py:1329-1343](search.py#L1329-L1343)

---

### Issue #3: No BM25 Match

**Result:** `bm25_rank: null`

**Why:** Property description is generic:
> "Well maintained home waiting to be called yours..."

**Missing Keywords:**
- ✗ "white"
- ✗ "granite"
- ✗ "hardwood"
- ✗ "wood floors"

**Impact:** Loses BM25 contribution entirely (0 points)

---

## Why Results Are Poor

### Current Ranking Logic

Without tag matching working, ranking is based purely on:

1. **kNN Text Similarity (33%)** - Comparing query embedding to description embedding
   - Rank 11 = weak match
   - Generic description doesn't mention features

2. **kNN Image Similarity (33%)** - Comparing query embedding to image embeddings
   - Rank 9 = moderate match
   - Multi-vector scoring finds some relevant images

3. **BM25 Keyword Match (33%)** - Traditional keyword search
   - Rank null = no match
   - Description lacks feature keywords

**Result:** Low combined score (0.0308) → poor ranking

---

### Expected Ranking Logic (If Fixed)

With tag matching working:

1. **Tag Matching (100% boost)** - Check if property has required features
   - 3/3 tags matched = **2.0x boost**
   - Score: 0.0308 × 2.0 = **0.0616**

2. **First Image Boost** - If top image matches feature
   - Additional 1.3x boost possible
   - Score: 0.0616 × 1.3 = **0.0801**

**Result:** Much higher score → better ranking

---

## Impact Assessment

### Severity: 🔴 CRITICAL

**Affected Queries:**
- ALL multi-feature queries
- Any query requesting specific visual features
- Essentially every real user query

**User Impact:**
- Users get irrelevant results
- Properties with exact features rank below random properties
- Search appears "broken" for specific requirements

**Business Impact:**
- Users lose trust in search
- Can't find properties they're looking for
- Poor conversion rates

---

## Solutions

### Solution #1: Populate feature_tags from image_tags (RECOMMENDED)

**When:** During indexing (when property is added/updated)

**Code Change Needed:**
```python
# In indexing logic (wherever properties are indexed)
def prepare_property_for_index(property_data):
    # ... existing code ...

    # Extract feature_tags from image_tags
    image_tags = property_data.get('image_tags', [])
    feature_tags = extract_feature_tags(image_tags)
    property_data['feature_tags'] = feature_tags

    return property_data

def extract_feature_tags(image_tags):
    """Extract structured feature tags from image tags."""
    feature_tags = []

    # Known feature patterns
    feature_mappings = {
        'granite countertops': lambda tags: any('granite countertops' in t for t in tags),
        'hardwood floors': lambda tags: any('hardwood floors' in t or ('hardwood' in t and 'floor' in t) for t in tags),
        'white exterior': lambda tags: any('white exterior' in t or 'white_exterior' in t for t in tags),
        'pool': lambda tags: any('pool' in t for t in tags),
        'fireplace': lambda tags: any('fireplace' in t for t in tags),
        # ... add more features ...
    }

    for feature, check_func in feature_mappings.items():
        if check_func(image_tags):
            feature_tags.append(feature)

    return feature_tags
```

**Deployment:**
1. Update indexing script
2. Re-index all properties (or run migration)
3. Verify feature_tags populated

**Timeline:** 1-2 hours development + re-indexing time

---

### Solution #2: Update Tag Matching to Check image_tags (QUICK FIX)

**When:** At search time

**Code Change:** [search.py:1671-1688](search.py#L1671-L1688)

**Before:**
```python
matched_tags = set()
for tag in expanded_must_tags:
    if tag in feature_tags:
        matched_tags.add(tag)
```

**After:**
```python
matched_tags = set()
for tag in expanded_must_tags:
    # Check feature_tags first (structured)
    if tag in feature_tags:
        matched_tags.add(tag)
    # Fallback to image_tags (visual features)
    elif tag in image_tags:
        matched_tags.add(tag)
    # Check variations (underscore vs space)
    elif tag.replace(' ', '_') in image_tags or tag.replace('_', ' ') in image_tags:
        matched_tags.add(tag)
```

**Pros:**
- ✅ Works immediately (no re-indexing)
- ✅ Simple one-line change
- ✅ Backward compatible

**Cons:**
- ❌ Slower at search time (checking larger lists)
- ❌ Less clean separation of concerns

**Timeline:** 5 minutes development + deployment

---

### Solution #3: Fix Sub-Query Generation

**Issue:** Sub-queries not being generated despite `use_multi_query=true`

**Investigation Needed:**
1. Check if LLM query parsing is failing
2. Verify `must_tags` extraction
3. Add logging to sub-query generation
4. Ensure debug_info is returned

**Code to Check:** [search.py:1329-1343](search.py#L1329-L1343)

```python
if use_multi_query and len(must_tags) >= 2:
    logger.info("🔀 MULTI-QUERY mode enabled - splitting query into sub-queries")

    # Split query using LLM
    t0 = time.time()
    sub_query_result = split_query_into_subqueries(q, list(must_tags))
    # ... handle result ...
```

**Debugging Steps:**
1. Add logging to see if condition is met
2. Check if `must_tags` is empty
3. Verify `split_query_into_subqueries` is working
4. Check if result is being returned in response

---

## Recommended Action Plan

### Phase 1: Immediate Fix (Deploy Today)
1. ✅ **Implement Solution #2** - Update tag matching to check image_tags
2. ✅ Deploy to production
3. ✅ Test with query: "White houses with granite countertops and wood floors"
4. ✅ Verify tag matching now works

### Phase 2: Debug Sub-Queries (Tomorrow)
1. 🔍 Add logging to sub-query generation
2. 🔍 Test with same query
3. 🔍 Identify why sub_queries is null
4. 🔍 Fix root cause

### Phase 3: Proper Solution (Next Week)
1. 📋 Implement Solution #1 - Populate feature_tags during indexing
2. 📋 Create migration script to update existing properties
3. 📋 Run migration on full index
4. 📋 Revert Solution #2 (clean up)

---

## Testing Plan

### Test Case #1: Original Query
**Query:** "White houses with granite countertops and wood floors"

**Expected After Fix:**
- ✅ Top results have all 3 features
- ✅ Tag match ratio = 100%
- ✅ Boost factor = 2.0x
- ✅ Scores 2x higher than before

### Test Case #2: Partial Match
**Query:** "Houses with granite countertops"

**Expected:**
- ✅ Results have granite countertops
- ✅ Tag match ratio = 100% (1/1)
- ✅ Boost factor = 2.0x

### Test Case #3: No Visual Features
**Query:** "3 bedroom house under $500k"

**Expected:**
- ✅ No tag matching (numeric filters)
- ✅ Boost factor = 1.0x
- ✅ No regression from before

---

## Data Evidence

### Sample Property (ZPID: 2080387168)

**Has Features (in image_tags):**
```json
[
  "granite countertops",     ✓
  "hardwood floors",         ✓
  "white exterior"           ✓
]
```

**Current Tag Matching:**
```json
{
  "matched_tags": [],        ← WRONG
  "required_tags": ["hardwood floors", "white exterior", "granite countertops"],
  "match_ratio": 0.0,        ← WRONG
  "boost_factor": 1.0        ← SHOULD BE 2.0x
}
```

**Expected After Fix:**
```json
{
  "matched_tags": ["granite countertops", "hardwood floors", "white exterior"],
  "required_tags": ["hardwood floors", "white exterior", "granite countertops"],
  "match_ratio": 1.0,        ← 100% match
  "boost_factor": 2.0        ← 2x boost
}
```

---

## Conclusion

The search quality issue is caused by a **data structure mismatch**:
- Visual features are detected and stored in `image_tags` ✓
- But tag matching checks `feature_tags` which is empty ✗
- Result: 0% matches despite perfect feature coverage

**Fix:** Update tag matching to check `image_tags` as fallback (5 min fix)

**Long-term:** Populate `feature_tags` during indexing (proper solution)

This is a **critical bug affecting all multi-feature queries** and should be fixed immediately.

---

**Diagnostic Tools Used:**
- ✅ Search API with `include_scoring_details=true`
- ✅ `jq` for JSON analysis
- ✅ Manual inspection of scoring_details
- ✅ Tag matching comparison

**Next Steps:**
1. Implement quick fix (Solution #2)
2. Deploy and test
3. Report results

