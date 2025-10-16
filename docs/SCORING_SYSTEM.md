# Hearth Search Scoring System - Complete Technical Documentation

**Last Updated:** 2025-10-15
**Version:** 2.0 (Multi-Vector with Adaptive Scoring)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Scoring Pipeline Overview](#scoring-pipeline-overview)
3. [Phase 1: Query Analysis](#phase-1-query-analysis)
4. [Phase 2: Parallel Search Execution](#phase-2-parallel-search-execution)
5. [Phase 3: Reciprocal Rank Fusion (RRF)](#phase-3-reciprocal-rank-fusion-rrf)
6. [Phase 4: Adaptive Weight Calculation](#phase-4-adaptive-weight-calculation)
7. [Phase 5: Tag Boosting](#phase-5-tag-boosting)
8. [Complete Scoring Examples](#complete-scoring-examples)
9. [Mathematical Formulas](#mathematical-formulas)
10. [Performance Characteristics](#performance-characteristics)
11. [Appendix: Score Breakdown API](#appendix-score-breakdown-api)

---

## Executive Summary

Hearth's scoring system combines **four independent ranking signals** into a single relevance score through a sophisticated fusion algorithm. The system automatically adapts its weighting strategy based on query characteristics to maximize accuracy for different search types.

### Key Innovation: Adaptive Weighting

Unlike traditional hybrid search systems that use fixed weights, Hearth dynamically adjusts the importance of each signal based on what the user is searching for:

- **Color queries** (e.g., "white house"): BM25 text search gets 4x more weight than images
- **Material queries** (e.g., "granite countertops"): BM25 and text embeddings boosted, images reduced
- **Visual style queries** (e.g., "modern architecture"): Image similarity gets 3x more weight
- **Feature queries** (e.g., "pool"): Balanced weights across all signals

### The Four Ranking Signals

| Signal | What It Measures | When It's Best |
|--------|------------------|----------------|
| **BM25 Text Search** | Keyword matching in descriptions + AI-generated image captions | Exact features, colors, materials |
| **kNN Text Embeddings** | Semantic similarity in property descriptions | Related concepts, synonyms, styles |
| **kNN Image Embeddings** | Visual similarity across property photos (multi-vector) | Architectural style, visual characteristics |
| **Tag Matching** | Exact feature matches from AI vision analysis | Required features, post-fusion boosting |

---

## Scoring Pipeline Overview

```
User Query: "modern white house with granite countertops"
    |
    v
[1. QUERY ANALYSIS]
    - LLM extracts: must_have=["white exterior", "granite countertops"]
    - Detects query_type="color" (triggers adaptive scoring)
    - Extracts hard filters: {} (none)
    - Generates query embedding: [0.023, -0.041, ...]
    |
    v
[2. PARALLEL SEARCH] (3 simultaneous queries)
    |
    +---> BM25 Search (keyword matching)
    |     Returns: 150 hits with scores [12.5, 11.8, 10.2, ...]
    |
    +---> kNN Text Search (semantic similarity)
    |     Returns: 150 hits with scores [0.89, 0.86, 0.82, ...]
    |
    +---> kNN Image Search (visual similarity, multi-vector)
          Returns: 150 hits with scores [0.76, 0.71, 0.68, ...]
    |
    v
[3. RECIPROCAL RANK FUSION]
    - Combines 3 result lists using rank-based scoring
    - Adaptive k-values based on query_type:
      * BM25: k=30 (higher weight for color query)
      * Text kNN: k=60 (standard weight)
      * Image kNN: k=120 (reduced weight for color query)
    - Formula: score = Σ(1/(k + rank))
    - Produces unified ranking: 150 results
    |
    v
[4. TAG BOOSTING]
    - Check each result for must_have tags
    - Apply multiplicative boost:
      * 100% match (2/2 tags): 2.0x boost
      * 75% match (3/4 tags): 1.5x boost
      * 50% match (2/4 tags): 1.25x boost
      * <50% match: no boost
    |
    v
[5. FINAL RANKING]
    - Sort by boosted scores
    - Return top 15 results
```

---

## Phase 1: Query Analysis

### 1.1 Natural Language Parsing

The system uses **Claude 3.5 Sonnet via Bedrock** to parse natural language queries into structured constraints. This happens BEFORE any search execution.

**LLM Prompt Structure:**
```
Parse this property search query into structured constraints:
"{user_query}"

Extract:
1. must_have: Required features (pool, garage, granite, etc.)
2. nice_to_have: Preferred but not required features
3. hard_filters: Numeric constraints (price, beds, baths)
4. architecture_style: Architectural preference (modern, craftsman, etc.)
5. proximity: Location requirements (near school, grocery, etc.)
6. query_type: Classification for adaptive scoring

Query Type Classification:
- "color": White, gray, blue, beige exterior/interior
- "material": Brick, stone, granite, marble, hardwood
- "visual_style": Architecture style, views, design characteristics
- "specific_feature": Pool, garage, fireplace, patio
- "room_type": Kitchen, bathroom, bedroom, living room
- "general": Vague or broad queries

Return JSON only.
```

### 1.2 Query Analysis Examples

#### Example 1: Color + Material Query
```json
Input: "white brick house with granite countertops under $500k"

Output: {
  "must_have": ["white_exterior", "brick_exterior", "granite_countertops"],
  "nice_to_have": [],
  "hard_filters": {
    "price_max": 500000
  },
  "architecture_style": null,
  "proximity": null,
  "query_type": "color"  ← TRIGGERS ADAPTIVE SCORING
}
```

**Why query_type="color"?**
- Query contains explicit color keyword ("white")
- Color is the primary search intent
- This will boost BM25 text search and de-boost image search

#### Example 2: Visual Style Query
```json
Input: "modern home with open floor plan and mountain views"

Output: {
  "must_have": ["open_floor_plan", "mountain_views"],
  "nice_to_have": [],
  "hard_filters": {},
  "architecture_style": "modern",
  "proximity": null,
  "query_type": "visual_style"  ← DIFFERENT ADAPTIVE STRATEGY
}
```

**Why query_type="visual_style"?**
- Query focuses on architectural style and visual characteristics
- This will boost image similarity and text embeddings
- BM25 remains standard weight

#### Example 3: Specific Feature Query
```json
Input: "3 bedroom house with pool and 2-car garage"

Output: {
  "must_have": ["pool", "2_car_garage"],
  "nice_to_have": [],
  "hard_filters": {
    "beds_min": 3
  },
  "architecture_style": null,
  "proximity": null,
  "query_type": "specific_feature"  ← BALANCED SCORING
}
```

**Why query_type="specific_feature"?**
- Query focuses on concrete amenities
- All search strategies work well for features
- Uses balanced weights across all signals

### 1.3 Query Embedding Generation

After parsing, the system generates a **1024-dimensional query embedding** using Amazon Titan Text Embeddings v2:

```python
query = "modern white house with granite countertops"
query_vector = embed_text(query)
# Returns: [0.023, -0.041, 0.115, -0.089, ..., 0.201]  (1024 floats)
```

This vector captures the semantic meaning of the entire query and will be used for kNN similarity searches.

**Cost:** $0.0001 per query

---

## Phase 2: Parallel Search Execution

The system executes **three independent searches simultaneously** against the OpenSearch index. Each search produces its own ranked list of results.

### 2.1 BM25 Text Search

**What it does:** Traditional keyword search with field-level boosting

**OpenSearch Query:**
```json
{
  "query": {
    "bool": {
      "filter": [
        {"range": {"price": {"gt": 0}}},
        {"term": {"has_valid_embeddings": true}}
      ],
      "should": [
        {
          "multi_match": {
            "query": "modern white house with granite countertops",
            "fields": [
              "description^3",              // Zillow's original description
              "visual_features_text^2.5",   // AI-generated image captions
              "llm_profile^2",              // Deprecated (always empty)
              "address^0.5",
              "city^0.3",
              "state^0.2"
            ],
            "type": "best_fields"
          }
        },
        {
          "terms": {
            "feature_tags": ["white_exterior", "white exterior", "granite_countertops", "granite countertops"]
          }
        },
        {
          "terms": {
            "image_tags": ["white_exterior", "white exterior", "granite_countertops", "granite countertops"]
          }
        }
      ],
      "minimum_should_match": 1
    }
  },
  "size": 150
}
```

**How BM25 Scoring Works:**

BM25 (Best Match 25) is a probabilistic ranking function based on term frequency and document length. The score for a document is calculated as:

```
BM25(D, Q) = Σ IDF(qi) × (f(qi, D) × (k1 + 1)) / (f(qi, D) + k1 × (1 - b + b × |D|/avgDL))

Where:
- D = document (listing)
- Q = query terms
- qi = individual query term
- f(qi, D) = frequency of qi in document D
- |D| = length of document D in words
- avgDL = average document length across corpus
- k1 = term frequency saturation (OpenSearch default: 1.2)
- b = document length normalization (OpenSearch default: 0.75)
- IDF(qi) = log((N - df(qi) + 0.5) / (df(qi) + 0.5))
  - N = total number of documents
  - df(qi) = number of documents containing qi
```

**Field Boosting Multipliers:**

The final BM25 score is multiplied by field-specific boost factors:
- `description^3`: Standard Zillow description gets 3x weight
- `visual_features_text^2.5`: AI-generated captions get 2.5x weight
- `address^0.5`: Address gets 0.5x weight (low priority)

**Example BM25 Scores:**

For query "granite countertops":
- Listing with "granite countertops" in description 3 times: **12.5**
- Listing with "granite" once in description: **6.8**
- Listing with "countertops" in image caption: **5.2**
- Listing with neither term: **0.0** (not returned)

**Typical BM25 Score Range:** 0.0 - 25.0 (higher = better match)

### 2.2 kNN Text Embeddings Search

**What it does:** Finds semantically similar listings based on description embeddings

**How it works:**
1. Each listing's description was embedded during indexing: `description → [0.1, 0.3, ...]`
2. Query was embedded: `query → [0.023, -0.041, ...]`
3. OpenSearch uses HNSW (Hierarchical Navigable Small World) algorithm to find nearest neighbors
4. Similarity metric: **Cosine similarity** (measures angle between vectors)

**OpenSearch Query:**
```json
{
  "size": 150,
  "query": {
    "bool": {
      "must": [
        {
          "knn": {
            "vector_text": {
              "vector": [0.023, -0.041, 0.115, ..., 0.201],  // 1024 floats
              "k": 300  // Search 300 candidates before filtering
            }
          }
        }
      ],
      "filter": [
        {"range": {"price": {"gt": 0}}},
        {"term": {"has_valid_embeddings": true}}
      ]
    }
  }
}
```

**Cosine Similarity Formula:**

```
cosine_similarity(A, B) = (A · B) / (||A|| × ||B||)

Where:
- A · B = dot product = Σ(Ai × Bi)
- ||A|| = magnitude of A = sqrt(Σ(Ai²))
- ||B|| = magnitude of B = sqrt(Σ(Bi²))
```

**Similarity Score Range:** -1.0 to 1.0
- 1.0 = identical vectors (perfect match)
- 0.0 = orthogonal vectors (no similarity)
- -1.0 = opposite vectors (very rare in practice)

**OpenSearch returns similarity as score:** 0.0 to 1.0 (negative similarities are rare)

**Example kNN Text Scores:**

For query "modern home with open floor plan":
- Listing: "Contemporary house with spacious open-concept living": **0.89** (high semantic similarity)
- Listing: "Updated property with flowing layout": **0.82** (moderate similarity via synonyms)
- Listing: "Traditional Victorian with formal dining": **0.45** (low similarity, different style)
- Listing: "Vacant lot ready to build": **0.23** (very low similarity)

**Why kNN Text Works:**
- Captures synonyms: "modern" ≈ "contemporary" ≈ "updated"
- Understands context: "open floor plan" ≈ "open-concept" ≈ "flowing layout"
- Ignores exact word matching: focuses on meaning

**Typical kNN Text Score Range:** 0.50 - 0.95 (for relevant results)

### 2.3 kNN Image Embeddings Search (Multi-Vector)

**What it does:** Finds visually similar properties by comparing property photos

**Key Innovation: Multi-Vector Schema**

Traditional approach (listings index):
- Average all image vectors into single vector
- Problem: Rare features get diluted by common features

Multi-vector approach (listings-v2 index):
- Store EVERY image vector separately in nested array
- Search ALL image vectors per listing
- Return listing if ANY image matches well (score_mode: "max")

**Example: Why Multi-Vector Matters**

Property has 20 images:
- 1 pool photo
- 1 granite countertop closeup
- 18 generic room photos

**Old System (Average Vector):**
```
pool_vector = [0.8, 0.9, 0.7, ...]
generic_vectors = [0.1, 0.2, 0.15, ...]  (18 of these)

averaged_vector = (pool_vector + 18×generic_vectors) / 19
                = [0.14, 0.20, 0.18, ...]  ← Pool signal LOST!

Query "house with pool" similarity: 0.23 (POOR - pool not detected)
```

**New System (Multi-Vector):**
```
image_vectors = [
  {"url": "...", "vector": [0.8, 0.9, 0.7, ...]},     ← Pool photo
  {"url": "...", "vector": [0.1, 0.2, 0.15, ...]},    ← Generic rooms
  {"url": "...", "vector": [0.1, 0.19, 0.14, ...]},   ← More generics...
  ...
]

Query "house with pool":
- Compare query to pool_vector: similarity = 0.91 (EXCELLENT!)
- Compare query to generic_vectors: similarity = 0.15-0.25 (low)
- Use score_mode="max": listing gets score = 0.91 ← BEST image wins!
```

**Result:** Properties with specific features rank properly even with many generic photos.

**OpenSearch Query (Multi-Vector):**
```json
{
  "size": 150,
  "query": {
    "bool": {
      "must": [
        {
          "nested": {
            "path": "image_vectors",
            "score_mode": "max",  // Use BEST matching image score
            "query": {
              "knn": {
                "image_vectors.vector": {
                  "vector": [0.023, -0.041, ..., 0.201],
                  "k": 300
                }
              }
            },
            "inner_hits": {
              "size": 100,     // Return up to 100 matching images
              "_source": true  // Include image metadata
            }
          }
        }
      ],
      "filter": [
        {"range": {"price": {"gt": 0}}},
        {"term": {"has_valid_embeddings": true}}
      ]
    }
  }
}
```

**Example kNN Image Scores:**

For query "modern kitchen with white cabinets":
- Listing with 1 matching modern white kitchen photo (among 15 total): **0.88** (high - multi-vector found it!)
- Listing with all traditional dark wood kitchens: **0.31** (low - no match)
- Listing with exterior photos only: **0.25** (very low - wrong image type)

**Why Multi-Vector is Critical:**
- Prevents feature dilution from averaging
- Allows rare features to be detected
- Makes image search actually useful (vs. old approach where it rarely helped)

**Typical kNN Image Score Range:** 0.40 - 0.90 (for visually relevant results)

---

## Phase 3: Reciprocal Rank Fusion (RRF)

After three parallel searches complete, we have three independent rankings:

```
BM25 Results:         kNN Text Results:      kNN Image Results:
1. zpid=12345 (12.5)  1. zpid=67890 (0.89)   1. zpid=54321 (0.88)
2. zpid=67890 (11.2)  2. zpid=12345 (0.86)   2. zpid=12345 (0.82)
3. zpid=11111 (10.8)  3. zpid=54321 (0.83)   3. zpid=99999 (0.76)
4. zpid=54321 (9.3)   4. zpid=22222 (0.79)   4. zpid=67890 (0.71)
5. zpid=22222 (8.1)   5. zpid=11111 (0.75)   5. zpid=11111 (0.68)
...                   ...                    ...
```

**Problem:** How do we combine these rankings into one?

**Why not just average scores?**
- BM25 scores (0-25) and kNN scores (0-1) are on different scales
- High BM25 score might dominate even if kNN scores are poor
- Doesn't account for rank position (being #1 vs #10 is important)

**Solution: Reciprocal Rank Fusion (RRF)**

RRF combines rankings based on **rank position**, not raw scores. It's scale-invariant and proven to work well across different search strategies.

### 3.1 RRF Formula

For each document, compute:

```
RRF_score(d) = Σ (1 / (k + rank_i(d)))

Where:
- d = document (listing)
- rank_i(d) = position of d in result list i (1-indexed)
- k = constant that controls weight (default: 60)
- Σ = sum across all result lists
```

**Lower k = higher weight for that result list**

### 3.2 RRF Calculation Example

Query: "modern white house with granite countertops"

**Step 1: Rank positions**

| Listing | BM25 Rank | Text kNN Rank | Image kNN Rank |
|---------|-----------|---------------|----------------|
| 12345   | 1         | 2             | 2              |
| 67890   | 2         | 1             | 4              |
| 54321   | 4         | 3             | 1              |
| 11111   | 3         | 5             | 5              |
| 22222   | 5         | 4             | Not found      |

**Step 2: Apply RRF formula (standard k=60 for all)**

**Listing 12345:**
```
RRF(12345) = 1/(60+1) + 1/(60+2) + 1/(60+2)
           = 1/61 + 1/62 + 1/62
           = 0.01639 + 0.01613 + 0.01613
           = 0.04865
```

**Listing 67890:**
```
RRF(67890) = 1/(60+2) + 1/(60+1) + 1/(60+4)
           = 1/62 + 1/61 + 1/64
           = 0.01613 + 0.01639 + 0.01563
           = 0.04815
```

**Listing 54321:**
```
RRF(54321) = 1/(60+4) + 1/(60+3) + 1/(60+1)
           = 1/64 + 1/63 + 1/61
           = 0.01563 + 0.01587 + 0.01639
           = 0.04789
```

**Listing 11111:**
```
RRF(11111) = 1/(60+3) + 1/(60+5) + 1/(60+5)
           = 1/63 + 1/65 + 1/65
           = 0.01587 + 0.01538 + 0.01538
           = 0.04663
```

**Listing 22222:**
```
RRF(22222) = 1/(60+5) + 1/(60+4) + 0
           = 1/65 + 1/64 + 0  (not in image results)
           = 0.01538 + 0.01563 + 0
           = 0.03101
```

**Final Ranking (by RRF score):**
1. **12345** (0.04865) - Top in BM25, #2 in both kNN → BEST OVERALL
2. **67890** (0.04815) - Strong in BM25 and text kNN
3. **54321** (0.04789) - #1 in images but weaker in text
4. **11111** (0.04663) - Consistent middle rankings
5. **22222** (0.03101) - Missing from image results hurts score

**Key Observations:**
- Listing 12345 wins despite NOT being #1 in any single list
- Being top-ranked in one list + decent in others beats being #1 in one and missing in others
- Consistent appearance across all lists is rewarded
- Missing from a result list = contributes 0 to score

---

## Phase 4: Adaptive Weight Calculation

This is where Hearth's scoring gets **intelligent**.

### 4.1 The Adaptive Weighting Concept

**Problem:** Different queries need different search strategies.
- "White house" → BM25 keyword search works best (tags have exact color)
- "Modern architecture" → Image similarity works best (visual characteristics)
- "Granite countertops" → BM25 and text embeddings work well, images less reliable

**Solution:** Dynamically adjust RRF k-values based on query characteristics.

**Remember:** Lower k = higher weight

### 4.2 Adaptive K-Value Selection

The system analyzes `must_have` tags and `query_type` to choose optimal k-values:

```python
def calculate_adaptive_weights(must_have_tags, query_type):
    # Define detection keywords
    COLOR_KEYWORDS = ['white', 'gray', 'grey', 'blue', 'beige', 'brown',
                      'red', 'tan', 'black', 'yellow', 'green', 'cream']
    MATERIAL_KEYWORDS = ['brick', 'stone', 'wood', 'granite', 'marble',
                         'quartz', 'vinyl', 'stucco', 'hardwood', 'tile']

    # Check what's in the query
    has_color = any(any(color in tag.lower() for color in COLOR_KEYWORDS)
                    for tag in must_have_tags)
    has_material = any(any(mat in tag.lower() for mat in MATERIAL_KEYWORDS)
                       for tag in must_have_tags)

    # Start with balanced weights
    bm25_k = 60
    text_k = 60
    image_k = 60

    # Apply adaptive logic
    if has_color:
        bm25_k = 30      # BOOST BM25 (tags have exact color)
        image_k = 120    # DE-BOOST images (embeddings don't capture color)

    if has_material:
        bm25_k = int(bm25_k * 0.7)  # Further boost BM25
        text_k = 45                  # Boost text (descriptions mention materials)

    if query_type == "visual_style":
        image_k = 40     # BOOST images (architectural queries)
        text_k = 45      # Moderate boost (descriptions have style info)

    return [bm25_k, text_k, image_k]
```

### 4.3 Adaptive Weighting Examples

#### Example 1: Color Query

Query: "white house with blue door"
- `must_have`: ["white_exterior", "blue_door"]
- `query_type`: "color"
- Detection: `has_color = True`

**Weights:**
```
bm25_k = 30    (high weight - 2x impact vs default)
text_k = 60    (standard weight)
image_k = 120  (low weight - 0.5x impact vs default)
```

**Why this works:**
- Image embeddings **cannot distinguish colors** (blue vs red vs green look similar)
- BM25 tags have exact color info from Claude vision: "white exterior", "blue door"
- Text embeddings might capture some color context but less reliable than tags

**RRF Score Comparison:**

Listing A (white house with blue door):
- BM25: rank 1 → 1/(30+1) = 0.0323
- Text: rank 5 → 1/(60+5) = 0.0154
- Image: rank 3 → 1/(120+3) = 0.0081
- **Total: 0.0558**

Listing B (gray house, no blue door):
- BM25: rank 10 → 1/(30+10) = 0.0250
- Text: rank 2 → 1/(60+2) = 0.0161
- Image: rank 1 → 1/(120+1) = 0.0083
- **Total: 0.0494**

**Result:** Listing A wins (0.0558 > 0.0494) because BM25 boost rewarded exact color match!

#### Example 2: Visual Style Query

Query: "modern architecture with mountain views"
- `must_have`: ["mountain_views"]
- `query_type`: "visual_style"
- `architecture_style`: "modern"

**Weights:**
```
bm25_k = 60    (standard weight)
text_k = 45    (moderate boost)
image_k = 40   (high weight - 1.5x impact vs default)
```

**Why this works:**
- Image embeddings **excel at visual characteristics** (modern vs traditional look)
- Text embeddings capture style context ("contemporary", "updated", "sleek")
- BM25 helps but less critical (style isn't always mentioned in description)

**RRF Score Comparison:**

Listing A (ultra-modern glass house):
- BM25: rank 5 → 1/(60+5) = 0.0154
- Text: rank 3 → 1/(45+3) = 0.0208
- Image: rank 1 → 1/(40+1) = 0.0244
- **Total: 0.0606**

Listing B (traditional Victorian):
- BM25: rank 2 → 1/(60+2) = 0.0161
- Text: rank 10 → 1/(45+10) = 0.0182
- Image: rank 15 → 1/(40+15) = 0.0182
- **Total: 0.0525**

**Result:** Listing A wins (0.0606 > 0.0525) because image boost rewarded visual similarity!

#### Example 3: Material Query

Query: "brick house with granite countertops and hardwood floors"
- `must_have`: ["brick_exterior", "granite_countertops", "hardwood_floors"]
- `query_type`: "material"
- Detection: `has_material = True`

**Weights:**
```
bm25_k = 42    (high weight - 60 * 0.7 from material boost)
text_k = 45    (moderate boost)
image_k = 60   (standard weight)
```

**Why this works:**
- BM25 tags capture exact materials from Claude vision
- Text embeddings help ("granite" vs "marble" vs "laminate" have semantic distance)
- Images somewhat reliable but materials can be subtle/ambiguous

#### Example 4: Balanced Query (No Adaptive Logic)

Query: "3 bedroom house with pool and 2-car garage"
- `must_have`: ["pool", "2_car_garage"]
- `query_type`: "specific_feature"
- No color, material, or visual style detected

**Weights:**
```
bm25_k = 60    (standard)
text_k = 60    (standard)
image_k = 60   (standard)
```

**Why this works:**
- All strategies equally effective for generic features
- Pool visible in images, mentioned in descriptions, tagged by vision
- Balanced approach ensures no signal over-dominates

### 4.4 RRF with Adaptive Weights - Full Calculation

Let's calculate a complete example with adaptive weights:

Query: "modern white house with granite countertops"
- Adaptive weights: `[30, 60, 120]` (color detected)

**Listing 12345 rankings:**
- BM25: rank 1
- Text kNN: rank 2
- Image kNN: rank 2

**Standard RRF (k=60 for all):**
```
RRF = 1/61 + 1/62 + 1/62 = 0.04865
```

**Adaptive RRF:**
```
RRF = 1/(30+1) + 1/(60+2) + 1/(120+2)
    = 1/31 + 1/62 + 1/122
    = 0.03226 + 0.01613 + 0.00820
    = 0.05659  ← 16% HIGHER than standard!
```

This listing benefits from adaptive scoring because it ranked #1 in BM25 (which got boosted).

**Listing 54321 rankings:**
- BM25: rank 4
- Text kNN: rank 3
- Image kNN: rank 1

**Standard RRF:**
```
RRF = 1/64 + 1/63 + 1/61 = 0.04789
```

**Adaptive RRF:**
```
RRF = 1/(30+4) + 1/(60+3) + 1/(120+1)
    = 1/34 + 1/63 + 1/121
    = 0.02941 + 0.01587 + 0.00826
    = 0.05354  ← 12% HIGHER, but still loses to 12345
```

**Result:** Listing 12345 wins with adaptive scoring (0.05659 > 0.05354)

If we used standard RRF, the gap would be smaller (0.04865 vs 0.04789), and tag boosting (next phase) might change the winner. Adaptive scoring makes the difference clearer.

---

## Phase 5: Tag Boosting

After RRF fusion, we apply **multiplicative boosting** based on exact tag matches. This is the final step before ranking.

### 5.1 Tag Matching Logic

**What gets matched:**
- `must_have` tags extracted from query (Phase 1)
- `feature_tags` stored in listing (from text description analysis)
- `image_tags` stored in listing (from Claude vision analysis)

**Tag expansion for compatibility:**
- Query parser may output "granite_countertops" (underscore)
- Vision system stores "granite countertops" (space)
- System expands all tags to both formats for matching

**Example:**
```python
must_have_tags = ["granite_countertops", "white_exterior"]

expanded_must_tags = {
    "granite_countertops",
    "granite countertops",  ← Added space version
    "white_exterior",
    "white exterior"        ← Added space version
}

listing_tags = {
    "granite countertops",  ← Stored with spaces
    "stainless steel appliances",
    "hardwood floors"
}

matched_tags = expanded_must_tags ∩ listing_tags
             = {"granite countertops"}
```

### 5.2 Boost Factor Calculation

The boost is based on the **match percentage** of required tags:

```python
match_ratio = len(matched_tags) / len(must_have_tags)

if match_ratio >= 1.0:      # 100% match (all tags present)
    boost = 2.0
elif match_ratio >= 0.75:   # 75% match (3 out of 4 tags)
    boost = 1.5
elif match_ratio >= 0.5:    # 50% match (2 out of 4 tags)
    boost = 1.25
else:                        # <50% match
    boost = 1.0              # No boost
```

**Why progressive boosting?**
- Rewards listings that match ALL required features with significant boost
- Still helps listings with partial matches (75%, 50%)
- Doesn't penalize listings with <50% match (they may still be good via semantic similarity)

### 5.3 Tag Boosting Examples

#### Example 1: Perfect Match (100%)

Query: "house with pool and granite countertops"
- `must_have`: ["pool", "granite_countertops"]

**Listing A:**
- `image_tags`: ["pool", "granite countertops", "stainless steel appliances"]
- **Matched:** 2/2 tags (100%)
- **Boost:** 2.0x
- RRF score: 0.055
- **Final score:** 0.055 × 2.0 = **0.110**

**Listing B:**
- `image_tags`: ["pool", "marble countertops", "hardwood floors"]
- **Matched:** 1/2 tags (50%)
- **Boost:** 1.25x
- RRF score: 0.062 (higher RRF than A!)
- **Final score:** 0.062 × 1.25 = **0.0775**

**Result:** Listing A wins (0.110 > 0.0775) despite lower RRF score, because it matched ALL required features!

#### Example 2: Partial Match (75%)

Query: "modern home with granite, stainless appliances, hardwood floors, and fireplace"
- `must_have`: ["granite_countertops", "stainless_steel_appliances", "hardwood_floors", "fireplace"]

**Listing C:**
- `image_tags`: ["granite countertops", "stainless steel appliances", "hardwood floors"]
- **Matched:** 3/4 tags (75%)
- **Boost:** 1.5x
- RRF score: 0.048
- **Final score:** 0.048 × 1.5 = **0.072**

**Listing D:**
- `image_tags`: ["granite countertops", "gas stove", "tile floors"]
- **Matched:** 1/4 tags (25%)
- **Boost:** 1.0x (no boost)
- RRF score: 0.053
- **Final score:** 0.053 × 1.0 = **0.053**

**Result:** Listing C wins (0.072 > 0.053) because 75% match earned 1.5x boost.

#### Example 3: No Boost (<50%)

Query: "white house with blue door, pool, granite, and mountain views"
- `must_have`: ["white_exterior", "blue_door", "pool", "granite_countertops", "mountain_views"]

**Listing E:**
- `image_tags`: ["white exterior", "pool"]
- **Matched:** 2/5 tags (40%)
- **Boost:** 1.0x (no boost - below 50% threshold)
- RRF score: 0.051
- **Final score:** 0.051 × 1.0 = **0.051**

This listing doesn't get penalized for partial match, but doesn't get rewarded either. It still appears in results if RRF score is competitive.

### 5.4 Why Multiplicative (Not Additive) Boosting?

**Multiplicative:** `final_score = rrf_score × boost`
**Additive:** `final_score = rrf_score + boost`

**Why multiplicative is better:**

1. **Preserves ranking quality**
   - High RRF score + boost = very high final score (correct!)
   - Low RRF score + boost = still relatively low (correct!)
   - With additive boost, a low-quality match with 100% tags could beat a high-quality partial match

2. **Scale-aware**
   - Works regardless of RRF score range
   - 2x boost means "this listing is twice as relevant" (intuitive)

**Example comparison:**

Listing A: RRF=0.08, 100% match, boost=2.0
- Multiplicative: 0.08 × 2.0 = **0.160**
- Additive: 0.08 + 2.0 = **2.080**

Listing B: RRF=0.02, 100% match, boost=2.0
- Multiplicative: 0.02 × 2.0 = **0.040**
- Additive: 0.02 + 2.0 = **2.020**

With **multiplicative**, A ranks higher (0.160 > 0.040) ← CORRECT (better RRF + same boost)
With **additive**, scores are nearly identical (2.080 vs 2.020) ← WRONG (ignores RRF quality difference)

---

## Complete Scoring Examples

Let's walk through complete end-to-end examples showing every step of the scoring pipeline.

### Example 1: "white brick house with pool under $500k"

#### Step 1: Query Analysis
```json
{
  "must_have": ["white_exterior", "brick_exterior", "pool"],
  "hard_filters": {"price_max": 500000},
  "query_type": "color"
}
```

#### Step 2: Generate Query Embedding
```python
query_vector = embed_text("white brick house with pool under $500k")
# [0.023, -0.041, 0.115, ..., 0.201]  (1024 dims)
```

#### Step 3: Calculate Adaptive Weights
```python
has_color = True  # "white" detected
has_material = True  # "brick" detected

bm25_k = 30 * 0.7 = 21  # Color boost + material boost
text_k = 45              # Material boost
image_k = 120            # Color de-boost

k_values = [21, 45, 120]
```

#### Step 4: Execute Parallel Searches

**BM25 Results:**
```
1. zpid=12345  score=15.2  (description: "Beautiful white brick home with pool")
2. zpid=67890  score=12.8  (description: "White exterior, brick facade, swimming pool")
3. zpid=54321  score=11.5  (description: "Brick house, white paint, pool in backyard")
4. zpid=99999  score=9.1   (description: "Updated home with brick and pool")
5. zpid=11111  score=8.3   (description: "White house with inground pool")
```

**Text kNN Results:**
```
1. zpid=67890  score=0.91  (semantic: white, brick, pool all mentioned)
2. zpid=12345  score=0.89  (semantic: similar wording)
3. zpid=54321  score=0.85  (semantic: all features present)
4. zpid=88888  score=0.81  (semantic: "light colored brick home with swimming area")
5. zpid=11111  score=0.78  (semantic: white + pool, no brick mention)
```

**Image kNN Results:**
```
1. zpid=54321  score=0.86  (visual: has white brick exterior photo + pool photo)
2. zpid=12345  score=0.79  (visual: brick visible, pool photo)
3. zpid=88888  score=0.74  (visual: light brick, water feature)
4. zpid=67890  score=0.68  (visual: white house, brick texture unclear)
5. zpid=99999  score=0.61  (visual: brick visible, pool in background)
```

#### Step 5: Apply RRF with Adaptive Weights

**Listing 12345:**
```
BM25: rank 1 → 1/(21+1) = 0.04545
Text: rank 2 → 1/(45+2) = 0.02128
Image: rank 2 → 1/(120+2) = 0.00820
RRF = 0.07493
```

**Listing 67890:**
```
BM25: rank 2 → 1/(21+2) = 0.04348
Text: rank 1 → 1/(45+1) = 0.02174
Image: rank 4 → 1/(120+4) = 0.00806
RRF = 0.07328
```

**Listing 54321:**
```
BM25: rank 3 → 1/(21+3) = 0.04167
Text: rank 3 → 1/(45+3) = 0.02083
Image: rank 1 → 1/(120+1) = 0.00826
RRF = 0.07076
```

**Listing 11111:**
```
BM25: rank 5 → 1/(21+5) = 0.03846
Text: rank 5 → 1/(45+5) = 0.02000
Image: not in top 5 → 0
RRF = 0.05846
```

**Listing 99999:**
```
BM25: rank 4 → 1/(21+4) = 0.04000
Text: not in top 5 → 0
Image: rank 5 → 1/(120+5) = 0.00800
RRF = 0.04800
```

**Listing 88888:**
```
BM25: not in top 5 → 0
Text: rank 4 → 1/(45+4) = 0.02041
Image: rank 3 → 1/(120+3) = 0.00813
RRF = 0.02854
```

**After RRF (before tag boosting):**
```
1. zpid=12345  RRF=0.07493
2. zpid=67890  RRF=0.07328
3. zpid=54321  RRF=0.07076
4. zpid=11111  RRF=0.05846
5. zpid=99999  RRF=0.04800
6. zpid=88888  RRF=0.02854
```

#### Step 6: Tag Matching and Boosting

Required tags: ["white_exterior", "white exterior", "brick_exterior", "brick exterior", "pool"]

**Listing 12345:**
```
Tags: ["white exterior", "brick exterior", "pool", "granite countertops"]
Matched: 3/3 required tags (100%)
Boost: 2.0x
Final: 0.07493 × 2.0 = 0.14986
```

**Listing 67890:**
```
Tags: ["white exterior", "brick facade", "pool", "2 car garage"]
Matched: 3/3 required tags (100%)  ← "brick facade" matches "brick exterior"
Boost: 2.0x
Final: 0.07328 × 2.0 = 0.14656
```

**Listing 54321:**
```
Tags: ["brick exterior", "pool", "hardwood floors"]
Matched: 2/3 required tags (67%)  ← Missing "white exterior"
Boost: 1.25x
Final: 0.07076 × 1.25 = 0.08845
```

**Listing 11111:**
```
Tags: ["white exterior", "pool", "mountain views"]
Matched: 2/3 required tags (67%)  ← Missing "brick"
Boost: 1.25x
Final: 0.05846 × 1.25 = 0.07308
```

**Listing 99999:**
```
Tags: ["brick exterior", "pool"]
Matched: 2/3 required tags (67%)  ← Missing "white"
Boost: 1.25x
Final: 0.04800 × 1.25 = 0.06000
```

**Listing 88888:**
```
Tags: ["stone exterior", "pool", "large windows"]
Matched: 1/3 required tags (33%)  ← Only "pool" matches
Boost: 1.0x (no boost)
Final: 0.02854 × 1.0 = 0.02854
```

#### Step 7: Final Ranking

```
1. zpid=12345  score=0.14986  (100% tag match + top RRF)
2. zpid=67890  score=0.14656  (100% tag match + strong RRF)
3. zpid=54321  score=0.08845  (67% tag match + good RRF)
4. zpid=11111  score=0.07308  (67% tag match + medium RRF)
5. zpid=99999  score=0.06000  (67% tag match + lower RRF)
6. zpid=88888  score=0.02854  (33% tag match + weak RRF)
```

**Winner: Listing 12345**
- Topped BM25 search (benefited from aggressive color/material boost)
- Strong in text kNN (#2)
- Good in image kNN (#2)
- Matched all required tags (2.0x boost)

### Example 2: "modern architecture with open floor plan"

#### Step 1: Query Analysis
```json
{
  "must_have": ["open_floor_plan"],
  "architecture_style": "modern",
  "query_type": "visual_style"
}
```

#### Step 2: Adaptive Weights
```python
has_color = False
has_material = False
query_type = "visual_style"

bm25_k = 60    # Standard
text_k = 45    # Moderate boost (descriptions mention style)
image_k = 40   # High boost (visual characteristics)

k_values = [60, 45, 40]
```

#### Step 3: Parallel Search Results

**BM25 Results:**
```
1. zpid=11111  score=10.5  (description: "Modern home with open concept living")
2. zpid=22222  score=9.8   (description: "Contemporary design, open floor plan")
3. zpid=33333  score=8.7   (description: "Updated modern interior, flowing layout")
4. zpid=44444  score=7.2   (description: "Open concept, sleek design")
5. zpid=55555  score=6.8   (description: "Spacious with open living areas")
```

**Text kNN Results:**
```
1. zpid=22222  score=0.93  (semantic: "contemporary" ≈ "modern")
2. zpid=11111  score=0.91  (semantic: perfect semantic match)
3. zpid=33333  score=0.88  (semantic: "updated modern" ≈ query)
4. zpid=66666  score=0.84  (semantic: "minimalist design with flowing spaces")
5. zpid=44444  score=0.82  (semantic: "sleek" + "open concept")
```

**Image kNN Results:**
```
1. zpid=33333  score=0.92  (visual: ultra-modern glass exterior, open interior photos)
2. zpid=22222  score=0.89  (visual: clean lines, contemporary style visible)
3. zpid=11111  score=0.85  (visual: modern facade, open layout visible)
4. zpid=66666  score=0.81  (visual: minimalist modern design)
5. zpid=77777  score=0.76  (visual: some modern elements)
```

#### Step 4: RRF with Adaptive Weights

**Listing 11111:**
```
BM25: rank 1 → 1/(60+1) = 0.01639
Text: rank 2 → 1/(45+2) = 0.02128
Image: rank 3 → 1/(40+3) = 0.02326
RRF = 0.06093
```

**Listing 22222:**
```
BM25: rank 2 → 1/(60+2) = 0.01613
Text: rank 1 → 1/(45+1) = 0.02174
Image: rank 2 → 1/(40+2) = 0.02381
RRF = 0.06168  ← HIGHEST RRF
```

**Listing 33333:**
```
BM25: rank 3 → 1/(60+3) = 0.01587
Text: rank 3 → 1/(45+3) = 0.02083
Image: rank 1 → 1/(40+1) = 0.02439  ← Best in images!
RRF = 0.06109
```

**After RRF:**
```
1. zpid=22222  RRF=0.06168
2. zpid=33333  RRF=0.06109
3. zpid=11111  RRF=0.06093
```

#### Step 5: Tag Boosting

Required tags: ["open_floor_plan", "open floor plan"]

**Listing 22222:**
```
Tags: ["open floor plan", "contemporary design", "large windows"]
Matched: 1/1 required tags (100%)
Boost: 2.0x
Final: 0.06168 × 2.0 = 0.12336
```

**Listing 33333:**
```
Tags: ["modern design", "large windows", "minimalist"]
Matched: 0/1 required tags (0%)  ← Missing "open floor plan"
Boost: 1.0x
Final: 0.06109 × 1.0 = 0.06109
```

**Listing 11111:**
```
Tags: ["open floor plan", "modern style", "vaulted ceilings"]
Matched: 1/1 required tags (100%)
Boost: 2.0x
Final: 0.06093 × 2.0 = 0.12186
```

#### Step 6: Final Ranking

```
1. zpid=22222  score=0.12336  (100% tags + highest RRF)
2. zpid=11111  score=0.12186  (100% tags + strong RRF)
3. zpid=33333  score=0.06109  (no boost - missing "open floor plan" tag)
```

**Winner: Listing 22222**
- Even though 33333 was #1 in image kNN (best visual match), it didn't have "open floor plan" tag
- Tag boosting (2.0x) made the decisive difference
- 22222 had slightly better RRF than 11111, maintained lead after boosting

**Key Insight:** Tags still matter even for visual queries! A listing needs BOTH visual similarity AND feature tags to rank #1.

---

## Mathematical Formulas

### Complete Score Calculation

```
final_score(listing) = RRF_score(listing) × tag_boost(listing)

Where:
    RRF_score = Σ(1 / (k_i + rank_i))

    k_i = adaptive weight for result list i:
        - Lower k = higher weight
        - Determined by query characteristics
        - k_values = [k_bm25, k_text, k_image]

    rank_i = position of listing in result list i (1-indexed)

    tag_boost = {
        2.0    if match_ratio >= 1.0
        1.5    if match_ratio >= 0.75
        1.25   if match_ratio >= 0.5
        1.0    otherwise
    }

    match_ratio = |matched_tags| / |required_tags|
```

### BM25 Score Formula

```
BM25(D, Q) = Σ IDF(q_i) × (f(q_i, D) × (k1 + 1)) / (f(q_i, D) + k1 × (1 - b + b × |D|/avgDL))

Where:
    D = document (listing)
    Q = query terms
    q_i = individual query term
    f(q_i, D) = frequency of term q_i in document D
    |D| = length of document D in words
    avgDL = average document length across corpus
    k1 = 1.2 (term frequency saturation parameter)
    b = 0.75 (document length normalization)

    IDF(q_i) = log((N - df(q_i) + 0.5) / (df(q_i) + 0.5))
    N = total number of documents in index
    df(q_i) = number of documents containing term q_i

Field boost applied:
    final_BM25 = BM25(description) × 3 +
                 BM25(visual_features_text) × 2.5 +
                 BM25(other_fields) × field_boost
```

### Cosine Similarity (kNN)

```
cosine_similarity(A, B) = (A · B) / (||A|| × ||B||)

Where:
    A = query embedding vector
    B = listing embedding vector
    A · B = Σ(A_i × B_i)  [dot product]
    ||A|| = sqrt(Σ(A_i²))  [magnitude of A]
    ||B|| = sqrt(Σ(B_i²))  [magnitude of B]

Score range: [-1, 1]
    1.0 = identical vectors
    0.0 = orthogonal (no similarity)
    -1.0 = opposite vectors
```

### Multi-Vector Score (Nested kNN)

```
multi_vector_score(listing, query) = max(cosine_similarity(query, image_i))
                                     for all image_i in listing.image_vectors

This uses OpenSearch nested query with score_mode="max":
    - Each image vector is compared independently to query
    - Listing score = BEST matching image score
    - Prevents feature dilution from averaging
```

### Adaptive Weight Calculation

```
k_values = calculate_adaptive_weights(must_have_tags, query_type)

Default weights:
    k_bm25 = 60
    k_text = 60
    k_image = 60

Adjustments:
    if has_color(must_have_tags):
        k_bm25 = 30      (boost by 2x)
        k_image = 120    (reduce by 0.5x)

    if has_material(must_have_tags):
        k_bm25 *= 0.7    (further boost)
        k_text = 45      (moderate boost)

    if query_type == "visual_style":
        k_image = 40     (boost by 1.5x)
        k_text = 45      (moderate boost)

Return [k_bm25, k_text, k_image]
```

---

## Performance Characteristics

### Score Ranges

| Metric | Min | Typical | Max | Notes |
|--------|-----|---------|-----|-------|
| **BM25 score** | 0.0 | 5.0 - 15.0 | 30.0+ | Keyword matches, unlimited range |
| **kNN text score** | 0.0 | 0.65 - 0.90 | 1.0 | Cosine similarity, capped at 1.0 |
| **kNN image score** | 0.0 | 0.50 - 0.85 | 1.0 | Visual similarity, capped at 1.0 |
| **RRF score (standard)** | 0.0 | 0.03 - 0.08 | 0.15+ | Sum of reciprocal ranks |
| **RRF score (adaptive)** | 0.0 | 0.04 - 0.10 | 0.20+ | Higher due to weight adjustments |
| **Tag boost** | 1.0 | 1.25 - 2.0 | 2.0 | Multiplicative factor |
| **Final score** | 0.0 | 0.05 - 0.15 | 0.40+ | RRF × tag_boost |

### Query Performance

| Operation | Time | Cost | Notes |
|-----------|------|------|-------|
| **Query parsing (LLM)** | 500-800ms | $0.0003 | Claude 3.5 Sonnet call |
| **Query embedding** | 50-100ms | $0.0001 | Titan Text v2 |
| **BM25 search** | 100-300ms | $0 | OpenSearch native |
| **kNN text search** | 150-400ms | $0 | HNSW algorithm |
| **kNN image search** | 150-500ms | $0 | HNSW on nested vectors |
| **RRF fusion** | 10-30ms | $0 | In-memory computation |
| **Tag boosting** | 5-10ms | $0 | String matching |
| **Total** | 1.0-2.3s | $0.0004 | Parallel execution |

**Note:** kNN searches run in parallel, so total time < sum of individual times.

### Indexing Performance

| Operation | Time per Listing | Cost per Listing | Notes |
|-----------|------------------|------------------|-------|
| **Text embedding** | 80ms | $0.0001 | 1 description |
| **Image embeddings** | 50ms × N | $0.00006 × N | N = image count |
| **Vision analysis** | 200ms × N | $0.00025 × N | Claude Haiku per image |
| **OpenSearch index** | 100ms | $0 | Bulk upload |
| **Total (10 images)** | 3.0s | $0.0031 | With 90% cache: $0.0004 |

**Cache hit rates:**
- Text embeddings: ~95% (descriptions rarely change)
- Image embeddings + analysis: ~90% (many duplicate images across re-indexing)

---

## Appendix: Score Breakdown API

### Enabling Score Details

Add `include_scoring_details: true` to search request:

```json
POST /search
{
  "query": "modern white house with pool",
  "limit": 10,
  "index": "listings-v2",
  "include_scoring_details": true
}
```

### Response Format with Scoring Details

```json
{
  "ok": true,
  "results": [
    {
      "zpid": "12345",
      "score": 0.14986,
      "boosted": true,
      "description": "Beautiful modern white home...",
      "_scoring_details": {
        "bm25": {
          "rank": 1,
          "original_score": 15.2,
          "rrf_contribution": 0.04545,
          "k": 30
        },
        "knn_text": {
          "rank": 2,
          "original_score": 0.89,
          "rrf_contribution": 0.02128,
          "k": 60
        },
        "knn_image": {
          "rank": 2,
          "original_score": 0.82,
          "rrf_contribution": 0.00820,
          "k": 120
        },
        "rrf_total": 0.07493,
        "tag_boosting": {
          "required_tags": ["white exterior", "pool"],
          "matched_tags": ["white exterior", "pool"],
          "match_ratio": 1.0,
          "boost_factor": 2.0,
          "score_before_boost": 0.07493,
          "score_after_boost": 0.14986
        },
        "query_context": {
          "query_type": "color",
          "k_values": {
            "bm25": 30,
            "knn_text": 60,
            "knn_image": 120
          },
          "adaptive_scoring_applied": true
        },
        "image_vectors_count": 12,
        "individual_image_scores": [
          {
            "index": 3,
            "url": "https://photos.zillowstatic.com/.../pool.jpg",
            "score": 0.91
          },
          {
            "index": 0,
            "url": "https://photos.zillowstatic.com/.../exterior.jpg",
            "score": 0.82
          },
          {
            "index": 5,
            "url": "https://photos.zillowstatic.com/.../kitchen.jpg",
            "score": 0.54
          }
        ]
      }
    }
  ]
}
```

### Interpreting Score Breakdown

**1. Check which strategy contributed most:**
```python
if rrf_contribution["bm25"] > rrf_contribution["knn_text"]:
    print("BM25 keyword matching was most important")
elif rrf_contribution["knn_image"] > others:
    print("Visual similarity drove this result")
```

**2. Understand adaptive weighting impact:**
```python
if k_values["bm25"] < 60:
    print("BM25 was boosted (color/material query detected)")
if k_values["image"] > 60:
    print("Image search was de-weighted")
```

**3. Identify which images matched:**
```python
top_matching_image = individual_image_scores[0]
print(f"Best match: {top_matching_image['url']} (score: {top_matching_image['score']})")
```

**4. Verify tag boosting:**
```python
if boost_factor > 1.0:
    print(f"Result boosted {boost_factor}x for matching {match_ratio:.0%} of required tags")
```

---

## Summary

Hearth's scoring system is a **multi-stage adaptive fusion algorithm** that:

1. **Analyzes queries** using LLM to extract features and classify query type
2. **Executes parallel searches** using three complementary strategies (BM25, text kNN, image kNN)
3. **Fuses results** using Reciprocal Rank Fusion with adaptive weights based on query characteristics
4. **Boosts exact matches** using multiplicative tag-based boosting
5. **Returns ranked results** sorted by final score

**Key innovations:**
- **Multi-vector image search** prevents feature dilution
- **Adaptive RRF weights** optimize for query type (color vs visual vs feature)
- **Progressive tag boosting** rewards listings with more matching features
- **Scale-invariant fusion** works regardless of individual score ranges

**Result:** A search engine that automatically adapts to find the most relevant properties for any natural language query, whether searching by color ("white house"), visual style ("modern architecture"), specific features ("granite countertops"), or combinations thereof.

---

## Known Issues & Limitations

### Issue 1: "Not Found in Top Results" for kNN Image Searches

**Problem:** Listings that score highly in isolated kNN image searches may rank poorly or disappear entirely in the final fused results.

**Example Scenario:**
```
Query: "modern architecture with clean lines"

Individual Search Results:
- kNN Image Search: Property A ranks #3 (score: 0.86)
- BM25 Search: Property A ranks #45 (score: 2.1)
- kNN Text Search: Property A ranks #38 (score: 0.62)

Final Fused Results: Property A ranks #27 (RRF score: 0.03)
```

**Root Cause Analysis:**
1. **Strategy Overlap:** BM25 and kNN text search both evaluate the same `description` field
   - BM25 uses keyword matching on description
   - kNN text embeds the description
   - Both return similar rankings for text-heavy queries
   - Image kNN becomes minority voice (1 out of 3)

2. **Equal Weighting Issue:** Current RRF uses k=60 for all three strategies
   - Each strategy gets equal weight in fusion
   - 2 text-based strategies vs 1 visual strategy = 2:1 text bias
   - Even with adaptive weighting, bias remains

3. **RRF Rank Sensitivity:** RRF heavily penalizes low ranks
   ```
   Property A contributions:
   - Image: 1/(60+3) = 0.0159 (strong)
   - BM25: 1/(60+45) = 0.0095 (weak - low rank hurts badly)
   - Text: 1/(60+38) = 0.0102 (weak)
   - Total: 0.0356 (mediocre despite strong image match)
   ```

**Why This Matters:**
- Visual queries like "modern architecture" should primarily use image similarity
- Current system over-weights text relevance even for visual queries
- Listings with poor descriptions but great visual matches are disadvantaged

**Status:** ⚠️ Under Investigation

**Proposed Solutions:**

**Option 1: Reduce Text Strategy Weight for Visual Queries**
```python
if query_type == "visual_style" or architecture_style:
    bm25_k = 90      # Reduce BM25 weight
    text_k = 90      # Reduce text kNN weight
    image_k = 30     # Boost image kNN weight (3x impact vs text)
```

**Option 2: Use Score-Based Fusion Instead of Rank-Based**
```python
# Instead of RRF (rank-based), use weighted score fusion
final_score = (w_bm25 * normalize(bm25_score) +
               w_text * text_score +
               w_image * image_score)
```

**Option 3: Remove kNN Text Search for Visual Queries**
```python
if query_type in ["visual_style", "color", "material"]:
    # Only run BM25 (for tags) + image kNN
    # Skip text kNN entirely (reduces strategy overlap)
```

**Option 4: Multi-Stage Fusion**
```python
# Stage 1: Fuse BM25 + text kNN (both text-based)
text_fusion_score = rrf([bm25_results, text_knn_results], k=60)

# Stage 2: Fuse text results with image results
final_score = rrf([text_fusion_results, image_knn_results], k=60)

# Now it's 1:1 (text vs visual), not 2:1
```

---

### Issue 2: Strategy Overlap Between BM25 and kNN Text

**Problem:** BM25 and kNN text search produce highly correlated rankings because they both analyze the same `description` field.

**Correlation Analysis:**
```
Query: "granite countertops with stainless steel appliances"

BM25 Top 10:          kNN Text Top 10:      Overlap:
1. zpid=12345         1. zpid=12345         ✓ (exact match)
2. zpid=67890         3. zpid=67890         ✓ (off by 1)
3. zpid=54321         2. zpid=54321         ✓ (off by 1)
4. zpid=99999         4. zpid=99999         ✓ (exact match)
5. zpid=11111         6. zpid=11111         ✓ (off by 1)
6. zpid=22222         5. zpid=22222         ✓ (off by 1)
7. zpid=33333         8. zpid=33333         ✓ (off by 1)
8. zpid=44444         7. zpid=44444         ✓ (off by 1)
9. zpid=55555         10. zpid=55555        ✓ (off by 1)
10. zpid=66666        9. zpid=66666         ✓ (off by 1)

Rank Correlation: 0.98 (Spearman's ρ)
```

**Why This Happens:**
- **BM25** scores based on keyword frequency in description
- **kNN Text** scores based on semantic similarity of description embedding
- Listings with many query keywords naturally embed closer to query
- Result: Both strategies favor the same listings

**Impact on Fusion:**
- Image kNN's unique signal gets diluted
- Text relevance is effectively double-counted
- Visual matches without keyword-rich descriptions are penalized twice

**Example:**
```
Property X: Modern glass architecture, minimal description ("Beautiful home")
- BM25: Rank 80 (no keywords → poor score)
- kNN Text: Rank 75 (short description → poor embedding match)
- kNN Image: Rank 2 (perfect visual match!)

RRF Score: 1/(60+80) + 1/(60+75) + 1/(60+2) = 0.0071 + 0.0074 + 0.0161 = 0.0306

Property Y: Traditional home, rich description with keywords
- BM25: Rank 2 (many keywords → great score)
- kNN Text: Rank 3 (detailed description → good embedding)
- kNN Image: Rank 45 (poor visual match)

RRF Score: 1/(60+2) + 1/(60+3) + 1/(60+45) = 0.0161 + 0.0159 + 0.0095 = 0.0415

Property Y wins (0.0415 > 0.0306) despite poor visual match!
```

**Status:** ⚠️ Known Limitation

**Potential Solutions:**
1. **Remove kNN text** for queries where visual matching is primary
2. **Use different text sources:**
   - BM25 on description
   - kNN text on AI-generated `visual_features_text` (image analysis captions)
   - This would reduce correlation
3. **De-duplicate signals** by detecting high correlation and down-weighting

---

### Issue 3: Adaptive Weighting Not Aggressive Enough

**Problem:** Current adaptive k-values provide modest weight adjustments (1.5x-2x), but strategy overlap requires more dramatic shifts.

**Current Adaptive Logic:**
```python
# Color query
bm25_k = 30      # 2x weight vs default (60)
image_k = 120    # 0.5x weight vs default (60)

# Impact on RRF scores:
# BM25 rank 10: 1/(30+10) = 0.025 (boosted)
# Image rank 10: 1/(120+10) = 0.0077 (reduced)
# Ratio: 0.025 / 0.0077 = 3.2x

# But with 2 text strategies + 1 visual strategy:
# Text contribution: 0.025 + 0.0167 (text kNN) = 0.0417
# Visual contribution: 0.0077
# Effective ratio: 0.0417 / 0.0077 = 5.4x text bias (too high!)
```

**Observation:** Even "aggressive" adaptive weighting doesn't overcome 2:1 strategy imbalance.

**Status:** ⚠️ Design Limitation

**Solution:** Combine adaptive weighting with strategy selection (remove redundant searches for certain queries).

---

### Issue 4: Tag Boosting Masks Relevance Issues

**Problem:** Tag boosting (2.0x multiplier) can elevate listings with perfect tag matches but poor overall relevance.

**Example:**
```
Query: "modern white house with pool"

Property A (mediocre relevance, perfect tags):
- RRF: 0.03 (low - bad visual/text match)
- Tags: 3/3 match → 2.0x boost
- Final: 0.03 × 2.0 = 0.06

Property B (excellent relevance, partial tags):
- RRF: 0.08 (high - great visual/text match!)
- Tags: 2/3 match → 1.25x boost
- Final: 0.08 × 1.25 = 0.10

Property B wins (correct), but gap is narrow (0.10 vs 0.06)
```

**Issue:** Tag boosting can compensate for poor fundamental relevance. If Property A's RRF were 0.04 instead of 0.03, it would win despite being a worse match overall.

**Why This Happens:**
- Tags are binary (match or no match)
- Doesn't account for "how well" the property matches the visual/semantic intent
- 2.0x boost is very aggressive

**Status:** ⚠️ Potential Over-Weighting

**Proposed Adjustments:**
```python
# Option 1: Reduce boost multipliers
if match_ratio >= 1.0:
    boost = 1.5  # Instead of 2.0
elif match_ratio >= 0.75:
    boost = 1.3  # Instead of 1.5
elif match_ratio >= 0.5:
    boost = 1.15 # Instead of 1.25

# Option 2: Make boost additive instead of multiplicative
final_score = rrf_score + (match_ratio * 0.02)
```

---

## Recommended Fixes (Prioritized)

### Priority 1: Address Strategy Overlap (High Impact)
**Fix:** For visual queries, remove kNN text search:
```python
def select_strategies(query_type, architecture_style):
    if query_type in ["visual_style", "color"] or architecture_style:
        return ["bm25", "image_knn"]  # Skip text kNN
    else:
        return ["bm25", "text_knn", "image_knn"]  # All three
```

**Impact:** Eliminates 2:1 text bias for visual queries, allows image similarity to have equal weight with text.

**Effort:** Low (1-2 hours implementation, 1-2 days testing)

### Priority 2: Implement More Aggressive Adaptive Weighting (Medium Impact)
**Fix:** Increase k-value range for dramatic weight shifts:
```python
if query_type == "visual_style":
    bm25_k = 120     # 0.5x weight (was 60)
    image_k = 20     # 3x weight (was 40)
    # Ratio: 120/20 = 6x favor visual

if query_type == "color":
    bm25_k = 15      # 4x weight (was 30)
    image_k = 180    # 0.33x weight (was 120)
    # Ratio: 15/180 = 12x favor text (colors in tags)
```

**Impact:** Stronger signal from primary strategy for each query type.

**Effort:** Low (1 hour implementation, 1-2 days testing)

### Priority 3: Reduce Tag Boost Multipliers (Low Impact)
**Fix:** Use more conservative boosting:
```python
if match_ratio >= 1.0:
    boost = 1.5  # Down from 2.0
elif match_ratio >= 0.75:
    boost = 1.3  # Down from 1.5
elif match_ratio >= 0.5:
    boost = 1.15 # Down from 1.25
```

**Impact:** Prevents tag matches from overriding fundamental relevance.

**Effort:** Low (5 minutes implementation, 1 day testing)

---

## Testing Plan for Fixes

### Test Suite 1: Visual Query Improvement
```python
queries = [
    "modern architecture with clean lines",
    "craftsman style home",
    "mid-century modern design",
    "contemporary glass house"
]

# For each query:
# 1. Run with current system
# 2. Run with strategy selection fix
# 3. Compare: Are visually similar homes ranking higher?
# 4. Metric: Image kNN top 5 should appear in final top 10
```

### Test Suite 2: Color Query Preservation
```python
queries = [
    "white house with blue door",
    "gray exterior",
    "beige home"
]

# Ensure color-based adaptive weighting still works correctly
# BM25 should still dominate (tags have exact colors)
```

### Test Suite 3: Balanced Query Stability
```python
queries = [
    "3 bedroom house with pool",
    "granite countertops and hardwood floors",
    "homes with mountain views"
]

# Ensure changes don't break feature-based queries
# All three strategies should contribute reasonably
```

---

## Path Forward

**Immediate Actions:**
1. ✅ Document all known issues (this section)
2. ⬜ Implement Priority 1 fix (strategy selection)
3. ⬜ Run Test Suite 1-3
4. ⬜ Deploy to staging Lambda for A/B testing
5. ⬜ Compare results with production system
6. ⬜ If successful, implement Priority 2 fix
7. ⬜ Repeat testing and comparison
8. ⬜ Deploy to production

**Success Metrics:**
- Visual queries: Top 10 results should have 50%+ overlap with image kNN top 10 (currently ~20%)
- Color queries: BM25 dominance preserved (>60% of RRF score from BM25)
- Balanced queries: No single strategy contributes >50% of RRF score

**Timeline:** 2-3 weeks for full implementation and validation
