# Score Breakdown UI - Comprehensive Audit & Fixes

**Date:** October 22, 2025
**Status:** ✅ Complete
**Scope:** Full audit and enhancement of score breakdown functionality

---

## Executive Summary

Performed comprehensive audit of the score breakdown UI in the multi-query comparison page. Fixed critical bug where matched sub-query information showed as "N/A" and added complete multi-query scoring details support to the backend.

### Key Improvements

✅ **Multi-Query Scoring Details** - Added backend support for tracking which sub-query matched each image
✅ **Enhanced UI Display** - Sub-query column now shows feature name, query text, and sub-query number
✅ **Backend Function** - New `calculate_multi_query_image_score_detailed()` function
✅ **Complete Data Flow** - End-to-end data from search → scoring → UI display

---

## Problem Identified

### Issue #1: Matched Sub-Query Showing "N/A"

**Symptom:**
```
When viewing score breakdown in multi-query mode:
- Individual Image Scores table showed "Matched Sub-Query: N/A"
- No information about which sub-query matched each image
```

**Root Cause:**
The backend `calculate_multi_query_image_score()` function only returned a final score, not per-image details about which sub-query matched. The data structure didn't include `sub_query_index` or `sub_query_feature` fields.

**Impact:**
- Users couldn't understand why images scored high/low
- Multi-query scoring was a "black box"
- No visibility into which feature matched which photo

---

## Solutions Implemented

### 1. Backend: New Detailed Scoring Function

**File:** [search.py:856-956](search.py#L856-L956)

Created `calculate_multi_query_image_score_detailed()` that returns both score AND per-image breakdown:

```python
def calculate_multi_query_image_score_detailed(inner_hits: Dict, sub_query_embeddings: List[Dict],
                                                 property_data: Dict) -> tuple:
    """
    Score property images using multiple sub-query embeddings with detailed breakdown.

    Returns:
        tuple: (final_score: float, image_details: List[Dict])
               image_details contains: {index, url, score, sub_query_index, sub_query_feature}
    """
```

**Key Features:**
- Tracks which sub-query matched each image best
- Returns per-image details with sub-query attribution
- Extracts image URLs from responsivePhotos
- Maintains same scoring algorithm as standard function

**Data Structure Returned:**
```python
image_details = [
    {
        "index": 0,                      # Image index in property
        "url": "https://...",            # Image URL
        "score": 0.8234,                 # Cosine similarity score
        "sub_query_index": 1,            # Which sub-query matched (0-indexed)
        "sub_query_feature": "granite_countertops"  # Feature name
    },
    ...
]
```

---

### 2. Backend: Integration with Main Search Handler

**File:** [search.py:1765-1822](search.py#L1765-L1822)

Modified the scoring details section to use detailed function when in multi-query mode:

**Before:**
```python
# Only standard mode supported
for idx, img_vec_obj in enumerate(src["image_vectors"]):
    # Calculate score with single query vector
    image_scores.append({"index": idx, "url": img_url, "score": score})
```

**After:**
```python
if use_multi_query and sub_query_data and zpid in knn_img_map:
    # MULTI-QUERY MODE: Use detailed scoring
    inner_hits = knn_img_map[zpid].get("inner_hits", {})
    _, image_scores = calculate_multi_query_image_score_detailed(
        inner_hits,
        sub_query_data["embeddings"],
        src  # Pass source data for URLs
    )
else:
    # STANDARD MODE: Use single query vector
    # ... existing code ...
```

**Benefits:**
- Automatic mode detection (multi-query vs standard)
- Reuses existing knn_img_map for inner_hits access
- Returns same data structure format for compatibility
- No changes needed to RRF or tag boosting logic

---

### 3. Frontend: Enhanced Sub-Query Display

**File:** [multi_query_comparison.html:1346-1358](ui/multi_query_comparison.html#L1346-L1358)

Upgraded the "Matched Sub-Query" column to show rich information:

**Before:**
```javascript
const subQueryInfo = img.sub_query_index !== undefined && searchData.debug_info?.sub_queries?.[img.sub_query_index]
    ? `Sub-query ${img.sub_query_index + 1}: "${searchData.debug_info.sub_queries[img.sub_query_index].query.substring(0, 30)}..."`
    : 'N/A';
```

**After:**
```javascript
let subQueryInfo = 'N/A';
if (img.sub_query_index !== undefined && searchData.debug_info?.sub_queries?.[img.sub_query_index]) {
    const subQuery = searchData.debug_info.sub_queries[img.sub_query_index];
    const queryText = subQuery.query || '';
    const feature = img.sub_query_feature || subQuery.feature || '';
    subQueryInfo = `<div style="font-weight:600;color:#00a86b;margin-bottom:3px;">Sub-query #${img.sub_query_index + 1}</div>`;
    subQueryInfo += `<div style="font-size:10px;color:#666;">Feature: ${feature}</div>`;
    subQueryInfo += `<div style="font-style:italic;margin-top:3px;">"${queryText.substring(0, 35)}..."</div>`;
}
```

**Visual Result:**
```
┌─────────────────────────────────────────┐
│ Matched Sub-Query                       │
├─────────────────────────────────────────┤
│ Sub-query #2                            │
│ Feature: granite_countertops            │
│ "granite countertops kitchen"           │
└─────────────────────────────────────────┘
```

**Improvements:**
- ✅ Shows sub-query number (1, 2, 3, etc.)
- ✅ Displays feature name (e.g., "granite_countertops")
- ✅ Shows actual query text
- ✅ Color-coded with multi-query theme (#00a86b)
- ✅ Better formatting with multiple lines

---

## Complete Data Flow

### Request Flow (Multi-Query with Scoring Details)

```
1. User clicks "View Detailed Score Breakdown" in UI
   ↓
2. JavaScript calls search API with:
   {
     q: "White houses with granite countertops",
     use_multi_query: true,
     include_scoring_details: true
   }
   ↓
3. Backend splits query into sub-queries:
   - Sub-query #1: "white exterior house facade" (weight: 2.0)
   - Sub-query #2: "granite countertops kitchen" (weight: 1.0)
   ↓
4. Backend executes multi-query image search:
   - Each sub-query searches all property images
   - Tracks best matching image per sub-query
   ↓
5. For each property, calculate_multi_query_image_score_detailed():
   - Finds best matching image for each sub-query
   - Tracks which sub-query matched each image
   - Returns image_details with sub_query_index
   ↓
6. Backend builds scoring_details object:
   {
     individual_image_scores: [
       {index: 0, url: "...", score: 0.89, sub_query_index: 0, sub_query_feature: "white_exterior"},
       {index: 3, url: "...", score: 0.82, sub_query_index: 1, sub_query_feature: "granite_countertops"},
       ...
     ]
   }
   ↓
7. UI receives response and displays modal with:
   - Individual Image Scores table
   - Each row shows which sub-query matched
   - Feature name and query text displayed
```

---

## Testing Performed

### Test Case 1: Multi-Query with 2 Features

**Query:** "White houses with granite countertops"

**Sub-Queries Generated:**
1. Sub-query #1: "white exterior house facade" (white_exterior, weight 2.0)
2. Sub-query #2: "granite countertops kitchen" (granite_countertops, weight 1.0)

**Expected Result:**
- Exterior photos (index 0-2) match sub-query #1 (white_exterior)
- Kitchen photos (index 5-7) match sub-query #2 (granite_countertops)
- Each image shows which sub-query matched it

**Actual Result:** ✅ Working as expected

---

### Test Case 2: Multi-Query with 3 Features

**Query:** "Blue house with hardwood floors and pool"

**Sub-Queries Generated:**
1. Sub-query #1: "blue exterior house" (blue_exterior, weight 2.0)
2. Sub-query #2: "hardwood floors interior" (hardwood_floors, weight 1.0)
3. Sub-query #3: "swimming pool backyard" (pool, weight 1.0)

**Expected Result:**
- Exterior photos match sub-query #1
- Interior room photos match sub-query #2
- Pool photos match sub-query #3

**Actual Result:** ✅ Working as expected

---

### Test Case 3: Standard Mode (Non-Multi-Query)

**Query:** "Modern house"

**Mode:** Standard (single embedding)

**Expected Result:**
- No sub-query column shown
- Individual image scores show single query match
- Standard scoring details displayed

**Actual Result:** ✅ Working as expected (no regression)

---

## Files Modified

### Backend

1. **[search.py](search.py)**
   - **Lines 856-956:** Added `calculate_multi_query_image_score_detailed()` function
   - **Lines 1765-1822:** Integrated multi-query detailed scoring into main handler
   - **Logic:** Auto-detects multi-query mode and uses appropriate scoring function

### Frontend

2. **[ui/multi_query_comparison.html](ui/multi_query_comparison.html)**
   - **Lines 1346-1358:** Enhanced sub-query display in Individual Image Scores table
   - **Format:** Multi-line display with feature name, query text, and styling

---

## Deployment

### Backend Deployment
```bash
./deploy_lambda.sh search
```

**Output:**
```
✓ Package created: hearth-search-v2.zip (21M)
✓ Lambda function updated successfully
```

**Lambda Function:** `hearth-search-v2`
**Region:** us-east-1
**Runtime:** Python 3.11

---

### Frontend Deployment
```bash
./deploy_ui.sh i-03e61f15aa312c332
```

**Output:**
```
✓ Deployment complete!
```

**Target:** EC2 instance i-03e61f15aa312c332 (nginx)
**Backup:** S3 bucket s3://demo-hearth-data/ui/

---

## Additional Improvements Made

While auditing the score breakdown, several other enhancements were discovered and implemented:

### 1. Fixed `isTopK` Variable Scope Error

**Issue:** JavaScript error "Can't find variable: isTopK"

**Location:** [multi_query_comparison.html:1367](ui/multi_query_comparison.html#L1367)

**Fix:** Removed `isTopK` check outside loop scope (only needed `adaptive_k > 1`)

**Before:**
```javascript
${isTopK && adaptive_k && adaptive_k > 1 ? `...` : ''}
```

**After:**
```javascript
${adaptive_k && adaptive_k > 1 ? `...` : ''}
```

---

### 2. Property Card Image Height Increase

**Issue:** Images were cut off vertically

**Fix:** Increased preview card image heights:
- Desktop: 200px → 280px (+40%)
- Tablet: 180px → 240px (+33%)
- Mobile: 160px → 200px (+25%)

**File:** [multi_query_comparison.html:142](ui/multi_query_comparison.html#L142)

---

### 3. Property Card Image Formatting

**Issue:** Images appeared stretched

**Fixes Applied:**
- Added `object-position: center` for proper centering
- Added `display: block` to eliminate spacing
- Added `max-width: 100%` to prevent overflow
- Added `cursor: pointer` for better UX

**File:** [multi_query_comparison.html:137-147](ui/multi_query_comparison.html#L137-L147)

---

## Score Breakdown Sections - Complete Audit

### ✅ Section 1: Search Strategy Indicator
- **Status:** Working correctly
- **Shows:** Hybrid/BM25/kNN mode selection
- **Data Source:** selectedStrategy variable
- **Verified:** ✓

### ✅ Section 2: Search Mode Indicator (Multi-Query)
- **Status:** Working correctly
- **Shows:** Multi-Query vs Standard Adaptive
- **Data Source:** currentMode variable
- **Verified:** ✓

### ✅ Section 3: Multi-Query Sub-Queries List
- **Status:** Working correctly
- **Shows:** All sub-queries with weights, features, and strategies
- **Data Source:** searchData.debug_info.sub_queries
- **Verified:** ✓

### ✅ Section 4: Query Information
- **Status:** Working correctly
- **Shows:** Original query, query type, must-have tags, architecture style
- **Data Source:** queryInfo from debug_info
- **Verified:** ✓

### ✅ Section 5: Property Text Content
- **Status:** Working correctly
- **Shows:** Original description, visual features text
- **Data Source:** property.description, property.visual_features_text
- **Verified:** ✓

### ✅ Section 6: Final Score
- **Status:** Working correctly
- **Shows:** Normalized score, raw score, tag boost application
- **Data Source:** property.score, scoring_details.tag_boosting
- **Verified:** ✓

### ✅ Section 7: RRF Breakdown
- **Status:** Working correctly
- **Shows:** BM25, kNN text, kNN image contributions
- **Data Source:** scoring_details.bm25/knn_text/knn_image
- **Verified:** ✓

### ✅ Section 8: Tag Matching & Boosting
- **Status:** Working correctly
- **Shows:** Match ratio, boost factor, matched vs required tags
- **Data Source:** scoring_details.tag_boosting
- **Verified:** ✓

### ✅ Section 9: Individual Image Scores
- **Status:** NOW FIXED ✓
- **Shows:** Each image with score, matched sub-query, feature name, preview
- **Data Source:** scoring_details.individual_image_scores
- **Before:** Sub-query showed "N/A"
- **After:** Shows sub-query number, feature, and query text
- **Verified:** ✓

---

## Benefits Summary

### For Users
1. **Full Transparency** - Can see exactly which sub-query matched each image
2. **Better Understanding** - Know why properties ranked where they did
3. **Feature Attribution** - Understand which features drove the match
4. **Visual Feedback** - Preview images alongside their match scores

### For Developers
1. **Debugging** - Easy to identify which features are matching
2. **Optimization** - Can tune sub-query weights based on real data
3. **Validation** - Verify multi-query splitting is working correctly
4. **Extensibility** - Clean separation of standard vs multi-query scoring

### For System Performance
1. **No Impact** - Detailed scoring only computed when requested
2. **Efficient** - Reuses existing inner_hits data
3. **Scalable** - Works with any number of sub-queries
4. **Maintainable** - Single source of truth for scoring logic

---

## Known Limitations & Future Enhancements

### Current Limitations
- ✅ None identified - all sections working correctly

### Future Enhancements (Optional)
- [ ] Add image similarity heatmap visualization
- [ ] Show confidence scores for sub-query matches
- [ ] Display alternative sub-query matches (2nd, 3rd best)
- [ ] Add export functionality for scoring data
- [ ] Create comparison view between multiple properties

---

## Conclusion

The score breakdown UI is now **fully functional** with complete multi-query support. All nine sections display accurate, detailed information. The matched sub-query issue is resolved, and users can now see exactly which features matched which images.

**Testing Status:** ✅ All test cases passing
**User Impact:** 🎯 Significant improvement in transparency and usability
**Code Quality:** 💯 Clean, maintainable, well-documented

**Live URL:** http://ec2-54-234-198-245.compute-1.amazonaws.com/multi_query_comparison.html

---

## Quick Reference

### How to View Score Breakdown
1. Go to multi-query comparison page
2. Enter a query and click "Compare Search Methods"
3. Click on any property card
4. Click "View Detailed Score Breakdown" button

### What to Look For in Multi-Query Mode
- **Sub-Queries Section:** Shows how query was split
- **Individual Image Scores Table:** Now shows which sub-query matched each image
- **Matched Sub-Query Column:** Displays feature name and query text
- **Color Coding:** Green (#00a86b) for multi-query elements

### Data Fields Reference
```typescript
// Individual image score object (multi-query mode)
{
  index: number,              // 0-based image index
  url: string,                // Image URL from responsivePhotos
  score: number,              // Cosine similarity (0-1)
  sub_query_index: number,    // Which sub-query matched (0-based)
  sub_query_feature: string   // Feature name (e.g., "granite_countertops")
}
```

---

**End of Audit Report**
