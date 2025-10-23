# Adaptive-K Diversification Investigation - Findings

**Date:** October 22, 2025
**Status:** 🔍 INVESTIGATION COMPLETE
**Blocking Issue Found:** Multi-query image search is completely broken

---

## Executive Summary

While investigating the adaptive-K diversification issue (all top-K images matching same sub-query), I discovered a **critical blocking bug**: **Multi-query image search returns ZERO results** due to a field mapping error.

The diversification issue **cannot be tested or fixed** until this blocking bug is resolved.

---

## Blocking Issue: Image kNN Returns Zero Results

### Error Message (from CloudWatch Logs)

```
[WARNING] Image kNN skipped (no mapping or field):
RequestError(400, 'search_phase_execution_exception',
"failed to create query: Field 'vector_image' is not knn_vector type.")
```

### Root Cause Analysis

**Expected behavior:**
- Multi-query mode should return properties ranked by kNN image similarity
- Properties should have `knn_image.rank` values
- `individual_image_scores` should be populated for properties in kNN results

**Actual behavior:**
- ALL properties have `knn_image.rank: null`
- NO properties in top 30 results have kNN image ranks
- `individual_image_scores` is empty for all results
- Only BM25 and text kNN are working

**Why this happens:**
The error message says "Field 'vector_image' is not knn_vector type" but the code shows:
1. Line 1418: `is_multi_vector = target_index.endswith("-v2")` → Should be True for `listings-v2`
2. Line 1488-1520: If `is_multi_vector`, uses nested query on `image_vectors.vector`
3. Line 1522-1541: Else (legacy), uses `vector_image` field

The logic suggests multi-vector path should be taken, but the error indicates legacy path is being executed.

### Hypothesis: Exception Handling Issue

Looking at line 1487:
```python
try:
    if is_multi_vector:
        # Multi-vector nested query (lines 1488-1520)
    else:
        # Legacy single-vector query (lines 1522-1541)

    # Line 1544: Execute query
    raw_img_hits = _os_search(knn_img_body, size=size * 3, index=target_index)
```

**Possible issue:** If an exception occurs in the multi-vector branch (lines 1488-1520), the except block might be catching it and falling through to legacy logic.

**Need to check:** Exception handling around line 1487-1580

---

## Original Diversification Issue (Cannot Test Yet)

### User's Observation

**Query:** "White homes with wood floors and granite countertops"
**ZPID:** 12780060 (brick house)
**Problem:** Top 3 images ALL matched "hardwood_floors" sub-query
**Expected:** 1 image per sub-query (floor, exterior, countertops)

### Root Cause (Theoretical)

`calculate_multi_query_image_score_detailed()` is **image-centric** instead of **sub-query-centric**:

```python
# CURRENT (image-centric):
for img in images:
    for sq in sub_queries:
        similarity = cosine_similarity(sq.embedding, img.vector)
        if similarity > img.best_match:
            img.best_match = {sq_index, similarity}

# Result: Top 3 images by similarity
# → Image 5 (0.85, hardwood_floors)
# → Image 16 (0.83, hardwood_floors)  ❌ DUPLICATE
# → Image 15 (0.82, hardwood_floors)  ❌ DUPLICATE

# SHOULD BE (sub-query-centric):
for sq in sub_queries:
    best_img = None
    for img in images:
        if img not in selected:  # Exclude already-selected
            similarity = cosine_similarity(sq.embedding, img.vector)
            if similarity > best_score:
                best_img = img

# Result: 1 image per sub-query
# → SQ0 (hardwood_floors) → Image 5 (0.85)  ✅
# → SQ1 (white_exterior) → Image 3 (0.60)   ✅ DIVERSIFIED
# → SQ2 (granite_countertops) → Image 12 (0.65)  ✅ DIVERSIFIED
```

**But this cannot be tested until kNN image search is working!**

---

## Investigation Questions - Answered

### Q1: Does my understanding match the problem?

**Answer:** YES, but there's a blocking issue.

The diversification problem is real and the root cause is correctly identified. However, we cannot demonstrate it because multi-query image search is returning zero results.

### Q2: Does greedy selection solution make sense?

**Answer:** YES, it's the right approach.

**Greedy selection algorithm:**
1. Calculate all (sub-query, image) pair similarities
2. Sort by similarity descending
3. Pick best match, exclude that sub-query from further selection
4. Repeat until K images selected or all sub-queries covered

**Benefits:**
- Ensures each sub-query contributes AT MOST 1 image
- Forces feature diversity
- Aligns with user intent ("white + granite + wood" = 3 distinct features)

**Implementation location:** [search.py:856-951](search.py#L856-L951) - `calculate_multi_query_image_score_detailed()`

### Q3: Edge case - What if property lacks matches for a feature?

**Test performed:**
- Query: "White exterior with pool and mountain views"
- Sub-queries created: "white exterior", "pool" (LLM didn't create separate "views" query)
- Top 5 results:
  - #1-3: white_ext=True, pool=False, views=True
  - #4: white_ext=True, pool=False, views=False
  - #5: white_ext=False, pool=True, views=True

**Answer:** Properties with PARTIAL matches rank highly due to tag boosting.

**Current behavior:** Tag boosting already handles this:
- 100% feature match → 2.0x boost
- 75% match → 1.5x boost
- 50% match → 1.25x boost

**For diversification:**
Option A (Include poor match): Property has floors (0.85), countertops (0.75), but poor exterior (0.35)
- Include all 3 → Ensures diversity but dilutes score
- **Recommendation:** DO THIS - user asked for white exterior, so show best attempt even if poor

Option B (Skip and select 2nd best from another SQ):
- Only include floors (0.85) and countertops (0.75)
- Skip exterior entirely
- **Problem:** Defeats purpose of multi-query diversity

Option C (Penalize property):
- Already handled by tag boosting
- Properties without all features get lower boost (1.5x vs 2.0x)

**Proposed solution:**
1. **Always include best image for each sub-query** (even if similarity is low)
2. **Let low similarity naturally lower the score**
3. **Tag boosting will handle feature completeness**

This ensures:
- ✅ Transparency: User sees which features property has/lacks
- ✅ Diversification: All sub-queries represented
- ✅ Fair ranking: Poor matches get lower scores

### Q4: Should weights affect selection priority?

**Current weights from LLM prompt:**
- Exterior features: `weight: 2.0` (PRIMARY)
- Architectural style: `weight: 1.5` (MODERATE)
- Interior/materials: `weight: 1.0` (SECONDARY)

**Current behavior:** Weights only affect score calculation:
```python
total_score += similarity * weight
final_score = total_score / total_weight
```

**Question:** Should `weight=2.0` mean exterior gets priority in top-K selection?

**Analysis:**

**Option A: Weights affect selection priority**
```python
# Sort (sub_query, image) pairs by: similarity * weight
# Select top K with diversity constraint

sorted_matches.sort(key=lambda x: x.similarity * x.weight, reverse=True)
```

**Pros:**
- Weighted exterior (2.0) more likely to be in top-K
- Aligns weight's semantic meaning (importance)

**Cons:**
- For K=3 with 3 features, all will be selected anyway
- Adds complexity without clear benefit

**Option B: Weights only affect score, not selection**
```python
# Select best image per sub-query (greedy, no weight consideration)
# Apply weights AFTER selection for final score

for sq in sub_queries:
    best_img = find_best_match(sq, remaining_images)
    selected.append((best_img, sq))

final_score = sum(img.similarity * sq.weight for img, sq in selected)
```

**Pros:**
- Simpler implementation
- Guarantees equal representation of all features
- Weights still affect final ranking

**Cons:**
- Low-weight features get same selection priority as high-weight

**Recommendation:** **Option B - Weights only affect score, not selection**

**Reasoning:**
1. **K typically equals feature count** (K=3 for 3 features), so all sub-queries will be represented anyway
2. **User specified ALL features** - even if exterior is "primary", user still wants to see granite and floors
3. **Weights already affect ranking** - properties with good exterior matches will rank higher
4. **Simpler to implement and explain** - "1 image per feature" is clearer than "weighted selection priority"

**Edge case:** If K < number of sub-queries (rare):
- Example: 5 features but K=3
- Current adaptive-K: `k = min(3, len(features))` so K=3
- Should we select the 3 highest-weighted features?

**Sub-recommendation for K < num_features:**
```python
if k < len(sub_queries):
    # Sort sub-queries by weight, take top K
    sorted_sqs = sorted(sub_queries, key=lambda x: x.weight, reverse=True)
    selected_sqs = sorted_sqs[:k]
else:
    selected_sqs = sub_queries
```

This ensures that if we can only select 3 images for 5 features, we prioritize the most important ones (exterior, etc.).

---

## Data Analysis: Feature Completeness

**Query:** "White homes with granite countertops and hardwood floors"
**Top 10 results:** ALL have 3/3 features (W=1, G=1, H=1)

**Conclusion:** Tag boosting is working excellently!

Properties with all requested features are ranking at the top. The issue is NOT about finding properties with features - it's about **how we SELECT which images represent those features** in the scoring breakdown.

---

## Weight Usage in Current Code

**Where weights are used:**

1. **LLM query splitting** ([search.py:695-786](search.py#L695-L786))
   - Sets `weight: 2.0` for exterior
   - Sets `weight: 1.0` for interior/materials

2. **Multi-query scoring** ([search.py:824-850](search.py#L824-L850))
   ```python
   for sq_embed in sub_query_embeddings:
       weight = sq_embed["weight"]
       best_score = max(similarities_for_this_subquery)
       weighted_score = best_score * weight
       total_score += weighted_score
   ```

3. **Currently NOT used in selection** - only in score calculation

**Recommendation:** Keep current behavior (weights affect score only, not selection priority)

---

## Adaptive-K Calculation Logic

**Function:** `calculate_adaptive_k_for_images()` ([search.py:592-625](search.py#L592-L625))

```python
feature_count = len(must_have_features)

if feature_count == 0:
    return 1  # General query → best match only
elif feature_count == 1:
    return 1  # Single feature → best match
elif feature_count == 2:
    return 2  # Two features → top 2
else:
    return 3  # 3+ features → top 3
```

**Philosophy:** K = number of features (capped at 3)

**Implication for diversification:**
- K=3, 3 features → Perfect: 1 image per feature
- K=2, 2 features → Perfect: 1 image per feature
- K=1, 1 feature → Perfect: 1 image for feature
- K=3, 5 features → Conflict: Need to prioritize

**Conclusion:** K is explicitly designed to match feature count for 1:1 representation. This confirms greedy selection (1 image per sub-query) is the intended behavior.

---

## Implementation Plan (After Blocking Bug is Fixed)

### Step 1: Fix Image kNN Field Mapping Error

**Problem:** `vector_image` field error despite `is_multi_vector=True`

**Investigation needed:**
1. Check exception handling around line 1487-1580
2. Verify `target_index` is actually "listings-v2"
3. Add debug logging to confirm which branch executes
4. Test nested query syntax directly in OpenSearch

**File:** [search.py:1487-1580](search.py#L1487-L1580)

### Step 2: Implement Greedy Selection for Diversification

**Modify:** `calculate_multi_query_image_score_detailed()` ([search.py:856-951](search.py#L856-L951))

**Algorithm:**
```python
def calculate_multi_query_image_score_detailed_diversified(
    inner_hits, sub_query_embeddings, property_data, adaptive_k
):
    # Calculate all (sub-query, image) pairs
    all_matches = []
    for sq_idx, sq_embed in enumerate(sub_query_embeddings):
        for img_idx, img_data in enumerate(image_vectors):
            similarity = cosine_similarity(sq_embed["embedding"], img_data["vector"])
            all_matches.append({
                "sub_query_index": sq_idx,
                "feature": sq_embed["feature"],
                "weight": sq_embed["weight"],
                "image_index": img_idx,
                "score": similarity,
                "url": image_urls[img_idx]
            })

    # Greedy selection: best match, then exclude that sub-query
    selected_images = []
    used_sub_queries = set()

    # Sort by score descending
    all_matches.sort(key=lambda x: x["score"], reverse=True)

    for match in all_matches:
        # Skip if we've already selected an image for this sub-query
        if match["sub_query_index"] in used_sub_queries:
            continue

        # Select this image
        selected_images.append(match)
        used_sub_queries.add(match["sub_query_index"])

        # Stop when we have K images OR all sub-queries covered
        if len(selected_images) >= adaptive_k:
            break

    # Calculate final score (weighted sum of selected)
    final_score = sum(img["score"] * img["weight"] for img in selected_images)
    total_weight = sum(img["weight"] for img in selected_images)
    final_score = final_score / total_weight if total_weight > 0 else 0.0

    # Return ALL images with their sub-query matches (for UI display)
    # But mark which ones were selected for top-K
    return final_score, selected_images
```

### Step 3: Update Non-Detailed Scoring (Optional)

**Question:** Should `calculate_multi_query_image_score()` (non-detailed) also use greedy selection?

**Answer:** NO - keep current behavior (max per sub-query)

**Reasoning:**
- Non-detailed version is for scoring only (no UI breakdown)
- Current "max per sub-query" already ensures diversification at scoring level
- Only detailed version needs greedy selection for top-K display

### Step 4: Update UI to Show Diversification

**File:** [ui/multi_query_comparison.html](ui/multi_query_comparison.html)

**Changes:**
1. Highlight which images were selected for top-K (with badge or color)
2. Show "Selected for top-K scoring" vs "Other images"
3. Display which sub-query each image matched

**Example UI:**
```
Individual Image Vector Scores (28 total)

[Top-K Selected Images - These contributed to final score]
┌──────┬──────────┬──────────┬──────────────────────┬─────────┬──────────┐
│ Rank │ Image #  │ Score    │ Matched Sub-Query    │ Preview │ Top-K    │
├──────┼──────────┼──────────┼──────────────────────┼─────────┼──────────┤
│ 🥇 #1│ Image 5  │ 0.850    │ SQ1: hardwood_floors │ [IMG]   │ ✅ K=1   │
│ 🥈 #2│ Image 12 │ 0.650    │ SQ3: granite_counter │ [IMG]   │ ✅ K=2   │
│ 🥉 #3│ Image 3  │ 0.600    │ SQ2: white_exterior  │ [IMG]   │ ✅ K=3   │
└──────┴──────────┴──────────┴──────────────────────┴─────────┴──────────┘

[Other Images - Not selected for top-K]
│ #4   │ Image 16 │ 0.830    │ SQ1: hardwood_floors │ [IMG]   │          │
│ #5   │ Image 15 │ 0.820    │ SQ1: hardwood_floors │ [IMG]   │          │
...
```

---

## Testing Plan (After Fix)

### Test Case 1: Original Problem
**Query:** "White homes with wood floors and granite countertops"
**Expected:** Top 3 images diversify across floor/exterior/countertop
**Verify:** Each sub-query contributes exactly 1 image to top-3

### Test Case 2: Property with Missing Feature
**Query:** "White exterior with pool and granite countertops"
**Property:** Has white exterior (0.75), granite (0.80), but no pool (best match: 0.25)
**Expected:** Top 3 includes poor pool match (0.25)
**Verify:** All 3 sub-queries represented, even with low similarity

### Test Case 3: Single-Feature Query
**Query:** "Modern kitchen"
**Expected:** K=1, single best kitchen image
**Verify:** No diversification needed (only 1 sub-query)

### Test Case 4: More Features than K
**Query:** "White house pool garage fireplace granite hardwood deck" (7 features)
**Expected:** K=3, top 3 highest-weighted features (white exterior=2.0, etc.)
**Verify:** Sub-queries sorted by weight, top 3 selected

---

## Recommendations

### Immediate Next Steps

1. **FIX BLOCKING BUG:** Resolve `vector_image` field error in image kNN
   - Add debug logging to confirm `is_multi_vector` value
   - Check exception handling
   - Test nested query directly

2. **VERIFY IMAGE KNN WORKS:** Confirm properties have `knn_image.rank` values
   - Test with simple query: "modern home"
   - Verify `individual_image_scores` populated

3. **IMPLEMENT DIVERSIFICATION:** Once image kNN works, apply greedy selection
   - Modify `calculate_multi_query_image_score_detailed()`
   - Test with original problem query
   - Verify each sub-query contributes 1 image

4. **UPDATE UI:** Show which images were selected for top-K
   - Add badges or highlighting
   - Display sub-query attribution clearly

### Design Decisions Summary

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Q1: Greedy selection?** | ✅ YES | Ensures 1 image per sub-query |
| **Q2: Include poor matches?** | ✅ YES | Transparency + diversity |
| **Q3: Weights affect selection?** | ❌ NO | Only affect score calculation |
| **Q4: When K < num_features?** | ✅ Prioritize by weight | Select highest-weighted sub-queries |

---

## Conclusion

**Primary finding:** Cannot test or fix diversification issue due to blocking bug in image kNN.

**Secondary finding:** Once image kNN works, greedy selection is the correct approach:
- 1 image per sub-query (guaranteed diversity)
- Include all sub-queries (even poor matches)
- Weights affect score only (not selection priority)

**Action required:** Fix `vector_image` field error FIRST, then implement greedy diversification.

---

**End of Investigation**
