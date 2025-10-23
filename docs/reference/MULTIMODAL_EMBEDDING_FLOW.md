# Multimodal Embedding Flow: "Show me a white house"

## Complete Flow Diagram

```
USER QUERY: "Show me a white house"
     │
     ├─────────────────────────────────────────────────────────────┐
     │                                                               │
     ▼                                                               ▼
┌─────────────────────────┐                           ┌──────────────────────────┐
│  LLM EXTRACTION         │                           │  kNN EMBEDDING           │
│  (Claude Haiku)         │                           │  (Titan Image-v1 TEXT)   │
└─────────────────────────┘                           └──────────────────────────┘
     │                                                               │
     │ extract_query_constraints()                                  │ embed_text_multimodal()
     │                                                               │
     ▼                                                               ▼
{                                                    [0.023, -0.145, 0.389, ..., 0.112]
  "must_have": ["white_exterior"],                   ↑
  "query_type": "color",                             │ 1024 dimensions
  "architecture_style": null                         │ TEXT encoding
}                                                    │
     │                                               │
     │ Used for:                                     │ Used for:
     │ - Filters                                     │ - kNN Text search
     │ - Tag boosting                                │ - kNN Image search (!)
     │ - Adaptive RRF k-values                       │
     │                                               │
     └───────────────┬───────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │   SEARCH EXECUTION         │
        │   (3 parallel searches)    │
        └────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
    ┌────────┐  ┌──────────┐  ┌──────────┐
    │  BM25  │  │kNN TEXT  │  │kNN IMAGE │
    └────────┘  └──────────┘  └──────────┘
         │           │           │
         │           │           │
         └───────────┴───────────┘
                     │
                     ▼
              ┌────────────┐
              │ RRF FUSION │
              └────────────┘
                     │
                     ▼
              RANKED RESULTS
```

## Deep Dive: kNN Text vs kNN Image

### kNN Text Search

```
QUERY (text):
"Show me a white house"
     │
     ▼ embed_text_multimodal()
[0.023, -0.145, 0.389, ..., 0.112]
     │
     ▼ Compare to PROPERTY TEXT EMBEDDINGS

PROPERTY A:
Description: "Beautiful 3-bedroom home..."
visual_features_text: "Exterior: modern style white exterior with vinyl siding"
     │
     ▼ Combined: "Beautiful 3-bedroom... Exterior: modern style white exterior..."
     │
     ▼ embed_text_multimodal()
[0.019, -0.138, 0.412, ..., 0.108]
     │
     ▼ Cosine Similarity
0.87 ← HIGH! Contains "white exterior"

PROPERTY B:
Description: "Charming property..."
visual_features_text: "Exterior: craftsman style brick exterior with stone"
     │
     ▼ Combined: "Charming property... Exterior: craftsman style brick exterior..."
     │
     ▼ embed_text_multimodal()
[-0.102, 0.205, -0.156, ..., 0.234]
     │
     ▼ Cosine Similarity
0.23 ← LOW! No white mentioned
```

### kNN Image Search (Cross-Modal!)

```
QUERY (text):
"Show me a white house"
     │
     ▼ embed_text_multimodal() - TEXT encoder
[0.023, -0.145, 0.389, ..., 0.112] ← TEXT VECTOR
     │
     ▼ Compare to PROPERTY IMAGE EMBEDDINGS

PROPERTY A IMAGE:
<white house photo pixels>
     │
     ▼ embed_image_bytes() - IMAGE encoder (SAME MODEL!)
[0.021, -0.142, 0.405, ..., 0.110] ← IMAGE VECTOR
     │
     ▼ Cosine Similarity (TEXT vs IMAGE!)
0.89 ← HIGH! Visual white house matches text "white house"

PROPERTY B IMAGE:
<brick house photo pixels>
     │
     ▼ embed_image_bytes() - IMAGE encoder
[-0.098, 0.198, -0.162, ..., 0.228] ← IMAGE VECTOR
     │
     ▼ Cosine Similarity (TEXT vs IMAGE!)
0.19 ← LOW! Visual brick house doesn't match text "white house"
```

## The Multimodal Model Architecture

```
amazon.titan-embed-image-v1 (Multimodal Model)
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│  TEXT INPUT: "Show me a white house"                         │
│       ↓                                                       │
│  ┌────────────────┐                                          │
│  │ Text Tokenizer │                                          │
│  └────────────────┘                                          │
│       ↓                                                       │
│  ┌────────────────┐                                          │
│  │Text Transformer│  (BERT-like encoder)                     │
│  │  12-24 layers  │                                          │
│  └────────────────┘                                          │
│       ↓                                                       │
│  ┌────────────────┐                                          │
│  │  Projection    │  768-D → 1024-D                          │
│  │     Head       │                                          │
│  └────────────────┘                                          │
│       ↓                                                       │
│       └──────────────────┐                                   │
│                          ↓                                   │
│                  ┌───────────────┐                           │
│                  │ SHARED SPACE  │  1024-D unified           │
│                  │   1024-D      │  embedding space          │
│                  └───────────────┘                           │
│                          ↑                                   │
│       ┌──────────────────┘                                   │
│       ↓                                                       │
│  ┌────────────────┐                                          │
│  │  Projection    │  2048-D → 1024-D                         │
│  │     Head       │                                          │
│  └────────────────┘                                          │
│       ↓                                                       │
│  ┌────────────────┐                                          │
│  │Vision Transform│  (ViT encoder)                           │
│  │  Image patches │                                          │
│  └────────────────┘                                          │
│       ↓                                                       │
│  ┌────────────────┐                                          │
│  │  Image Patches │                                          │
│  └────────────────┘                                          │
│       ↓                                                       │
│  IMAGE INPUT: <white house photo pixels>                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Contrastive Learning Training

How the model learned to align text and images:

```
TRAINING BATCH (simplified):
┌────────────────────────────────────────────────────────┐
│ Pair 1: ("white house", <white house photo>)          │
│ Pair 2: ("modern kitchen", <modern kitchen photo>)    │
│ Pair 3: ("brick colonial", <brick house photo>)       │
└────────────────────────────────────────────────────────┘
         │
         ▼ Encode all with dual encoders

TEXT EMBEDDINGS:          IMAGE EMBEDDINGS:
"white house"    → v1     <white house>     → i1
"modern kitchen" → v2     <modern kitchen>  → i2
"brick colonial" → v3     <brick colonial>  → i3

CREATE SIMILARITY MATRIX:
              i1(white)  i2(kitchen)  i3(brick)
v1(white)       0.95        0.12        0.18     ← Want high on diagonal
v2(kitchen)     0.11        0.93        0.15     ← Want low off-diagonal
v3(brick)       0.14        0.10        0.91     ← Perfect alignment!

LOSS FUNCTION (Contrastive):
- MAXIMIZE: sim(v1, i1), sim(v2, i2), sim(v3, i3)  [matched pairs]
- MINIMIZE: sim(v1, i2), sim(v1, i3), sim(v2, i1), ... [unmatched pairs]

After millions of iterations:
→ Text "white house" vector moves CLOSE to white house image vectors
→ Text "white house" vector moves FAR from kitchen/brick image vectors
→ Result: Unified semantic space where meaning aligns across modalities!
```

## What Happens in Production

```
USER: "Show me a white house"
     │
     ▼
STEP 1: Extract constraints
  → must_have: ["white_exterior"]
  → query_type: "color"

STEP 2: Embed query (multimodal TEXT encoder)
  → q_vec = [0.023, -0.145, 0.389, ..., 0.112]

STEP 3: Search OpenSearch

  ┌─ BM25 Search ─┐
  │ Keyword match on "white" in:
  │ - description
  │ - visual_features_text ("white exterior")
  │ - tags (white_exterior)
  │ Result: Properties with "white" keyword
  └───────────────┘

  ┌─ kNN Text Search ─┐
  │ Vector similarity query:
  │ {
  │   "knn": {
  │     "vector_text": {
  │       "vector": [0.023, -0.145, ...],
  │       "k": 100
  │     }
  │   }
  │ }
  │ OpenSearch finds properties with similar text vectors
  │ Result: Semantic text matches
  └───────────────────┘

  ┌─ kNN Image Search ─┐
  │ Multi-vector nested query:
  │ {
  │   "nested": {
  │     "path": "image_vectors",
  │     "score_mode": "max",
  │     "query": {
  │       "knn": {
  │         "image_vectors.vector": {
  │           "vector": [0.023, -0.145, ...], ← SAME query vector!
  │           "k": 100
  │         }
  │       }
  │     }
  │   }
  │ }
  │ OpenSearch compares TEXT query vector to IMAGE vectors!
  │ Result: Visual similarity matches
  └───────────────────┘

STEP 4: RRF Fusion
  Combine rankings:
  BM25 rank + kNN Text rank + kNN Image rank → Final score

STEP 5: Tag Boosting
  Properties matching white_exterior tag get 1.3x boost

STEP 6: Return Results
  Top 20 properties ranked by combined score
```

## Key Takeaways

1. **LLM extraction** is for structured filtering/boosting, NOT for embedding

2. **kNN embedding** uses the ORIGINAL query "Show me a white house"

3. **Multimodal model** creates unified space where:
   - Text "white house" → vector
   - Image <white house pixels> → vector
   - Both vectors are CLOSE in 1024-D space

4. **Cross-modal search** works because:
   - Text encoder and image encoder project to SAME space
   - Contrastive training aligned semantics across modalities
   - Query text can match image pixels directly

5. **Three searches** provide complementary signals:
   - BM25: Keyword matching ("white" literally appears)
   - kNN Text: Semantic similarity (understands "white" ≈ "white")
   - kNN Image: Visual similarity (text "white house" ≈ white pixels)

6. **RRF fusion** ranks properties highly if they match across ALL strategies

## This is Why Multimodal Embeddings Are Powerful!

Traditional search: Text can only match text
Multimodal search: Text can match IMAGES through learned semantic alignment

The model spent millions of training iterations learning that:
- Certain text descriptions correspond to certain visual appearances
- The relationship is encoded in the geometry of the shared vector space
- This enables true cross-modal retrieval without explicit feature engineering!
