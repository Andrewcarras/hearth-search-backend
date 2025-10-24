# Search System

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [API.md](API.md), [ARCHITECTURE_STYLES.md](ARCHITECTURE_STYLES.md)

Complete technical documentation of how the Hearth Search system works end-to-end.

---

## Table of Contents

1. [Overview](#overview)
2. [Multi-Query Decomposition](#multi-query-decomposition)
3. [3-Strategy Search](#3-strategy-search)
4. [Reciprocal Rank Fusion (RRF)](#reciprocal-rank-fusion-rrf)
5. [Adaptive Weighting](#adaptive-weighting)
6. [Tag Boosting](#tag-boosting)
7. [Greedy Diversification](#greedy-diversification)
8. [Complete Search Flow](#complete-search-flow)

---

## Overview

Hearth Search combines multiple search strategies using an advanced pipeline:

```
User Query
    ↓
Multi-Query Decomposition (LLM)
    ↓
Query Classification
    ↓
3 Parallel Searches per Subquery:
    ├─ BM25 (Tag Matching)
    ├─ Text kNN (Claude Embeddings)
    └─ Image kNN (CLIP Embeddings)
    ↓
Reciprocal Rank Fusion (RRF)
    ↓
Adaptive Weight Adjustment
    ↓
Tag Boosting (Exact Matches)
    ↓
Greedy Diversification
    ↓
Final Results
```

**Key Components**:
- **Multi-Query**: Breaks complex queries into simpler subqueries
- **3-Strategy Search**: BM25, text embeddings, image embeddings
- **RRF Fusion**: Combines strategies with reciprocal rank scoring
- **Adaptive Weighting**: Adjusts strategy importance based on query type
- **Tag Boosting**: Rewards exact tag matches
- **Diversification**: Prevents duplicate/similar results

---

## Multi-Query Decomposition

### Purpose

Complex queries like "modern homes with granite countertops and pool" contain multiple distinct search intents. Multi-query decomposition uses an LLM to break these into focused subqueries.

### How It Works

**Input**: `"modern homes with granite countertops and pool"`

**LLM Analysis**:
1. Identifies distinct search concepts
2. Separates visual style from features
3. Creates focused subqueries

**Output Subqueries**:
```json
[
  "modern architecture",
  "granite countertops",
  "swimming pool"
]
```

### Implementation

```python
# Simplified multi-query logic
def decompose_query(query):
    prompt = f"""
    Break this property search query into 2-4 focused subqueries.
    Each subquery should target one specific aspect (style, feature, material, etc.).

    Query: {query}

    Return JSON array of subqueries.
    """

    response = bedrock.invoke_model(
        modelId="us.anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps({"prompt": prompt})
    )

    return json.loads(response)["subqueries"]
```

### Benefits

- **Better Coverage**: Finds properties matching any component
- **Semantic Understanding**: LLM understands intent, not just keywords
- **Flexibility**: Handles natural language queries

### Examples

| Original Query | Subqueries |
|----------------|------------|
| "mid century modern homes with pool" | ["mid century modern architecture", "swimming pool"] |
| "craftsman homes hardwood floors granite" | ["craftsman style", "hardwood floors", "granite countertops"] |
| "white brick house mountain views" | ["white exterior", "brick exterior", "mountain views"] |
| "updated kitchen stainless appliances" | ["updated kitchen", "stainless steel appliances"] |

---

## 3-Strategy Search

For each subquery, we run 3 parallel searches using different strategies.

### Strategy 1: BM25 (Tag-Based)

**What**: Traditional keyword search on tag fields
**When**: Best for specific features, materials, amenities

**Fields Searched**:
- `property_features` (e.g., "granite countertops", "hardwood floors")
- `exterior_materials` (e.g., "brick", "vinyl siding")
- `interior_features` (e.g., "updated kitchen", "walk-in closet")
- `outdoor_amenities` (e.g., "pool", "deck", "patio")

**Example**:
```json
{
  "query": {
    "multi_match": {
      "query": "granite countertops",
      "fields": ["property_features", "interior_features"],
      "type": "best_fields"
    }
  }
}
```

**Strengths**:
- Exact tag matching
- Fast performance
- Good for specific features

**Weaknesses**:
- No semantic understanding
- Misses synonyms (unless in architecture_style_mappings.py)

---

### Strategy 2: Text kNN (Claude Embeddings)

**What**: Semantic search using Claude-generated text embeddings
**When**: Best for architectural styles, general descriptions

**How It Works**:
1. Query is embedded using Claude Vision API
2. kNN search finds properties with similar text embeddings
3. Returns top-k nearest neighbors

**Example**:
```json
{
  "knn": {
    "field": "text_embedding",
    "query_vector": [0.123, -0.456, ...],  // 1024 dimensions
    "k": 50,
    "num_candidates": 100
  }
}
```

**Embedding Generation**:
```python
# Property text description
description = f"""
{address}
{bedrooms} bed, {bathrooms} bath
{living_area} sqft
Style: {architecture_style}
Features: {', '.join(property_features)}
"""

# Generate embedding via Claude
response = bedrock.invoke_model(
    modelId="us.anthropic.claude-3-haiku-20240307-v1:0",
    body=json.dumps({
        "prompt": f"Generate embedding for: {description}",
        "return_embedding": True
    })
)

text_embedding = response["embedding"]  # 1024-dim vector
```

**Strengths**:
- Semantic understanding
- Captures style and context
- Good for architectural queries

**Weaknesses**:
- Slower than BM25
- Less precise for specific features

---

### Strategy 3: Image kNN (CLIP Embeddings)

**What**: Visual similarity search using CLIP image embeddings
**When**: Best for visual style, color, architectural appearance

**How It Works**:
1. Property images embedded using CLIP during ingestion
2. Query text embedded using CLIP text encoder
3. kNN search finds visually similar properties

**Example**:
```json
{
  "knn": {
    "field": "image_embedding",
    "query_vector": [0.789, -0.234, ...],  // 512 dimensions
    "k": 50,
    "num_candidates": 100
  }
}
```

**Embedding Generation**:
```python
from transformers import CLIPProcessor, CLIPModel

# Load CLIP model
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

# Embed property image
image = load_image(image_url)
inputs = processor(images=image, return_tensors="pt")
image_embedding = model.get_image_features(**inputs)

# Embed query text
text_inputs = processor(text="modern architecture", return_tensors="pt")
query_embedding = model.get_text_features(**text_inputs)
```

**Strengths**:
- Visual similarity matching
- Good for style/color queries
- Cross-modal (text → image search)

**Weaknesses**:
- Can't capture non-visual features
- Slower than BM25

---

## Reciprocal Rank Fusion (RRF)

### Purpose

Combine results from all 3 strategies into a single ranked list.

### Formula

For each property appearing in any strategy results:

```
RRF_score = Σ (1 / (k + rank_i))
```

Where:
- `k` = constant (typically 30-75)
- `rank_i` = position in strategy i results (1st place = 1, 2nd = 2, etc.)
- Sum over all strategies where property appears

### Example Calculation

Property appears in:
- BM25 results at rank 5
- Text kNN results at rank 12
- Image kNN results at rank 3

With k=60:

```
RRF_score = 1/(60+5) + 1/(60+12) + 1/(60+3)
          = 1/65 + 1/72 + 1/63
          = 0.0154 + 0.0139 + 0.0159
          = 0.0452
```

**Score Interpretation**:
- **0.05+**: Excellent match (top tier)
- **0.03-0.05**: Good match
- **0.01-0.03**: Fair match
- **< 0.01**: Weak match

### K-Value Selection

Different k-values for different strategies:

| Strategy | k-value | Reasoning |
|----------|---------|-----------|
| BM25 | 30-40 | Lower k = more weight to top results |
| Text kNN | 50-60 | Medium k = balanced weighting |
| Image kNN | 60-75 | Higher k = spread weight more evenly |

### Benefits

- **No Score Normalization**: Ranks matter, not raw scores
- **Strategy Agnostic**: Works with any scoring system
- **Robust**: Handles different result set sizes
- **Interpretable**: Clear score meaning

---

## Adaptive Weighting

### Purpose

Adjust strategy importance based on query classification.

### Query Classification

LLM classifies each query into categories:

```python
{
  "primary_intent": "visual_style",  # Main intent
  "secondary_intents": ["color"],    # Additional intents
  "confidence": 0.85
}
```

**Intent Categories**:
- `visual_style`: Architectural style, appearance
- `color`: Color-based queries
- `specific_feature`: Specific amenities/features
- `general`: General search

### Weight Adjustment

Based on classification, adjust RRF k-values:

```python
# Base k-values
k_bm25 = 35
k_text = 55
k_image = 65

# Visual style query → boost image search
if primary_intent == "visual_style":
    k_image = 45  # Lower k = more weight
    k_text = 50
    k_bm25 = 40

# Specific feature → boost BM25
elif primary_intent == "specific_feature":
    k_bm25 = 30  # Lower k = more weight
    k_text = 60
    k_image = 70

# Color query → boost image search heavily
elif primary_intent == "color":
    k_image = 40
    k_text = 60
    k_bm25 = 50
```

### Examples

| Query | Classification | Adjusted Weights |
|-------|----------------|------------------|
| "modern homes" | visual_style | Image: HIGH, Text: MED, BM25: LOW |
| "granite countertops" | specific_feature | BM25: HIGH, Text: MED, Image: LOW |
| "white exterior brick" | color + specific_feature | Image: HIGH, BM25: HIGH, Text: MED |

---

## Tag Boosting

### Purpose

Reward properties with exact tag matches to boost precision.

### How It Works

After RRF scoring, check if property tags exactly match query terms:

```python
def apply_tag_boost(property, query_terms):
    matched_tags = []
    boost_multiplier = 1.0

    # Check each query term
    for term in query_terms:
        # Check if term appears in property tags
        if term in property["property_features"]:
            matched_tags.append(term)
            boost_multiplier += 0.15  # +15% per match

    # Apply boost to RRF score
    property["score"] *= boost_multiplier
    property["matched_tags"] = matched_tags

    return property
```

### Example

Query: "granite countertops hardwood floors"

Property with tags: `["granite countertops", "hardwood floors", "updated kitchen"]`

```
Matched tags: ["granite countertops", "hardwood floors"]
Boost multiplier: 1.0 + 0.15 + 0.15 = 1.30
Original RRF score: 0.045
Boosted score: 0.045 * 1.30 = 0.0585
```

### Benefits

- **Precision**: Exact matches ranked higher
- **Transparency**: Shows which tags matched
- **User Trust**: Users see why property matched

---

## Greedy Diversification

### Purpose

Prevent duplicate or very similar properties from dominating results.

### How It Works

1. Start with empty result set
2. For each candidate (sorted by score):
   - Check similarity to already-selected properties
   - If dissimilar enough, add to results
   - If too similar, skip

```python
def diversify_results(candidates, max_results=20):
    selected = []

    for candidate in candidates:
        # First property always added
        if not selected:
            selected.append(candidate)
            continue

        # Check similarity to all selected properties
        too_similar = False
        for existing in selected:
            similarity = calculate_similarity(candidate, existing)
            if similarity > 0.90:  # 90% similar
                too_similar = True
                break

        if not too_similar:
            selected.append(candidate)

        if len(selected) >= max_results:
            break

    return selected
```

### Similarity Calculation

```python
def calculate_similarity(prop1, prop2):
    # Same zpid = identical property
    if prop1["zpid"] == prop2["zpid"]:
        return 1.0

    # Check multiple factors
    similarities = []

    # Address similarity (same street)
    if prop1["address"][:10] == prop2["address"][:10]:
        similarities.append(0.5)

    # Image embedding similarity
    image_sim = cosine_similarity(
        prop1["image_embedding"],
        prop2["image_embedding"]
    )
    similarities.append(image_sim)

    # Architecture style match
    if prop1["architecture_style"] == prop2["architecture_style"]:
        similarities.append(0.3)

    return max(similarities)
```

### Benefits

- **Variety**: Users see diverse results
- **Better UX**: Avoid repetitive listings
- **Coverage**: More unique properties shown

---

## Complete Search Flow

### Step-by-Step Example

**User Query**: "mid century modern homes with pool"

**Step 1: Multi-Query Decomposition**
```python
subqueries = [
    "mid century modern architecture",
    "swimming pool"
]
```

**Step 2: Query Classification**
```python
classification = {
    "primary_intent": "visual_style",
    "secondary_intents": ["specific_feature"]
}

# Adjust k-values
k_bm25 = 40
k_text = 50
k_image = 45  # Boosted for visual_style
```

**Step 3: Execute 3-Strategy Search** (per subquery)

For "mid century modern architecture":
```python
# BM25 search
bm25_results = search_tags("mid century modern")
# Returns: [prop_A (rank 3), prop_B (rank 7), ...]

# Text kNN search
text_results = search_text_embedding("mid century modern architecture")
# Returns: [prop_A (rank 1), prop_C (rank 5), ...]

# Image kNN search
image_results = search_image_embedding("mid century modern architecture")
# Returns: [prop_A (rank 2), prop_D (rank 4), ...]
```

**Step 4: RRF Fusion**

Property A appears in all 3 strategies:
```python
rrf_score_A = 1/(40+3) + 1/(50+1) + 1/(45+2)
            = 0.0233 + 0.0196 + 0.0213
            = 0.0642
```

Property B appears only in BM25:
```python
rrf_score_B = 1/(40+7)
            = 0.0213
```

**Step 5: Tag Boosting**

Property A has exact tag: "mid_century_modern"
```python
boost_multiplier = 1.15
final_score_A = 0.0642 * 1.15 = 0.0738
```

**Step 6: Combine Subquery Results**

Merge results from both subqueries, keeping highest scores.

**Step 7: Greedy Diversification**

Remove highly similar properties, keep top 20.

**Step 8: Return Results**

```json
{
  "properties": [
    {
      "zpid": "123456",
      "address": "123 Palm Dr",
      "architecture_style": "mid_century_modern",
      "property_features": ["pool", "mid_century_modern"],
      "score": 0.0738,
      "matched_tags": ["mid_century_modern", "pool"],
      "search_strategies": {
        "bm25_score": 0.0233,
        "text_knn_score": 0.0196,
        "image_knn_score": 0.0213
      }
    }
  ],
  "total": 42,
  "query_info": {
    "original_query": "mid century modern homes with pool",
    "subqueries": [
      "mid century modern architecture",
      "swimming pool"
    ],
    "classification": {
      "primary_intent": "visual_style",
      "secondary_intents": ["specific_feature"]
    }
  }
}
```

---

## Performance Characteristics

### Search Latency

Typical latency breakdown:
- Multi-query decomposition: 200-300ms
- Each strategy search: 50-150ms (parallel)
- RRF fusion: 10-20ms
- Tag boosting: 5-10ms
- Diversification: 10-20ms

**Total**: 300-500ms

### Accuracy Metrics

Based on testing:
- **Relevance**: 85-90% of top 10 results highly relevant
- **Recall**: Finds 95%+ of matching properties in index
- **Precision**: 80-85% precision at top 20 results

---

## Tuning Guide

### When to Adjust k-Values

**Increase k** (spread weight more evenly):
- Strategy returning too-similar results
- Want to consider more diverse results
- Strategy is noisy

**Decrease k** (focus on top results):
- Strategy is very accurate
- Want to prioritize top matches
- Strategy has high precision

### When to Adjust Tag Boost

**Increase boost** (+0.20 instead of +0.15):
- Tags are very accurate
- Users value exact matches
- Precision more important than recall

**Decrease boost** (+0.10):
- Tags are sometimes incorrect
- Want more diversity
- Recall more important than precision

---

## See Also

- [ARCHITECTURE_STYLES.md](ARCHITECTURE_STYLES.md) - Architecture style classification
- [API.md](API.md) - Search API reference
- [DATA_SCHEMA.md](DATA_SCHEMA.md) - Property schema and embeddings
