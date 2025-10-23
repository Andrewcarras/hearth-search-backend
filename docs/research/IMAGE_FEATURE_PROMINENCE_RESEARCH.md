# Image Feature Prominence Research: Runtime Techniques Without Reindexing

**Date:** October 21, 2025
**Context:** Real estate search with 20-30 photos per property, flat 100+ tag arrays, need to distinguish primary features (brown exterior) from incidental details (white walls)

---

## Problem Statement

### Current Situation
- **Each property has:** 20-30 photos (exterior, interior rooms, details)
- **Image tags:** Flat array of 100+ tags from vision analysis (all images combined)
- **Core issue:** Cannot distinguish "brown exterior" (primary, visible feature) from "white walls" (incidental interior detail)
- **Photo ordering:** First photo is usually exterior, but sometimes interior
- **Existing data:**
  - `image_tags[]`: Flat keyword array (e.g., ["brown", "brick", "white", "kitchen", "granite"])
  - `image_vectors[]`: Nested array with URL, type, and embedding per image
  - `image_type`: "exterior", "interior", "kitchen", etc. (from Claude vision analysis)
  - First image boost already implemented (1.2x for score ≥0.75)

### Goal
Identify techniques to better weight/prioritize predominant features at **query time** without reindexing or re-processing images.

---

## Research Findings

## 1. Position-Based Weighting Strategies

### Technique 1.1: First N Photos Exponential Decay
**Concept:** Weight photos by position with exponential decay

```python
def calculate_position_weighted_score(image_scores, positions, k=3, decay=0.5):
    """
    Apply position-based weights to image scores.

    First photo gets full weight, subsequent photos decay.
    Useful because first 3-5 photos are typically most important.

    Args:
        image_scores: List of similarity scores per image
        positions: Image indices (0=first)
        k: Number of images to include
        decay: Decay factor (0.5 = half weight for each position)

    Returns:
        Weighted sum of top K positioned scores
    """
    weighted = []
    for score, pos in zip(image_scores, positions):
        weight = decay ** pos  # 1.0, 0.5, 0.25, 0.125...
        weighted.append((score * weight, score, pos))

    # Sort by weighted score, take top K
    weighted.sort(reverse=True, key=lambda x: x[0])
    return sum(w[0] for w in weighted[:k])
```

**Example:**
```
Query: "brown house"
Property has 5 images with scores:
  [0] Exterior (brown): 0.72 × 1.0   = 0.72
  [1] Living room:      0.45 × 0.5   = 0.225
  [2] Kitchen:          0.38 × 0.25  = 0.095
  [3] Bedroom:          0.28 × 0.125 = 0.035
  [4] Bathroom:         0.22 × 0.0625= 0.014

Total (k=3): 0.72 + 0.225 + 0.095 = 1.04
```

**Latency:** ~5-10ms (Python calculation on existing scores)
**Cost:** $0 (uses cached image vectors)
**Accuracy:** Good for typical listings, breaks if first photo isn't exterior
**Implementation complexity:** Low - modify `calculate_top_k_image_score()`

**Current Status:** Partially implemented via first-image boost (lines 1256-1277 in search.py)

---

### Technique 1.2: Image Type Category Weighting
**Concept:** Weight images by their semantic category (already tagged)

```python
def calculate_category_weighted_score(image_vectors, query_vec, query_context):
    """
    Weight images based on their category and query context.

    Uses existing image_type field: "exterior", "interior", "kitchen", etc.
    Query context determines which categories are most relevant.

    Args:
        image_vectors: Nested array with image_url, image_type, vector
        query_vec: Query embedding
        query_context: Dict with query_type, must_have_tags

    Returns:
        Category-weighted image score
    """
    # Determine category weights based on query
    category_weights = {
        "exterior": 1.0,  # Always important
        "interior": 0.5,  # Less important unless specific room mentioned
        "kitchen": 0.3,
        "bathroom": 0.3,
        "bedroom": 0.3,
        "living_room": 0.3,
    }

    # Boost specific categories if mentioned in query
    if "kitchen" in query_context.get("must_have_tags", []):
        category_weights["kitchen"] = 1.0
    if "pool" in query_context.get("must_have_tags", []):
        category_weights["exterior"] = 1.2  # Pool is exterior feature

    # Calculate weighted scores
    weighted_scores = []
    for img in image_vectors:
        img_type = img.get("image_type", "unknown")
        similarity = cosine_similarity(query_vec, img["vector"])
        weight = category_weights.get(img_type, 0.3)
        weighted_scores.append(similarity * weight)

    # Sum top 3 weighted scores
    return sum(sorted(weighted_scores, reverse=True)[:3])
```

**Example:**
```
Query: "brown house" (no specific room mentioned)
Property has 5 images:
  [0] Exterior (brown):  0.72 × 1.0  = 0.72  ← High weight
  [1] Kitchen (white):   0.45 × 0.3  = 0.135 ← Low weight
  [2] Bedroom (beige):   0.38 × 0.3  = 0.114 ← Low weight
  [3] Living room:       0.28 × 0.5  = 0.14  ← Medium weight
  [4] Bathroom:          0.22 × 0.3  = 0.066 ← Low weight

Top 3 weighted: 0.72 + 0.14 + 0.135 = 0.995
```

**Latency:** ~5-10ms (Python calculation)
**Cost:** $0 (uses existing `image_type` field)
**Accuracy:** Excellent - semantically aware of what matters
**Implementation complexity:** Low - `image_type` already exists in schema

**Data availability:** CHECK NEEDED - verify `image_type` is populated for all images

---

## 2. Runtime Image Analysis for Candidate Validation

### Technique 2.1: Cheap Vision API Reranking (Top-N Only)
**Concept:** Re-analyze only the top 10 candidates with a fast vision model

**Services:**
- **AWS Rekognition:** $0.001/image, 200-500ms latency
  - DetectLabels: Returns labels with confidence scores
  - Limitation: Generic labels, not real-estate specific

- **Claude Haiku (already in use):** $0.00025/image, 300-800ms latency
  - Already caching in DynamoDB (hearth-vision-cache)
  - Can ask specific questions about prominence
  - Cache hit rate: ~90% (from code comments)

- **GPT-4o-mini Vision:** $0.0001/image, 200-400ms latency
  - Cheaper than Claude Haiku
  - Good for structured output
  - Not currently integrated

**Implementation:**
```python
async def rerank_with_vision_validation(top_candidates, query):
    """
    Re-analyze first photo of top 10 candidates to validate prominence.

    Uses Claude Haiku with DynamoDB cache to avoid repeated API calls.

    Args:
        top_candidates: Top 10-15 search results
        query: User query with must_have features

    Returns:
        Reranked candidates with prominence-adjusted scores
    """
    reranked = []

    for candidate in top_candidates[:10]:
        # Get first image (usually exterior)
        first_image_url = candidate["image_vectors"][0]["image_url"]

        # Check cache first (90% hit rate)
        cached = get_vision_cache(first_image_url)

        if not cached:
            # Prompt: "Is this image showing [feature] as a PRIMARY characteristic?"
            prompt = f"""Is the {query.must_have_tags[0]} a PRIMARY, visually dominant
            feature in this image? Or is it incidental/background?

            Answer: PRIMARY or INCIDENTAL"""

            analysis = await claude_haiku_vision(first_image_url, prompt)
            cache_vision_result(first_image_url, analysis)
        else:
            analysis = cached

        # Boost/penalize based on prominence
        if analysis == "PRIMARY":
            candidate["score"] *= 1.3
        elif analysis == "INCIDENTAL":
            candidate["score"] *= 0.7

        reranked.append(candidate)

    return sorted(reranked, key=lambda x: x["score"], reverse=True)
```

**Latency:**
- Cache hit (90%): ~30ms DynamoDB lookup × 10 = ~300ms total
- Cache miss (10%): ~500ms Claude call × 1 = ~500ms total
- **Average:** ~350ms added latency

**Cost:**
- Cache hit (90%): $0
- Cache miss (10%): $0.00025 × 1 = $0.00025 per search
- **Average:** $0.000025 per search (~$0.025 per 1000 searches)

**Accuracy:** Very high - LLM understands prominence/dominance
**Implementation complexity:** Medium - needs async infrastructure

**Trade-off:** Adds 300-500ms latency but could improve top-10 quality significantly

---

### Technique 2.2: Zero-Shot Classification on Embeddings
**Concept:** Use CLIP-style queries on existing image embeddings

```python
def classify_feature_prominence(image_embedding, feature):
    """
    Classify if a feature is primary/prominent using text prompts.

    Uses existing Titan Multimodal embeddings - no new API calls!

    Args:
        image_embedding: Existing 1024-dim image vector
        feature: Feature to check (e.g., "brown exterior")

    Returns:
        Prominence score 0-1
    """
    # Generate embeddings for prominence queries
    primary_prompt = f"a house where {feature} is the PRIMARY visible characteristic"
    incidental_prompt = f"a house where {feature} is barely visible or incidental"

    primary_vec = embed_text_multimodal(primary_prompt)
    incidental_vec = embed_text_multimodal(incidental_prompt)

    # Compare image to both prompts
    primary_sim = cosine_similarity(image_embedding, primary_vec)
    incidental_sim = cosine_similarity(image_embedding, incidental_vec)

    # Normalize to prominence score
    prominence = (primary_sim - incidental_sim + 1) / 2

    return prominence
```

**Example:**
```
Query: "brown house"
Image #0 (exterior, brown):
  vs "brown is PRIMARY": 0.82
  vs "brown is incidental": 0.35
  → Prominence: (0.82 - 0.35 + 1) / 2 = 0.735 → HIGH

Image #3 (living room, brown accent wall):
  vs "brown is PRIMARY": 0.48
  vs "brown is incidental": 0.71
  → Prominence: (0.48 - 0.71 + 1) / 2 = 0.385 → LOW
```

**Latency:**
- Text embedding: ~100ms × 2 prompts = 200ms
- Similarity calculation: ~1ms × 2 × N images = ~40ms (N=20)
- **Total:** ~240ms per property

**Cost:**
- Text embeddings: $0.0002 per 1000 tokens × 20 tokens = ~$0.000004
- **Total:** ~$0.000004 per property (~$0.004 per 1000 properties)

**Accuracy:** Medium - depends on embedding space capturing prominence
**Implementation complexity:** Low - uses existing infrastructure

**Advantage:** No new API calls, works with cached data!

---

## 3. Tag Filtering/Scoring Based on Frequency or Context

### Technique 3.1: Tag Co-occurrence Analysis
**Concept:** Exterior features appear in fewer images (1-3), interior features appear in more images (5-10)

```python
def calculate_tag_prominence_from_frequency(image_tags_per_image):
    """
    Infer tag prominence from how many images it appears in.

    Assumption: Primary features (exterior color) appear in fewer images.
    Incidental features (white walls) appear in many images.

    Args:
        image_tags_per_image: List of tag lists, one per image
            [[brown, brick], [white, kitchen], [white, bedroom], ...]

    Returns:
        Dict of tag -> prominence score
    """
    tag_counts = Counter()
    for tags in image_tags_per_image:
        tag_counts.update(tags)

    total_images = len(image_tags_per_image)

    prominence_scores = {}
    for tag, count in tag_counts.items():
        # Inverse frequency: Fewer images = more prominent
        # 1-3 images (exterior): prominence ~0.8-0.95
        # 5-10 images (common interior): prominence ~0.3-0.5
        # 15+ images (very common): prominence ~0.1-0.2

        frequency_ratio = count / total_images
        prominence = 1.0 - (frequency_ratio ** 0.5)  # Square root for smoother curve
        prominence_scores[tag] = prominence

    return prominence_scores
```

**Example:**
```
Property with 20 images:
  "brown": 2 images (exterior) → freq=0.1 → prominence = 1 - √0.1 = 0.68
  "white": 12 images (interior walls) → freq=0.6 → prominence = 1 - √0.6 = 0.23
  "granite": 3 images (kitchen) → freq=0.15 → prominence = 1 - √0.15 = 0.61
```

**Latency:** ~5ms (count operation)
**Cost:** $0 (uses existing data)
**Accuracy:** Medium - heuristic based on Zillow photo patterns
**Implementation complexity:** Very low

**Limitation:** Requires per-image tag arrays (currently only have flat combined array)

---

### Technique 3.2: Semantic Tag Grouping
**Concept:** Group tags by semantic category (exterior vs interior)

```python
# Pre-defined semantic groups (can be generated once)
EXTERIOR_TAGS = {
    "brown", "brick", "white_exterior", "gray_exterior", "siding",
    "roof", "driveway", "garage", "porch", "yard", "fence",
    "trees", "landscaping", "colonial", "craftsman", "modern_exterior"
}

INTERIOR_TAGS = {
    "kitchen", "bedroom", "bathroom", "living_room", "hardwood_floors",
    "granite_countertops", "white_cabinets", "tile", "carpet",
    "stainless_appliances", "fireplace", "ceiling"
}

def boost_tags_by_category(must_have_tags, query_type):
    """
    Boost exterior tags for general queries, interior tags when specific room mentioned.

    Args:
        must_have_tags: Tags extracted from query
        query_type: "general", "visual_style", "room_specific", etc.

    Returns:
        Tag weights for scoring
    """
    weights = {}

    for tag in must_have_tags:
        if tag in EXTERIOR_TAGS:
            if query_type in ["general", "visual_style"]:
                weights[tag] = 2.0  # Highly relevant
            else:
                weights[tag] = 1.0  # Normal relevance
        elif tag in INTERIOR_TAGS:
            if query_type == "room_specific":
                weights[tag] = 2.0  # Highly relevant
            else:
                weights[tag] = 1.0  # Normal relevance
        else:
            weights[tag] = 1.0  # Unknown, normal weight

    return weights
```

**Latency:** ~1ms (dictionary lookup)
**Cost:** $0
**Accuracy:** High for predefined tags, medium for new tags
**Implementation complexity:** Very low

**Current status:** Partially implemented in VISUAL_DOMINANT_FEATURES, TEXT_DOMINANT_FEATURES (search.py lines 665-724)

---

## 4. Confidence Scoring for Existing Tags

### Technique 4.1: LLM-Based Confidence Scores (Existing Data)
**Concept:** Vision analysis already returns confidence, but not currently used

**Check existing data structure:**
```python
# From common.py detect_labels_with_response():
{
    "analysis": {
        "features": ["brown", "brick", "two_story"],
        "image_type": "exterior",
        "confidence": "high"  # ← Currently ignored!
    }
}
```

**Implementation:**
```python
def weight_tags_by_confidence(image_tags_with_confidence):
    """
    Use existing confidence scores from vision analysis.

    Args:
        image_tags_with_confidence:
            [{"tag": "brown", "confidence": "high"},
             {"tag": "white", "confidence": "low"}, ...]

    Returns:
        Weighted tag scores
    """
    confidence_weights = {
        "high": 1.0,
        "medium": 0.6,
        "low": 0.3
    }

    weighted = {}
    for item in image_tags_with_confidence:
        tag = item["tag"]
        confidence = item.get("confidence", "medium")
        weighted[tag] = confidence_weights.get(confidence, 0.5)

    return weighted
```

**Latency:** ~1ms
**Cost:** $0 (data already exists)
**Accuracy:** High if confidence is accurate
**Implementation complexity:** Low

**ACTION REQUIRED:** Check if confidence is stored per-tag or per-image in current schema

---

### Technique 4.2: Embedding Magnitude as Confidence Proxy
**Concept:** Stronger embeddings = more confident visual features

```python
def calculate_visual_confidence(image_embedding, feature_tags):
    """
    Use embedding magnitude as proxy for visual strength.

    Assumption: Images with strong dominant features have higher-magnitude
    embeddings for those features.

    Args:
        image_embedding: 1024-dim vector
        feature_tags: Tags detected in this image

    Returns:
        Tag confidence scores
    """
    # Calculate embedding magnitude
    magnitude = np.linalg.norm(image_embedding)

    # Higher magnitude = stronger visual features
    # Normalize to 0-1 range (typical magnitudes: 0.8-1.2)
    confidence = min(1.0, magnitude / 1.2)

    # Apply to all tags in this image
    return {tag: confidence for tag in feature_tags}
```

**Latency:** ~1ms per image
**Cost:** $0
**Accuracy:** Low - magnitude doesn't directly correlate with feature prominence
**Implementation complexity:** Very low

**Not recommended:** Weak correlation between magnitude and prominence

---

## 5. Using Image Embeddings Directly for Validation

### Technique 5.1: Per-Feature Query Decomposition
**Concept:** Split multi-feature query into individual feature queries

```python
def decompose_query_by_feature(query, must_have_tags):
    """
    Split "brown house with granite countertops" into:
    - "brown house exterior"
    - "granite countertops kitchen"

    Then score each independently.

    Args:
        query: Original query text
        must_have_tags: Extracted features

    Returns:
        Feature-specific scores
    """
    feature_queries = []

    for tag in must_have_tags:
        # Contextualize feature
        if tag in EXTERIOR_TAGS:
            feature_query = f"{tag} house exterior"
        elif tag in INTERIOR_TAGS:
            feature_query = f"{tag} interior detail"
        else:
            feature_query = tag

        feature_queries.append({
            "tag": tag,
            "query": feature_query,
            "embedding": embed_text_multimodal(feature_query)
        })

    return feature_queries

def score_property_per_feature(image_vectors, feature_queries):
    """
    Score property separately for each feature.

    Returns:
        {feature: best_image_score}
    """
    scores = {}

    for fq in feature_queries:
        # Find best image for this specific feature
        best_score = 0
        for img in image_vectors:
            sim = cosine_similarity(fq["embedding"], img["vector"])
            if sim > best_score:
                best_score = sim

        scores[fq["tag"]] = best_score

    return scores
```

**Example:**
```
Query: "brown house with granite countertops"
Decompose to:
  1. "brown house exterior" → best match: Image #0 (exterior) = 0.82
  2. "granite countertops kitchen" → best match: Image #2 (kitchen) = 0.78

Combined score: (0.82 + 0.78) / 2 = 0.80

vs. Single query embedding:
  "brown house with granite countertops" → best match: 0.74 (kitchen only)
```

**Latency:**
- Text embeddings: ~100ms × N features
- Similarity calculations: ~1ms × N features × M images
- **Total:** ~200ms for 2 features, ~300ms for 3 features

**Cost:**
- $0.0002 per text embedding × N features
- **Total:** ~$0.0004 per search (2 features)

**Accuracy:** Very high - each feature matched independently
**Implementation complexity:** Medium

**Recommended:** This addresses the multi-feature query problem directly!

---

## 6. Hybrid Approach: Combining Multiple Techniques

### Recommended Implementation Strategy

**Phase 1: Low-Hanging Fruit (Immediate - No reindexing needed)**

1. **Image Type Category Weighting** (Technique 1.2)
   - Use existing `image_type` field
   - Implementation: 30 minutes
   - Latency: +5ms
   - Cost: $0
   - Expected improvement: 15-25%

2. **Position-Based Weighting** (Technique 1.1)
   - Enhance existing first-image boost
   - Implementation: 20 minutes
   - Latency: +5ms
   - Cost: $0
   - Expected improvement: 10-15%

3. **Semantic Tag Grouping** (Technique 3.2)
   - Extend existing VISUAL_DOMINANT_FEATURES
   - Implementation: 15 minutes
   - Latency: +1ms
   - Cost: $0
   - Expected improvement: 5-10%

**Combined Phase 1 Improvement:** 30-50% better feature identification
**Total Latency:** +11ms (negligible)
**Total Cost:** $0
**Implementation Time:** ~1 hour

---

**Phase 2: Medium Effort (Week 2 - Requires code refactoring)**

4. **Per-Feature Query Decomposition** (Technique 5.1)
   - Split multi-feature queries
   - Implementation: 3-4 hours
   - Latency: +200-300ms
   - Cost: ~$0.0004 per search
   - Expected improvement: 40-60% for multi-feature queries

5. **Zero-Shot Prominence Classification** (Technique 2.2)
   - Use embedding comparisons
   - Implementation: 2 hours
   - Latency: +240ms
   - Cost: ~$0.000004 per property
   - Expected improvement: 20-30%

**Combined Phase 2 Improvement:** 60-90% better for complex queries
**Total Added Latency:** +440-540ms
**Total Cost:** ~$0.0004 per search
**Implementation Time:** ~6 hours

---

**Phase 3: Advanced (Future - If needed)**

6. **Vision API Reranking** (Technique 2.1)
   - Only for top-10 results
   - Implementation: 4-6 hours
   - Latency: +300-500ms
   - Cost: ~$0.000025 per search
   - Expected improvement: 20-40% for top-10 quality

**Trade-off:** Significant latency increase, but highest accuracy

---

## Comparison Matrix

| Technique | Latency | Cost/Search | Accuracy | Complexity | Reindex? |
|-----------|---------|-------------|----------|------------|----------|
| Position weighting | +5ms | $0 | Medium | Low | No |
| Category weighting | +5ms | $0 | High | Low | No |
| Tag frequency | +5ms | $0 | Medium | Low | No* |
| Semantic grouping | +1ms | $0 | High | Very Low | No |
| Zero-shot classification | +240ms | $0.000004 | Medium | Low | No |
| Feature decomposition | +300ms | $0.0004 | Very High | Medium | No |
| Vision reranking | +400ms | $0.000025 | Very High | Medium | No |

*Requires per-image tags (not currently stored separately)

---

## Recommended Implementation Plan

### Immediate (This week):
```python
# search.py - Add to calculate_top_k_image_score()

def calculate_enhanced_image_score(image_vectors, query_vec, query_context, k):
    """
    Enhanced scoring with category and position weighting.

    NO REINDEXING NEEDED - uses existing data!
    """
    weighted_scores = []

    # Category weights based on query type
    category_weights = get_category_weights(query_context)

    for idx, img in enumerate(image_vectors):
        # Base similarity score
        similarity = cosine_similarity(query_vec, img["vector"])

        # Category weight (uses existing image_type field)
        img_type = img.get("image_type", "unknown")
        category_weight = category_weights.get(img_type, 0.5)

        # Position weight (first images more important)
        position_weight = 0.5 ** idx  # Exponential decay

        # Combined weight
        final_weight = category_weight * position_weight
        weighted_score = similarity * final_weight

        weighted_scores.append((weighted_score, similarity, idx))

    # Sort by weighted score, sum top K
    weighted_scores.sort(reverse=True, key=lambda x: x[0])
    return sum(w[0] for w in weighted_scores[:k])
```

**Expected Results:**
- "brown house" query: Exterior photos weighted 2x higher → brown exterior ranks higher
- "white kitchen" query: Kitchen photos weighted 2x higher → kitchen features prioritized
- "modern home with pool" query: Exterior photos dominate → correct primary features identified

---

### Medium-term (Next sprint):

Implement per-feature decomposition for multi-feature queries:

```python
# search.py - Add to handler()

if len(must_tags) >= 2:
    # Multi-feature query: Use decomposition
    feature_scores = []

    for tag in must_tags:
        # Generate feature-specific embedding
        feature_query = contextualize_feature(tag)  # "brown exterior", "granite kitchen"
        feature_vec = embed_text_multimodal(feature_query)

        # Find best image for this feature
        best_score = max(
            cosine_similarity(feature_vec, img["vector"])
            for img in property["image_vectors"]
        )
        feature_scores.append(best_score)

    # Average of feature-specific scores
    multi_feature_score = sum(feature_scores) / len(feature_scores)
else:
    # Single-feature: Use existing top-k scoring
    multi_feature_score = calculate_enhanced_image_score(...)
```

---

## Testing Strategy

### Test Queries:
1. **"brown house"** - Should prioritize exterior brown over interior brown details
2. **"white house with granite countertops"** - Should find properties with BOTH features
3. **"modern kitchen"** - Should prioritize kitchen photos over exterior
4. **"brick colonial with pool"** - Multi-feature exterior query

### Success Metrics:
- **Feature precision:** % of top-10 results that actually have primary feature as described
- **Multi-feature recall:** % of properties with ALL features that appear in top-20
- **User preference:** A/B test with real users (current vs enhanced)

### A/B Test Setup:
```python
# 50% traffic to enhanced scoring, 50% to current
if random.random() < 0.5:
    scoring_mode = "enhanced"  # Phase 1 techniques
else:
    scoring_mode = "current"   # Existing max scoring
```

---

## Cost Analysis

### Phase 1 (Immediate - Category + Position weighting):
- **Development:** 1 hour
- **Latency:** +11ms
- **Cost:** $0/search
- **Improvement:** 30-50%

### Phase 2 (Feature decomposition):
- **Development:** 6 hours
- **Latency:** +440ms (acceptable for complex queries)
- **Cost:** $0.0004/search = **$0.40 per 1000 searches**
- **Improvement:** 60-90% for multi-feature queries

### Phase 3 (Vision reranking - optional):
- **Development:** 6 hours
- **Latency:** +400ms
- **Cost:** $0.000025/search = **$0.025 per 1000 searches**
- **Improvement:** 20-40% for top-10 quality

**Total Cost at 10,000 searches/month:**
- Phase 1: $0
- Phase 2: $4/month
- Phase 3: $0.25/month
- **Total: $4.25/month** (negligible)

---

## Open Questions / Action Items

1. ✅ **Check if `image_type` is populated** - Need to verify schema
2. ✅ **Review confidence scores** - Check if stored per-tag or per-image
3. ⚠️ **Per-image tag arrays** - Currently only flat combined array, need to verify if individual image tags are available
4. 🔍 **Benchmark position decay factor** - Test decay=0.5 vs decay=0.7 for optimal weighting
5. 📊 **Collect baseline metrics** - Run test queries to establish current accuracy before changes

---

## Conclusion

**Best approach for immediate improvement without reindexing:**

1. **Start with Phase 1** (Category + Position weighting)
   - Zero cost, minimal latency
   - Uses existing data (image_type, position)
   - Expected 30-50% improvement
   - Can implement today in ~1 hour

2. **Add Phase 2 if needed** (Feature decomposition)
   - Handles multi-feature queries correctly
   - Modest cost increase ($4/month @ 10K searches)
   - Acceptable latency for complex queries
   - Addresses root cause of "white house + granite" problem

3. **Consider Phase 3 only if** top-10 quality is critical
   - Highest accuracy but most latency
   - Useful for final reranking only
   - Negligible cost increase

**Recommendation:** Implement Phase 1 immediately, measure improvement, then decide on Phase 2 based on results.
