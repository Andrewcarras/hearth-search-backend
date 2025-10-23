# Query Classification & Scoring Analysis

## Problem Statement

The current query classification system incorrectly de-boosts image search for color-based queries, causing issues like:
- "white houses with wood floors" → ranks brown house #1
- "pink bathtub" → de-boosts images even though color is VISUAL
- "white fence in backyard" → de-boosts images for visual feature

## Root Cause Analysis

### Current Logic (FLAWED)
```python
# Line 683-686 in search.py
if has_color:
    bm25_k = 30      # BOOST BM25 (tags have exact color info)
    image_k = 120    # DE-BOOST images (embeddings don't distinguish colors)
```

**Assumption**: Color queries work better with BM25 tag matching than image embeddings

**Reality**: This assumption is ONLY true for **interior colors** like:
- "Blue kitchen cabinets" → Color tag works well
- "Gray countertops" → Specific material color

But FAILS for **exterior colors** which are HIGHLY VISUAL:
- "White house" → Needs image similarity
- "Gray exterior" → Visual feature
- "Brick exterior" → Visual + textural

### Why Current Approach Fails

1. **Conflates two different use cases**:
   - Interior specific colors (tags work): "blue cabinets", "pink bathroom"
   - Exterior/structural colors (images essential): "white house", "gray siding"

2. **Single query_type is too coarse**:
   - Can't distinguish "white fence" (visual) from "white countertops" (specific tag)
   - Can't handle mixed queries: "modern white house with pool"

3. **Hard-coded weights are inflexible**:
   - Always sets image_k=120 for ANY color
   - No gradation for partial matches
   - No way to boost both BM25 AND images

## Query Pattern Analysis

### Tested Queries

| Query | Type | Has Color | Has Material | Has Arch | Has Feature | Current Weights | Problem? |
|-------|------|-----------|--------------|----------|-------------|----------------|----------|
| white houses with wood floors | color | ✓ | ✓ | ✗ | ✗ | BM25=21↑, Img=120↓ | ❌ WRONG |
| pink bathtub | color | ✓ | ✗ | ✗ | ✓ | BM25=21↑, Img=120↓ | ❌ WRONG |
| white fence in backyard | color | ✓ | ✗ | ✗ | ✓ | BM25=21↑, Img=120↓ | ❌ WRONG |
| blue house | color | ✓ | ✗ | ✗ | ✗ | BM25=21↑, Img=120↓ | ✓ OK |
| mid-century modern with pool | visual_style | ✗ | ✗ | ✓ | ✓ | Img=40↑, Text=45↑ | ✓ OK |
| modern home with granite | visual_style | ✗ | ✓ | ✓ | ✗ | BM25=42↑, Text=45↑ | ✓ OK |
| craftsman with brick exterior | visual_style | ✗ | ✓ | ✓ | ✗ | BM25=42↑, Text=45↑ | ✓ OK |
| mountain views | visual_style | ✗ | ✗ | ✗ | ✗ | Img=40↑, Text=45↑ | ✓ OK |
| large kitchen open floorplan | specific_feature | ✗ | ✗ | ✗ | ✓ | All=60 balanced | ✓ OK |
| contemporary stone fireplace | visual_style | ✗ | ✓ | ✓ | ✓ | BM25=42↑, Text=45↑ | ✓ OK |

**Key Insight**: Color queries where color is applied to STRUCTURES (house, fence, exterior) should BOOST images, not de-boost them.

## Proposed Solutions

### Option 1: Feature-Context Classification (RECOMMENDED)

Classify each feature by its **search behavior** rather than just its category:

```python
# Define feature contexts
VISUAL_DOMINANT = {
    'exterior_features': ['white_exterior', 'gray_exterior', 'brick_exterior', 'stone_exterior'],
    'structure_colors': ['white_house', 'blue_house', 'red_house'],
    'outdoor_structures': ['white_fence', 'stone_patio', 'brick_walkway'],
    'architectural': ['mid_century_modern', 'craftsman', 'contemporary'],
    'environmental': ['mountain_views', 'lake_views', 'wooded_lot']
}

TEXT_DOMINANT = {
    'interior_specifics': ['blue_cabinets', 'pink_bathroom', 'granite_countertops'],
    'amenities': ['pool', 'garage', 'fireplace'],  # These work with all strategies
    'room_types': ['master_bedroom', 'kitchen_island', 'walk_in_closet']
}

HYBRID_FEATURES = {
    'materials': ['hardwood_floors', 'tile_backsplash', 'marble_shower'],  # Both visual + tag
    'spaces': ['open_floorplan', 'vaulted_ceilings', 'large_yard']  # Description + visual
}
```

**Weighting Logic**:
```python
def calculate_adaptive_weights_v2(must_have_tags, query_type):
    visual_score = sum(1 for tag in must_have_tags if tag in VISUAL_DOMINANT_FEATURES)
    text_score = sum(1 for tag in must_have_tags if tag in TEXT_DOMINANT_FEATURES)
    hybrid_score = sum(1 for tag in must_have_tags if tag in HYBRID_FEATURES)

    total = visual_score + text_score + hybrid_score
    if total == 0:
        return [60, 60, 60]  # No features, balanced

    # Calculate weights based on feature distribution
    visual_ratio = visual_score / total
    text_ratio = text_score / total

    # Interpolate k values (lower k = higher weight)
    # Heavy visual: BM25=60, Text=50, Image=30
    # Balanced: BM25=60, Text=60, Image=60
    # Heavy text: BM25=40, Text=50, Image=80

    if visual_ratio > 0.6:  # Dominant visual features
        return [60, 50, 30]
    elif visual_ratio > 0.3:  # Significant visual component
        return [50, 55, 45]
    elif text_ratio > 0.6:  # Dominant text/tag features
        return [40, 50, 80]
    else:  # Mixed or hybrid
        return [55, 55, 55]
```

**Pros**:
- Granular control per feature
- Handles mixed queries naturally
- Self-documenting (feature lists show intent)
- Easy to tune individual features

**Cons**:
- Requires manual classification of ~50-100 common features
- Need to maintain feature lists as new patterns emerge

### Option 2: Multi-Dimensional Query Classification

Instead of single `query_type`, return multiple dimensions:

```python
{
    "visual_importance": 0.8,  # 0-1 scale
    "text_importance": 0.6,
    "tag_importance": 0.9,
    "spatial_importance": 0.3  # For "backyard", "front porch"
}
```

**Weighting Logic**:
```python
# Convert importance scores to k values
bm25_k = 20 + (80 * (1 - tag_importance))      # Range: 20-100
text_k = 20 + (80 * (1 - text_importance))     # Range: 20-100
image_k = 20 + (80 * (1 - visual_importance))  # Range: 20-100
```

**Pros**:
- Captures query nuance
- Natural gradation (not binary)
- LLM excels at multi-dimensional classification

**Cons**:
- More complex LLM prompt
- Harder to debug/understand
- May need training examples

### Option 3: Query Decomposition + Per-Feature Weights

Break complex queries into feature groups, score separately:

```
Query: "white mid-century modern house with pool and hardwood floors"

Decomposed:
- Visual Group: [white_exterior, mid_century_modern] → Weight images heavily
- Amenity Group: [pool] → Balanced
- Interior Group: [hardwood_floors] → Weight text/tags
```

Score each group independently, then combine.

**Pros**:
- Handles very complex queries
- Each feature gets optimal search strategy
- Most accurate for multi-faceted searches

**Cons**:
- Much more complex implementation
- Slower (multiple searches or complex RRF)
- Harder to explain to users

### Option 4: Learned Weights (ML-Based)

Train a small model to predict optimal weights:

```python
Input: [query_embedding, extracted_features, query_length, ...]
Output: [bm25_k, text_k, image_k]
```

**Pros**:
- Optimal weights based on actual data
- Adapts to new patterns automatically

**Cons**:
- Requires training data (labeled queries with ideal weights)
- Black box (hard to debug)
- Overkill for current scale

## Recommendation: Option 1 (Feature-Context Classification)

### Why This is Best

1. **Immediate Fix**: Can be deployed today with known feature patterns
2. **Transparent**: Easy to understand and debug ("white_exterior is VISUAL_DOMINANT")
3. **Maintainable**: Adding new features is straightforward
4. **Scalable**: Works for simple and complex queries
5. **No Training Required**: Uses domain knowledge, not ML

### Implementation Plan

1. **Create feature classification dictionary** (30 minutes)
   - Categorize top 50 most common features
   - Group by search behavior (visual/text/hybrid)

2. **Update adaptive weights function** (1 hour)
   - Replace keyword matching with feature lookup
   - Implement ratio-based weighting
   - Add logging for transparency

3. **Update LLM prompt** (15 minutes)
   - Add context hints about feature types
   - Remove or refine query_type classification

4. **Test with diverse queries** (1 hour)
   - Test all edge cases
   - Verify white house ranks correctly
   - Check complex multi-feature queries

5. **Deploy and monitor** (30 minutes)
   - Deploy to Lambda
   - Monitor logs for unexpected weights
   - Collect user feedback

### Expected Results

| Query | Current Result | New Result |
|-------|---------------|------------|
| white houses with wood floors | Brown house #1 (Image k=120) | White house #1 (Image k=40) |
| pink bathtub | Poor image matching | Strong image+tag matching |
| white fence in backyard | De-boosted images | Boosted images for visual match |
| mid-century modern with pool | Good (already works) | Same or better |
| blue kitchen cabinets | Good (tags work) | Same (tags still prioritized) |

## Alternative: Hybrid Approach

Combine Option 1 + Option 2:
- Use feature lists for known patterns (fast, reliable)
- Use LLM multi-dimensional scoring for unknown/complex queries (flexible)
- Fall back gracefully

This gives best of both worlds but adds complexity.

## Next Steps

1. ✅ Document analysis (this file)
2. ⏳ Get user approval on approach
3. ⏳ Implement Option 1
4. ⏳ Test thoroughly
5. ⏳ Deploy and monitor
