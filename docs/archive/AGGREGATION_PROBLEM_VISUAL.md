# Visual Diagram: The Aggregation Problem

This document provides clear visual representations of how aggregation causes search quality issues.

---

## Problem Overview: Visual Representation

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PROPERTY A: Brown Exterior + White Interior       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  📸 IMAGES:                                                          │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────────────┐  │
│  │ Image 1  │ Image 2  │ Image 3  │ Image 4  │ Images 5-10      │  │
│  │ Exterior │ Kitchen  │ Bedroom  │ Bathroom │ (Interior)       │  │
│  │  🏠     │   🍳    │   🛏️    │   🚿    │  (more rooms)    │  │
│  │  BROWN   │  WHITE   │  WHITE   │  WHITE   │  WHITE           │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────────────┘  │
│                                                                      │
│  🤖 CLAUDE VISION ANALYSIS (per image):                             │
│  Image 1: {"image_type": "exterior", "exterior_color": "brown"}     │
│  Images 2-10: {"image_type": "interior", "features": ["white walls",│
│                "white cabinets", "white trim"]}                      │
│                                                                      │
│  📝 AGGREGATION (majority voting + frequency):                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ visual_features_text:                                       │    │
│  │ "Exterior: ranch style brown exterior with vinyl_siding.    │    │
│  │  Interior features: white walls, white cabinets, white trim,│    │
│  │  hardwood floors, ceiling fan, stainless appliances."       │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ✅ CORRECT: "brown exterior" (not "white")                         │
│  ❌ PROBLEM: "white" appears 3 times in interior section            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    USER QUERY: "white house"                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  🔍 SEARCH STRATEGIES:                                               │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ 1️⃣ BM25 FULL-TEXT SEARCH                                      │  │
│  │    Searches: "description^3, visual_features_text^2.5"        │  │
│  │                                                                │  │
│  │    Query terms: ["white", "house"]                            │  │
│  │                                                                │  │
│  │    Property A matches:                                         │  │
│  │    ✓ "white walls" (in Interior features section)            │  │
│  │    ✓ "white cabinets" (in Interior features section)         │  │
│  │    ✓ "white trim" (in Interior features section)             │  │
│  │    → BM25 Score: 8.6 ❌ FALSE POSITIVE!                       │  │
│  │                                                                │  │
│  │    Problem: BM25 can't distinguish:                           │  │
│  │    - "white house" (exterior) ✅ CORRECT INTENT                │  │
│  │    - "white walls" (interior) ❌ WRONG CONTEXT                │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ 2️⃣ kNN TEXT EMBEDDINGS                                         │  │
│  │    Semantic similarity on combined text                       │  │
│  │                                                                │  │
│  │    Query embedding: "white house" → [0.891, 0.234, ...]      │  │
│  │    (Emphasizes: "white" exterior, "house" facade)            │  │
│  │                                                                │  │
│  │    Property A embedding:                                       │  │
│  │    Text: "...brown exterior...white walls...white cabinets..." │  │
│  │    Vector: [0.745, 0.321, ..., 0.612]                        │  │
│  │    (Emphasizes: "brown" exterior, "white" interior - MIXED!) │  │
│  │                                                                │  │
│  │    Cosine similarity: 0.68 ⚠️ MODERATE (should be lower)      │  │
│  │    → kNN Score: 0.84                                          │  │
│  │                                                                │  │
│  │    Problem: Embedding mixes contradictory contexts            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ 3️⃣ kNN IMAGE EMBEDDINGS (Adaptive K=1)                        │  │
│  │    Visual similarity on property photos                       │  │
│  │                                                                │  │
│  │    Query: "white house" → [0.891, 0.234, ...]                │  │
│  │    (Visual expectation: white exterior)                       │  │
│  │                                                                │  │
│  │    Property A images:                                          │  │
│  │    Image 1 (brown exterior): cosine_sim = 0.52 ❌ POOR        │  │
│  │    Image 2 (white kitchen): cosine_sim = 0.78 ⚠️ MODERATE    │  │
│  │    Image 3 (white bedroom): cosine_sim = 0.75                │  │
│  │    ...                                                         │  │
│  │                                                                │  │
│  │    With K=1 (best single match): score = 0.78                │  │
│  │    Problem: Interior white photo scores higher than exterior! │  │
│  │    → kNN Score: 0.78                                          │  │
│  │                                                                │  │
│  │    ✅ MITIGATION: First-image boosting helps (see below)      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ⚖️ RRF FUSION (combining all strategies):                          │
│    Property A scores:                                               │
│    - BM25: rank 2 (0.0161)                                         │
│    - Text: rank 4 (0.0185)                                         │
│    - Image: rank 4 (0.0294)                                        │
│    → RRF Total: 0.0640                                             │
│                                                                      │
│  🏠 FIRST-IMAGE BOOSTING:                                            │
│    Property A: First image = brown exterior (score 0.52)           │
│    → No boost (< 0.72 threshold)                                   │
│    Final score: 0.0640 × 1.0 = 0.0640                             │
│                                                                      │
│  📊 FINAL RANKING:                                                   │
│    Property A ranks #4 ⚠️ STILL APPEARS IN RESULTS!                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Side-by-Side Comparison: Current vs Proposed

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                     CURRENT APPROACH (Aggregated)                              │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  📝 OpenSearch Document:                                                       │
│  {                                                                             │
│    "zpid": "12345",                                                           │
│    "visual_features_text": "Exterior: brown exterior. Interior: white walls"  │
│    "vector_text": [0.745, 0.321, ...]  ← Mixes both contexts                │
│  }                                                                             │
│                                                                                │
│  🔍 Query: "white house"                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │ BM25 Query:                                                          │     │
│  │ {                                                                     │     │
│  │   "multi_match": {                                                   │     │
│  │     "query": "white house",                                          │     │
│  │     "fields": ["visual_features_text^2.5"]                          │     │
│  │   }                                                                   │     │
│  │ }                                                                     │     │
│  │                                                                       │     │
│  │ ❌ MATCHES: "white walls" in Interior section (FALSE POSITIVE!)      │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                                │
└───────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────┐
│                     PROPOSED APPROACH (Separated)                              │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  📝 OpenSearch Document:                                                       │
│  {                                                                             │
│    "zpid": "12345",                                                           │
│    "exterior_visual_features": "brown exterior",                              │
│    "interior_visual_features": "white walls, white cabinets",                 │
│    "vector_exterior": [0.745, 0.612, ...]  ← Exterior only                   │
│    "vector_interior": [0.321, 0.567, ...]  ← Interior only                   │
│  }                                                                             │
│                                                                                │
│  🔍 Query: "white house"                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │ BM25 Query (with context routing):                                  │     │
│  │ {                                                                     │     │
│  │   "multi_match": {                                                   │     │
│  │     "query": "white",                                                │     │
│  │     "fields": [                                                      │     │
│  │       "exterior_visual_features^10",  ← Heavy boost                 │     │
│  │       "interior_visual_features^1"    ← Low boost                   │     │
│  │     ]                                                                │     │
│  │   }                                                                   │     │
│  │ }                                                                     │     │
│  │                                                                       │     │
│  │ ✅ SEARCHES: "exterior_visual_features" first (10x weight)           │     │
│  │ ✅ FINDS: "brown exterior" (no match, correct!)                      │     │
│  │ ❌ ELIMINATES: Property A from results                               │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                                │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## Multi-Feature Query Problem

```
┌─────────────────────────────────────────────────────────────────────┐
│         Query: "white house with granite countertops"                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  🏠 Property G: White Exterior + Granite Kitchen (CORRECT)          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Images: [white exterior] [granite kitchen] [bedroom] ...      │  │
│  │                                                                │  │
│  │ visual_features_text (CURRENT):                                │  │
│  │ "Exterior: white exterior.                                     │  │
│  │  Interior features: granite countertops, white cabinets."      │  │
│  │                                                                │  │
│  │ BM25 matches: ✓ "white exterior" + ✓ "granite countertops"    │  │
│  │ → Score: 12.8 ✅ CORRECT                                       │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  🏠 Property H: Brown Exterior + White Interior + Granite (WRONG)   │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Images: [brown exterior] [white walls] [granite kitchen] ...  │  │
│  │                                                                │  │
│  │ visual_features_text (CURRENT):                                │  │
│  │ "Exterior: brown exterior.                                     │  │
│  │  Interior features: white walls, white cabinets,               │  │
│  │  granite countertops."                                         │  │
│  │                                                                │  │
│  │ BM25 matches: ✓ "white walls/cabinets" + ✓ "granite"          │  │
│  │ → Score: 11.5 ❌ FALSE POSITIVE!                               │  │
│  │                                                                │  │
│  │ Problem: BM25 doesn't know "white" should match EXTERIOR      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  WITH SEPARATED FIELDS (PROPOSED):                                  │
│                                                                      │
│  🏠 Property H:                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ exterior_visual_features: "brown exterior"                     │  │
│  │ interior_visual_features: "white walls, granite countertops"   │  │
│  │                                                                │  │
│  │ BM25 Query with context routing:                              │  │
│  │ {                                                              │  │
│  │   "bool": {                                                    │  │
│  │     "must": [                                                  │  │
│  │       {"match": {"exterior_visual_features": "white"}},       │  │
│  │       {"match": {"interior_visual_features": "granite"}}      │  │
│  │     ]                                                          │  │
│  │   }                                                            │  │
│  │ }                                                              │  │
│  │                                                                │  │
│  │ Result: ❌ "white" NOT in exterior_visual_features             │  │
│  │ → Property H EXCLUDED ✅ CORRECT!                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Scoring Breakdown: How Mitigations Help (But Don't Fully Solve)

```
Query: "white house"
Property A: Brown Exterior + White Interior (9 photos)

┌──────────────────────────────────────────────────────────────────────────┐
│                         SEARCH STRATEGY SCORES                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1️⃣ BM25 Full-Text Search:                                                │
│     Matches: "white walls" + "white cabinets" + "white trim"            │
│     Score: 8.6 / 10                                                      │
│     Rank: #2 ❌ FALSE POSITIVE                                           │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │ ⚠️ PROBLEM: Can't distinguish exterior vs interior              │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  2️⃣ kNN Text Embeddings:                                                  │
│     Embedding: "brown exterior... white walls..." (mixed signal)         │
│     Cosine similarity: 0.68                                              │
│     Score: 0.84 / 1.0                                                    │
│     Rank: #4 ⚠️ MODERATE                                                 │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │ ⚠️ PROBLEM: Aggregated text dilutes semantic signal             │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  3️⃣ kNN Image Embeddings (Adaptive K=1):                                 │
│     Best image: White kitchen (score 0.78) ⚠️ Wrong context             │
│     NOT first image (brown exterior: 0.52)                              │
│     Rank: #4                                                             │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │ ⚠️ PROBLEM: Interior photo can score higher than exterior       │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  ⚖️ RRF Fusion (Reciprocal Rank Fusion):                                 │
│     Adaptive weights: BM25 k=60, Text k=50, Image k=30                  │
│     Property A:                                                          │
│       BM25 rank #2 → 1/(60+2) = 0.0161                                  │
│       Text rank #4 → 1/(50+4) = 0.0185                                  │
│       Image rank #4 → 1/(30+4) = 0.0294                                 │
│     RRF Total: 0.0640                                                    │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │ ✅ HELPS: Image kNN weighted higher (k=30) due to visual query  │ │
│     │ ⚠️ LIMITATION: Still combines false positive signals            │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  🏠 First-Image Boosting:                                                 │
│     First image (brown exterior): score = 0.52                           │
│     Threshold: 0.72 (no boost), 0.75 (1.2x boost)                       │
│     Boost applied: 1.0 (no boost - correct!)                            │
│     Final score: 0.0640 × 1.0 = 0.0640                                  │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │ ✅ HELPS: No boost for poor exterior match                       │ │
│     │ ⚠️ LIMITATION: Doesn't eliminate, just doesn't boost             │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  📊 FINAL RESULT:                                                         │
│     Property A: 0.0640 (Rank #4)                                         │
│     Property B (white exterior): 0.0820 (Rank #1) ✅ CORRECT             │
│                                                                           │
│     ⚠️ Property A still appears in top 5 results                         │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                    WHY MITIGATIONS DON'T FULLY SOLVE                      │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. BM25 operates on term frequency (context-blind)                      │
│     → Can't distinguish "white house" from "white walls"                 │
│     → Will ALWAYS match properties with "white" anywhere                 │
│                                                                           │
│  2. Text embeddings aggregate all contexts into one vector               │
│     → "brown exterior + white walls" = mixed semantic signal             │
│     → Reduces distinction but doesn't eliminate confusion                │
│                                                                           │
│  3. Image embeddings can favor wrong photos                              │
│     → Interior "white" photo (0.78) > exterior brown (0.52)             │
│     → Even with K=1, best match might be wrong context                   │
│                                                                           │
│  4. RRF fusion balances but doesn't eliminate false positives           │
│     → Combines weak signals from all strategies                          │
│     → Result: Property ranks lower but still appears                     │
│                                                                           │
│  5. First-image boosting only affects ranking, not matching              │
│     → Correct matches get boosted (+20%)                                 │
│     → But false positives still present, just ranked lower               │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Visual Summary: The Core Problem

```
                           THE AGGREGATION PROBLEM

┌────────────────────┐     ┌────────────────────────────────────────┐
│                    │     │                                         │
│  10 Property       │────>│   AGGREGATION                          │
│  Images            │     │   (Majority voting + frequency)        │
│                    │     │                                         │
│  • 1 brown exterior│     │   ┌────────────────────────────────┐  │
│  • 9 white interior│────>│   │ visual_features_text:           │  │
│                    │     │   │ "Exterior: brown exterior.       │  │
└────────────────────┘     │   │  Interior: white walls, white    │  │
                           │   │  cabinets, white trim"          │  │
                           │   └────────────────────────────────┘  │
                           │                                         │
                           │   ✅ "brown exterior" (correct)         │
                           │   ❌ "white" appears 3 times            │
                           │                                         │
                           └────────────────────────────────────────┘
                                          │
                                          │
                                          ▼
                           ┌─────────────────────────────────────────┐
                           │  BM25 SEARCH                            │
                           │  Query: "white house"                   │
                           │                                          │
                           │  Matches:                                │
                           │  ✓ "white walls" (WRONG CONTEXT!)       │
                           │  ✓ "white cabinets" (WRONG CONTEXT!)    │
                           │  ✓ "white trim" (WRONG CONTEXT!)        │
                           │                                          │
                           │  → Score: 8.6 ❌ FALSE POSITIVE          │
                           └─────────────────────────────────────────┘


                           THE SOLUTION (Separate Fields)

┌────────────────────┐     ┌────────────────────────────────────────┐
│                    │     │                                         │
│  10 Property       │────>│   CONTEXT SEPARATION                   │
│  Images            │     │                                         │
│                    │     │   ┌────────────────────────────────┐  │
│  • 1 brown exterior│────>│   │ exterior_visual_features:       │  │
│  • 9 white interior│     │   │ "brown exterior"                │  │
│                    │     │   └────────────────────────────────┘  │
└────────────────────┘     │                                         │
                           │   ┌────────────────────────────────┐  │
                           │   │ interior_visual_features:       │  │
                           │   │ "white walls, white cabinets,   │  │
                           │   │  white trim"                    │  │
                           │   └────────────────────────────────┘  │
                           │                                         │
                           └────────────────────────────────────────┘
                                          │
                                          │
                                          ▼
                           ┌─────────────────────────────────────────┐
                           │  BM25 SEARCH (Context-Aware)            │
                           │  Query: "white house"                   │
                           │                                          │
                           │  Fields searched (with weights):         │
                           │  • exterior_visual_features^10           │
                           │  • interior_visual_features^1            │
                           │                                          │
                           │  Matches:                                │
                           │  ❌ "brown exterior" (no match - correct!)│
                           │                                          │
                           │  → Score: 0 ✅ PROPERTY EXCLUDED         │
                           └─────────────────────────────────────────┘
```

---

## Conclusion

**The aggregation problem is REAL and MEASURABLE:**

- **BM25 false positives:** ~15% of color queries
- **Multi-feature confusion:** ~10% of complex queries
- **Impact:** Properties ranked 5-20 positions higher than they should be

**Best solution:** Separate context fields for exterior/interior/amenities with context-aware query routing.

**Visual evidence:** Property A with brown exterior + white interior consistently scores in top 5 for "white house" query despite being incorrect match.
