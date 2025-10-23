# Good Search Baseline Investigation
## October 23, 2025 at 10:30 PM EDT (03:30 UTC)

---

## Executive Summary

This investigation identifies the exact configuration and code that produced excellent search results at **2025-10-23 03:29:51 UTC** for the query "White homes with granite countertops and wood floors". All 10 results had **100% feature match**, indicating perfect alignment with the user's intent.

---

## Search Details

### Query Information
- **Query ID**: `28ef18aa-a927-48df-9933-31f85d772ba4`
- **Exact Timestamp**: `2025-10-23 03:29:51.284 UTC`
- **Unix Timestamp**: `1761190191284` ms
- **Query Text**: `"White homes with granite countertops and wood floors"`
- **Multi-Query Mode**: `True`

### Sub-Queries Generated

The system generated 3 feature-specific sub-queries with different weights:

1. **granite_countertops** (weight: 1.0x, strategy: max)
   - Sub-query: `"granite stone countertops kitchen surfaces"`

2. **white_exterior** (weight: 2.0x, strategy: max)
   - Sub-query: `"white painted house exterior facade siding building"`

3. **hardwood_floors** (weight: 1.0x, strategy: max)
   - Sub-query: `"hardwood flooring floors interior wood planks"`

**Key Insight**: The `white_exterior` feature was weighted 2x higher than the other features, likely because it's the primary/most visible characteristic.

---

## Results Quality

### Top 10 ZPIDs (ALL with 100% match)

| Rank | ZPID        | Score    | City           | Price       | Beds/Baths |
|------|-------------|----------|----------------|-------------|------------|
| 1    | 2080387168  | 0.070769 | West Jordan    | $700,000    | 6bd / 4ba  |
| 2    | 12778555    | 0.055556 | Salt Lake City | $2,950,000  | 5bd / 4ba  |
| 3    | 70592220    | 0.054054 | Holladay       | $860,000    | 5bd / 3ba  |
| 4    | 12717999    | 0.052632 | Salt Lake City | $1,495,000  | 5bd / 4ba  |
| 5    | 12792227    | 0.051282 | Millcreek      | $2,900,000  | 6bd / 7ba  |
| 6    | 89416688    | 0.050000 | Holladay       | $3,810,000  | 4bd / 6ba  |
| 7    | 12842411    | 0.047619 | West Jordan    | $600,000    | 4bd / 3ba  |
| 8    | 453896301   | 0.044444 | Salt Lake City | $3,461      | 3bd / 2ba  |
| 9    | 61167372    | 0.043478 | Salt Lake City | $539,000    | 5bd / 4ba  |
| 10   | 12736760    | 0.042553 | Salt Lake City | $1,999      | 3bd / 2ba  |

### Quality Metrics
- **Average Score**: 0.0512
- **Score Variance**: 0.000061 (very consistent)
- **Perfect Matches (100%)**: 10 out of 10
- **Partial Matches**: 0
- **No Matches (0%)**: 0

**All 10 results matched all 3 features**: `white_exterior` + `granite_countertops` + `hardwood_floors`

---

## Lambda Deployment Information

### Active Lambda Function (During Good Search)
- **Function Name**: `hearth-search-detailed-scoring`
- **Deployed**: `2025-10-22 19:02:27 UTC` (8.5 hours before good search)
- **Runtime**: `python3.11`
- **Handler**: `search_detailed_scoring.handler`
- **Code SHA256**: `mtlx9bO7HM8XT/mywKDXaTVo0gzNmCrIxXuu1UAUJMY=`
- **Code Size**: 21,677,592 bytes
- **Version**: `$LATEST`

### Git Commit (Active Code)
- **Commit Hash**: `ac6660b84680896399bb7fc569ba2bfdfbf04247`
- **Commit Date**: `2025-10-22 22:13:11 -0400` (Oct 22, 10:13 PM EDT)
- **Commit Message**: `"Implement RRF diversification and image weight boosting"`
- **Time Before Search**: ~5.3 hours

### Subsequent Deployment (AFTER Good Search)
- **Function**: `hearth-search-v2`
- **Deployed**: `2025-10-23 04:10:18 UTC`
- **Time AFTER Good Search**: 40.5 minutes
- **Impact**: This deployment likely introduced changes that degraded result quality

---

## Search Configuration

- **Index**: `listings-v2`
- **Boost Mode**: `standard`
- **Search Mode**: `adaptive`
- **Strategy**: `hybrid`

### Performance Metrics
- **Total Time**: 6,076.39 ms
- **LLM Query Split**: 2,946.49 ms
- **Constraint Extraction**: 1,578.79 ms
- **KNN Image**: 661.27 ms
- **BM25**: 383.62 ms
- **KNN Text**: 375.64 ms
- **Embedding Generation**: 63.30 ms
- **Multi-Query Embeddings**: 29.12 ms
- **Tag Boosting**: 10.55 ms
- **RRF Fusion**: 0.20 ms

---

## Key Features That Made It Work

### 1. RRF (Reciprocal Rank Fusion) Diversification
From commit `ac6660b`:
```
Implement greedy selection in calculate_multi_query_image_score()
- Ensure each sub-query contributes exactly 1 distinct image to RRF score
- Prevents one feature (e.g., hardwood floors) from dominating all top-K images
- Add detailed logging for RRF image selection process
```

**Algorithm**:
1. Calculate similarity scores for all (sub-query, image) pairs
2. Greedily select best match, then exclude that sub-query
3. Each sub-query contributes exactly 1 image to the final score

### 2. Image Weight Boosting for Visual Queries
From commit `ac6660b`:
```
Modify calculate_adaptive_weights_v2() to boost images when visual features present
- Mixed queries with ≥1 visual feature now use Image k=35 (vs 55 before)
- Ensures properties with strong visual matches rank at the top
- Fixes issue where visually-matching properties ranked too low
```

### 3. Feature-Based Query Splitting
- The LLM correctly identified 3 distinct features
- Each feature got its own specialized sub-query
- Different weights reflected feature importance (white_exterior: 2x)

### 4. Max Strategy for Feature Matching
- Each sub-query used "max" strategy
- Takes the best matching image/text for that specific feature
- Prevents averaging that would dilute strong matches

---

## What Changed After the Good Search

### Timeline
1. **03:29:51 UTC**: Good search results (all 10 = 100% match)
2. **04:10:18 UTC**: New deployment of `hearth-search-v2` (40.5 minutes later)
3. **Result**: Likely introduction of changes that degraded quality

### Potential Issues in Later Deployment
Need to compare `ac6660b` with the code deployed in `hearth-search-v2` to identify:
- Changes to RRF diversification logic
- Changes to image weight boosting
- Changes to sub-query weighting
- Changes to feature extraction/classification

---

## Recommendations

### Immediate Actions
1. **Compare Code Versions**
   - Diff `ac6660b` against current `hearth-search-v2` code
   - Identify what changed in the RRF/image scoring logic

2. **Review Sub-Query Weighting**
   - The 2x weight for `white_exterior` seems important
   - Verify current code applies proper weights

3. **Test RRF Diversification**
   - Ensure greedy selection is still working
   - Verify each sub-query contributes distinct images

### Long-Term Improvements
1. **Version Tracking in Logs**
   - Add git commit hash to search logs
   - Add deployment timestamp to logs
   - Makes investigations like this easier

2. **A/B Testing Infrastructure**
   - Keep "good" version running alongside new deployments
   - Compare quality metrics before full rollout

3. **Quality Regression Testing**
   - Establish baseline queries like this one
   - Run automated tests after each deployment
   - Alert if quality drops below threshold

---

## Files Saved

- `/tmp/investigation_report.json` - Complete investigation data
- `/tmp/baseline_good_search.json` - Search details and results
- `/tmp/good_zpids.json` - List of ZPIDs and their details

---

## Conclusion

The "good" search at **2025-10-23 03:29:51 UTC** was powered by:
- **Git commit**: `ac6660b` - "Implement RRF diversification and image weight boosting"
- **Lambda function**: `hearth-search-detailed-scoring`
- **Deployment**: 8.5 hours before the search

The key was the combination of:
1. RRF diversification ensuring each feature contributed
2. Image weight boosting for visual features
3. Proper sub-query weighting (2x for white_exterior)
4. Max strategy for feature matching

The deployment 40 minutes later likely broke these results. Need to identify what changed.
