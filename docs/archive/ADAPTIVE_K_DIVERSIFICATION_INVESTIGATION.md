# Adaptive-K Diversification Investigation

**Date:** October 22, 2025
**Issue:** Top-K images all match same sub-query instead of diversifying across features
**Status:** 🔍 INVESTIGATION (No code changes yet)

---

## Problem Statement

### User Observation

**Query:** "White homes with wood floors and granite countertops"

**Expected Behavior:**
- 3 sub-queries created: "hardwood floors", "white exterior", "granite countertops"
- With K=3 adaptive scoring, should select:
  - 1 image matching "hardwood floors" (interior floor shot)
  - 1 image matching "white exterior" (exterior house shot)
  - 1 image matching "granite countertops" (kitchen countertop shot)

**Actual Behavior:**
- ZPID 12780060 (brick house - not white!)
- **ALL 3 top images matched "hardwood floors" sub-query**
- No diversification across sub-queries

### Why This Matters

The whole point of multi-query + adaptive-K is to capture **multiple distinct features** in a property. If all K images match the same sub-query, we're:

1. **Defeating the purpose of multi-query splitting** - Why split if we ignore 2/3 features?
2. **Rewarding one-dimensional properties** - A house with amazing floors but wrong exterior/countertops ranks higher than a house with all 3 features
3. **Missing user intent** - User wants white exterior AND granite AND wood floors, not just 3 great floor photos

---

## Current Implementation Analysis

### How Multi-Query Scoring Works Now

#### Step 1: Query Splitting
```python
# split_query_into_subqueries() creates:
sub_queries = [
    {"query": "hardwood floors", "feature": "hardwood_floors", "weight": 1.0, "strategy": "max"},
    {"query": "white exterior", "feature": "white_exterior", "weight": 1.0, "strategy": "max"},
    {"query": "granite countertops", "feature": "granite_countertops", "weight": 1.0, "strategy": "max"}
]
```

#### Step 2: Multi-Query Image Scoring
**File:** [search.py:788-853](search.py#L788-L853) - `calculate_multi_query_image_score()`

```python
def calculate_multi_query_image_score(inner_hits, sub_query_embeddings):
    # For EACH sub-query:
    for sq_embed in sub_query_embeddings:
        # Calculate similarity with ALL images
        similarities = []
        for img_vec in image_vectors:
            similarity = cosine_similarity(sq_embed["embedding"], img_vec)
            similarities.append(similarity)

        # Take MAX similarity (best single image for this sub-query)
        best_score = max(similarities)
        total_score += best_score * weight

    # Return average across sub-queries
    return total_score / total_weight
```

**Key Issue:** This ONLY uses the BEST matching image per sub-query. It doesn't track WHICH images were selected.

#### Step 3: Standard Mode Top-K Scoring
**File:** [search.py:627-659](search.py#L627-L659) - `calculate_top_k_image_score()`

```python
def calculate_top_k_image_score(inner_hits, k):
    # Extract ALL image scores from inner_hits
    scores = [hit.get("_score", 0.0) for hit in hits]

    # Sort descending and take top K
    scores.sort(reverse=True)
    top_k_scores = scores[:k]

    # SUM the top K scores
    return sum(top_k_scores)
```

**CRITICAL PROBLEM:** This function is used in **standard mode only** (line 1567), NOT in multi-query mode!

In multi-query mode, `calculate_multi_query_image_score()` is used instead, which:
- Returns a SINGLE score (weighted average of max similarities)
- Does NOT sum top-K images
- Does NOT track which images were selected

---

## The Missing Piece: Sub-Query Diversification

### What Should Happen

When adaptive-K = 3 and we have 3 sub-queries:

1. **For "hardwood floors" sub-query:**
   - Find BEST matching image
   - Lock it in as "Image A matches hardwood_floors"
   - Score contribution: similarity_A * weight

2. **For "white exterior" sub-query:**
   - Find BEST matching image (EXCLUDING Image A)
   - Lock it in as "Image B matches white_exterior"
   - Score contribution: similarity_B * weight

3. **For "granite countertops" sub-query:**
   - Find BEST matching image (EXCLUDING Images A & B)
   - Lock it in as "Image C matches granite_countertops"
   - Score contribution: similarity_C * weight

4. **Final Score:** Sum of (similarity * weight) for selected images

### What Actually Happens

```python
# Current: calculate_multi_query_image_score()

# Sub-query 1: "hardwood floors"
similarities_1 = [0.85, 0.83, 0.82, 0.45, 0.42, ...]  # Images 5, 16, 15 are all floor shots
best_1 = 0.85  # Image 5 selected
score += 0.85 * 1.0

# Sub-query 2: "white exterior"
similarities_2 = [0.60, 0.58, 0.57, 0.55, ...]  # Best match is Image 3 (exterior)
best_2 = 0.60  # Image 3 selected
score += 0.60 * 1.0

# Sub-query 3: "granite countertops"
similarities_3 = [0.65, 0.63, 0.61, ...]  # Best match is Image 12 (kitchen)
best_3 = 0.65  # Image 12 selected
score += 0.65 * 1.0

# Final score = (0.85 + 0.60 + 0.65) / 3 = 0.70
```

**Problem:** While the SCORE is calculated correctly (each sub-query contributes), the **UI breakdown and adaptive-K logic** don't track diversification.

---

## The Real Bug: Detailed Scoring Function

### Current: `calculate_multi_query_image_score_detailed()`
**File:** [search.py:856-951](search.py#L856-L951)

```python
def calculate_multi_query_image_score_detailed(inner_hits, sub_query_embeddings, property_data):
    # Track best match for EACH IMAGE across ALL sub-queries
    image_best_matches = {}  # {image_index: {score, sub_query_index, feature}}

    for sq_idx, sq_embed in enumerate(sub_query_embeddings):
        for img_data in image_vectors:
            similarity = cosine_similarity(sq_embed["embedding"], img_data["vector"])

            # Track BEST sub-query match for this image
            if img_index not in image_best_matches or similarity > image_best_matches[img_index]["score"]:
                image_best_matches[img_index] = {
                    "score": similarity,
                    "sub_query_index": sq_idx,
                    "sub_query_feature": feature
                }
```

**This is the issue!** The function tracks:
- **For each IMAGE: which sub-query matches it BEST**

But it should track:
- **For each SUB-QUERY: which image matches it BEST (excluding already-selected images)**

### Example Breakdown

Property has 28 images. 3 sub-queries (floors, exterior, countertops).

**Current logic:**
```
Image 5 (floor): Best match = SQ0 (hardwood_floors, 0.85)
Image 16 (floor): Best match = SQ0 (hardwood_floors, 0.83)
Image 15 (floor): Best match = SQ0 (hardwood_floors, 0.82)
Image 3 (exterior): Best match = SQ1 (white_exterior, 0.60)
Image 12 (kitchen): Best match = SQ2 (granite_countertops, 0.65)
...
```

When sorted by score, top 3 are:
1. Image 5 → SQ0 (hardwood_floors)
2. Image 16 → SQ0 (hardwood_floors)  ❌ DUPLICATE SUB-QUERY
3. Image 15 → SQ0 (hardwood_floors)  ❌ DUPLICATE SUB-QUERY

**Correct logic should be:**
```
SQ0 (hardwood_floors): Best image = Image 5 (0.85)
SQ1 (white_exterior): Best image = Image 3 (0.60)
SQ2 (granite_countertops): Best image = Image 12 (0.65)
```

Top 3 would be:
1. Image 5 → SQ0 (hardwood_floors)  ✅
2. Image 12 → SQ2 (granite_countertops)  ✅ DIVERSIFIED
3. Image 3 → SQ1 (white_exterior)  ✅ DIVERSIFIED

---

## Root Cause Summary

### The Core Issue

**`calculate_multi_query_image_score_detailed()` is image-centric, not sub-query-centric.**

It answers: "For each image, what sub-query matches it best?"
Should answer: "For each sub-query, what image matches it best?"

### Why This Causes Poor Results

1. **Properties with one strong feature dominate** - A house with amazing hardwood floors but brick exterior gets top 3 images all from floors
2. **Multi-feature requirement ignored** - User wanted white + granite + wood, but search rewards properties that excel at ANY ONE feature
3. **Defeats purpose of query splitting** - We split the query but don't ensure each split gets represented
4. **Adaptive-K doesn't work as intended** - K=3 should mean "3 features covered", but instead means "top 3 images (possibly all same feature)"

---

## Proposed Solution (Conceptual)

### Option 1: Sub-Query Greedy Selection

```python
def calculate_multi_query_image_score_detailed_diversified(
    inner_hits, sub_query_embeddings, property_data, adaptive_k
):
    """
    Select top-K images ensuring each sub-query contributes AT MOST 1 image.
    This ensures feature diversity in adaptive-K scoring.
    """
    # Step 1: For each sub-query, find ALL image similarities
    sub_query_matches = []  # List of {sq_idx, feature, image_idx, score}

    for sq_idx, sq_embed in enumerate(sub_query_embeddings):
        for img_idx, img_data in enumerate(image_vectors):
            similarity = cosine_similarity(sq_embed["embedding"], img_data["vector"])
            sub_query_matches.append({
                "sub_query_index": sq_idx,
                "feature": sq_embed["feature"],
                "image_index": img_idx,
                "score": similarity
            })

    # Step 2: Greedy selection - pick best overall match, then exclude that sub-query
    selected_images = []
    used_sub_queries = set()

    # Sort all matches by score descending
    sub_query_matches.sort(key=lambda x: x["score"], reverse=True)

    for match in sub_query_matches:
        # Skip if we've already selected an image for this sub-query
        if match["sub_query_index"] in used_sub_queries:
            continue

        # Select this image
        selected_images.append(match)
        used_sub_queries.add(match["sub_query_index"])

        # Stop when we have K images OR covered all sub-queries
        if len(selected_images) >= adaptive_k:
            break

    # Calculate final score (sum of selected image scores)
    final_score = sum(img["score"] for img in selected_images)

    return final_score, selected_images
```

**Pros:**
- Guarantees each sub-query contributes AT MOST 1 image to top-K
- Forces feature diversity
- Aligns with user intent (white + granite + wood)

**Cons:**
- Might select slightly lower-scoring images to ensure diversity
- More complex logic

### Option 2: Weighted Diversity Penalty

```python
# Penalize selecting multiple images from same sub-query
penalty_factor = 0.5  # Each additional image from same SQ gets 50% penalty

for match in sorted_matches:
    sq_idx = match["sub_query_index"]
    count_from_this_sq = sum(1 for img in selected_images if img["sub_query_index"] == sq_idx)

    # Apply penalty for duplicate sub-queries
    adjusted_score = match["score"] * (penalty_factor ** count_from_this_sq)

    # Select if still competitive after penalty
    if len(selected_images) < K and adjusted_score > threshold:
        selected_images.append(match)
```

**Pros:**
- Soft constraint - allows duplicates if they're significantly better
- More forgiving for single-feature queries

**Cons:**
- Still allows all K images from same sub-query in extreme cases
- Adds complexity with penalty tuning

### Option 3: Strict 1-Image-Per-Sub-Query

```python
# Simplest: Just take best image for each sub-query, no more
selected_images = []

for sq_idx, sq_embed in enumerate(sub_query_embeddings):
    best_image = None
    best_score = 0.0

    for img_idx, img_data in enumerate(image_vectors):
        similarity = cosine_similarity(sq_embed["embedding"], img_data["vector"])
        if similarity > best_score:
            best_score = similarity
            best_image = img_idx

    if best_image is not None:
        selected_images.append({
            "image_index": best_image,
            "sub_query_index": sq_idx,
            "feature": sq_embed["feature"],
            "score": best_score
        })

# K = number of sub-queries (always)
final_score = sum(img["score"] for img in selected_images)
```

**Pros:**
- Simplest to implement
- Guarantees perfect feature diversity
- K automatically equals number of features

**Cons:**
- Fixed K based on feature count (can't do K=5 for 3 features)
- Might miss opportunity to weight important features higher

---

## Questions to Answer Before Implementing

### 1. Should K be tied to number of sub-queries?

**Current:** `adaptive_k = min(3, len(must_tags))` - K based on feature count
**Makes sense:** If query has 3 features, K=3 ensures all 3 represented

**Edge case:** What if query has 5 features but some are minor?
- "White house with pool, garage, granite, hardwood, and fireplace"
- K=5 might be too diluted
- Maybe K should be min(3, num_major_features)?

### 2. What if property lacks images for a sub-query?

**Example:** Property has no good exterior shots (all interior)
- Query: "white exterior, granite countertops, hardwood floors"
- Best matches: floors=0.85, countertops=0.75, exterior=0.35 (poor match)

**Options:**
- **A) Still include poor match** - Ensures all features represented, but dilutes score
- **B) Skip and select 2nd best from another SQ** - Maintains quality but loses diversity
- **C) Penalize property in ranking** - Fair since it doesn't match user requirement

### 3. Should strategy="sum" work differently?

Current sub-query strategies: `max` (best image per SQ)

But the LLM can output `strategy="sum"` for some features. What does that mean?
- Sum top-K images for THAT sub-query only?
- If so, how do we ensure diversity across sub-queries?

### 4. What about weights?

Some sub-queries have `weight=2.0` (exterior primary feature)

**Current:** Weight affects score contribution
**Proposed:** Should weight affect selection priority?
- Higher weight = more likely to get into top-K?
- Or just affects final score calculation?

---

## Testing Plan

Once solution is chosen, test with:

### Test Case 1: Original Problem
**Query:** "White homes with wood floors and granite countertops"
**ZPID:** 12780060 (brick house)
**Expected:** Top 3 images should diversify across floor/exterior/countertop
**Current:** All 3 are floor images ❌

### Test Case 2: Property Lacking Feature
**Query:** "White exterior with pool and mountain views"
**Property:** Has pool and views, but gray exterior
**Expected:** Should include exterior image (even if poor match) OR penalize property
**Current:** Unknown

### Test Case 3: Single-Feature Query
**Query:** "Modern kitchen"
**Expected:** K=1, single best kitchen image
**Current:** Likely works correctly (only 1 sub-query)

### Test Case 4: Many Features
**Query:** "White house pool garage fireplace granite hardwood deck"
**Expected:** K=3, top 3 most important features (exterior, pool, granite?)
**Current:** Unknown

---

## Recommendation

**Implement Option 1: Sub-Query Greedy Selection**

### Why?

1. **Aligns with user intent** - User listed 3 features, they want all 3 represented
2. **Fixes the reported bug** - No more all-floor-images results
3. **Maintains adaptive-K purpose** - K still adapts to query complexity
4. **Clean implementation** - One-time selection, no penalties or complex rules

### Implementation Steps

1. **Modify `calculate_multi_query_image_score_detailed()`:**
   - Change from image-centric to sub-query-centric
   - Implement greedy selection (best match, then exclude that SQ)
   - Respect adaptive-K limit

2. **Update `calculate_multi_query_image_score()` (non-detailed):**
   - Keep current behavior (max per SQ is fine for scoring)
   - Only detailed version needs diversification for UI display

3. **Update UI to show diversification:**
   - Highlight that top-K ensures feature diversity
   - Show which sub-query each image matched

4. **Test with problem queries:**
   - Verify diversification works
   - Ensure scores still make sense
   - Check edge cases (missing features, single-feature queries)

---

## Impact Assessment

### Properties That Will Rank Higher
- **Multi-feature properties** - Houses with white exterior AND granite AND wood floors
- **Balanced properties** - Homes with decent matches for all user requirements

### Properties That Will Rank Lower
- **One-trick ponies** - Amazing floors but wrong exterior/countertops
- **Partial matches** - Only 1 out of 3 features present

### User Experience
- **More relevant results** - Results actually match ALL stated requirements
- **Better transparency** - UI shows which feature each image matches
- **Clearer intent matching** - Search respects all parts of query, not just strongest feature

---

## Next Steps

**WAITING FOR USER CONFIRMATION BEFORE MAKING CHANGES**

Please confirm:
1. ✅ Problem understanding is correct?
2. ✅ Proposed solution (Option 1: Greedy Selection) makes sense?
3. ✅ Any edge cases or concerns to address first?

Once confirmed, I'll implement the fix and test thoroughly.

---

**End of Investigation**
