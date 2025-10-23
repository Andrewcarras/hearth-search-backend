# Research: Handling Zero Overlap in Reciprocal Rank Fusion (RRF)

## Executive Summary

Your real estate search system faces a critical challenge: three strategies (BM25, kNN text, kNN image) are returning completely different results with zero overlap. This research compiles academic findings, production implementations, and practical techniques to address this issue **without requiring reindexing**.

## Current Problem Analysis

**Observed Behavior:**
- BM25 returns properties A, B, C
- kNN text returns properties D, E, F
- kNN image returns properties G, H, I
- Zero overlap between strategies
- RRF defaults to picking the strategy with the lowest k-value

**Your Current Implementation** (`/Users/andrewcarras/hearth_backend_new/search.py`):
```python
def _rrf(*ranked_lists, k=60, k_values=None, top=50, include_scoring_details=False):
    # Uses adaptive k_values: [bm25_k, text_k, image_k]
    # Example: [30, 60, 120] for color queries
    # Formula: score += 1 / (k + rank)
```

---

## 1. TECHNIQUES FOR LOW OVERLAP IN RRF

### 1.1 Weighted Reciprocal Rank Fusion (Production-Ready)

**Source:** Elasticsearch 8.x (2024), Azure AI Search

**How It Works:**
```python
# Standard RRF
score = 1 / (k + rank)

# Weighted RRF
score = weight × 1 / (k + rank)
```

**Implementation for Your System:**
```python
def _rrf_weighted(*ranked_lists, k_values=None, weights=None, top=50):
    """
    Enhanced RRF with per-strategy weights.

    Args:
        weights: [bm25_weight, text_weight, image_weight]
                 Example: [0.7, 0.2, 0.1] for text-heavy queries
                 Example: [0.2, 0.3, 0.5] for visual queries
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)

    for strategy_idx, (lst, k_val, weight) in enumerate(zip(ranked_lists, k_values, weights)):
        for i, hit in enumerate(lst):
            rank = i + 1
            rrf_contribution = weight × (1.0 / (k_val + rank))
            scores[hit["_id"]]["score"] += rrf_contribution
```

**When to Use Different Weights:**

| Query Type | BM25 Weight | Text Weight | Image Weight | Reasoning |
|-----------|-------------|-------------|--------------|-----------|
| "white exterior house" | 0.6 | 0.3 | 0.1 | BM25 captures exact tags best |
| "modern architecture" | 0.3 | 0.3 | 0.4 | Visual features dominate |
| "granite countertops" | 0.5 | 0.4 | 0.1 | Text-based feature, rarely visible |
| "3 bed 2 bath pool" | 0.4 | 0.3 | 0.3 | Balanced hybrid query |

**Benefits:**
- No reindexing required
- Directly addresses zero overlap by prioritizing trusted strategies
- Query-adaptive based on feature classification
- Production-proven (Elastic, Azure, Weaviate)

---

### 1.2 CombMNZ: Overlap-Aware Fusion

**Source:** Academic IR research (2005-2024), metasearch systems

**How It Works:**
```python
def comb_mnz_fusion(ranked_lists, scores_dict):
    """
    CombMNZ = Sum of normalized scores × Number of lists containing document

    Advantages:
    - Automatically rewards consensus
    - Penalizes documents appearing in only one list
    - Robust to zero overlap scenarios
    """
    results = {}

    for doc_id in all_doc_ids:
        normalized_score_sum = 0
        num_lists_containing = 0

        for lst_idx, lst in enumerate(ranked_lists):
            if doc_id in lst:
                # Normalize score to [0, 1] range
                max_score = lst[0]["_score"]
                normalized_score = lst[doc_id]["_score"] / max_score
                normalized_score_sum += normalized_score
                num_lists_containing += 1

        # CombMNZ formula: multiply sum by count
        final_score = normalized_score_sum * num_lists_containing
        results[doc_id] = final_score

    return sorted(results.items(), key=lambda x: x[1], reverse=True)
```

**Comparison with RRF:**

| Method | Zero Overlap Handling | Consensus Reward | Requires Score Normalization |
|--------|----------------------|------------------|------------------------------|
| RRF | Each list contributes independently | Implicit (higher ranks) | No |
| CombMNZ | Penalizes single-list documents | Explicit (multiplier) | Yes |
| CombSUM | Each list contributes equally | No penalty | Yes |

**Academic Finding:**
> "CombMNZ is considered the best ranking fusion method, even if it performed only slightly better than CombSUM. The multiplication factor (number of systems returning a document) rewards consensus." - BMC Bioinformatics (2011)

**When CombMNZ Helps Your Case:**
- If BM25 consistently returns better results than kNN for certain query types
- Documents appearing in multiple strategies should be heavily boosted
- You want to penalize "orphan" documents (only in one list)

**Drawback:**
- Requires score normalization (BM25 unbounded, cosine similarity bounded)
- May overly penalize valid results that only one strategy finds

---

### 1.3 Diversity-Weighted Ensemble Fusion

**Source:** Ensemble Learning Research (2024), "Not All Accuracy Is Equal" (arXiv 2024)

**Core Principle:**
> "What matters is whether a model contributes complementary information; a model that adds even a modest amount of novel information can be more valuable than one that achieves higher stand-alone accuracy but contributes only redundant signals."

**Implementation Strategy:**
```python
def calculate_strategy_diversity(bm25_hits, text_hits, image_hits):
    """
    Calculate diversity/complementarity between strategies.
    Low overlap = high diversity = valuable signal
    """
    all_zpids = set()
    bm25_set = set(h["_id"] for h in bm25_hits)
    text_set = set(h["_id"] for h in text_hits)
    image_set = set(h["_id"] for h in image_hits)

    all_zpids = bm25_set | text_set | image_set

    # Jaccard diversity (1 - similarity)
    overlap_bm25_text = len(bm25_set & text_set) / len(bm25_set | text_set) if all_zpids else 0
    overlap_bm25_image = len(bm25_set & image_set) / len(bm25_set | image_set) if all_zpids else 0
    overlap_text_image = len(text_set & image_set) / len(text_set | image_set) if all_zpids else 0

    diversity = {
        "bm25_text_diversity": 1 - overlap_bm25_text,
        "bm25_image_diversity": 1 - overlap_bm25_image,
        "text_image_diversity": 1 - overlap_text_image,
        "avg_diversity": 1 - ((overlap_bm25_text + overlap_bm25_image + overlap_text_image) / 3)
    }

    return diversity

def adaptive_fusion_with_diversity(bm25_hits, text_hits, image_hits, must_tags):
    """
    Adjust fusion weights based on diversity metrics.

    High diversity (low overlap) = strategies are complementary
    Low diversity (high overlap) = strategies agree (boost consensus)
    """
    diversity = calculate_strategy_diversity(bm25_hits, text_hits, image_hits)

    # If diversity is high (>0.7), use balanced weights
    if diversity["avg_diversity"] > 0.7:
        logger.info(f"⚠️ High diversity detected ({diversity['avg_diversity']:.2%}) - strategies finding different properties")
        # Use confidence-based weighting instead
        weights = calculate_confidence_weights(bm25_hits, text_hits, image_hits, must_tags)
    else:
        # Low diversity = strategies agree, use standard adaptive weights
        weights = calculate_adaptive_weights_v2(must_tags, query_type)

    return weights
```

**Research Insight:**
> "Larger training sample sizes increase the likelihood of substantial overlaps among randomly generated subsamples, thereby impairing the diversity. Data subsets that are inherently mutually exclusive maximize the diversity among them." - MDPI Entropy (2024)

**Application to Your System:**
- Zero overlap is actually GOOD for diversity
- Each strategy captures different property aspects
- Don't penalize diversity - embrace it with confidence weighting

---

## 2. MINIMUM OVERLAP THRESHOLDS & PENALTIES

### 2.1 Overlap Detection & Logging

**Practical Implementation:**
```python
def analyze_strategy_overlap(bm25_hits, text_hits, image_hits):
    """
    Monitor overlap metrics to detect zero-overlap scenarios.
    """
    bm25_ids = set(h["_id"] for h in bm25_hits[:20])
    text_ids = set(h["_id"] for h in text_hits[:20])
    image_ids = set(h["_id"] for h in image_hits[:20])

    overlap_metrics = {
        "bm25_text_overlap": len(bm25_ids & text_ids),
        "bm25_image_overlap": len(bm25_ids & image_ids),
        "text_image_overlap": len(text_ids & image_ids),
        "three_way_overlap": len(bm25_ids & text_ids & image_ids),
        "total_unique": len(bm25_ids | text_ids | image_ids),
        "overlap_ratio": len(bm25_ids & text_ids & image_ids) / 20.0
    }

    # Alert on zero overlap
    if overlap_metrics["three_way_overlap"] == 0:
        logger.warning(f"⚠️ ZERO 3-WAY OVERLAP detected!")
        logger.warning(f"  BM25-Text: {overlap_metrics['bm25_text_overlap']}")
        logger.warning(f"  BM25-Image: {overlap_metrics['bm25_image_overlap']}")
        logger.warning(f"  Text-Image: {overlap_metrics['text_image_overlap']}")

    return overlap_metrics
```

### 2.2 Minimum Overlap Thresholds (Research-Based)

**Academic Guidance:**
- No established "minimum overlap threshold" in literature
- RRF explicitly designed to handle zero overlap (documents contribute 0 from missing lists)
- CombMNZ penalizes low overlap through multiplication factor

**Recommended Thresholds for Alerts:**

| Overlap Level | Threshold | Action |
|---------------|-----------|--------|
| Healthy | >30% three-way | Normal operation |
| Concerning | 10-30% three-way | Log warning, investigate query parsing |
| Critical | <10% three-way | Switch to confidence-weighted fusion |
| Zero | 0% three-way | Use query-type-specific weights |

### 2.3 Dynamic Penalty System

**NOT RECOMMENDED** based on research:
- Penalizing diversity reduces ensemble effectiveness
- Zero overlap often indicates complementary strategies (good thing)
- Better approach: weight by confidence, not penalize disagreement

---

## 3. DYNAMIC STRATEGY WEIGHTING BASED ON AGREEMENT

### 3.1 Confidence-Based Weighting

**Implementation:**
```python
def calculate_confidence_weights(bm25_hits, text_hits, image_hits, must_tags):
    """
    Weight strategies based on their confidence/quality for this query.

    Confidence Indicators:
    - Score distribution (tight clustering = high confidence)
    - Top score magnitude (high score = strong match)
    - Tag coverage (matches must_have tags = high confidence)
    """

    def score_confidence(hits, must_tags):
        if not hits or len(hits) < 3:
            return 0.0

        # Metric 1: Score separation (higher is better)
        top_score = hits[0].get("_score", 0)
        third_score = hits[2].get("_score", 0) if len(hits) > 2 else 0
        score_separation = (top_score - third_score) / (top_score + 1e-10)

        # Metric 2: Absolute score magnitude
        score_magnitude = min(top_score / 10.0, 1.0)  # Normalize to [0, 1]

        # Metric 3: Tag coverage (for BM25/text)
        if must_tags:
            top_doc = hits[0].get("_source", {})
            doc_tags = set(top_doc.get("feature_tags", []) + top_doc.get("image_tags", []))
            tag_coverage = len(must_tags & doc_tags) / len(must_tags)
        else:
            tag_coverage = 0.5

        # Combined confidence score
        confidence = (score_separation * 0.4 + score_magnitude * 0.3 + tag_coverage * 0.3)
        return confidence

    bm25_confidence = score_confidence(bm25_hits, must_tags)
    text_confidence = score_confidence(text_hits, must_tags)
    image_confidence = score_confidence(image_hits, must_tags)

    # Normalize to weights summing to 1.0
    total_confidence = bm25_confidence + text_confidence + image_confidence
    if total_confidence > 0:
        weights = [
            bm25_confidence / total_confidence,
            text_confidence / total_confidence,
            image_confidence / total_confidence
        ]
    else:
        weights = [0.33, 0.33, 0.34]  # Equal weights fallback

    logger.info(f"🎯 Confidence-based weights: BM25={weights[0]:.2f}, Text={weights[1]:.2f}, Image={weights[2]:.2f}")
    logger.info(f"   Confidences: BM25={bm25_confidence:.3f}, Text={text_confidence:.3f}, Image={image_confidence:.3f}")

    return weights
```

### 3.2 Agreement Score Method

**Source:** Ensemble diversity literature

```python
def calculate_agreement_score(bm25_hits, text_hits, image_hits):
    """
    Calculate pairwise agreement between strategies.
    Use agreement to adjust weights.
    """
    def rank_correlation(list1, list2):
        """Simplified Kendall's Tau for top-20 results."""
        ids1 = [h["_id"] for h in list1[:20]]
        ids2 = [h["_id"] for h in list2[:20]]

        # Count concordant pairs
        concordant = 0
        total_pairs = 0

        for i, id1 in enumerate(ids1):
            if id1 in ids2:
                rank2 = ids2.index(id1)
                for j in range(i + 1, len(ids1)):
                    id2 = ids1[j]
                    if id2 in ids2:
                        rank2_j = ids2.index(id2)
                        if rank2 < rank2_j:
                            concordant += 1
                        total_pairs += 1

        return concordant / total_pairs if total_pairs > 0 else 0

    bm25_text_agreement = rank_correlation(bm25_hits, text_hits)
    bm25_image_agreement = rank_correlation(bm25_hits, image_hits)
    text_image_agreement = rank_correlation(text_hits, image_hits)

    return {
        "bm25_text": bm25_text_agreement,
        "bm25_image": bm25_image_agreement,
        "text_image": text_image_agreement,
        "avg_agreement": (bm25_text_agreement + bm25_image_agreement + text_image_agreement) / 3
    }
```

---

## 4. ALTERNATIVE FUSION METHODS

### 4.1 Score-Based Fusion with Min-Max Normalization

**When to Use:** High overlap, but RRF over-penalizes good results

```python
def normalized_score_fusion(bm25_hits, text_hits, image_hits, weights=[0.33, 0.33, 0.34]):
    """
    Normalize scores to [0, 1] and combine with weighted sum.

    Advantages:
    - Preserves score magnitudes (unlike rank-based)
    - Better for cases with strong confidence signals

    Disadvantages:
    - Requires careful normalization
    - BM25 scores unbounded (use max-scaling)
    """

    def normalize_scores(hits):
        if not hits:
            return {}
        max_score = hits[0]["_score"]
        return {h["_id"]: h["_score"] / max_score for h in hits}

    bm25_normalized = normalize_scores(bm25_hits)
    text_normalized = normalize_scores(text_hits)
    image_normalized = normalize_scores(image_hits)

    all_ids = set(bm25_normalized.keys()) | set(text_normalized.keys()) | set(image_normalized.keys())

    final_scores = {}
    for doc_id in all_ids:
        score = (
            weights[0] * bm25_normalized.get(doc_id, 0) +
            weights[1] * text_normalized.get(doc_id, 0) +
            weights[2] * image_normalized.get(doc_id, 0)
        )
        final_scores[doc_id] = score

    return sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
```

**Research Finding:**
> "RRF excels when BM25 and semantic models produce scores on incompatible scales. Score-based normalization can lead to more precise ranking in well-tuned systems because each document's final score reflects balanced lexical and semantic relevance." - OpenSearch Blog (2024)

### 4.2 Two-Stage Fusion (Cascade Retrieval)

**Concept:** Use one strategy to retrieve, another to re-rank

```python
def cascade_fusion(query, must_tags, query_type):
    """
    Stage 1: Broad retrieval (highest-recall strategy)
    Stage 2: Semantic re-ranking (highest-precision strategy)
    """

    # Determine primary strategy based on query type
    if query_type in ["visual_style", "architecture"]:
        # Stage 1: Image kNN (broad visual search)
        primary_hits = knn_image_search(query, size=100)
        # Stage 2: Text kNN re-rank (semantic precision)
        final_results = text_knn_rerank(primary_hits, query, size=20)

    elif must_tags and any(tag in TEXT_DOMINANT_FEATURES for tag in must_tags):
        # Stage 1: BM25 (broad keyword search)
        primary_hits = bm25_search(query, size=100)
        # Stage 2: Text kNN re-rank
        final_results = text_knn_rerank(primary_hits, query, size=20)

    else:
        # Balanced query - use standard RRF
        final_results = rrf_fusion(bm25_hits, text_hits, image_hits)

    return final_results
```

**Source:** Elasticsearch hybrid search patterns (2024)

**Trade-offs:**
- ✅ Simpler than multi-strategy fusion
- ✅ Reduces zero-overlap issue (only one final strategy)
- ❌ May miss results only found by secondary strategy
- ❌ Requires careful strategy selection logic

### 4.3 Borda Count (Positional Voting)

**How It Works:**
```python
def borda_count_fusion(ranked_lists, top=50):
    """
    Each document gets points = (total_docs - rank)
    Higher rank = more points

    Example:
    - Rank 1 in list of 100 = 99 points
    - Rank 50 in list of 100 = 50 points
    """
    scores = {}

    for lst in ranked_lists:
        list_size = len(lst)
        for i, hit in enumerate(lst):
            rank = i + 1
            points = list_size - rank
            scores[hit["_id"]] = scores.get(hit["_id"], 0) + points

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top]
```

**Comparison with RRF:**
- Borda: Linear decay (rank 1 gets N points, rank 2 gets N-1 points)
- RRF: Hyperbolic decay (rank 1 gets 1/61, rank 2 gets 1/62)

**When to Use Borda:**
- Lists of similar length
- Want linear weighting of positions
- Academic ensemble applications

**Research Finding:**
> "Ensembles and clustered ensembles based on weighted Borda count show very balanced performance, achieving quality results across all investigated measures." - ScienceDirect (2018)

---

## 5. ACADEMIC PAPERS & PRODUCTION SYSTEMS

### 5.1 Key Academic Papers

1. **"Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods"**
   - Cormack et al., SIGIR 2009
   - Original RRF paper
   - Key finding: k=60 robust across datasets
   - Zero overlap explicitly supported

2. **"Comparing Rank and Score Combination Methods for Data Fusion in Information Retrieval"**
   - Fox & Shaw, 1994
   - Introduced CombSUM and CombMNZ
   - Finding: CombMNZ best for metasearch

3. **"Applying Machine Learning Diversity Metrics to Data Fusion in Information Retrieval"**
   - Springer, 2011
   - Diversity improves ensemble performance
   - Low overlap = high diversity = better results

4. **"Not All Accuracy Is Equal: Prioritizing Diversity in Infectious Disease Forecasting"**
   - arXiv 2024
   - Key insight: Complementarity > standalone accuracy
   - Novel information beats redundant high-accuracy

5. **"Performance prediction of data fusion for information retrieval"**
   - ScienceDirect, 2006
   - Overlap rate predicts fusion effectiveness
   - Lower overlap requires different weighting

### 5.2 Production System Implementations

| System | Fusion Method | Zero Overlap Handling | Adaptive Weighting |
|--------|---------------|----------------------|-------------------|
| **Elasticsearch 8.x** | RRF + Weighted RRF | Documents contribute 0 from missing lists | Per-retriever weights |
| **Azure AI Search** | RRF with rank_constant | Native zero-overlap support | Query-dependent k values |
| **OpenSearch 2.x** | RRF + Normalization | Hybrid scoring pipelines | Plugin-based weighting |
| **Weaviate** | RRF + alpha parameter | Balanced hybrid search | alpha ∈ [0, 1] for BM25/vector mix |
| **Pinecone** | Sparse-Dense fusion | Score normalization required | User-defined weights |

### 5.3 Real-World Use Cases

**Elasticsearch - Restaurant Search:**
- Query: "pizza near me" → Weight location signals heavily
- Query: "Italian restaurants that serve cacio e pepe" → Weight cuisine/menu matching
- Query: "highly reviewed Italian restaurants" → Weight ratings heavily

**Azure AI Search - E-commerce:**
- Product search combines title match (BM25) + image similarity (vector)
- Zero overlap common: text matches != visual matches
- Solution: Weighted RRF with query-type detection

**Weaviate - Document Retrieval:**
- RAG applications with hybrid search
- BM25 for exact terms, vectors for semantic meaning
- RRF handles cases where keyword != semantic match

---

## 6. PRACTICAL RECOMMENDATIONS FOR YOUR SYSTEM

### 6.1 Immediate Actions (No Reindexing)

**Priority 1: Implement Weighted RRF**
```python
# Add to search.py
def calculate_weighted_rrf_params(must_tags, query_type, overlap_metrics):
    """
    Combine feature-context classification with overlap analysis.
    """
    # Start with feature-based k-values
    k_values = calculate_adaptive_weights_v2(must_tags, query_type)

    # Add weights based on overlap/confidence
    if overlap_metrics["avg_diversity"] > 0.7:
        # High diversity - use confidence weighting
        weights = calculate_confidence_weights(bm25_hits, text_hits, image_hits, must_tags)
    else:
        # Low diversity - equal weights
        weights = [1.0, 1.0, 1.0]

    return k_values, weights
```

**Priority 2: Add Overlap Monitoring**
```python
# Add to handler() function
overlap_metrics = analyze_strategy_overlap(bm25_hits, knn_text_hits, knn_img_hits)

if overlap_metrics["three_way_overlap"] == 0:
    logger.warning("⚠️ Zero overlap detected - using confidence weighting")
    weights = calculate_confidence_weights(bm25_hits, knn_text_hits, knn_img_hits, must_tags)
else:
    weights = [1.0, 1.0, 1.0]  # Standard operation
```

**Priority 3: Enhanced Debug Logging**
```python
# Add to debug_info in search_detailed_scoring.py
debug_info["overlap_analysis"] = overlap_metrics
debug_info["fusion_method"] = "weighted_rrf" if weights != [1.0, 1.0, 1.0] else "standard_rrf"
debug_info["weights"] = {"bm25": weights[0], "text": weights[1], "image": weights[2]}
```

### 6.2 Medium-Term Improvements

1. **A/B Test Fusion Methods**
   - Standard RRF vs Weighted RRF vs CombMNZ
   - Track metrics: user clicks, dwelling time, conversion

2. **Query-Type Classification Enhancement**
   - Add overlap-based query classification
   - High diversity queries → use confidence weighting
   - Low diversity queries → use standard adaptive k-values

3. **Score Distribution Analysis**
   - Monitor score separations per strategy
   - Tight clustering = high confidence
   - Wide spread = low confidence

### 6.3 Advanced Optimization

1. **Machine Learning Approach**
   ```python
   # Train a lightweight model to predict optimal weights
   # Features: query_type, must_tags, overlap_metrics, score_distributions
   # Labels: optimal weights (from manual relevance judgments)

   from sklearn.ensemble import RandomForestRegressor

   def predict_optimal_weights(query_features):
       # Load pre-trained model
       model = load_trained_weight_predictor()
       weights = model.predict([query_features])
       return weights
   ```

2. **User Feedback Loop**
   - Track which properties users click
   - Learn which strategy produced the best result
   - Adjust future weights based on historical performance

3. **Ensemble Meta-Learning**
   - Train a meta-ranker on top of RRF
   - Input: RRF scores + individual strategy scores
   - Output: final ranking
   - Learns to trust certain strategies for certain queries

---

## 7. COMPARISON MATRIX: FUSION METHODS

| Method | Zero Overlap Handling | Setup Complexity | Reindex Required | Best For |
|--------|----------------------|------------------|------------------|----------|
| **Standard RRF** | ✅ Excellent | Low | No | General purpose |
| **Weighted RRF** | ✅ Excellent | Medium | No | Query-adaptive search |
| **CombMNZ** | ⚠️ Penalizes zero overlap | Medium | No | High-overlap scenarios |
| **CombSUM** | ✅ Good | Medium | No | Equal strategy trust |
| **Min-Max Fusion** | ✅ Good | High (normalization) | No | Well-tuned score ranges |
| **Borda Count** | ✅ Good | Low | No | Academic/ensemble apps |
| **Cascade Retrieval** | N/A (single strategy) | Medium | No | Clear primary strategy |
| **Confidence Weighting** | ✅ Excellent | High | No | Diverse query types |

---

## 8. ZERO OVERLAP IS NOT A BUG - IT'S A FEATURE

### Key Research Insight

> "What matters is whether a model contributes complementary information; within certain boundaries, a model that adds even a modest amount of novel information can be more valuable than one that achieves higher stand-alone accuracy but contributes only redundant signals." - Ensemble Diversity Research (2024)

**Application to Your System:**

1. **BM25 finds:** Properties with exact tag matches ("white_exterior", "pool")
2. **kNN Text finds:** Properties with semantic similarity (descriptions mention "modern aesthetic", "swimming area")
3. **kNN Image finds:** Properties that LOOK right but aren't tagged correctly

**This is GOOD:**
- Each strategy captures different aspects of "relevance"
- Zero overlap means complementary information
- Fusion should embrace diversity, not penalize it

**Your Current Approach is Sound:**
- Adaptive k-values based on feature context ✅
- Lower k = higher weight (boost trusted strategies) ✅
- Feature classification (visual vs text) ✅

**What to Add:**
- Confidence-based weights when overlap is zero
- Overlap monitoring and logging
- Weighted RRF for explicit query-type preferences

---

## 9. IMPLEMENTATION ROADMAP

### Phase 1: Monitoring (Week 1)
- [ ] Add overlap analysis to search.py
- [ ] Log overlap metrics to CloudWatch
- [ ] Add to debug_info in search_detailed_scoring.py
- [ ] Create dashboard to visualize overlap patterns

### Phase 2: Weighted RRF (Week 2-3)
- [ ] Implement weighted RRF function
- [ ] Add confidence calculation
- [ ] Integrate with existing adaptive k-values
- [ ] A/B test: standard vs weighted RRF

### Phase 3: Query-Type Optimization (Week 4-5)
- [ ] Build query-type classifier
- [ ] Create weight lookup tables per query type
- [ ] Test on historical queries
- [ ] Deploy to production with feature flag

### Phase 4: Advanced Features (Month 2)
- [ ] CombMNZ implementation (comparison)
- [ ] User feedback collection
- [ ] ML-based weight prediction
- [ ] Automated retraining pipeline

---

## 10. CODE EXAMPLES

### Complete Implementation

```python
# Add to search.py after line 565

def calculate_confidence_weights(bm25_hits, text_hits, image_hits, must_tags):
    """Calculate strategy weights based on result quality."""
    def score_confidence(hits, must_tags):
        if not hits or len(hits) < 3:
            return 0.0

        top_score = hits[0].get("_score", 0)
        third_score = hits[2].get("_score", 0) if len(hits) > 2 else 0
        score_separation = (top_score - third_score) / (top_score + 1e-10)
        score_magnitude = min(top_score / 10.0, 1.0)

        if must_tags:
            top_doc = hits[0].get("_source", {})
            doc_tags = set(top_doc.get("feature_tags", []) + top_doc.get("image_tags", []))
            expanded_must = set()
            for tag in must_tags:
                expanded_must.add(tag)
                expanded_must.add(tag.replace("_", " "))
            tag_coverage = len(expanded_must & doc_tags) / len(expanded_must)
        else:
            tag_coverage = 0.5

        confidence = (score_separation * 0.4 + score_magnitude * 0.3 + tag_coverage * 0.3)
        return confidence

    bm25_conf = score_confidence(bm25_hits, must_tags)
    text_conf = score_confidence(text_hits, must_tags)
    image_conf = score_confidence(image_hits, must_tags)

    total = bm25_conf + text_conf + image_conf
    if total > 0:
        return [bm25_conf/total, text_conf/total, image_conf/total]
    return [0.33, 0.33, 0.34]


def analyze_strategy_overlap(bm25_hits, text_hits, image_hits, top_n=20):
    """Analyze overlap between search strategies."""
    bm25_ids = set(h["_id"] for h in bm25_hits[:top_n])
    text_ids = set(h["_id"] for h in text_hits[:top_n])
    image_ids = set(h["_id"] for h in image_hits[:top_n])

    return {
        "bm25_text_overlap": len(bm25_ids & text_ids),
        "bm25_image_overlap": len(bm25_ids & image_ids),
        "text_image_overlap": len(text_ids & image_ids),
        "three_way_overlap": len(bm25_ids & text_ids & image_ids),
        "total_unique": len(bm25_ids | text_ids | image_ids),
        "overlap_ratio": len(bm25_ids & text_ids & image_ids) / top_n if top_n > 0 else 0,
        "avg_diversity": 1 - ((len(bm25_ids & text_ids) + len(bm25_ids & image_ids) + len(text_ids & image_ids)) / (3 * top_n))
    }


def _rrf_weighted(*ranked_lists, k_values=None, weights=None, top=50, include_scoring_details=False):
    """
    Weighted Reciprocal Rank Fusion.

    Args:
        k_values: [bm25_k, text_k, image_k] - Lower k = higher influence
        weights: [bm25_weight, text_weight, image_weight] - Direct multipliers
    """
    if k_values is None:
        k_values = [60] * len(ranked_lists)
    if weights is None:
        weights = [1.0] * len(ranked_lists)

    scores = {}
    strategy_names = ["bm25", "knn_text", "knn_image"]

    for strategy_idx, (lst, k_val, weight) in enumerate(zip(ranked_lists, k_values, weights)):
        for i, hit in enumerate(lst):
            rank = i + 1
            doc_id = hit["_id"]

            if doc_id not in scores:
                scores[doc_id] = {
                    "doc": hit,
                    "score": 0.0,
                    "scoring_details": {
                        "bm25": {"rank": None, "original_score": None, "rrf_contribution": 0.0, "k": k_values[0], "weight": weights[0]},
                        "knn_text": {"rank": None, "original_score": None, "rrf_contribution": 0.0, "k": k_values[1], "weight": weights[1]},
                        "knn_image": {"rank": None, "original_score": None, "rrf_contribution": 0.0, "k": k_values[2], "weight": weights[2]},
                        "rrf_total": 0.0
                    } if include_scoring_details else None
                }

            # Weighted RRF formula
            rrf_contribution = weight * (1.0 / (k_val + rank))
            scores[doc_id]["score"] += rrf_contribution

            if include_scoring_details and strategy_idx < len(strategy_names):
                strategy_name = strategy_names[strategy_idx]
                scores[doc_id]["scoring_details"][strategy_name]["rank"] = rank
                scores[doc_id]["scoring_details"][strategy_name]["original_score"] = hit.get("_score", 0.0)
                scores[doc_id]["scoring_details"][strategy_name]["rrf_contribution"] = rrf_contribution

    # Attach scores to documents
    for entry in scores.values():
        entry["doc"]["_rrf_score"] = entry["score"]
        if include_scoring_details:
            entry["scoring_details"]["rrf_total"] = entry["score"]
            entry["doc"]["scoring_details"] = entry["scoring_details"]

    fused = list(scores.values())
    fused.sort(key=lambda x: x["score"], reverse=True)
    return [x["doc"] for x in fused[:top]]


# Modify handler() around line 1186-1194:

# After executing all searches, before RRF fusion:
overlap_metrics = analyze_strategy_overlap(bm25_hits, knn_text_hits, knn_img_hits)
logger.info(f"📊 Overlap metrics: {overlap_metrics}")

# Determine if we need confidence weighting
use_weighted_rrf = overlap_metrics["three_way_overlap"] == 0 or overlap_metrics["avg_diversity"] > 0.7

if use_weighted_rrf:
    weights = calculate_confidence_weights(bm25_hits, knn_text_hits, knn_img_hits, must_tags)
    logger.info(f"⚖️ Using weighted RRF: weights={weights}")
    fused = _rrf_weighted(bm25_hits, knn_text_hits, knn_img_hits,
                          k_values=k_values, weights=weights, top=size * 3,
                          include_scoring_details=include_scoring_details)
else:
    logger.info(f"⚖️ Using standard RRF: k_values={k_values}")
    fused = _rrf(bm25_hits, knn_text_hits, knn_img_hits,
                 k_values=k_values, top=size * 3,
                 include_scoring_details=include_scoring_details)
```

---

## 11. REFERENCES

### Academic Papers
1. Cormack, G. V., Clarke, C. L., & Büttcher, S. (2009). Reciprocal rank fusion outperforms condorcet and individual rank learning methods. SIGIR.
2. Fox, E. A., & Shaw, J. A. (1994). Combination of multiple searches. TREC.
3. Lee, J. H. (1997). Analyses of multiple evidence combination. SIGIR.
4. "Not All Accuracy Is Equal: Prioritizing Diversity in Infectious Disease Forecasting" (arXiv 2024)
5. "Applying Machine Learning Diversity Metrics to Data Fusion" (Springer 2011)

### Production Documentation
1. Elasticsearch: https://www.elastic.co/search-labs/blog/weighted-reciprocal-rank-fusion-rrf
2. Azure AI Search: https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking
3. OpenSearch: https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/
4. Weaviate: https://weaviate.io/blog/hybrid-search-explained

### Code Repositories
1. https://github.com/drigoni/RankFusion-IRProject (CombSUM, CombMNZ implementations)
2. https://safjan.com/implementing-rank-fusion-in-python/ (RRF Python examples)

---

## CONCLUSION

Zero overlap in your real estate search system is **not a bug** - it indicates that your three strategies (BM25, kNN text, kNN image) are capturing **complementary** aspects of relevance. The research is clear: diversity improves ensemble performance.

**Key Takeaways:**

1. **RRF already handles zero overlap** - documents contribute 0 from missing lists
2. **Your adaptive k-values are the right approach** - feature-context classification is sound
3. **Add weighted RRF** for explicit confidence-based weighting when overlap is low
4. **Monitor overlap metrics** to understand when strategies disagree
5. **Don't penalize diversity** - embrace it with confidence weighting

**Immediate Next Steps:**

1. Implement overlap monitoring (1 day)
2. Add confidence-based weighting (2-3 days)
3. Deploy weighted RRF with feature flag (1 day)
4. A/B test and measure impact (1-2 weeks)

The good news: All solutions are implementable **without reindexing**. Your existing infrastructure supports these enhancements.
