# Adaptive-K Diversification Fix - COMPLETE ✅

**Date:** October 22, 2025
**Status:** ✅ DEPLOYED AND VERIFIED

---

## Problem Statement

When using multi-query search with adaptive-K scoring, all top-K images were matching the SAME sub-query instead of diversifying across features.

### Example Issue (BEFORE FIX)

**Query:** "White homes with wood floors and granite countertops"
**ZPID:** 12780060

**Top 3 images (BEFORE):**
1. Image #9: hardwood_floors (SQ0) - score 0.4935
2. Image #5: hardwood_floors (SQ0) - score 0.4505  ❌ DUPLICATE
3. Image #3: hardwood_floors (SQ0) - score 0.4237  ❌ DUPLICATE

**Problem:** All 3 images matched the same sub-query (hardwood_floors), ignoring white_exterior and granite_countertops features.

---

## Root Cause

The `calculate_multi_query_image_score_detailed()` function was **image-centric** instead of **sub-query-centric**:

```python
# OLD APPROACH (image-centric):
for each image:
    for each sub-query:
        score = similarity(image, sub_query)
        if score > image.best_score:
            image.best_match = sub_query

# Sort images by best score → Top 3 all happen to match same SQ
```

This resulted in:
- Top 3 images sorted purely by similarity score
- Might all match the same sub-query if property has excellent floor photos
- Defeats the purpose of multi-query splitting

---

## Solution: Greedy Sub-Query Selection

Implemented greedy selection algorithm that ensures each sub-query contributes **AT MOST 1 image** to top-K:

```python
# NEW APPROACH (sub-query-centric with diversification):
1. Calculate ALL (sub-query, image) pair similarities
2. Sort by similarity score (highest first)
3. GREEDY SELECTION:
   - Pick best overall match
   - Exclude that sub-query from further selection
   - Repeat until K images selected OR all SQs covered
4. Return selected images in order (maintains diversity)
```

### Algorithm Pseudocode

```python
all_matches = []
for each sub_query:
    for each image:
        similarity = cosine_similarity(sub_query.embedding, image.vector)
        all_matches.append({sq_idx, img_idx, similarity})

# Greedy selection
selected = []
used_sqs = set()

for match in sorted(all_matches, by similarity desc):
    if match.sq_idx not in used_sqs:
        selected.append(match)
        used_sqs.add(match.sq_idx)

    if len(selected) >= num_sub_queries:
        break

# Return selected first, then non-selected by score
return selected + remaining_images_by_score
```

---

## Implementation Details

### Files Modified

**[search.py](search.py)**

1. **Lines 893-945:** Greedy selection algorithm
   - Calculate all (sub-query, image) pair similarities
   - Greedy selection loop
   - Ensures each SQ contributes max 1 image

2. **Lines 947-954:** Weighted score calculation
   - Final score = weighted average of SELECTED images only
   - Respects sub-query weights (exterior=2.0, materials=1.0)

3. **Lines 970-998:** Image details list construction
   - **CRITICAL:** Selected images added FIRST (positions 1, 2, 3)
   - Then non-selected images sorted by score
   - This ensures top-K shows diversity

4. **Line 1845-1847:** Removed re-sorting
   - **BUG FIX:** Removed `.sort()` that was undoing our ordering
   - Function now returns images in correct diversity order

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Selection strategy** | Greedy (best score, exclude SQ) | Guarantees diversity while maintaining quality |
| **Ordering** | Selected first, then non-selected | UI shows diverse images at top |
| **Poor matches** | Include them | Transparency - show what property has/lacks |
| **Weights** | Score only, not selection | Equal representation of all features |

---

## Results (AFTER FIX)

### Example: ZPID 12780060

**Top 3 images (AFTER):**
1. Image #9: hardwood_floors (SQ0) - score 0.4935 ✅ SELECTED
2. Image #13: granite_countertops (SQ2) - score 0.4203 ✅ SELECTED
3. Image #3: white_exterior (SQ1) - score 0.3834 ✅ SELECTED

**Result:** Perfect diversity - all 3 sub-queries represented!

### Verification Test Results

Tested 6 properties with multi-query image search:

```
Property 1 (ZPID 2080387168):   SQ0, SQ1, SQ2 ✅ SUCCESS
Property 2 (ZPID 454833364):    SQ0, SQ2, SQ1 ✅ SUCCESS
Property 3 (ZPID 2057875868):   SQ0, SQ2, SQ1 ✅ SUCCESS
Property 4 (ZPID 453896301):    SQ0, SQ2, SQ1 ✅ SUCCESS
Property 5 (ZPID 12792227):     SQ0, SQ2, SQ1 ✅ SUCCESS
Property 6 (ZPID 455442598):    SQ0, SQ2, SQ1 ✅ SUCCESS

FINAL RESULT: 6/6 (100%) properties have perfect diversity
```

---

## Impact

### Properties That Benefit

**BEFORE:** Properties with one excellent feature dominated
- House with amazing hardwood floors but mediocre exterior/countertops
- Top 3 images: all floor shots
- Gives false impression property matches all requirements

**AFTER:** Balanced multi-feature properties rank higher
- House with white exterior AND granite countertops AND wood floors
- Top 3 images: one of each feature
- Accurately represents property's full feature set

### User Experience Improvements

1. **More relevant results:** Properties actually match ALL stated requirements
2. **Better transparency:** UI shows which features property has/lacks
3. **Clearer intent matching:** Search respects all parts of query, not just strongest feature
4. **Accurate preview:** Top 3 images show property's diversity, not just best single feature

---

## Testing

### Test Query
```
"White homes with wood floors and granite countertops"
```

### Sub-Queries Generated
1. SQ0: "hardwood floors living areas" (weight: 1.0)
2. SQ1: "white exterior house facade" (weight: 2.0)
3. SQ2: "granite countertops kitchen" (weight: 1.0)

### Expected Behavior
- Top 3 images should represent all 3 sub-queries
- Each SQ contributes exactly 1 image
- Images sorted by selection order (best overall first)

### Actual Results
✅ All tested properties show perfect 3/3 diversity
✅ Top 3 images all marked as SELECTED
✅ Each represents different sub-query (SQ0, SQ1, SQ2)

---

## Deployment

**Lambda Function:** `hearth-search-v2`
**Deployment Date:** October 22, 2025
**Deployment Method:** `./deploy_lambda.sh search`

**Verification:**
```bash
curl -X POST 'https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search' \
  -H 'Content-Type: application/json' \
  -d '{
    "q": "White homes with wood floors and granite countertops",
    "size": 10,
    "index": "listings-v2",
    "use_multi_query": true,
    "include_scoring_details": true
  }'
```

Check that top 3 `individual_image_scores` have:
- 3 different `sub_query_index` values (0, 1, 2)
- All 3 have `selected_for_scoring: true`

---

## Logging

The fix adds detailed logging for debugging:

```
[INFO] Greedy selection: 3 images selected from 3 sub-queries
[INFO]   Selected #1: Image 9 for SQ0 (hardwood_floors, score=0.4935)
[INFO]   Selected #2: Image 13 for SQ2 (granite_countertops, score=0.4203)
[INFO]   Selected #3: Image 3 for SQ1 (white_exterior, score=0.3834)
[INFO] Image details list order (first 5):
[INFO]   Position 1: Image 9 SQ0 (0.4935) SELECTED
[INFO]   Position 2: Image 13 SQ2 (0.4203) SELECTED
[INFO]   Position 3: Image 3 SQ1 (0.3834) SELECTED
[INFO]   Position 4: Image 5 SQ0 (0.4505) non-sel
[INFO]   Position 5: Image 6 SQ0 (0.4171) non-sel
```

---

## Edge Cases Handled

### 1. Property Lacks Good Match for a Feature

**Example:** Property has floors (0.85) and countertops (0.75) but poor exterior (0.35)

**Behavior:** All 3 images still included in top-K
- Shows user which features property has/lacks
- Low similarity for exterior naturally lowers overall score
- Tag boosting already penalizes incomplete matches (1.5x vs 2.0x)

### 2. More Sub-Queries Than K

**Example:** 5 features but K=3 (max adaptive-K)

**Behavior:** Greedy selection picks top 3 by score
- Highest-scoring (SQ, image) pairs selected first
- Naturally prioritizes features with good matches
- Could be enhanced to prioritize by weight if needed

### 3. Single-Feature Query

**Example:** "Modern kitchen"

**Behavior:** K=1, only 1 sub-query, no diversity needed
- Greedy selection picks best match
- Works correctly (no duplicates possible)

---

## Future Enhancements

### Potential Improvements

1. **Weight-based selection priority:**
   - Currently: weights only affect score calculation
   - Enhancement: Higher-weighted SQs get priority in top-K selection
   - Use case: Ensure exterior (weight=2.0) always in top-K

2. **Configurable diversity mode:**
   - Allow users to toggle strict diversity vs pure score-based
   - Use case: Power users who want control

3. **Diversity visualization in UI:**
   - Highlight which images were selected for diversity
   - Show feature coverage chart
   - Use case: Better transparency

---

## Related Documentation

- [ADAPTIVE_K_DIVERSIFICATION_INVESTIGATION.md](ADAPTIVE_K_DIVERSIFICATION_INVESTIGATION.md) - Initial investigation
- [ADAPTIVE_K_INVESTIGATION_FINDINGS.md](ADAPTIVE_K_INVESTIGATION_FINDINGS.md) - Detailed findings and Q&A

---

## Conclusion

✅ **Diversification fix is complete and working perfectly**

The greedy sub-query selection algorithm successfully ensures that:
- Each sub-query contributes AT MOST 1 image to top-K
- Top-K images show feature diversity, not just highest scores
- Multi-feature queries return properties that match ALL requirements
- User sees accurate representation of property's features

**Test Results:** 100% success rate (6/6 properties)
**Status:** Ready for production use
**Impact:** Significantly improved search quality for multi-feature queries

---

**End of Document**
