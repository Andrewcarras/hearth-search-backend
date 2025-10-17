# Hearth Search Infrastructure Deep Dive - Part 1 of 2
**Complete Technical Documentation: BM25, Vector Search, and OpenSearch**

---

## Table of Contents - Part 1

1. [Introduction and Overview](#introduction-and-overview)
2. [BM25 Algorithm in OpenSearch](#bm25-algorithm-in-opensearch)
3. [kNN Vector Search Fundamentals](#knn-vector-search-fundamentals)
4. [Vector Embeddings Deep Dive](#vector-embeddings-deep-dive)
5. [OpenSearch kNN Implementation](#opensearch-knn-implementation)

**See Part 2 for:**
- Embedding Spaces and Multimodal Models
- Amazon Titan Models Specifications
- Hearth System Implementation Details
- Complete Code Examples and Best Practices

---

## Introduction and Overview

This document provides a complete technical explanation of the Hearth real estate search system, covering every component from theoretical foundations to production implementation.

### System Architecture Overview

The Hearth search system implements a sophisticated **hybrid semantic search** combining three complementary strategies:

```
User Query: "modern white kitchen with marble countertops"
         ↓
    [Query Processing]
         ↓
    ┌────┴────┬──────────┬─────────┐
    ↓         ↓          ↓         ↓
  BM25    kNN Text   kNN Image   Filters
(keywords) (semantic) (visual)  (price, beds)
    ↓         ↓          ↓         ↓
    └────┬────┴──────────┴─────────┘
         ↓
  [RRF Score Fusion]
         ↓
  [Tag Boosting]
         ↓
   Top 20 Results
```

**Three Search Strategies:**

1. **BM25 (Best Matching 25)**: Keyword-based text search with field boosting
   - Scores documents based on term frequency and rarity
   - Searches: description, visual_features_text, address, tags
   - Best for: Specific features ("granite countertops", "3 bedrooms")

2. **kNN Text Search**: Semantic vector similarity using text embeddings
   - Converts text to 1024-dimensional vectors
   - Finds semantically similar properties
   - Best for: Conceptual matches ("cozy home", "modern aesthetic")

3. **kNN Image Search**: Visual similarity using image embeddings
   - Multiple images per property (nested vectors)
   - Finds visually similar properties
   - Best for: Visual style matching ("similar to this kitchen")

**Score Fusion:**
- **RRF (Reciprocal Rank Fusion)**: Combines rankings from all three strategies
- **Adaptive Weights**: Query-type-aware k-values (color queries boost BM25, visual queries boost images)
- **Tag Boosting**: Post-RRF multiplicative boost for feature tag matches

---

## BM25 Algorithm in OpenSearch

### What is BM25?

BM25 (Best Matching 25) is the industry-standard probabilistic ranking function used by modern search engines. It estimates document relevance by measuring how well query terms appear in documents while accounting for term rarity and document length.

**Why BM25 replaced TF-IDF:**
- **Saturation**: Prevents keyword stuffing (10 mentions ≠ 10x relevance)
- **Length normalization**: Fair comparison across document sizes
- **Probabilistic foundation**: Theoretically grounded in information retrieval theory
- **Empirically superior**: Consistently outperforms TF-IDF in benchmarks

### The Complete BM25 Formula

```
score(D,Q) = Σ IDF(qᵢ) · [f(qᵢ,D) · (k₁ + 1)] / [f(qᵢ,D) + k₁ · (1 - b + b · |D|/avgdl)]
```

**Components Explained:**

**IDF (Inverse Document Frequency):**
```
IDF(qᵢ) = ln[(N - n + 0.5) / (n + 0.5) + 1]

Where:
- N = total documents in index
- n = documents containing term qᵢ
- +0.5 = smoothing factor
- +1 = ensure positive scores
```

**Key Insight**: Rare terms (low n) get higher IDF, making them more valuable for ranking.

**Example:**
```
Index: 1,000,000 properties

Term "pool":
- Appears in 50,000 properties (5%)
- IDF = ln[(1,000,000 - 50,000 + 0.5) / (50,000 + 0.5) + 1]
- IDF ≈ 3.04

Term "modern":
- Appears in 200,000 properties (20%)
- IDF = ln[(1,000,000 - 200,000 + 0.5) / (200,000 + 0.5) + 1]
- IDF ≈ 1.79

"Pool" is 1.7x more valuable than "modern" for ranking
```

**TF Component (Term Frequency with Saturation):**
```
TF = [f(qᵢ,D) · (k₁ + 1)] / [f(qᵢ,D) + k₁ · (1 - b + b · |D|/avgdl)]

Where:
- f(qᵢ,D) = term frequency (count in document)
- k₁ = saturation parameter (default: 1.2)
- b = length normalization (default: 0.75)
- |D| = document length
- avgdl = average document length
```

**Saturation Effect (k₁ = 1.2, ignoring length for clarity):**
```
1 occurrence  → TF ≈ 0.55
2 occurrences → TF ≈ 0.88  (1.6x increase)
3 occurrences → TF ≈ 1.05  (1.2x increase)
10 occurrences → TF ≈ 1.57 (1.5x increase from 3)
100 occurrences → TF ≈ 1.98 (approaches asymptote at k₁+1 = 2.2)
```

Notice how additional occurrences have diminishing returns!

### BM25 Parameters

#### Parameter k₁: Term Frequency Saturation Control

**Default:** 1.2
**Range:** 1.0 - 2.0

**What it controls:** How quickly term frequency reaches saturation point.

**Higher k₁ (e.g., 2.0):**
- Slower saturation
- Additional term occurrences continue boosting score significantly
- Better for: Technical documents, keyword-dense content, long-form text
- Example: Research papers where repeated technical terms indicate relevance

**Lower k₁ (e.g., 0.8):**
- Faster saturation
- Diminishing returns kick in quickly
- Better for: Short documents, spam prevention, natural language
- Example: Product descriptions where 1-2 mentions are sufficient

**Practical Example:**
```
Query: "granite countertops"
Document A: "granite countertops" mentioned 2 times (k₁=1.2)
Document B: "granite countertops" mentioned 10 times (k₁=1.2)

Score ratio: ~1.8x (not 5x!)

With k₁=0.5: Score ratio: ~1.3x (even more saturation)
With k₁=2.0: Score ratio: ~2.5x (less saturation)
```

#### Parameter b: Document Length Normalization

**Default:** 0.75
**Range:** 0.0 - 1.0

**What it controls:** How much document length affects scoring.

The normalization factor in the formula:
```
1 - b + b · |D|/avgdl
```

**b = 0 (no normalization):**
- Document length has no effect on scoring
- Longer documents have advantage (more opportunities for matches)
- Best for: Homogeneous collections where longer = more comprehensive
- Example: All property descriptions are ~200 words

**b = 1 (full normalization):**
- Heavily penalizes longer documents
- Term frequency divided by document length
- Best for: Heterogeneous collections with varying sizes
- Example: Mix of short (tweets) and long (articles) documents

**b = 0.75 (default, partial normalization):**
- Balanced approach
- Some penalty for length but not extreme
- Works well for most use cases

**Practical Example:**
```
Query: "modern kitchen"
Average document length: 100 words

Document A: 50 words (short), contains "modern kitchen" once
Document B: 200 words (long), contains "modern kitchen" once

With b=0 (no normalization):
  Both get same TF score (length doesn't matter)

With b=1 (full normalization):
  Doc A gets 2x the score (penalize long doc)
  Normalization factor A: 1 - 1 + 1 · 50/100 = 0.5
  Normalization factor B: 1 - 1 + 1 · 200/100 = 2.0
  Doc A TF is 4x higher than Doc B

With b=0.75 (default):
  Doc A gets ~1.6x the score (moderate penalty)
  Normalization factor A: 1 - 0.75 + 0.75 · 50/100 = 0.625
  Normalization factor B: 1 - 0.75 + 0.75 · 200/100 = 1.75
  Doc A TF is ~2.8x higher than Doc B
```

### BM25 in OpenSearch Implementation

OpenSearch uses BM25 as the **default similarity algorithm** for all text fields. Every `match`, `multi_match`, and `match_phrase` query uses BM25 scoring automatically.

**Version Note:**
- **OpenSearch 3.0+**: Native Lucene `BM25Similarity` (cleaner normalization)
- **Before 3.0**: `LegacyBM25Similarity` (included extra k₁+1 factor)
- **Impact**: Scores in 3.0+ are ~2.2x lower but ranking order unchanged

### Field-Level Boosting

Field boosting multiplies BM25 scores by a constant:

```json
{
  "query": {
    "multi_match": {
      "query": "modern kitchen granite countertops",
      "fields": [
        "description^3.0",           // 3x weight
        "visual_features_text^2.5",  // 2.5x weight
        "address^0.5",               // 0.5x weight
        "tags^1.5"                   // 1.5x weight
      ]
    }
  }
}
```

**How Boosting Works:**
```
Final score = (3.0 × BM25_description) + (2.5 × BM25_visual) + (0.5 × BM25_address) + (1.5 × BM25_tags)
```

**Real Example from Hearth System:**

Query: "modern kitchen with granite countertops"

```
Property #123:
  description: "Beautiful modern kitchen renovation with granite..."
    - BM25 score: 8.2
    - Boosted: 8.2 × 3.0 = 24.6

  visual_features_text: "Interior features: granite countertops, stainless appliances..."
    - BM25 score: 5.4
    - Boosted: 5.4 × 2.5 = 13.5

  address: "123 Modern Street"
    - BM25 score: 2.1
    - Boosted: 2.1 × 0.5 = 1.05

  tags: ["modern", "updated_kitchen"]
    - BM25 score: 3.0
    - Boosted: 3.0 × 1.5 = 4.5

Total BM25 score: 24.6 + 13.5 + 1.05 + 4.5 = 43.65
```

**Best Practices for Field Boosting:**
- **Keep boosts moderate**: 0.5x to 5x range (avoid >10x)
- **Title/description highest**: Most curated, highest relevance
- **Structured fields moderate**: Tags, categories have good signal
- **Address/metadata lowest**: Less relevant for content matching
- **Rationale**: Extreme boosts (100x) make other fields irrelevant

### Multi-Match Query Types

The `multi_match` query supports different types that fundamentally change scoring behavior:

#### 1. best_fields (Default)

**Behavior:**
- Runs separate `match` query for each field
- Wraps in `dis_max` (disjunction max) query
- Takes **maximum score** from any field
- Uses `tie_breaker` to include other fields

**Formula:**
```
score = max(field_scores) + tie_breaker × sum(other_field_scores)
```

**Default tie_breaker:** 0.0 (only best field counts)

**When to use:**
- Multi-word queries best found in **same field**
- Want best matching field to dominate
- Example: "modern white kitchen" → better when all terms in description

**Example:**
```json
{
  "multi_match": {
    "query": "modern white kitchen",
    "fields": ["description^3", "tags"],
    "type": "best_fields",
    "tie_breaker": 0.3
  }
}

Result:
  description score: 10.5
  tags score: 3.2
  Final: 10.5 + (0.3 × 3.2) = 11.46
```

#### 2. most_fields

**Behavior:**
- Runs `match` query for each field
- **Sums all field scores** together
- All matching fields contribute equally

**Formula:**
```
score = sum(all_field_scores)
```

**When to use:**
- Same content analyzed differently (stemming, synonyms, original)
- Want to maximize coverage across all fields
- Reward documents matching in multiple places

**Example:**
```json
{
  "multi_match": {
    "query": "running",
    "fields": ["title", "title.stemmed", "title.synonyms"],
    "type": "most_fields"
  }
}

Result:
  title score: 2.5 (exact "running")
  title.stemmed: 2.8 (matches "run", "runs")
  title.synonyms: 2.3 (matches "jogging")
  Final: 2.5 + 2.8 + 2.3 = 7.6
```

#### 3. cross_fields

**Behavior:**
- **Term-centric** (not field-centric)
- Searches each term across all fields as if one big field
- Uses combined field statistics for IDF
- Can apply `operator` and `minimum_should_match` across all fields

**When to use:**
- Structured data where terms split across fields
- Names, addresses, multi-part identifiers
- Want terms matched across different fields

**Critical Difference:**

**best_fields** (field-centric):
```
Query: "Will Smith"
Document: title="Will Rogers talks about Smith Street"
Result: HIGH SCORE (both terms in one field)
```

**cross_fields** (term-centric):
```
Query: "Will Smith"
Document: first_name="Will", last_name="Smith"
Result: HIGH SCORE (terms across related fields)

Document: title="Will Rogers talks about Smith Street"
Result: LOWER SCORE (terms far apart, not structured match)
```

**Example:**
```json
{
  "multi_match": {
    "query": "Will Smith",
    "fields": ["first_name", "last_name"],
    "type": "cross_fields",
    "operator": "and"
  }
}
```

**Comparison Table:**

| Type | Scoring Approach | Best For | Example Use Case |
|------|------------------|----------|------------------|
| `best_fields` | max(scores) + tie | Multi-word in same field | "modern kitchen remodel" |
| `most_fields` | sum(all scores) | Same content, different analysis | Stemmed + synonym variants |
| `cross_fields` | Term-centric across fields | Structured multi-field data | Person names, addresses |

### Match vs Match Phrase

Both use BM25 but with different matching requirements:

#### Match Query

**Behavior:**
- Analyzes query into individual terms
- Matches documents with **any** term (OR by default)
- Terms can appear anywhere in any order
- Each term scored independently

**Example:**
```json
{
  "match": {
    "description": {
      "query": "modern white kitchen",
      "operator": "or"  // default
    }
  }
}

Matches:
  ✓ "modern kitchen with granite"
  ✓ "white cabinets and appliances"
  ✓ "kitchen remodel featuring modern design"
  ✓ "beautiful white and gray home"

Score = BM25(modern) + BM25(white) + BM25(kitchen)
```

#### Match Phrase Query

**Behavior:**
- Requires terms in **exact order**
- Uses positional information from inverted index
- Can use `slop` parameter for fuzzy matching
- Higher scoring than match but more restrictive

**Example:**
```json
{
  "match_phrase": {
    "description": {
      "query": "modern white kitchen",
      "slop": 0  // default, no words between
    }
  }
}

Matches (slop=0):
  ✓ "This home has a modern white kitchen with granite"
  ✗ "modern kitchen with white cabinets"  (wrong order)
  ✗ "modern and white kitchen"  (word between)

With slop=1 (allows 1 edit):
  ✓ "modern white kitchen"
  ✓ "modern designer white kitchen"  (1 word inserted)
  ✓ "white modern kitchen"  (1 position swap)
```

**Slop Explanation:**

Slop is the number of position changes needed to match the phrase:

```
Query: "modern white kitchen" (positions: 0, 1, 2)

Text: "modern white kitchen"
  Positions match: 0, 1, 2
  Edits needed: 0
  Match with slop=0: ✓

Text: "modern designer white kitchen"
  Positions: modern=0, white=2, kitchen=3
  Expected: 0, 1, 2
  Edits: white moved right 1, kitchen moved right 1
  Match with slop=2: ✓

Text: "white modern kitchen"
  Positions: white=0, modern=1, kitchen=2
  Expected positions: modern=0, white=1, kitchen=2
  Edits: swap white and modern (counts as 2 position changes)
  Match with slop=2: ✓
```

**Performance:**
- `match`: Fast (simple term lookup)
- `match_phrase`: Slower (requires positional data)
- Use `match_phrase` only when word order matters

### Boolean Query Score Combination

Boolean queries combine multiple clauses with different scoring behaviors:

```json
{
  "bool": {
    "must": [/* queries that must match, contribute to score */],
    "should": [/* queries that optionally match, contribute to score */],
    "filter": [/* queries that must match, NO score */],
    "must_not": [/* queries that must NOT match, NO score */]
  }
}
```

#### must Clause

**Behavior:**
- All queries must match (AND logic)
- **Contributes to score**
- Scores are summed

**Formula:**
```
score = score_must_1 + score_must_2 + ... + score_must_n
```

**Example:**
```json
{
  "bool": {
    "must": [
      {"match": {"description": "modern kitchen"}},  // Score: 8.5
      {"match": {"tags": "updated"}}                 // Score: 2.3
    ]
  }
}

Final score: 8.5 + 2.3 = 10.8
```

#### should Clause

**Behavior:**
- Optional matches (OR logic)
- More matches = higher score
- **Contributes to score**
- Becomes required if no `must` or `filter` (unless `minimum_should_match=0`)

**Formula:**
```
score = score_should_1 + score_should_2 + ... + score_should_n
```

**Example:**
```json
{
  "bool": {
    "must": [
      {"match": {"description": "kitchen"}}
    ],
    "should": [
      {"match": {"tags": "granite"}},      // Score: 1.5 (if present)
      {"match": {"tags": "stainless"}},    // Score: 1.2 (if present)
      {"match": {"tags": "hardwood"}}      // Score: 0.8 (if present)
    ],
    "minimum_should_match": 0  // All optional
  }
}

Result examples:
  Property with granite: 8.0 + 1.5 = 9.5
  Property with granite + stainless: 8.0 + 1.5 + 1.2 = 10.7
  Property with all three: 8.0 + 1.5 + 1.2 + 0.8 = 11.5
```

#### filter Clause

**Behavior:**
- Must match (AND logic)
- **Does NOT contribute to score**
- Results are **cached** by OpenSearch
- Much faster than `must` for binary conditions

**Example:**
```json
{
  "bool": {
    "must": [
      {"match": {"description": "modern kitchen"}}  // Score: 8.5
    ],
    "filter": [
      {"term": {"status": "active"}},               // No score
      {"range": {"price": {"lte": 1000000}}}        // No score
    ]
  }
}

Final score: 8.5 (filters don't affect score)
```

**When to use filter:**
- Price ranges, date ranges
- Category selection (status, type)
- Binary yes/no conditions
- Any filtering that doesn't indicate relevance

**Performance Benefit:**
- Filters are cached aggressively
- Executed once, reused for many queries
- Can use bitsets for fast evaluation

#### must_not Clause

**Behavior:**
- Documents must NOT match
- **Does NOT contribute to score**
- Excludes documents from results

**Example:**
```json
{
  "bool": {
    "must": [
      {"match": {"description": "home"}}
    ],
    "must_not": [
      {"match": {"tags": "under_construction"}},
      {"match": {"description": "rendering"}}
    ]
  }
}

Result: Only active homes, no construction or renderings
```

**Complete Example:**

```json
{
  "bool": {
    "must": [
      {"match": {"description": "modern kitchen"}}      // +8.5 score
    ],
    "should": [
      {"match_phrase": {"description": "modern kitchen"}},  // +2.0 bonus if exact phrase
      {"match": {"tags": "updated"}}                    // +1.5 bonus if tagged
    ],
    "filter": [
      {"term": {"status": "active"}},                   // No score
      {"range": {"price": {"gte": 500000, "lte": 1000000}}},  // No score
      {"term": {"bedrooms": 3}}                         // No score
    ],
    "must_not": [
      {"match": {"description": "under construction"}}  // Exclude
    ],
    "minimum_should_match": 0  // should clauses are optional
  }
}

Scoring:
  Base (must): 8.5
  Bonus (should): 0 to 3.5 depending on matches
  Final: 8.5 to 12.0
  Filters reduce result set but don't affect scores
```

### BM25 Configuration in OpenSearch

#### Index-Time Configuration

```json
PUT /hearth-listings
{
  "settings": {
    "index": {
      "similarity": {
        "custom_bm25": {
          "type": "BM25",
          "k1": 1.2,
          "b": 0.75,
          "discount_overlaps": true
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "similarity": "custom_bm25"
      },
      "visual_features_text": {
        "type": "text",
        "similarity": "custom_bm25"
      }
    }
  }
}
```

#### Per-Field Similarity

Different fields can use different parameters:

```json
{
  "settings": {
    "similarity": {
      "title_sim": {
        "type": "BM25",
        "k1": 1.5,
        "b": 0.5  // Titles are short, less length penalty
      },
      "content_sim": {
        "type": "BM25",
        "k1": 1.2,
        "b": 0.9  // Content varies, more length penalty
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {"type": "text", "similarity": "title_sim"},
      "content": {"type": "text", "similarity": "content_sim"}
    }
  }
}
```

### BM25 Best Practices

**1. Start with defaults** (k₁=1.2, b=0.75)
- Works well for 90% of use cases
- Only tune if you have evidence of problems

**2. Use field boosting strategically**
```json
"fields": [
  "title^3",        // Most important
  "tags^2",         // Curated metadata
  "description"     // Full text
]
```

**3. Use filters for binary conditions**
```json
{
  "bool": {
    "must": [{"match": {"content": "search"}}],
    "filter": [
      {"term": {"status": "published"}},  // Cached, fast
      {"range": {"date": {"gte": "2024-01-01"}}}
    ]
  }
}
```

**4. Avoid over-boosting**
- Keep boosts between 0.5x and 5x
- Boosts >10x make other fields irrelevant

**5. Use Explain API for debugging**
```bash
GET /my-index/_explain/doc_id
{
  "query": {
    "match": {"content": "modern kitchen"}
  }
}
```

Returns complete score breakdown with all BM25 components.

---

## kNN Vector Search Fundamentals

### What is k-Nearest Neighbors?

k-Nearest Neighbors (k-NN) is an algorithm that finds the k most similar items to a query by comparing vector representations in a high-dimensional space.

**Core Concept:**
```
Given:
  - Query vector Q
  - Database of N document vectors
  - Distance metric (cosine similarity)

Find: k documents with smallest distance to Q
```

**Traditional Search vs Semantic Search:**

| Aspect | Keyword Search (BM25) | Semantic Search (kNN) |
|--------|----------------------|----------------------|
| Matching | Exact lexical terms | Conceptual meaning |
| "Buy sneakers" | Only matches "sneakers" | Matches "running shoes", "athletic footwear" |
| Synonyms | Must include variants | Understands equivalence |
| Misspellings | Typically fails | Often handles well |
| Context | No understanding | Contextually aware |

### Distance Metrics

kNN relies on distance metrics to measure vector similarity:

#### Cosine Similarity (Recommended for Embeddings)

Measures angle between vectors, ignoring magnitude:

```
cosine_similarity(A, B) = (A · B) / (||A|| × ||B||)

Result: -1 (opposite) to 1 (identical), 0 = orthogonal
```

**Properties:**
- Focuses on direction, not magnitude
- Invariant to vector scaling
- Perfect for normalized embeddings
- Most embedding models trained with cosine

**Example:**
```
Vector A (dog): [0.8, 0.6, 0.1]
Vector B (puppy): [0.75, 0.65, 0.05]
Vector C (car): [-0.2, 0.1, 0.9]

cosine(A, B) = 0.96 (highly similar)
cosine(A, C) = 0.15 (dissimilar)
```

**Why cosine for embeddings:**
1. Embedding models encode meaning in direction, not magnitude
2. Training objectives optimize cosine similarity
3. Normalized vectors make cosine = dot product (efficient)
4. Stable in high dimensions (768-1536 dims)

#### Euclidean Distance (L2)

Straight-line distance in space:

```
euclidean(A, B) = √(Σ(A_i - B_i)²)

Result: 0 (identical) to ∞ (very different)
```

**When to use:**
- Spatial data (coordinates, measurements)
- Vector magnitude contains information
- Low-dimensional data

**Relationship to cosine:**
For normalized vectors:
```
euclidean_distance = √(2(1 - cosine_similarity))
```

They rank results identically on normalized data!

#### Dot Product (Inner Product)

Sum of element-wise products:

```
dot_product(A, B) = Σ(A_i × B_i)

Result: -∞ to ∞ (higher = more similar)
```

**When to use:**
- Pre-normalized embeddings
- When both direction and magnitude matter
- Computationally efficient

**Note:** For unit vectors, dot product = cosine similarity

---

## Vector Embeddings Deep Dive

### What Are Embeddings?

Embeddings are dense numerical representations that encode semantic meaning as vectors in a continuous space where similarity is measured by proximity.

```
Text: "golden retriever puppy"
↓ [Embedding Model]
Vector: [0.23, -0.45, 0.89, 0.12, ..., -0.34] (1024 dimensions)
```

**Key Properties:**
- **Dense**: Most values non-zero (vs sparse one-hot encoding)
- **Fixed-size**: Always same dimensions regardless of input length
- **Semantic**: Similar concepts → nearby vectors
- **Learned**: Generated by neural networks trained on massive data

### How Neural Networks Generate Embeddings

**Training Process:**

1. **Data Collection**: Billions of text examples
2. **Model Architecture**: Transformer (BERT, GPT-based)
3. **Training Objective**: Contrastive learning
4. **Output**: Model that maps text → vectors

**Contrastive Learning:**
```
Positive pairs (similar):
  "dog" ↔ "puppy" → pull vectors together

Negative pairs (dissimilar):
  "dog" ↔ "car" → push vectors apart

Result: Semantic meaning encoded in geometry
```

**Inference (Generating an Embedding):**

```
Input: "modern white kitchen"
    ↓
[1] Tokenization: ["modern", "white", "kitchen"]
    ↓
[2] Token Embeddings: [[0.1, 0.2, ...], [0.3, 0.4, ...], [0.5, 0.6, ...]]
    ↓
[3] Positional Encoding: Add position information
    ↓
[4] Transformer Layers: 12-24 layers of self-attention
    ↓
[5] Pooling: Mean or CLS token extraction
    ↓
Output: [0.23, -0.45, 0.89, ..., 0.12] (1024-D vector)
```

### Embedding Dimensions

Common dimensions and their trade-offs:

| Dimensions | Use Case | Quality | Speed | Storage (1M docs) |
|-----------|----------|---------|-------|-------------------|
| 256 | Prototyping, mobile | 97% | Fastest | 1 GB |
| 384 | Lightweight production | 98% | Fast | 1.5 GB |
| 512 | Balanced production | 99% | Medium | 2 GB |
| 768 | BERT-base standard | 99.5% | Medium | 3 GB |
| 1024 | High quality (Titan default) | 100% | Slower | 4 GB |
| 1536 | OpenAI ada-002 | 100% | Slowest | 6 GB |

**Matryoshka Representation Learning (MRL):**
Modern models allow dimension truncation without retraining:
- Train at 3072 dimensions
- Use any lower dimension (1024, 512, 256)
- Graceful quality degradation

**Storage Calculation:**
```
Storage = num_docs × dimensions × 4 bytes (float32)

1M docs × 1024 dims × 4 bytes = 4 GB
1M docs × 512 dims × 4 bytes = 2 GB (50% savings)
```

### Why Embeddings Capture Semantic Meaning

**Distributional Hypothesis:**
> "Words appearing in similar contexts have similar meanings"

Neural networks learn this by observing billions of examples.

**Geometric Properties:**

1. **Similarity = Proximity**
```
"dog", "puppy", "canine" → cluster together
"car", "vehicle", "automobile" → separate cluster
```

2. **Vector Arithmetic**
```
vector("king") - vector("man") + vector("woman") ≈ vector("queen")
vector("Paris") - vector("France") + vector("Italy") ≈ vector("Rome")
```

3. **Contextual Sensitivity**
Modern models (BERT) generate different vectors for same word in different contexts:
```
"bank" in "river bank" → vector_1
"bank" in "savings bank" → vector_2
```

4. **Hierarchical Structure**
```
Broad categories: "animal" vs "vehicle" (far apart)
Fine-grained: "cat" vs "lion" vs "tiger" (nearby but distinct)
```

**Visualization (Conceptual 2D projection of 1024-D space):**

```
          modern ●
              ● contemporary
        ● sleek
              ● minimalist

  traditional ●
        ● classic
    ● vintage
            ● rustic

(Real space is 1024 dimensions, not 2D!)
```

---

## OpenSearch kNN Implementation

### OpenSearch kNN Architecture

OpenSearch provides native vector search through its kNN plugin:

**Components:**

1. **Custom Codec**: Writes vectors to native library indices
2. **Native Libraries**: FAISS, NMSLIB, or Lucene for vector ops
3. **Index Structure**: Combines inverted index + vector graph
4. **Memory Management**: Native memory (outside JVM heap)

**Index Creation:**

```json
PUT /hearth-listings-v2
{
  "settings": {
    "index": {
      "knn": true,
      "knn.algo_param.ef_search": 100
    }
  },
  "mappings": {
    "properties": {
      "vector_text": {
        "type": "knn_vector",
        "dimension": 1024,
        "method": {
          "name": "hnsw",
          "engine": "lucene",
          "space_type": "cosinesimil",
          "parameters": {
            "ef_construction": 128,
            "m": 16
          }
        }
      }
    }
  }
}
```

### HNSW Algorithm (Hierarchical Navigable Small World)

HNSW is the state-of-the-art algorithm for approximate nearest neighbor search.

**Core Idea:** Multi-layer graph with skip-list structure

```
Layer 2: [●]----------------[●]  (sparse, long links)
           ↓                  ↓
Layer 1: [●]------[●]-------[●]-------[●]  (medium density)
           ↓       ↓         ↓         ↓
Layer 0: [●]-[●]-[●]-[●]-[●]-[●]-[●]-[●]  (all nodes, short links)
```

**Search Process:**

1. **Start**: Top layer at entry point
2. **Greedy traversal**: Move to closest neighbor
3. **Descend**: When no closer neighbors, go to next layer
4. **Refine**: Bottom layer finds exact k-nearest
5. **Return**: Top-k results

**Time Complexity:**
- Search: O(log n) average
- Insertion: O(log n)
- Construction: O(n log n)

**Memory Requirements:**
```
Memory per vector ≈ 1.1 × (4 × dimension + 8 × M) bytes

Example (1M vectors, 1024-D, M=16):
Memory ≈ 1.1 × (4 × 1024 + 8 × 16) × 1,000,000
       ≈ 1.1 × 4,224 × 1,000,000
       ≈ 4.6 GB
```

### OpenSearch kNN Engines

**1. Lucene (Recommended for most use cases)**

**Pros:**
- Native to OpenSearch (no external deps)
- Best latency for < few million vectors
- Most memory-efficient
- Excellent filtering support
- Smart automatic strategy selection

**Cons:**
- Max 1,024 dimensions
- Not optimal for > 5M vectors
- Lower recall at very high k

**When to use:** Most production systems

**2. Faiss (Facebook AI Similarity Search)**

**Pros:**
- Scales to billions of vectors
- Supports up to 16,000 dimensions
- Advanced optimization (IVF, PQ)
- GPU acceleration available

**Cons:**
- External library dependency
- Higher memory usage
- More complex configuration

**When to use:** Large-scale (>5M vectors), high dimensions

**3. NMSLIB (DEPRECATED in OpenSearch 3.0)**

Migrate existing indices to Lucene or Faiss.

**Engine Comparison:**

| Feature | Lucene | Faiss | NMSLIB |
|---------|--------|-------|--------|
| Max Dimensions | 1,024 | 16,000 | 16,000 |
| Optimal Size | < 5M | Millions to billions | N/A |
| Memory Efficiency | Best | Good | Fair |
| Filtering | Excellent | Good | Basic |
| Status | Active | Active | Deprecated |

### kNN Query Parameters

**Basic Query:**

```json
GET /hearth-listings-v2/_search
{
  "size": 20,
  "query": {
    "knn": {
      "vector_text": {
        "vector": [0.23, -0.45, 0.89, ..., 0.12],
        "k": 50
      }
    }
  }
}
```

**Key Parameters:**

**1. k (required)**
- Number of nearest neighbors to retrieve
- Larger k = more candidates = better recall = slower
- Typical: 10-100
- **Important**: OpenSearch may return < k after filtering

**2. vector (required)**
- Query vector (must match indexed dimension)
- Generated by same embedding model as indexed docs

**3. ef_search (query-time, optional)**
- Size of candidate list during HNSW traversal
- Higher = better recall, slower queries
- Default: varies by engine (100-512)
- **Rule of thumb**: ef_search ≥ k, typically 2-10x k

```json
{
  "knn": {
    "vector_text": {
      "vector": [...],
      "k": 20,
      "method_parameters": {
        "ef_search": 100  // Check 100 candidates to find top 20
      }
    }
  }
}
```

**4. ef_construction (index-time, in mapping)**
- Candidate list size during index building
- Higher = better graph quality = slower indexing
- Typical: 100-512

**5. m (index-time, in mapping)**
- Max bidirectional links per node
- Higher = better recall = more memory = slower indexing
- Typical: 16-48
- Memory impact: ~8 bytes per link per vector

**Parameter Tuning Guide:**

| Priority | ef_construction | m | ef_search | k |
|----------|----------------|---|-----------|---|
| Speed | 64 | 8 | 20 | 10 |
| Balanced | 128 | 16 | 100 | 20 |
| Accuracy | 256 | 32 | 512 | 50 |

### Approximate vs Exact kNN

**Approximate kNN (Default):**
- Uses HNSW graph for O(log n) search
- 95-99% recall (misses some true neighbors)
- Fast, scalable to billions of vectors
- Production standard

**Exact kNN:**
- Brute force: compares query to every vector
- 100% recall (guaranteed true k-nearest)
- O(n) complexity (slow for large datasets)
- Only practical for < 10K documents

**When to use exact:**
- Small datasets (< 10,000 docs)
- Validation/benchmarking
- When perfect recall required

**Performance Comparison (1M vectors, 768-D):**
```
Approximate kNN: 5-20ms, 95-99% recall
Exact kNN:       200-500ms, 100% recall
```

---

**Continue to Part 2 for:**
- Multi-vector search (nested image embeddings)
- Filtering strategies with kNN
- Embedding spaces and multimodal models
- Amazon Titan model specifications
- Hearth system implementation details
- Complete production examples and best practices
