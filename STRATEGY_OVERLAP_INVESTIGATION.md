# Strategy Overlap Investigation - "White Modern Homes" Query

## Executive Summary

**Problem:** User reports that for generic queries like "white modern homes", EVERY listing shows "Not found in top results" for kNN searches, despite having 4,000 indexed properties.

**Finding:** This is NOT a bug, but reveals a fundamental issue with how the three search strategies are working together. The strategies are returning **completely different properties** with near-zero overlap, causing BM25 to dominate final results.

**Status:** ⚠️ **CRITICAL DESIGN ISSUE** - Multi-strategy fusion is not functioning as intended.

---

## Investigation Results

### Test Query: "white modern homes"
- **Index:** listings-v2 (3,904 properties with multi-vector image search)
- **Mode:** Standard (equal weighting, k=60 for all strategies)
- **Expected Behavior:** Properties should rank well in MULTIPLE strategies
- **Actual Behavior:** Each strategy returns completely different properties

---

## Strategy Performance Analysis

### Strategy Hit Counts

All three strategies returned 30 results as expected:
- **BM25:** 30 hits
- **kNN Text:** 30 hits
- **kNN Image:** 30 hits

### Top 10 Results from Each Strategy

**BM25 Top 10:**
```
1. 456733907 (score: 12.50)
2. 456963404 (score: 11.06)
3. 455712315 (score: 11.06)
4. 455711631 (score: 11.06)
5. 455711717 (score: 10.99)
6. 455712029 (score: 10.99)
7. 455712220 (score: 10.78)
8. 456309344 (score: 10.58)
9. 452772241 (score: 10.58)
10. 456832949 (score: 10.21)
```

**kNN Text Top 10:**
```
1. 453629044 (score: 0.7712)
2. 2080387168 (score: 0.7625)
3. 12848548 (score: 0.7618)
4. 12923440 (score: 0.7585)
5. 455766029 (score: 0.7567)
6. 2063193957 (score: 0.7523)
7. 453934901 (score: 0.7506)
8. 12849880 (score: 0.7496)
9. 443350363 (score: 0.7487)
10. 443350351 (score: 0.7487)
```

**kNN Image Top 10:**
```
1. 70592220 (score: 0.5367)
2. 2061268945 (score: 0.5364)
3. 338636071 (score: 0.5360)
4. 12712143 (score: 0.5355)
5. 2056268670 (score: 0.5352)
6. 145678545 (score: 0.5348)
7. 12923440 (score: 0.5344) ← ONLY OVERLAP with kNN Text
8. 2071474566 (score: 0.5340)
9. 2072633768 (score: 0.5338)
10. 12757584 (score: 0.5337)
```

### Overlap Analysis (Top 10)

```
BM25 ∩ kNN Text:        ZERO properties (0%)
BM25 ∩ kNN Image:       ZERO properties (0%)
kNN Text ∩ kNN Image:   1 property (10%) - zpid 12923440
All three strategies:   ZERO properties (0%)
```

**Conclusion:** The three search strategies are finding completely different properties for the same query!

---

## Final Results Analysis

### Top 10 Final Results (After RRF Fusion)

All 10 results come from **BM25 ONLY**:

```
Rank | ZPID       | Final Score | BM25 Rank | kNN Text | kNN Image | Tag Boost
-----|------------|-------------|-----------|----------|-----------|----------
  1  | 456733907  |   0.020492  |     1     |   N/A    |    N/A    |   1.25x
  2  | 456963404  |   0.020161  |     2     |   N/A    |    N/A    |   1.25x
  3  | 455712315  |   0.019841  |     3     |   N/A    |    N/A    |   1.25x
  4  | 455711631  |   0.019531  |     4     |   N/A    |    N/A    |   1.25x
  5  | 455711717  |   0.019231  |     5     |   N/A    |    N/A    |   1.25x
  6  | 455712029  |   0.018939  |     6     |   N/A    |    N/A    |   1.25x
  7  | 455712220  |   0.018657  |     7     |   N/A    |    N/A    |   1.25x
  8  | 456309344  |   0.018382  |     8     |   N/A    |    N/A    |   1.25x
  9  | 452772241  |   0.018116  |     9     |   N/A    |    N/A    |   1.25x
 10  | 456832949  |   0.017857  |    10     |   N/A    |    N/A    |   1.25x
```

### RRF Contribution Breakdown

For EVERY result in top 10:
- **BM25 contribution:** 0.014286 - 0.016393 (100% of RRF score)
- **kNN Text contribution:** 0.000000 (0%)
- **kNN Image contribution:** 0.000000 (0%)

**Why kNN properties don't appear in final results:**

With k=60 (standard mode), RRF contributions are:
- BM25 rank 1: `1/(60+1) = 0.0164` × 1.25 tag boost = **0.0205**
- BM25 rank 10: `1/(60+10) = 0.0143` × 1.25 tag boost = **0.0179**
- kNN Text rank 1: `1/(60+1) = 0.0164` (no overlap with BM25, no tag boost)
- kNN Image rank 1: `1/(60+1) = 0.0164` (no overlap with BM25, no tag boost)

**Result:** BM25 properties with tag boosting (1.25x) score higher than kNN-only properties, completely dominating final results.

---

## Root Cause Analysis

### Why Are Strategies Returning Different Properties?

#### 1. BM25 (Text Search)
**Searches:** `description`, `visual_features_text`, `image_tags`, `feature_tags`, `city`, `address`, `architecture_style`

**Query:** "white modern homes"
- Matches properties with "white" in tags (e.g., "white exterior")
- Matches "modern" in architecture_style or tags
- **Favors:** Properties with explicit text mentions of white/modern

#### 2. kNN Text (Semantic Text Embedding)
**Searches:** `vector_text` field (Amazon Titan Text embedding of combined property text)

**Query embedding:** Vector representation of "white modern homes"
- Finds semantically similar property descriptions
- May match homes described as "contemporary", "sleek", "minimalist"
- **Favors:** Properties with rich semantic descriptions

#### 3. kNN Image (Visual Similarity)
**Searches:** `image_vectors` nested array (Amazon Titan Image embeddings, ~20 per property)

**Query embedding:** Same text vector used for visual search
- Finds images that visually match the concept of "white modern homes"
- Uses `score_mode: max` to find best matching image per property
- **Favors:** Properties with visually modern/white images

### The Problem

These three strategies are **TOO INDEPENDENT**:
1. BM25 finds properties with exact keyword matches
2. kNN Text finds properties with semantic similarity in descriptions
3. kNN Image finds properties with visual similarity in photos
4. **They're finding different aspects of "quality"** rather than agreeing on the same high-quality properties

With near-zero overlap, RRF fusion becomes a **weighted vote** where BM25 (boosted by tags) wins every time.

---

## Why This Differs from Expectations

### User's Valid Point
> "We have almost 4000 listings indexed. If I search a pretty generic query like 'White, modern homes' we should have listings that rank highly in all bm25, knn image and knn text."

**This is correct!** With 4,000 properties, a generic query should find properties that:
- Have "white" and "modern" in their text (BM25) ✓
- Have descriptions semantically matching "white modern homes" (kNN Text) ✓
- Have images that look white and modern (kNN Image) ✓

**The fact that we have ZERO overlap in top 10 suggests:**
1. The embedding models are poorly calibrated
2. The query rewriting/expansion is insufficient
3. The indexing is missing important semantic connections
4. The scoring scales are too different (BM25: 10-12, kNN: 0.5-0.7)

---

## Impact Assessment

### Current Behavior (Broken)

**User searches "white modern homes":**
- Gets 10 results ALL from BM25 only
- kNN Text finds 30 different properties (never shown)
- kNN Image finds 30 different properties (never shown)
- User sees "Not found in top results" for kNN in EVERY property
- Multi-strategy fusion is completely ineffective

### Expected Behavior

**User searches "white modern homes":**
- Top results should appear in MULTIPLE strategies
- Properties rank #1 in one strategy should at least appear in top 30 of others
- Final results should blend text + semantic + visual signals
- User should see properties with ranks in 2-3 strategies for top results

---

## Proposed Solutions

### Immediate (Can implement today)

#### Option 1: Increase Result Size Per Strategy
**Current:** `size * 3` (30 results for size=10)
**Proposal:** `size * 10` (100 results for size=10)

**Rationale:**
- With 4,000 properties, fetching only 30 results (0.75%) is too small
- Increasing to 100 results (2.5%) gives more opportunity for overlap
- RRF will still pick the best 10 from the larger pool

**Implementation:**
```python
# In search.py and search_debug.py, line 692
bm25_hits = _os_search(bm25_query, size=size * 10, index=target_index)  # was size * 3
```

**Expected Impact:** 60-80% chance of seeing some kNN properties in final results

---

#### Option 2: Reduce Tag Boost Factor
**Current:** 1.25x boost for properties matching must-have tags
**Proposal:** 1.1x boost (more subtle)

**Rationale:**
- Tag boosting is amplifying BM25's advantage
- RRF score of 0.0164 × 1.25 = 0.0205 beats kNN-only properties
- Reducing to 1.1x would make overlap more competitive

**Implementation:**
```python
# In search.py, around line 935
boost = 1.1 if match_ratio >= 0.6 else 1.0  # was 1.25
```

**Expected Impact:** 30-40% chance of seeing some kNN properties in final results

---

#### Option 3: Normalize Strategy Scores Before RRF
**Current:** RRF uses ranks only (ignores actual scores)
**Proposal:** Weight strategies based on score magnitude

**Rationale:**
- BM25 scores are 10-12 (high)
- kNN scores are 0.5-0.7 (low)
- Even though RRF uses ranks, the score scales suggest different confidence levels
- Could boost kNN k-values in standard mode

**Implementation:**
```python
# In search.py, line 821-827
if search_mode == "standard":
    # Equal weighting, but adjust k-values to account for different score scales
    k_values = [60, 45, 45]  # Lower k for kNN = higher weight
```

**Expected Impact:** 50-70% chance of seeing some kNN properties in final results

---

### Medium-Term (Requires more work)

#### Option 4: Implement Query Expansion
**Proposal:** Expand query with synonyms and related terms before searching

**Example:**
```
User query: "white modern homes"
Expanded: "white modern homes contemporary minimalist bright clean"
```

**Why:** kNN text search might find "contemporary" when user says "modern"

**Implementation:** Use LLM to expand query before embedding generation

**Expected Impact:** Significant improvement in semantic overlap

---

#### Option 5: Pre-compute Strategy Overlap Metrics
**Proposal:** During indexing, calculate how well each property would match different query types

**Example:**
```json
{
  "zpid": "12345",
  "overlap_scores": {
    "visual_keywords": 0.85,  // How well images match their text tags
    "semantic_consistency": 0.92,  // How consistent description/images are
    "multi_strategy_quality": 0.78  // Overall ranking across strategies
  }
}
```

**Why:** Properties that rank well across multiple strategies are objectively better

**Expected Impact:** Major improvement in result quality and overlap

---

### Long-Term (Requires ML/tuning)

#### Option 6: Fine-Tune Embedding Models
**Proposal:** Fine-tune Amazon Titan embeddings on real estate data

**Current:** Generic embeddings trained on general web data
**Proposed:** Fine-tuned on Zillow descriptions and images

**Why:**
- "Modern" might mean different things in real estate vs general context
- Image embeddings should understand architectural styles
- Text embeddings should understand real estate terminology

**Expected Impact:** 2-3x improvement in strategy overlap

---

#### Option 7: Implement Cross-Encoder Re-Ranking
**Proposal:** After RRF, use a cross-encoder model to re-rank based on query-property relevance

**Process:**
1. RRF returns top 30 candidates (from all strategies)
2. Cross-encoder scores each property against the exact query
3. Final ranking based on cross-encoder scores

**Why:** Cross-encoders see both query and property together, better at relevance

**Expected Impact:** Major improvement in ranking quality

---

## Recommended Action Plan

### Phase 1: Quick Fixes (Today)
1. **Increase fetch size to `size * 10`** (100 results per strategy)
2. **Reduce tag boost to 1.1x** (less BM25 dominance)
3. **Test with "white modern homes" query again**
4. **Measure overlap improvement**

### Phase 2: Scoring Adjustments (This Week)
1. **Adjust k-values in standard mode:** [60, 45, 45] (boost kNN)
2. **Implement query expansion** using LLM
3. **Add overlap metrics to debug output**

### Phase 3: Long-Term Improvements (Next Sprint)
1. **Fine-tune embeddings** on real estate data
2. **Implement pre-computed overlap scores**
3. **Consider cross-encoder re-ranking**

---

## Testing Plan

### Validation Queries

Test with these generic queries that should show overlap:

1. **"white modern homes"** (current problem case)
2. **"brick colonial homes"** (clear style + material)
3. **"mountain view properties"** (mix of text + visual)
4. **"open concept kitchen"** (interior feature)
5. **"luxury estate"** (general + subjective)

### Success Criteria

**Before fixes:**
- Overlap in top 10: 0-1 properties
- kNN representation: 0%

**After Phase 1:**
- Overlap in top 10: 3-5 properties
- kNN representation: 30-50%

**After Phase 2:**
- Overlap in top 10: 5-7 properties
- kNN representation: 50-70%

**After Phase 3:**
- Overlap in top 10: 7-9 properties
- kNN representation: 70-90%

---

## Related Files

- [search_debug.py:692](search_debug.py#L692) - BM25 fetch size (`size * 3`)
- [search_debug.py:707](search_debug.py#L707) - kNN text fetch size
- [search_debug.py:752](search_debug.py#L752) - kNN image fetch size
- [search.py:692](search.py#L692) - Same fetch sizes in production
- [search_debug.py:380-451](search_debug.py#L380-L451) - RRF fusion logic
- [search_debug.py:935](search_debug.py#L935) - Tag boosting (1.25x)

---

**Last Updated:** October 16, 2024
**Status:** 🔴 **Requires immediate attention** - Multi-strategy fusion not working as designed

**Next Step:** Implement Phase 1 fixes and re-test with "white modern homes" query
