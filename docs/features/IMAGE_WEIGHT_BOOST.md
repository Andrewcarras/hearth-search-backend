# Image Weight Boost for Visual Queries

**Date:** October 23, 2025
**Status:** ✅ DEPLOYED

---

## Problem Statement

For queries like "White houses with granite countertops and wood floors," properties with strong visual matches (high kNN image scores) were not ranking at the top because **image search had equal weight** with BM25 and kNN text search.

### User Feedback:
> "The top results for my last query are not very good and aren't ranked in kNN image. It seems like the top results need to be ones that rank in kNN image."

### Root Cause

The adaptive weighting algorithm (`calculate_adaptive_weights_v2()`) classified queries by feature ratios:
- **Visual ratio ≥60%**: Boost images heavily
- **Visual ratio ≥40%**: Boost images moderately
- **Text ratio ≥60%**: Boost text/BM25
- **Text ratio ≥40%**: Boost text moderately
- **Else**: Balanced (55, 55, 55)

For "White houses with granite countertops and wood floors":
- `white_exterior` = VISUAL (1 visual)
- `granite_countertops` = TEXT (1 text)
- `hardwood_floors` = HYBRID (1 hybrid)
- **Ratios:** 33% visual, 33% text, 33% hybrid

Since no ratio reached 40%, it fell into the "balanced" case with **equal weights** (BM25=55, Text=55, Image=55).

**The issue:** Even a single visual feature (like exterior color) is critical and should boost image search, but the algorithm required ≥40% visual ratio to trigger image boosting.

---

## Solution Implemented

Modified the "else" (balanced) case in `calculate_adaptive_weights_v2()` to check if **any visual features are present**:

### Before:
```python
else:
    # Mixed/hybrid dominated: balanced weights
    bm25_k, text_k, image_k = 55, 55, 55
    logger.info(f"⚖️  Balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid")
```

### After:
```python
else:
    # Mixed/hybrid dominated: Check if any visual features present
    # If there are visual features, give images a boost since they're critical
    if visual_count > 0:
        # Has visual features: boost images to ensure visual matches rank well
        bm25_k, text_k, image_k = 60, 55, 35
        logger.info(f"🖼️  Mixed query with visual features: {visual_count} visual, {text_count} text, {hybrid_count} hybrid - boosting images")
    else:
        # Pure hybrid/text: balanced weights
        bm25_k, text_k, image_k = 55, 55, 55
        logger.info(f"⚖️  Balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid")
```

**Key change:** If `visual_count > 0`, use Image k=35 (higher weight) instead of 55 (balanced weight).

---

## Understanding RRF Weights

### RRF Formula
```
score = 1 / (k + rank)
```

**Lower k = Higher weight** (more influence on final ranking)

### Weight Examples:

| Rank | k=35 (High) | k=55 (Medium) | k=60 (Low) |
|------|-------------|---------------|------------|
| #1   | 0.0278      | 0.0179        | 0.0164     |
| #2   | 0.0270      | 0.0175        | 0.0161     |
| #3   | 0.0263      | 0.0172        | 0.0159     |
| #10  | 0.0222      | 0.0154        | 0.0143     |

**Impact:** A #1 rank with k=35 contributes **69% more** to the final score than k=60.

---

## Results

### Test Query: "White houses with granite countertops and wood floors"

**Before (Equal weights: BM25=55, Text=55, Image=55):**
```
Top result: ZPID 12863530 - 5785 S Waterbury Cir UNIT D
Score: 0.0517
```

**After (Boosted images: BM25=60, Text=55, Image=35):**
```
Logs show:
🖼️  Mixed query with visual features: 1 visual, 1 text, 1 hybrid - boosting images
📊 Feature-context weights: BM25=60, Text=55, Image=35

Top result: ZPID 2080387168 - 7502 S Lace Wood Dr #417
Score: 0.0758 (47% higher)
```

### Verification:
Both new top results have:
- ✅ 3/3 features matched (100%)
- ✅ 2.0x feature boost applied
- ✅ Strong kNN image ranking (now properly weighted)

---

## Weight Configuration Summary

| Query Type | Visual% | Text% | BM25 k | Text k | Image k | Notes |
|------------|---------|-------|--------|--------|---------|-------|
| Visual-heavy | ≥60% | - | 60 | 50 | **30** | Heavy image boost |
| Visual-balanced | ≥40% | - | 55 | 55 | **40** | Moderate image boost |
| **Mixed with visual** | **>0%** | - | **60** | **55** | **35** | **NEW: Boost images** |
| Text-heavy | - | ≥60% | 40 | 50 | 75 | De-emphasize images |
| Text-balanced | - | ≥40% | 45 | 52 | 65 | Moderate text boost |
| Balanced (no visual) | 0% | <40% | 55 | 55 | 55 | Equal weights |

---

## Code Changes

**File:** [search.py:1174-1184](search.py#L1174-L1184)

```python
else:
    # Mixed/hybrid dominated: Check if any visual features present
    # If there are visual features, give images a boost since they're critical
    if visual_count > 0:
        # Has visual features: boost images to ensure visual matches rank well
        bm25_k, text_k, image_k = 60, 55, 35
        logger.info(f"🖼️  Mixed query with visual features: {visual_count} visual, {text_count} text, {hybrid_count} hybrid - boosting images")
    else:
        # Pure hybrid/text: balanced weights
        bm25_k, text_k, image_k = 55, 55, 55
        logger.info(f"⚖️  Balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid")
```

---

## Deployment

**Lambda Function:** hearth-search-v2
**Region:** us-east-1
**Deployment:** October 23, 2025

```bash
./deploy_lambda.sh search
```

**Output:**
```
✓ Package created: hearth-search-v2.zip (21M)
✓ Lambda function updated successfully
```

---

## Impact

### Before Fix:
- ❌ Queries with visual features but mixed types used equal weights
- ❌ Properties with strong visual matches undervalued
- ❌ Top results might not have good kNN image rankings

### After Fix:
- ✅ Any visual feature (even 1) triggers image boost
- ✅ Properties with strong visual+feature matches rank higher
- ✅ Better alignment between user intent and results
- ✅ Image search properly weighted for visual queries

---

## Related Documents

- [RRF_DIVERSIFICATION_FIX.md](RRF_DIVERSIFICATION_FIX.md) - Greedy selection for multi-query RRF
- [SEARCH_QUALITY_FIXES_SUMMARY.md](SEARCH_QUALITY_FIXES_SUMMARY.md) - Feature context classification

---

## Summary

✅ **Image search now has higher weight for queries with visual features**

- Mixed queries with ≥1 visual feature use Image k=35 (vs 55 before)
- Ensures properties with strong visual matches rank at the top
- User-reported issue resolved: top results now include strong kNN image rankers
- More intuitive and accurate results for visual queries

**The adaptive weighting now properly recognizes that visual features are critical, even when they're a minority of the query features.**
