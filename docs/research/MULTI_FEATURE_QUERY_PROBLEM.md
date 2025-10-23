# Multi-Feature Query Problem: "Show me a white house with granite countertops"

## The Problem

**Query**: "Show me a white house with granite countertops"

**Current Behavior** (with `score_mode: "max"`):

A property has 5 images:
1. **Exterior photo**: White house exterior → Similarity to query: **0.65** (partial match - "white house")
2. **Kitchen photo**: Granite countertops → Similarity to query: **0.72** (partial match - "granite countertops")
3. **Bedroom**: No match → Similarity: **0.15**
4. **Bathroom**: No match → Similarity: **0.18**
5. **Living room**: No match → Similarity: **0.12**

With `score_mode: "max"`:
- **Property score = 0.72** (takes kitchen photo - highest single match)
- **Only the kitchen photo matters!**
- The white exterior photo (0.65) is **ignored**

## The Issue Visualized

```
Query: "white house with granite countertops"
          ↓
   Embedding: [0.045, -0.132, 0.298, ...]
          ↓
   Compare to ALL property images:

Property A (Perfect - has both features):
  Image 1 (exterior): White house     → sim = 0.65 ⚠️ IGNORED
  Image 2 (kitchen):  Granite counter → sim = 0.72 ✓ USED (max)
  Image 3 (bedroom):  Generic         → sim = 0.15
  ────────────────────────────────────────────────
  Final score: 0.72 (only kitchen counts)

Property B (Interior-only - granite but NOT white):
  Image 1 (exterior): Brick house     → sim = 0.28
  Image 2 (kitchen):  Granite counter → sim = 0.78 ✓ USED (max)
  Image 3 (bedroom):  Generic         → sim = 0.16
  ────────────────────────────────────────────────
  Final score: 0.78 (only kitchen counts)

❌ Property B ranks HIGHER than Property A!
   But Property B doesn't have white exterior!
```

## Why This Happens

The query embedding **"white house with granite countertops"** contains BOTH concepts:
- White exterior visual features
- Granite countertop visual features

A **single image** can only show ONE of these (exterior OR interior).

With `score_mode: "max"`:
- We pick whichever image scores highest
- But that image only matches ONE feature
- The other feature is completely ignored!

**Result**: Properties with BOTH features don't score higher than properties with ONE feature.

## Real-World Example

```
Query: "modern white kitchen with marble countertops"

Property A (Has everything):
  - Exterior: Modern white house        → sim = 0.62
  - Kitchen: Marble countertops         → sim = 0.75 ← MAX
  - Living room: Modern design          → sim = 0.58
  SCORE: 0.75

Property B (Only has kitchen):
  - Exterior: Old brick house           → sim = 0.25
  - Kitchen: Marble countertops         → sim = 0.80 ← MAX
  - Bedroom: Outdated                   → sim = 0.18
  SCORE: 0.80

Property C (Only has exterior):
  - Exterior: Modern white house        → sim = 0.85 ← MAX
  - Kitchen: Laminate countertops       → sim = 0.30
  - Bedroom: Generic                    → sim = 0.20
  SCORE: 0.85

RANKING:
1. Property C (0.85) - Has modern white exterior but NO marble
2. Property B (0.80) - Has marble but NO white exterior
3. Property A (0.75) - HAS BOTH! But ranks LOWEST!

❌ The property with BOTH features ranks WORST!
```

## Why We Use max Currently

From the audit and Part 1 documentation, `score_mode: "max"` was chosen because:

1. ✅ **Variable image counts**: Properties have 2-20 images
2. ✅ **Not all images relevant**: Only kitchen photo matters for kitchen query
3. ✅ **Best single match**: Find the ONE perfect image

**This works great for SINGLE-feature queries:**
- "modern kitchen" → Kitchen photo gets high score ✓
- "brick exterior" → Exterior photo gets high score ✓

**But fails for MULTI-feature queries:**
- "white house with granite countertops" → Can't reward BOTH features ✗

## Alternative: score_mode: "sum"

```
Property A (Has everything):
  - Exterior: Modern white house        → sim = 0.62
  - Kitchen: Marble countertops         → sim = 0.75
  - Living room: Modern design          → sim = 0.58
  SCORE: 0.62 + 0.75 + 0.58 + 0.15 + 0.12 = 2.22 ✓

Property B (Only has kitchen):
  - Exterior: Old brick house           → sim = 0.25
  - Kitchen: Marble countertops         → sim = 0.80
  - Bedroom: Outdated                   → sim = 0.18
  SCORE: 0.25 + 0.80 + 0.18 = 1.23

Property C (Only has exterior):
  - Exterior: Modern white house        → sim = 0.85
  - Kitchen: Laminate countertops       → sim = 0.30
  - Bedroom: Generic                    → sim = 0.20
  SCORE: 0.85 + 0.30 + 0.20 = 1.35

RANKING:
1. Property A (2.22) - HAS BOTH! ✓✓✓
2. Property C (1.35) - White exterior only
3. Property B (1.23) - Marble kitchen only
```

### Problem with "sum":

```
Property D (Has 15 mediocre images):
  - 15 images × 0.40 average similarity = 6.00 SCORE

Property A (Has 3 excellent images):
  - 3 images × 0.75 average similarity = 2.25 SCORE

❌ Property D wins just because it has more images!
```

## Alternative: score_mode: "avg"

```
Property A (Has everything - 5 images):
  - Exterior: White house        → 0.62
  - Kitchen: Granite counter     → 0.75
  - Living room: Modern          → 0.58
  - Bedroom: Generic             → 0.15
  - Bathroom: Generic            → 0.12
  SCORE: (0.62 + 0.75 + 0.58 + 0.15 + 0.12) / 5 = 0.444

Property B (Only kitchen - 3 images):
  - Exterior: Brick              → 0.25
  - Kitchen: Granite counter     → 0.80
  - Bedroom: Outdated            → 0.18
  SCORE: (0.25 + 0.80 + 0.18) / 3 = 0.410

Property C (Only exterior - 4 images):
  - Exterior: Modern white       → 0.85
  - Kitchen: Laminate            → 0.30
  - Living: Generic              → 0.20
  - Bedroom: Generic             → 0.15
  SCORE: (0.85 + 0.30 + 0.20 + 0.15) / 4 = 0.375

RANKING:
1. Property A (0.444) - HAS BOTH! ✓
2. Property B (0.410) - Marble only
3. Property C (0.375) - White exterior only
```

### Problem with "avg":

- **Penalizes comprehensive listings**: More photos = lower average (if extras are irrelevant)
- **Not true global top-k**: OpenSearch limitation (retrieves max, then reorders)

## Current Impact Analysis

Let's test this with a real query:

```python
# Simulate query embedding for "white house with granite countertops"
# This embedding contains BOTH concepts mixed together

Property 1: 3 bed home, white exterior, granite kitchen
  Images:
    - exterior_front.jpg:  White house visual    → 0.68
    - kitchen_1.jpg:       Granite counters      → 0.74 ← MAX selected
    - living_room.jpg:     Neutral decor         → 0.22
  kNN Image score with max: 0.74

Property 2: 4 bed home, brick exterior, granite kitchen
  Images:
    - exterior_front.jpg:  Brick house visual    → 0.31
    - kitchen_1.jpg:       Granite counters      → 0.79 ← MAX selected
    - kitchen_2.jpg:       More granite          → 0.76
    - bedroom.jpg:         Generic               → 0.18
  kNN Image score with max: 0.79

Property 3: 2 bed home, white exterior, laminate counters
  Images:
    - exterior_front.jpg:  White house visual    → 0.82 ← MAX selected
    - kitchen_1.jpg:       Laminate counters     → 0.28
  kNN Image score with max: 0.82

Visual similarity ranking:
1. Property 3 (0.82) - White exterior, NO granite ✗
2. Property 2 (0.79) - Granite kitchen, NO white ✗
3. Property 1 (0.74) - HAS BOTH but ranks WORST ✗
```

## Why RRF Doesn't Fix This

You might think: "RRF combines BM25 + kNN Text + kNN Image, so the other strategies compensate."

**Problem**: The issue exists in the kNN Image strategy itself!

```
Query: "white house with granite countertops"

BM25 (text keywords):
  - Searches: description, visual_features_text
  - Finds: Properties with "white exterior" AND "granite countertops" in text
  - Property 1 (has both): HIGH score ✓

kNN Text (semantic text):
  - Embedding of combined text: description + visual_features_text
  - Property 1 text: "...white exterior... granite countertops..."
  - Property 1: HIGH score ✓

kNN Image (visual similarity):
  - Property 1 exterior photo: 0.68 (white house)
  - Property 1 kitchen photo: 0.74 (granite) ← ONLY THIS COUNTS
  - Property 1: MEDIUM score (misses white exterior!)

RRF Fusion:
  BM25 rank:      #1 (Property 1 high)
  kNN Text rank:  #1 (Property 1 high)
  kNN Image rank: #3 (Property 1 penalized!)

  Final score still affected by weak kNN Image signal!
```

## The Fundamental Tension

**Single-feature queries** ("modern kitchen"):
- `max` is PERFECT → Pick the best kitchen photo
- `sum` is WRONG → All photos boost score (bedroom shouldn't help)
- `avg` is OK → But diluted by irrelevant photos

**Multi-feature queries** ("white house with granite countertops"):
- `max` is WRONG → Only ONE feature scores
- `sum` is BETTER → Both features contribute (but biased by image count)
- `avg` is BETTER → Both features contribute (but penalizes comprehensive listings)

## Proposed Solutions

### Solution 1: Query-Aware score_mode

Detect query complexity and use different score modes:

```python
def select_score_mode(query, constraints):
    """
    Choose score_mode based on query characteristics
    """
    feature_count = len(constraints.get("must_have", []))

    if feature_count >= 2:
        # Multi-feature query: Need aggregate scoring
        return "sum"  # or "avg"
    else:
        # Single-feature query: Best single match
        return "max"
```

**Pros**:
- Works well for both query types
- No manual configuration needed

**Cons**:
- Need to detect query complexity (already have LLM extraction!)
- Still has sum/avg problems (image count bias)

### Solution 2: Weighted Sum with Decay

Sum scores but apply diminishing returns:

```python
def calculate_weighted_image_score(image_scores):
    """
    Sum image scores with decay to prevent count inflation

    Formula: score_1 + score_2*0.5 + score_3*0.25 + score_4*0.125 + ...
    """
    sorted_scores = sorted(image_scores, reverse=True)

    total = 0
    for i, score in enumerate(sorted_scores):
        weight = 0.5 ** i  # Exponential decay
        total += score * weight

    return total
```

**Example**:
```
Property A (white + granite):
  - 0.68 (white exterior) × 1.0   = 0.68
  - 0.74 (granite kitchen) × 0.5  = 0.37
  - 0.22 (living room) × 0.25     = 0.055
  Total: 1.105

Property B (granite only):
  - 0.79 (granite kitchen) × 1.0  = 0.79
  - 0.76 (more granite) × 0.5     = 0.38
  - 0.31 (brick exterior) × 0.25  = 0.078
  Total: 1.248

Property C (white only):
  - 0.82 (white exterior) × 1.0   = 0.82
  - 0.28 (laminate kitchen) × 0.5 = 0.14
  Total: 0.96
```

Still not perfect, but better balance.

**Pros**:
- Rewards multiple good matches
- Limits impact of image count
- Works for both single and multi-feature queries

**Cons**:
- Custom implementation (can't use OpenSearch score_mode)
- Requires post-processing scores

### Solution 3: Feature-Specific Image Matching (Advanced)

Use LLM to categorize images AND queries, then match specifically:

```python
query_features = {
    "exterior": "white house",
    "interior_kitchen": "granite countertops"
}

property_images = {
    "exterior": [...],      # Exterior-tagged images
    "interior_kitchen": [...],  # Kitchen-tagged images
}

# Match each query feature to corresponding images
exterior_score = max_similarity(query_features["exterior"], property_images["exterior"])
kitchen_score = max_similarity(query_features["interior_kitchen"], property_images["interior_kitchen"])

# Combine with equal weight
final_score = (exterior_score + kitchen_score) / 2
```

**Pros**:
- Most semantically accurate
- Each feature matched to appropriate images

**Cons**:
- Requires image classification (exterior vs interior vs room type)
- Complex implementation
- Expensive (LLM calls per image)

### Solution 4: Hybrid: Top-K Images Sum

Take top K images and sum:

```python
def top_k_sum(image_scores, k=3):
    """
    Sum the top K image scores

    For multi-feature queries, K should be >= num_features
    For single-feature queries, K=1 is like max
    """
    return sum(sorted(image_scores, reverse=True)[:k])
```

**Example** (k=3):
```
Property A (white + granite - 5 images):
  Top 3: 0.74 + 0.68 + 0.58 = 2.00

Property B (granite only - 4 images):
  Top 3: 0.79 + 0.76 + 0.31 = 1.86

Property C (white only - 2 images):
  Top 3: 0.82 + 0.28 = 1.10 (only has 2)

Ranking:
1. Property A (2.00) - HAS BOTH ✓
2. Property B (1.86) - Granite only
3. Property C (1.10) - White only
```

**Pros**:
- Simple to implement
- Rewards multiple features
- Limits image count bias (capped at k)
- Can tune k based on query complexity

**Cons**:
- Fixed k might not work for all queries
- Still some image count sensitivity

## Recommendation

**Implement Solution 4: Top-K Images Sum** with adaptive K:

```python
def calculate_image_score(image_vectors, query_vec, must_have_features):
    """
    Calculate aggregate image score

    K is adaptive based on query complexity:
    - 1-2 features: k=2 (allow both to contribute)
    - 3+ features: k=3 (allow multiple to contribute)
    - 0 features (general query): k=1 (best single match)
    """
    feature_count = len(must_have_features)

    if feature_count == 0:
        k = 1  # Single best match (like current max)
    elif feature_count <= 2:
        k = 2  # Top 2 images
    else:
        k = 3  # Top 3 images

    # Calculate similarities for all images
    similarities = [
        cosine_similarity(query_vec, img_vec)
        for img_vec in image_vectors
    ]

    # Sum top K
    top_k_scores = sorted(similarities, reverse=True)[:k]
    return sum(top_k_scores)
```

This would require custom scoring in Python (can't use OpenSearch score_mode directly), but provides the best balance.

## Next Steps

1. Test current behavior with multi-feature queries
2. Implement top-k sum scoring
3. A/B test: max vs top-k-sum
4. Measure improvement on queries like:
   - "white house with granite countertops"
   - "modern kitchen with stainless appliances and hardwood floors"
   - "brick colonial with pool and deck"

Want me to implement and test this?
