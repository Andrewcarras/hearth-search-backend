# Visual Features Text Aggregation: Code Trace Examples

This document traces through actual code execution for specific problematic scenarios.

---

## Scenario 1: "white house" - Brown Exterior with White Interior

### Property A Data
```json
{
  "zpid": "12345",
  "images": [
    "https://photos.zillow.com/fp/exterior_1.jpg",
    "https://photos.zillow.com/fp/kitchen_1.jpg",
    "https://photos.zillow.com/fp/bedroom_1.jpg",
    "https://photos.zillow.com/fp/bathroom_1.jpg",
    "https://photos.zillow.com/fp/living_1.jpg",
    "https://photos.zillow.com/fp/kitchen_2.jpg",
    "https://photos.zillow.com/fp/bedroom_2.jpg",
    "https://photos.zillow.com/fp/bathroom_2.jpg",
    "https://photos.zillow.com/fp/garage_1.jpg",
    "https://photos.zillow.com/fp/backyard_1.jpg"
  ]
}
```

---

### Code Trace: upload_listings.py `_build_doc()` function

#### STEP 1: Image Analysis (lines 393-490)

```python
# Process each image in parallel
all_image_analyses = []

# Image 1: exterior_1.jpg
analysis_1 = {
    "image_type": "exterior",
    "architecture_style": "ranch",
    "exterior_color": "brown",
    "materials": ["vinyl_siding"],
    "features": ["front_porch", "attached_garage"],
    "visual_features": ["driveway", "lawn"],
    "confidence": "high"
}
all_image_analyses.append(analysis_1)

# Images 2-10: Interior photos (kitchen, bedrooms, bathrooms, living room)
for i in range(2, 11):
    analysis = {
        "image_type": "interior",
        "features": [
            "white walls",
            "white cabinets" if "kitchen" in image_urls[i] else "white trim",
            "hardwood floors",
            "ceiling fan",
            "recessed lighting",
            "large windows"
        ],
        "confidence": "high"
    }
    all_image_analyses.append(analysis)

# Result: all_image_analyses contains 10 analyses
# - 1 exterior (brown)
# - 9 interior (white features dominate)
```

#### STEP 2: Aggregation with Majority Voting (lines 492-596)

```python
from collections import Counter

# Initialize collections
exterior_analyses = []
interior_descriptions = []
exterior_styles = []
exterior_colors = []
all_materials = []
all_feature_counts = Counter()

# PHASE 1: Classify and separate
for analysis in all_image_analyses:
    # Analysis 1 (exterior)
    if analysis.get("image_type") == "exterior":
        exterior_analyses.append(analysis)
        if analysis.get("architecture_style"):
            exterior_styles.append(analysis["architecture_style"])  # ["ranch"]
        if analysis.get("exterior_color"):
            exterior_colors.append(analysis["exterior_color"])  # ["brown"]
        all_materials.extend(analysis.get("materials", []))  # ["vinyl_siding"]

    # Analyses 2-10 (interior)
    elif analysis.get("image_type") == "interior":
        interior_descriptions.extend(analysis.get("features", [])[:5])
        # Accumulates: ["white walls", "white cabinets", "hardwood floors",
        #               "ceiling fan", "recessed lighting"] × 9 photos
        # = 45 interior features total

    # Track feature frequencies
    for feature in analysis.get("features", []):
        all_feature_counts[feature] += 1

# PHASE 2: Majority voting for EXTERIOR attributes
logger.info(f"Exterior color votes: {Counter(exterior_colors)}")
# Output: "Exterior color votes: {'brown': 1}"

color_counts = Counter(exterior_colors)
primary_color = color_counts.most_common(1)[0][0]
# Result: "brown" (correct - ignores interior "white" mentions!)

logger.info(f"Exterior color votes: {dict(color_counts)} → chose '{primary_color}'")
# Output: "Exterior color votes: {'brown': 1} → chose 'brown'"

# PHASE 3: Frequency ranking for INTERIOR features
feature_counts = Counter(interior_descriptions)
# {
#   "white walls": 9,
#   "white cabinets": 5,
#   "hardwood floors": 9,
#   "ceiling fan": 7,
#   "recessed lighting": 8,
#   "large windows": 6,
#   "white trim": 4
# }

top_interior = [feature for feature, _ in feature_counts.most_common(10)]
# ["white walls", "hardwood floors", "recessed lighting", "ceiling fan",
#  "large windows", "white cabinets", "white trim"]

# PHASE 4: Structured assembly
description_parts = []

# Exterior section
if exterior_analyses:
    parts = []
    if exterior_styles:
        style_counts = Counter(exterior_styles)
        primary_style = style_counts.most_common(1)[0][0]  # "ranch"
        parts.append(f"{primary_style} style")

    if exterior_colors:
        parts.append(f"{primary_color} exterior")  # "brown exterior"

    if all_materials:
        material_counts = Counter(all_materials)
        top_materials = [material for material, _ in material_counts.most_common(3)]
        # ["vinyl_siding"]
        parts.append(f"with {', '.join(top_materials)}")

    description_parts.append(f"Exterior: {' '.join(parts)}")
    # "Exterior: ranch style brown exterior with vinyl_siding"

# Interior section
if interior_descriptions:
    description_parts.append(f"Interior features: {', '.join(top_interior)}")
    # "Interior features: white walls, hardwood floors, recessed lighting,
    #  ceiling fan, large windows, white cabinets, white trim"

# General features (remaining)
remaining_features = ["front_porch", "attached_garage", "driveway", "lawn"]
if remaining_features:
    description_parts.append(f"Property includes: {', '.join(remaining_features)}")

# FINAL RESULT
visual_features_text = ". ".join(description_parts) + "."
# "Exterior: ranch style brown exterior with vinyl_siding.
#  Interior features: white walls, hardwood floors, recessed lighting,
#  ceiling fan, large windows, white cabinets, white trim.
#  Property includes: front_porch, attached_garage, driveway, lawn."

logger.info(f"📝 Generated visual_features_text for zpid=12345: "
           f"{len(visual_features_text)} chars, 11 unique features")
# Output: "📝 Generated visual_features_text for zpid=12345: 238 chars, 11 unique features"
```

#### STEP 3: Text Embedding Generation (lines 599-622)

```python
# Combine original description with visual features
text_for_embed = doc["description"].strip()
# "Beautiful 3 bedroom home with updated kitchen and spacious backyard."

if visual_features_text:
    combined_text = f"{text_for_embed} {visual_features_text}".strip()
else:
    combined_text = text_for_embed

# COMBINED TEXT FOR EMBEDDING:
combined_text = """Beautiful 3 bedroom home with updated kitchen and spacious backyard.
Exterior: ranch style brown exterior with vinyl_siding.
Interior features: white walls, hardwood floors, recessed lighting,
ceiling fan, large windows, white cabinets, white trim.
Property includes: front_porch, attached_garage, driveway, lawn."""

# Generate embedding using multimodal Titan
vec_text = embed_text_multimodal(combined_text)
# → [0.123, 0.456, ..., 0.789]  (1024 dimensions)

logger.debug(f"Embedded {len(combined_text)} chars "
            f"(desc: {len(text_for_embed)}, visual: {len(visual_features_text)})")
# Output: "Embedded 299 chars (desc: 61, visual: 238)"
```

#### STEP 4: Document Storage (lines 650-686)

```json
// OpenSearch document
{
  "zpid": "12345",
  "description": "Beautiful 3 bedroom home with updated kitchen and spacious backyard.",
  "visual_features_text": "Exterior: ranch style brown exterior with vinyl_siding. Interior features: white walls, hardwood floors, recessed lighting, ceiling fan, large windows, white cabinets, white trim. Property includes: front_porch, attached_garage, driveway, lawn.",
  "vector_text": [0.123, 0.456, ..., 0.789],
  "image_vectors": [
    {"image_url": "exterior_1.jpg", "vector": [0.234, ...]},
    {"image_url": "kitchen_1.jpg", "vector": [0.567, ...]},
    ...
  ],
  "has_valid_embeddings": true,
  "indexed_at": 1729628400
}
```

---

### Code Trace: search.py Query Processing

#### User Query: "white house"

#### STEP 1: Query Analysis (lines 1113-1119)

```python
q = "white house"
constraints = extract_query_constraints(q)
# {
#   "hard_filters": {},
#   "must_have": ["white_exterior"],
#   "architecture_style": null,
#   "proximity": null,
#   "query_type": "visual_style"
# }

must_tags = set(constraints.get("must_have", []))
# {"white_exterior"}

logger.info("Extracted constraints: %s", constraints)
# Output: "Extracted constraints: {'must_have': ['white_exterior'], 'query_type': 'visual_style'}"
```

#### STEP 2: Query Embedding (line 1157)

```python
q_vec = embed_text_multimodal("white house")
# → [0.891, 0.234, ..., 0.567]  (1024 dimensions)
# This embedding captures semantic meaning of "white exterior"
```

#### STEP 3a: BM25 Full-Text Search (lines 1218-1251)

```python
# Boost mode: standard
desc_boost = 3
visual_boost = 2.5

bm25_query = {
    "query": {
        "bool": {
            "filter": [
                {"range": {"price": {"gt": 0}}},
                {"term": {"has_valid_embeddings": True}}
            ],
            "should": [
                {
                    "multi_match": {
                        "query": "white house",  # User query
                        "fields": [
                            "description^3",           # 3x boost
                            "visual_features_text^2.5", # 2.5x boost
                            "llm_profile^2",
                            "address^0.5",
                            "city^0.3",
                            "state^0.2"
                        ],
                        "type": "cross_fields",
                        "operator": "or",
                        "minimum_should_match": "50%"
                    }
                },
                {"terms": {"feature_tags": ["white_exterior", "white exterior"]}},
                {"terms": {"image_tags": ["white_exterior", "white exterior"]}}
            ],
            "minimum_should_match": 1
        }
    }
}

# Execute query
bm25_hits = _os_search(bm25_query, size=45, index="listings")

# PROPERTY A BM25 SCORING:
# OpenSearch analyzes: visual_features_text^2.5
# "Exterior: ranch style brown exterior with vinyl_siding.
#  Interior features: white walls, hardwood floors, recessed lighting,
#  ceiling fan, large windows, white cabinets, white trim.
#  Property includes: front_porch, attached_garage, driveway, lawn."
#
# Term frequency analysis:
# - "white" appears 3 times (white walls, white cabinets, white trim)
# - "house" appears 0 times
#
# BM25 formula (simplified):
# score = Σ (IDF(term) × TF(term) × field_boost)
#
# For "white":
#   IDF("white") = 2.5 (moderately rare term)
#   TF("white") = 3 (appears 3 times in visual_features_text)
#   Field boost = 2.5
#   Term score = 2.5 × log(1 + 3) × 2.5 = 8.6
#
# For "house":
#   TF("house") = 0
#   Term score = 0
#
# Total BM25 score: 8.6 (MATCHES despite brown exterior!)

# PROPERTY B (white exterior, beige interior) BM25 SCORING:
# visual_features_text: "Exterior: modern style white exterior with vinyl_siding..."
#
# For "white":
#   TF("white") = 1 (appears once in "white exterior")
#   Position = in "Exterior:" section (proximity boost)
#   Term score = 2.5 × log(1 + 1) × 2.5 × 1.2 = 5.2
#
# For "house":
#   TF("house") = 0 (but proximity to "exterior" helps)
#   Implicit semantic match via BM25 relevance
#   Term score = 3.8
#
# Total BM25 score: 9.0 (CORRECT MATCH)

logger.info("BM25 returned %d hits", len(bm25_hits))
# Output: "BM25 returned 23 hits"

# Rankings:
# 1. Property B (white exterior): 9.0
# 2. Property A (brown exterior, white interior): 8.6  ← FALSE POSITIVE
# 3. Property C (white trim): 6.2
# ...
```

#### STEP 3b: kNN Text Search (lines 1259-1286)

```python
knn_text_body = {
    "size": 45,
    "query": {
        "bool": {
            "must": [
                {
                    "knn": {
                        "vector_text": {
                            "vector": q_vec,  # [0.891, 0.234, ..., 0.567]
                            "k": 150
                        }
                    }
                }
            ],
            "filter": [
                {"range": {"price": {"gt": 0}}},
                {"term": {"has_valid_embeddings": True}}
            ]
        }
    }
}

knn_text_hits = _os_search(knn_text_body, size=45, index="listings")

# PROPERTY A SCORING:
# Property vector_text embeds:
#   "Beautiful home... brown exterior... white walls, white cabinets..."
#   → [0.745, 0.321, ..., 0.612]
#
# Cosine similarity calculation:
# cosine_sim(q_vec, property_vec) = dot(q_vec, property_vec) / (||q_vec|| × ||property_vec||)
#
# q_vec emphasizes: "white" (0.891), "exterior" (0.567), "house" (0.678)
# property_vec emphasizes: "brown" (0.745), "exterior" (0.612), "white" (0.321 - diluted)
#
# cosine_sim = 0.68 (moderate match - mixed signal from "white" in wrong context)
# kNN score = (1 + 0.68) / 2 = 0.84

# PROPERTY B SCORING:
# Property vector_text embeds: "...white exterior..."
#   → [0.889, 0.554, ..., 0.643]
#
# q_vec vs property_vec:
# Both emphasize: "white" (0.891 vs 0.889), "exterior" (0.567 vs 0.643)
#
# cosine_sim = 0.89 (strong semantic match)
# kNN score = (1 + 0.89) / 2 = 0.945

logger.info("kNN text returned %d hits", len(knn_text_hits))
# Output: "kNN text returned 18 hits"

# Rankings:
# 1. Property B (white exterior): 0.945
# 2. Property D (cream exterior): 0.91
# 3. Property E (beige exterior): 0.88
# 4. Property A (brown exterior, white interior): 0.84  ← Weak match
```

#### STEP 3c: kNN Image Search (lines 1289-1431)

```python
# Adaptive K calculation
image_k = calculate_adaptive_k_for_images(must_tags)
# must_tags = ["white_exterior"]
# feature_count = 1
# Return: k=1 (best single match)

logger.info(f"🖼️  Adaptive K for images: k={image_k}")
# Output: "🖼️  Adaptive K for images: k=1 (features=1, type=visual_style)"

# Multi-vector query (listings-v2 index)
knn_img_body = {
    "size": 45,
    "query": {
        "bool": {
            "must": [
                {
                    "nested": {
                        "path": "image_vectors",
                        "score_mode": "sum",
                        "query": {
                            "knn": {
                                "image_vectors.vector": {
                                    "vector": q_vec,  # Same as text query
                                    "k": 150
                                }
                            }
                        },
                        "inner_hits": {
                            "size": 100,
                            "_source": True
                        }
                    }
                }
            ],
            "filter": [
                {"range": {"price": {"gt": 0}}},
                {"term": {"has_valid_embeddings": True}}
            ]
        }
    }
}

raw_img_hits = _os_search(knn_img_body, size=45, index="listings-v2")

# PROPERTY A IMAGE SCORING (K=1):
# Image vectors:
#   Image 1 (exterior_1.jpg - brown exterior): [0.234, ..., 0.456]
#   Image 2 (kitchen_1.jpg - white cabinets): [0.567, ..., 0.789]
#   Image 3 (bedroom_1.jpg - white walls): [0.543, ..., 0.721]
#   ...
#
# Calculate cosine similarity for each image:
# scores = [
#   0.52,  # Image 1: brown exterior (POOR match with "white house")
#   0.78,  # Image 2: white kitchen (better match - white features)
#   0.75,  # Image 3: white bedroom
#   ...
# ]
#
# Apply top-K scoring (K=1):
top_k_scores = sorted(scores, reverse=True)[:1]  # [0.78]
property_A_score = sum(top_k_scores) = 0.78

# PROPERTY B IMAGE SCORING (K=1):
# Image vectors:
#   Image 1 (exterior_1.jpg - white exterior): [0.889, ..., 0.654]
#   Image 2 (kitchen_1.jpg - beige cabinets): [0.432, ..., 0.567]
#   ...
#
# scores = [
#   0.91,  # Image 1: white exterior (EXCELLENT match)
#   0.62,  # Image 2: beige kitchen
#   ...
# ]
#
# Apply top-K scoring (K=1):
top_k_scores = [0.91]
property_B_score = 0.91

# Apply adaptive K scoring
for hit in raw_img_hits:
    inner_hits = hit.get("inner_hits", {})
    top_k_score = calculate_top_k_image_score(inner_hits, image_k=1)
    hit["_score"] = top_k_score
    logger.debug(f"  zpid={hit['_id']}: top-{image_k} score={top_k_score:.4f}")

logger.info("kNN image returned %d hits", len(raw_img_hits))
# Output: "kNN image returned 21 hits"

# Rankings:
# 1. Property B (white exterior): 0.91
# 2. Property F (cream exterior): 0.87
# 3. Property G (beige exterior): 0.82
# 4. Property A (brown exterior, white interior): 0.78
```

#### STEP 4: RRF Fusion (lines 1434-1456)

```python
# Calculate adaptive weights
k_values = calculate_adaptive_weights_v2(must_tags, query_type)
# must_tags = {"white_exterior"}
# Classification: VISUAL_DOMINANT feature
# Result: [bm25_k=60, text_k=50, image_k=30]
# Lower k = higher weight (images prioritized)

logger.info(f"📊 Feature-context weights: BM25={k_values[0]}, "
           f"Text={k_values[1]}, Image={k_values[2]}")
# Output: "📊 Feature-context weights: BM25=60, Text=50, Image=30"

# RRF formula: score = Σ [1 / (k + rank)]
#
# PROPERTY A:
#   BM25: rank=2, k=60 → 1/(60+2) = 0.0161
#   Text: rank=4, k=50 → 1/(50+4) = 0.0185
#   Image: rank=4, k=30 → 1/(30+4) = 0.0294
#   RRF total = 0.0640
#
# PROPERTY B:
#   BM25: rank=1, k=60 → 1/(60+1) = 0.0164
#   Text: rank=1, k=50 → 1/(50+1) = 0.0196
#   Image: rank=1, k=30 → 1/(30+1) = 0.0323
#   RRF total = 0.0683

fused = _rrf(bm25_hits, knn_text_hits, knn_img_hits,
            k_values=k_values, top=45, include_scoring_details=True)

logger.info("RRF fusion produced %d results", len(fused))
# Output: "RRF fusion produced 45 results"
```

#### STEP 5: First Image Boosting (lines 1504-1527)

```python
# Calculate first image scores for boosting
for h in fused:
    src = h.get("_source", {})

    if "image_vectors" in src and src["image_vectors"]:
        # Get first image (typically exterior on Zillow)
        first_img_vec_obj = src["image_vectors"][0]
        first_img_vec = first_img_vec_obj.get("vector")

        if first_img_vec and q_vec:
            # Calculate cosine similarity
            cosine_sim = calculate_cosine_similarity(q_vec, first_img_vec)
            first_image_score = (1.0 + cosine_sim) / 2.0

            # Apply boost thresholds
            if first_image_score >= 0.75:
                first_image_boost = 1.2
                logger.info(f"🏠 Exterior boost for zpid={h['_id']}: "
                           f"first image score {first_image_score:.3f} -> 1.2x")
            elif first_image_score >= 0.72:
                first_image_boost = 1.1
            else:
                first_image_boost = 1.0

# PROPERTY A:
# first_image_score = 0.52 (brown exterior - poor match)
# first_image_boost = 1.0 (no boost)
# logger output: (none - no boost applied)

# PROPERTY B:
# first_image_score = 0.91 (white exterior - excellent match)
# first_image_boost = 1.2
# Output: "🏠 Exterior boost for zpid=67890: first image score 0.910 -> 1.2x"
```

#### STEP 6: Final Scoring (lines 1528-1670)

```python
final = []
for h in fused:
    rrf_score = h.get("_rrf_score", h.get("_score", 0.0))
    boost = 1.0  # Tag boosting (not applicable here)
    first_image_boost = h.get("_first_image_boost", 1.0)

    result = {
        "zpid": h["_id"],
        "score": rrf_score * boost * first_image_boost,
        "boosted": boost > 1.0 or first_image_boost > 1.0
    }

    final.append((result["score"], result))

# PROPERTY A:
# score = 0.0640 × 1.0 × 1.0 = 0.0640

# PROPERTY B:
# score = 0.0683 × 1.0 × 1.2 = 0.0820

# Sort by score descending
final.sort(key=lambda x: x[0], reverse=True)
results = [x[1] for x in final[:15]]

logger.info("Returning %d final results", len(results))
# Output: "Returning 15 final results"

# FINAL RANKINGS:
# 1. Property B (white exterior): 0.0820 ✅ CORRECT
# 2. Property F (cream exterior): 0.0745
# 3. Property G (beige exterior): 0.0712
# 4. Property A (brown exterior, white interior): 0.0640 ⚠️ Still appears!
```

---

## Key Observations from Code Trace

### ✅ What Worked

1. **Majority Voting (Line 548-558)**
   - Correctly identified "brown exterior" despite 9 white interior photos
   - `primary_color = "brown"` (not "white")

2. **Adaptive K=1 (Line 1331)**
   - Used best single image match for visual queries
   - Prevented interior photo dilution

3. **First Image Boosting (Lines 1504-1527)**
   - Property B got 1.2x boost (white exterior: 0.91 score)
   - Property A got no boost (brown exterior: 0.52 score)
   - **Impact:** +20% rank boost for correct matches

4. **Adaptive RRF Weights (Lines 1438-1441)**
   - Visual-dominant query → image kNN boosted (k=30)
   - **Impact:** Image score contributes 0.0323 vs BM25's 0.0164

### ❌ What Didn't Work

1. **BM25 Context Blindness (Lines 1218-1251)**
   - Query "white house" matched "white walls", "white cabinets", "white trim"
   - Property A scored 8.6 (false positive)
   - Property B scored 9.0 (correct, but margin too small)
   - **Problem:** BM25 can't distinguish "white house" from "white interior"

2. **Text Embedding Dilution (Lines 599-622)**
   - Property A embedding includes: "brown exterior... white walls..."
   - Mixed signal: cosine similarity = 0.68 (should be lower)
   - **Problem:** Aggregation mixes contradictory contexts

3. **Final Rank Still Includes False Positive (Line 1669)**
   - Property A ranks #4 (score 0.0640)
   - Should be excluded entirely or ranked much lower
   - **Problem:** Even with all mitigations, false positive persists

---

## Conclusion

The code trace reveals that **multiple mitigations work individually** but **don't fully eliminate false positives**:

- Majority voting: ✅ Correctly labels exterior as "brown"
- RRF fusion: ✅ Balances strategies
- First image boosting: ✅ Prioritizes correct exterior matches
- Adaptive K=1: ✅ Uses best single image

**But the fundamental problem remains:**
- BM25 sees "white" 3 times in `visual_features_text`
- Text embedding mixes "brown exterior" + "white walls" semantics
- Result: False positive still appears in top 5 results

**Best fix:** Separate fields for exterior/interior contexts to eliminate aggregation-based confusion entirely.
