# Search Quality Research Archive

This directory contains research documents for future search improvements. All techniques are **implementation-ready** and require **NO REINDEXING**.

---

## 📊 Priority Order (by estimated impact)

### 1. QUERY_EXPANSION_RESEARCH.md
**Impact:** +15-25% precision, +20-30% recall, -70% zero-result queries
**Effort:** 15-20 hours (Phases 2-4)
**Status:** Phase 1 (Feature Classification) ✅ IMPLEMENTED

**Remaining Phases:**
- **Phase 2:** Synonym Expansion (~3 hours, +10-15% recall)
- **Phase 3:** Constraint Relaxation (~4 hours, -70% zero-results)
- **Phase 4:** Multi-Query Rewriting (~8 hours, +15-20% precision)

**Cost:** $0 (uses existing Claude LLM calls)

---

### 2. IMAGE_FEATURE_PROMINENCE_RESEARCH.md
**Impact:** +30-50% feature accuracy
**Effort:** 7 hours (Phases 1-2)
**Status:** Partially implemented (semantic grouping exists)

**Remaining Work:**
- **Phase 1:** Category Weighting using `image_type` field (~2 hours, +20% accuracy)
- **Phase 1:** Position-Based Weighting (~2 hours, +15% accuracy)
- **Phase 2:** Per-Feature Vector Decomposition (~3 hours, +30% accuracy)

**Cost:** $0 (runtime only, +11ms latency)

---

### 3. MULTI_FEATURE_QUERY_PROBLEM.md
**Impact:** Fixes multi-feature scoring inconsistency
**Effort:** ~3 hours
**Status:** Not implemented

**Problem:**
- Query: "white house with granite countertops"
- Property A: White exterior + granite countertops
- Property B: White exterior only
- **Bug:** Property B can rank higher than A (score_mode="max" only uses best match)

**Solution:** Top-K Sum (Solution 4)
- Sum top-K image scores instead of max
- K adaptive based on feature count (2 features → k=2)
- Already researched and validated

**Cost:** $0

---

### 4. RRF_ZERO_OVERLAP_RESEARCH.md
**Impact:** Preventive monitoring for fusion issues
**Effort:** ~4 hours
**Status:** Not needed yet (system working well)

**Use When:**
- Zero overlap becomes frequent (>30% of queries)
- Strategy consensus drops significantly
- Ranking quality degrades

**Solutions Ready:**
- Weighted RRF with confidence scoring
- Overlap monitoring metrics
- Diversity-aware fusion

---

## 📈 Combined Impact

If all research is implemented:

| Metric | Current | After Implementation | Improvement |
|--------|---------|---------------------|-------------|
| **Precision** | Baseline | +30-40% | Query expansion + multi-query |
| **Recall** | Baseline | +30-40% | Synonym expansion + relaxation |
| **Feature Accuracy** | Baseline | +40-60% | Prominence + multi-feature fix |
| **Zero-Result Queries** | Baseline | -70% | Constraint relaxation |
| **Total Development Time** | - | ~30 hours | Across all phases |
| **Total Cost** | - | $0 | No reindexing, no new services |

---

## 🚀 Recommended Implementation Order

**Sprint 1 (Week 1):** Quick Wins
1. MULTI_FEATURE_QUERY_PROBLEM.md - Top-K Sum (~3 hours)
2. IMAGE_FEATURE_PROMINENCE Phase 1 (~4 hours)

**Sprint 2 (Week 2):** Query Expansion Phase 2
3. QUERY_EXPANSION Phase 2 - Synonym Expansion (~3 hours)
4. QUERY_EXPANSION Phase 3 - Constraint Relaxation (~4 hours)

**Sprint 3 (Week 3):** Advanced Improvements
5. QUERY_EXPANSION Phase 4 - Multi-Query Rewriting (~8 hours)
6. IMAGE_FEATURE_PROMINENCE Phase 2 (~3 hours)

**Sprint 4 (Optional):** Monitoring
7. RRF_ZERO_OVERLAP - Implement monitoring (~4 hours)

---

## 📚 Document Details

### QUERY_EXPANSION_RESEARCH.md (1,386 lines)
Comprehensive research on query rewriting and expansion techniques.

**Academic Sources:**
- DMQR-RAG: 14.46% precision improvement
- Multi-query retrieval approaches
- Constraint relaxation strategies

**Techniques:**
- LLM-based synonym expansion
- Feature-context aware rewriting
- Constraint relaxation for zero-result recovery
- Multi-query voting for precision

---

### IMAGE_FEATURE_PROMINENCE_RESEARCH.md (844 lines)
Runtime techniques for image feature prominence without reindexing.

**6 Techniques Researched:**
1. Position-Based Weighting (exterior photos first)
2. Category Weighting (using `image_type` field)
3. Vision Reranking (Claude Vision for top-N)
4. Zero-Shot Classification (CLIP for features)
5. Tag Filtering (semantic validation)
6. Per-Feature Vector Decomposition

**Already Available:**
- `image_type` field exists in index ✅
- No reindexing needed ✅

---

### MULTI_FEATURE_QUERY_PROBLEM.md (463 lines)
Analysis of score_mode="max" limitations and solutions.

**Problem Example:**
```
Query: "white house with pool"
Property A: 10 photos (1 white exterior, 1 pool)
Property B: 10 photos (10 white exteriors, 0 pools)

Current (max): Property B scores higher (best white photo)
Correct (top-k): Property A scores higher (has both features)
```

**Solution Ready:** Top-K adaptive sum

---

### RRF_ZERO_OVERLAP_RESEARCH.md (894 lines)
Handling scenarios where search strategies return different results.

**Key Insight:** Zero overlap is NOT a bug - indicates strategy diversity (good for ensemble learning)

**Monitoring Metrics:**
- Overlap coefficient
- Strategy agreement rate
- Consensus confidence

**Solutions if Needed:**
- Weighted RRF by confidence
- Dynamic k-value adjustment
- Diversity-aware scoring

---

## ⚡ Quick Start

To implement any research:

1. **Read the full document** - Each contains complete implementation details
2. **Check current state** - Some features partially implemented
3. **Follow the code examples** - Ready-to-use implementations provided
4. **Test thoroughly** - All techniques include validation strategies
5. **Monitor metrics** - Impact measurement built into research

---

## 📝 Notes

- **No Reindexing Required:** All techniques work with current index
- **Cost-Effective:** Primarily runtime optimizations, minimal compute overhead
- **Academic Backing:** Research-supported approaches with proven impact
- **Implementation-Ready:** Complete code examples and integration points provided

---

Last Updated: 2025-10-21
