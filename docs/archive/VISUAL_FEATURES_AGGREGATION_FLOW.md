# Visual Features Text: Data Flow & Aggregation Logic

This diagram shows exactly how multiple image analyses are aggregated into a single `visual_features_text` field and how that affects search quality.

---

## STEP 1: Image Analysis (per image)

```
Property A (Brown exterior, white interior)
├─ Image 1: exterior_front.jpg
│   └─ Claude Haiku Vision Analysis:
│       {
│         "image_type": "exterior",
│         "architecture_style": "ranch",
│         "exterior_color": "brown",
│         "materials": ["vinyl_siding"],
│         "features": ["front_porch", "attached_garage"],
│         "confidence": "high"
│       }
│
├─ Image 2-10: kitchen, bedroom, bathroom, living room (9 photos)
│   └─ Analysis for each interior photo:
│       {
│         "image_type": "interior",
│         "features": ["white walls", "white cabinets", "white trim",
│                      "hardwood floors", "stainless appliances",
│                      "granite countertops", "ceiling fan"],
│         "confidence": "high"
│       }
```

---

## STEP 2: Aggregation with Majority Voting

```python
# CODE: upload_listings.py lines 492-596

# PHASE 1: CLASSIFY & COUNT
exterior_colors = ["brown"]  # From 1 exterior photo
interior_features = [
    "white walls",      # 9 mentions
    "white cabinets",   # 8 mentions
    "white trim",       # 7 mentions
    "hardwood floors",  # 6 mentions
    "stainless appliances", # 4 mentions
    "granite countertops",  # 4 mentions
    "ceiling fan"       # 5 mentions
]

# PHASE 2: MAJORITY VOTING (for exterior attributes)
from collections import Counter

color_counts = Counter(exterior_colors)
# {"brown": 1}

primary_color = color_counts.most_common(1)[0][0]
# Result: "brown" (even though "white" appears 24 times in interiors!)

# PHASE 3: FREQUENCY RANKING (for interior features)
feature_counts = Counter(interior_features)
# {
#   "white walls": 9,
#   "white cabinets": 8,
#   "white trim": 7,
#   "hardwood floors": 6,
#   "ceiling fan": 5,
#   "stainless appliances": 4,
#   "granite countertops": 4
# }

top_interior = [f for f, _ in feature_counts.most_common(10)]
# ["white walls", "white cabinets", "white trim", "hardwood floors",
#  "ceiling fan", "stainless appliances", "granite countertops"]

# PHASE 4: STRUCTURED ASSEMBLY
visual_features_text = (
    "Exterior: ranch style brown exterior with vinyl siding. "
    "Interior features: white walls, white cabinets, white trim, "
    "hardwood floors, ceiling fan, stainless appliances, granite countertops. "
    "Property includes: front porch, attached garage."
)
```

---

## STEP 3: Indexing to OpenSearch

```json
// OpenSearch Document
{
  "zpid": "12345",
  "description": "Beautiful home with updated kitchen...",
  "visual_features_text": "Exterior: ranch style brown exterior with vinyl siding. Interior features: white walls, white cabinets, white trim, hardwood floors, ceiling fan, stainless appliances, granite countertops. Property includes: front porch, attached garage.",
  "vector_text": [0.123, 0.456, ...],  // Embedding of: description + visual_features_text
  "image_vectors": [
    {"image_url": "exterior_front.jpg", "vector": [0.789, ...]},
    {"image_url": "kitchen.jpg", "vector": [0.234, ...]},
    ...
  ]
}
```

**CRITICAL:** `vector_text` embeds **BOTH** description AND visual_features_text!
- Text: "Beautiful home with updated kitchen..."
- Visual: "Exterior: ranch style brown exterior... white walls, white cabinets..."
- Combined embedding captures both contexts

---

## STEP 4: Search Query Processing

### Query: "white house"

```
┌─────────────────────────────────────────────────────────┐
│                    SEARCH PIPELINE                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. LLM Extraction:                                      │
│     - must_have_tags: ["white_exterior"]                │
│     - query_type: "visual_style"                        │
│                                                          │
│  2. Embedding Generation:                               │
│     q_vec = embed_text("white house")                   │
│     → [0.891, 0.234, ...]                               │
│                                                          │
│  3. Three Parallel Searches:                            │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ A) BM25 Full-Text Search                         │  │
│  │    Fields: description^3, visual_features_text^2.5│  │
│  │                                                   │  │
│  │    Property A (brown exterior, white interior):   │  │
│  │    ✓ Matches "white walls"                       │  │
│  │    ✓ Matches "white cabinets"                    │  │
│  │    ✓ Matches "white trim"                        │  │
│  │    → BM25 Score: 8.5 (FALSE POSITIVE!)           │  │
│  │                                                   │  │
│  │    Property B (white exterior, beige interior):   │  │
│  │    ✓ Matches "white exterior"                    │  │
│  │    → BM25 Score: 9.2 (CORRECT)                   │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ B) kNN Text Embeddings                           │  │
│  │    Semantic similarity on vector_text            │  │
│  │                                                   │  │
│  │    Property A:                                    │  │
│  │    vector_text embeds: "...brown exterior...     │  │
│  │                         white walls..."          │  │
│  │    Cosine similarity: 0.68 (mixed signal)        │  │
│  │    → kNN Score: 0.84                             │  │
│  │                                                   │  │
│  │    Property B:                                    │  │
│  │    vector_text embeds: "...white exterior..."    │  │
│  │    Cosine similarity: 0.89 (strong match)        │  │
│  │    → kNN Score: 0.945                            │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ C) kNN Image Embeddings (Adaptive K=1)           │  │
│  │    Best single image match                       │  │
│  │                                                   │  │
│  │    Property A:                                    │  │
│  │    Image 1: Brown exterior                       │  │
│  │    Cosine similarity: 0.52 (poor match)          │  │
│  │    → kNN Score: 0.76                             │  │
│  │                                                   │  │
│  │    Property B:                                    │  │
│  │    Image 1: White exterior                       │  │
│  │    Cosine similarity: 0.91 (excellent match)     │  │
│  │    → kNN Score: 0.955                            │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  4. RRF Fusion (Reciprocal Rank Fusion):                │
│                                                          │
│     Adaptive weights (visual-dominant query):           │
│     - BM25 k=60 (standard weight)                       │
│     - Text kNN k=50 (slight boost)                      │
│     - Image kNN k=30 (strong boost - lower k)           │
│                                                          │
│     Property A:                                          │
│     - BM25: rank 2 → 1/(60+2) = 0.0161                 │
│     - Text: rank 5 → 1/(50+5) = 0.0182                 │
│     - Image: rank 12 → 1/(30+12) = 0.0238              │
│     → RRF Total: 0.0581                                 │
│                                                          │
│     Property B:                                          │
│     - BM25: rank 1 → 1/(60+1) = 0.0164                 │
│     - Text: rank 1 → 1/(50+1) = 0.0196                 │
│     - Image: rank 1 → 1/(30+1) = 0.0323                │
│     → RRF Total: 0.0683                                 │
│                                                          │
│  5. First Image Boosting:                                │
│                                                          │
│     Property A: First image (brown) score=0.52          │
│                 → No boost (< 0.72)                     │
│     Property B: First image (white) score=0.91          │
│                 → 1.2x boost (≥ 0.75)                   │
│                                                          │
│  6. Final Scores:                                        │
│     Property A: 0.0581 × 1.0 = 0.0581                   │
│     Property B: 0.0683 × 1.2 = 0.0820                   │
│                                                          │
│  ✅ RESULT: Property B ranks higher (correct!)          │
│     ⚠️  BUT: Property A still appears in results        │
└─────────────────────────────────────────────────────────┘
```

---

## STEP 5: Multi-Feature Query Problem

### Query: "white house with granite countertops"

```
Property G: White exterior + granite kitchen
visual_features_text: "Exterior: modern style white exterior with vinyl siding.
                       Interior features: granite countertops, white cabinets..."

Property H: Brown exterior + white interior + granite kitchen
visual_features_text: "Exterior: ranch style brown exterior with brick.
                       Interior features: white walls, white cabinets, granite countertops..."

┌─────────────────────────────────────────────────────────┐
│            BM25 MATCHING (PROBLEMATIC)                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Query terms: ["white", "house", "granite", "countertops"]│
│                                                          │
│  Property G:                                             │
│    ✓ "white" in "white exterior"                        │
│    ✓ "granite countertops"                              │
│    → Score: 12.8 (both features correct context)        │
│                                                          │
│  Property H:                                             │
│    ✓ "white" in "white walls" + "white cabinets"        │
│    ✓ "granite countertops"                              │
│    → Score: 11.5 (white in WRONG context!)              │
│                                                          │
│  ❌ PROBLEM: BM25 can't distinguish "white house"       │
│              from "white walls"                          │
│                                                          │
│  ⚠️  Property H incorrectly matches both features!      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│       TEXT EMBEDDING (PARTIALLY COMPENSATES)             │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Query embedding: "white house with granite"            │
│    → Semantic vector expects WHITE EXTERIOR context     │
│                                                          │
│  Property G: "white exterior... granite..."             │
│    → Cosine similarity: 0.87 (strong semantic match)    │
│                                                          │
│  Property H: "brown exterior... white walls... granite..."│
│    → Cosine similarity: 0.71 (mixed semantic signal)    │
│                                                          │
│  ✅ Text embeddings PARTIALLY distinguish context       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│      IMAGE EMBEDDING (STRONGLY COMPENSATES)              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Query: "white house with granite"                      │
│    → Visual expectation: White exterior + granite interior│
│                                                          │
│  Property G: Image 1 = white exterior                   │
│    → First image score: 0.88 (excellent match)          │
│    → 1.2x boost applied                                 │
│                                                          │
│  Property H: Image 1 = brown exterior                   │
│    → First image score: 0.54 (poor match)               │
│    → No boost                                           │
│                                                          │
│  ✅ Image embeddings STRONGLY distinguish context       │
└─────────────────────────────────────────────────────────┘

FINAL RANKING (after RRF + boosting):
1. Property G: 0.095 (white exterior + granite) ✅ CORRECT
2. Property H: 0.067 (brown exterior + white interior + granite) ⚠️ STILL APPEARS
```

---

## Key Insights

### ✅ What Works

1. **Majority Voting Prevents Exterior Color Confusion**
   ```
   1 brown exterior photo > 9 white interior photos
   Result: "brown exterior" (correct)
   ```

2. **Adaptive K=1 Prevents Feature Dilution**
   ```
   Query: "modern kitchen"
   Uses: Best single kitchen photo (ignores other rooms)
   ```

3. **First Image Boosting Prioritizes Exterior**
   ```
   White exterior (score 0.91) → 1.2x boost
   Brown exterior (score 0.52) → no boost
   ```

4. **RRF Fusion Balances False Positives**
   ```
   BM25 false positive + weak kNN scores = lower rank
   BM25 correct + strong kNN scores = higher rank
   ```

### ❌ What Doesn't Work

1. **BM25 Context Blindness**
   ```
   Query: "white house"
   BM25 matches: "white walls", "white cabinets" (WRONG context)
   Problem: Can't distinguish exterior vs interior
   ```

2. **Multi-Feature Context Confusion**
   ```
   Query: "white house with granite"
   Property H: "brown exterior... white walls... granite"
   BM25: ✓ "white" + ✓ "granite" = match (WRONG!)
   ```

3. **Frequency-Based Dilution**
   ```
   3 modern photos + 17 traditional photos
   Result: "traditional" ranks higher in features list
   Impact: Weakens match for "modern kitchen"
   ```

---

## Recommended Solution

### Separate Context Fields

```json
// PROPOSED SCHEMA
{
  "zpid": "12345",
  "description": "Beautiful home...",

  // SEPARATED CONTEXTS (instead of single visual_features_text)
  "exterior_visual_features": "modern style white exterior with vinyl siding, front porch, attached garage",
  "interior_visual_features": "granite countertops, white cabinets, hardwood floors, stainless appliances",
  "amenities_visual_features": "pool, deck, spa, covered patio",

  // Embeddings
  "vector_text": [...],  // Embeds: description + ALL visual features
  "vector_exterior": [...],  // NEW: Embeds exterior_visual_features only
  "vector_interior": [...],  // NEW: Embeds interior_visual_features only
  "image_vectors": [...]
}
```

### Context-Aware Query Routing

```python
# Query: "white house with granite countertops"
query_classification = {
    "exterior_features": ["white"],
    "interior_features": ["granite_countertops"]
}

# BM25 with context-specific field boosting
bm25_query = {
    "bool": {
        "must": [
            {"match": {"exterior_visual_features": "white"}},  # Must match exterior
            {"match": {"interior_visual_features": "granite"}}  # Must match interior
        ],
        "should": [
            {"match": {"description": "white house granite"}}  # Original description
        ]
    }
}

# kNN with context-specific vectors
knn_exterior_query = {
    "knn": {"vector_exterior": {"vector": embed_text("white house"), "k": 100}}
}
knn_interior_query = {
    "knn": {"vector_interior": {"vector": embed_text("granite countertops"), "k": 100}}
}
```

**Impact:** ✅ Eliminates ALL context confusion problems

---

## Conclusion

The current aggregation approach uses **clever mitigations** (majority voting, first-image boosting, RRF fusion) that work reasonably well, but **BM25 context blindness** remains a fundamental problem.

**Trade-off:**
- ✅ Current system is SIMPLE (single field, single embedding)
- ❌ But causes false positives for color/context queries

**Best fix:** Separate fields for exterior/interior/amenities with context-aware query routing.
