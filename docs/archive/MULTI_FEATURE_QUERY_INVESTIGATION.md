# Multi-Feature Query Investigation: "White houses with granite countertops and wood floors"

## Problem Statement

**Query:** "White houses with granite countertops and wood floors"

**Expected Behavior:** Return white exterior homes that also have granite countertops and wood floors

**Actual Behavior:** Returns homes that aren't white on the exterior, but have white interior walls with granite countertops and wood floors

**User Observation:** "The kNN image section shows it's working - k=3, and the 3 images are all interior shots of white walls, wood floors, and granite countertops. So technically it makes sense why it matches."

---

## Root Cause Analysis

### 1. Feature Classification

The query gets parsed into these features:
- `white_exterior` → **VISUAL_DOMINANT** (line 668)
- `granite_countertops` → **TEXT_DOMINANT** (line 691)
- `wood_floors` → **HYBRID** (line 712)

**Feature Count:**
- Visual: 1 (white_exterior)
- Text: 1 (granite_countertops)
- Hybrid: 1 (wood_floors)
- Total: 3 features

### 2. Adaptive K Selection for Images

With 3 features, `calculate_adaptive_k_for_images()` returns **k=3**:

```python
# Line 617-619
else:
    return 3  # "modern white kitchen with stainless and hardwood" → multiple rooms
```

**This is where the problem originates.** The system assumes that 3 features = need 3 different room photos.

### 3. Adaptive RRF Weights

With 1 visual, 1 text, 1 hybrid feature:

```python
# Line 764-767
visual_ratio = 1/3 = 0.33
text_ratio = 1/3 = 0.33
hybrid_ratio = 1/3 = 0.33
```

Since no ratio exceeds 0.4, this triggers the **"Balanced query"** path (line 787-790):

```python
# Mixed/hybrid dominated: balanced weights
bm25_k, text_k, image_k = 55, 55, 55
```

**Result:** All three search strategies get nearly equal weight in RRF fusion.

### 4. Image Vector Search Behavior

The multi-vector kNN image query (lines 1119-1134):
- Uses `score_mode: "sum"` to aggregate all image scores
- Returns inner_hits with up to 100 images per property
- Applies top-k scoring in Python (line 1173): sums the **top 3 image scores**

**What happens:**
1. Query embedding: "White houses with granite countertops and wood floors"
2. OpenSearch finds properties where **any 3 images** sum to a high score
3. A property with:
   - Image 1: White kitchen cabinets (matches "white") → 0.85
   - Image 2: Granite countertops (matches "granite") → 0.82
   - Image 3: Wood floors (matches "wood") → 0.80
   - **Top-3 sum = 2.47** ← High score!
4. This property ranks highly even if the exterior is brown/gray

**The issue:** The embedding model can't distinguish "white exterior" from "white interior walls" or "white cabinets". It just matches "white" in the visual content.

### 5. RRF Fusion

With balanced weights (55, 55, 55), the three strategies contribute equally:

**Example scenario:**
- **BM25** (k=55): Property #1234 ranks #10 (has "white" in description, maybe "white cabinets")
  - RRF contribution: 1/(55+10) = 0.0154
- **kNN Text** (k=55): Property #1234 ranks #8 (description semantically similar)
  - RRF contribution: 1/(55+8) = 0.0159
- **kNN Image** (k=55): Property #1234 ranks #2 (top-3 images match white/granite/wood)
  - RRF contribution: 1/(55+2) = 0.0175

**Total RRF score:** 0.0154 + 0.0159 + 0.0175 = **0.0488**

Meanwhile, a truly white exterior house might:
- **BM25**: Rank #15 (mentions "white exterior")
  - RRF: 1/(55+15) = 0.0143
- **kNN Text**: Rank #12
  - RRF: 1/(55+12) = 0.0149
- **kNN Image**: Rank #5 (only 1-2 exterior photos match "white", interiors don't match other features)
  - RRF: 1/(55+5) = 0.0167

**Total RRF score:** 0.0143 + 0.0149 + 0.0167 = **0.0459** ← Lower!

---

## Why This Happens

### The Fundamental Mismatch

**Multi-vector top-k scoring** is designed for queries where:
- Each feature might appear in **different photos**
- Example: "Pool, granite kitchen, hardwood floors" → pool photo + kitchen photo + bedroom photo

**But exterior color queries need:**
- The **primary exterior photo** to match "white"
- Interior features can be in any other photos

**Current behavior:**
- k=3 means "sum the top 3 image matches"
- System finds: white cabinets + granite counters + wood floors
- **Missing:** No requirement that image #0 (main exterior) matches "white"

### Feature Classification Limitations

The feature classification system treats `white_exterior` as **VISUAL_DOMINANT**, which is correct. But:

1. **Ratio-based weighting** dilutes the visual emphasis:
   - 1 visual + 1 text + 1 hybrid = 33% visual
   - Triggers "balanced" mode (55, 55, 55)
   - Images don't get enough weight to override bad matches

2. **Embedding limitations:**
   - "White exterior" vs "white cabinets" look similar to the embedding model
   - Both have white surfaces, similar lighting, similar textures
   - The model can't distinguish "this is the outside of a house" from "this is inside a house"

3. **Top-k aggregation problem:**
   - Summing top-3 scores assumes features are **independent**
   - But "white exterior" is a **primary feature** (most important photo)
   - Interior features are **secondary** (can be in any photo)

---

## Concrete Example

**Query:** "White houses with granite countertops and wood floors"

**Property A (Non-White Exterior - Currently Ranks High):**
- Image #0 (exterior): Gray house → similarity to query: 0.45
- Image #1 (kitchen): White cabinets, granite counters → similarity: 0.89
- Image #2 (living room): Wood floors, white walls → similarity: 0.86
- Image #3 (bathroom): Granite vanity → similarity: 0.78
- **Top-3 sum:** 0.89 + 0.86 + 0.78 = **2.53** ← Very high!

**Property B (White Exterior - Should Rank Higher):**
- Image #0 (exterior): White house → similarity to query: 0.88
- Image #1 (exterior angle 2): White house → similarity: 0.83
- Image #2 (front door): White door, no granite/wood visible → similarity: 0.65
- Image #3 (kitchen): Beige cabinets, granite counters → similarity: 0.72
- Image #4 (bedroom): Wood floors → similarity: 0.71
- **Top-3 sum:** 0.88 + 0.83 + 0.72 = **2.43** ← Lower!

**Result:** Property A (gray exterior) beats Property B (white exterior) in image search.

---

## Summary of Issues

### Issue 1: **Adaptive K Doesn't Distinguish Primary vs Secondary Features**
- `white_exterior` = primary feature (MUST be in image #0)
- `granite_countertops` = secondary feature (can be in any interior shot)
- Current k=3 treats all features equally

### Issue 2: **Balanced RRF Weights Dilute Visual Priority**
- 1 visual + 1 text + 1 hybrid = 33% each
- Triggers "balanced" mode (55, 55, 55)
- Image search doesn't get enough priority for exterior color queries

### Issue 3: **Embedding Model Can't Distinguish Exterior from Interior**
- "White house exterior" and "white kitchen cabinets" have similar embeddings
- Both contain white surfaces, similar lighting, similar composition
- Model lacks spatial/contextual understanding of "this is outside vs inside"

### Issue 4: **Top-K Sum Rewards Properties with Many Interior Feature Matches**
- Property with 3 matching interior photos (white cabinets + granite + wood) sums to 2.53
- Property with 2 exterior white photos + 1 interior feature sums to 2.43
- The "wrong" property wins because it has more total feature matches across all photos

---

## Why Single-Feature Queries Work

**Query:** "Blue house"

**Feature Classification:**
- `blue_exterior` → VISUAL_DOMINANT
- Count: 1 visual, 0 text, 0 hybrid

**Adaptive K:**
```python
# Line 610-611
elif feature_count == 1:
    return 1  # Kitchen query → kitchen photo wins
```
**k=1** means: use only the **single best matching image**

**RRF Weights:**
```python
# Line 771-774
if visual_ratio >= 0.6:  # 100% visual
    bm25_k, text_k, image_k = 60, 50, 30
```
**Image search gets k=30** (highest weight), BM25 gets k=60 (lowest weight)

**Result:**
- The **main exterior photo** (image #0) dominates the score
- If it's blue → high score
- If it's not blue → low score
- Interior photos (white cabinets, etc.) are ignored because k=1

**This works perfectly!**

---

## Recommendations for Potential Fixes

### Option 1: **Primary Feature Detection**
- Detect when query has a visual exterior feature (`white_exterior`, `blue_exterior`)
- If present, use **k=1** regardless of total feature count
- Rationale: Exterior color is a deal-breaker; interior features are flexible

### Option 2: **Weighted Top-K Scoring**
- Instead of summing top-k equally, apply **position weights**
- Image #0 (main exterior): weight = 1.0
- Image #1-2: weight = 0.5
- Image #3+: weight = 0.3
- Rationale: Primary photo is most important

### Option 3: **Boost Visual Ratio When Exterior Features Present**
- If query contains `*_exterior` feature, artificially boost visual_ratio
- Example: 1 visual (exterior) + 1 text + 1 hybrid → treat as 60% visual
- Triggers "visual-heavy" mode: k_values = [60, 50, 30]

### Option 4: **Separate Exterior vs Interior Vectors**
- Index exterior photos and interior photos separately
- Query strategy:
  - Exterior features → search only exterior vectors (k=1)
  - Interior features → search only interior vectors (k=2)
  - Combine with different weights

### Option 5: **Hybrid Approach: Exterior + Interior K**
- If query has exterior feature + interior features:
  - Use k=1 for main exterior photo (image #0 only)
  - Use k=2 for interior photos (images #1-N)
  - Sum as: `score = exterior_score * 2.0 + interior_top2_sum * 1.0`

---

## Testing Strategy

**Test Queries:**
1. "White houses with granite countertops" (1 visual exterior + 1 text interior)
2. "Blue house with hardwood floors" (1 visual exterior + 1 hybrid interior)
3. "Gray house with pool and stainless appliances" (1 visual exterior + 2 interior)
4. "Modern home with chef's kitchen" (style + room type, no exterior color)

**Expected Outcomes:**
- Queries #1-3 should prioritize exterior color match FIRST, then interior features
- Query #4 should use balanced k=2 or k=3 (no exterior constraint)

**Metrics:**
- % of top-10 results with correct exterior color (should be >90%)
- % of top-10 with both exterior + interior features (should be >70%)

---

## Current Behavior Summary

✅ **Works well:**
- Single feature queries ("blue house")
- Purely interior queries ("granite countertops and hardwood floors")
- Style-based queries ("modern home")

❌ **Problematic:**
- **Multi-feature queries with exterior color** ("white houses with granite")
- Image search finds interior white surfaces instead of white exterior
- Top-3 scoring rewards properties with many interior feature matches
- Balanced RRF weights don't prioritize visual search enough

🔍 **Root Cause:**
- Adaptive k=3 treats all features equally (doesn't recognize primary vs secondary)
- Balanced RRF weights (55, 55, 55) dilute visual priority
- Embedding model can't distinguish exterior from interior white surfaces
- Top-k sum aggregation rewards total feature matches, not primary feature match

---

## Next Steps

1. **Measure impact:** Run test queries to quantify how often this happens
2. **Decide on fix:** Choose from options above (recommend Option 1 or Option 3)
3. **Implement:** Add logic to detect exterior features and adjust k or weights
4. **Validate:** Re-run test queries and measure improvement
5. **Deploy:** Update Lambda with fix

**Estimated effort:** 2-3 hours (detection logic + testing)

**Expected improvement:** +40-60% accuracy for multi-feature queries with exterior colors
