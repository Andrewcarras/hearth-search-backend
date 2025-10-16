# Score Breakdown UI Improvements

## Summary

Updated the Detailed Score Breakdown modal to fix inconsistencies between Standard and Adaptive search modes, and added a new feature to view complete raw listing data in JSON format.

---

## Changes Made

### 1. Fixed Explanations for Standard vs Adaptive Mode

**Problem:** The score breakdown explanations were written assuming Adaptive mode, which was confusing when using Standard mode with equal weighting (k=60 for all strategies).

**Solution:** Updated all explanatory text to be context-aware based on `selectedSearchMode`.

#### Updated Sections:

**A. Query Type Explanation (Lines 1278-1316)**
- **Standard Mode:** Explains that all strategies are weighted equally (k=60)
- **Adaptive Mode:** Provides query-type-specific explanations (visual_style, color, material, specific_feature, general)
- Shows which strategies actually matched the property
- Clarifies why "Not found in top results" is expected behavior

**B. RRF Description (Lines 1339-1344)**
- **Standard Mode:** "All strategies use k=60 (equal weighting), so every strategy contributes proportionally based on rank only"
- **Adaptive Mode:** "Lower k-values = higher weight for that strategy. The adaptive k-values above show which strategies are prioritized for your query type"

**C. "Why Not Found is Normal" Explanation (Lines 1343-1351)**
- **Standard Mode:** "Even in Standard mode with equal weighting, not every property appears in all three strategy results. Each strategy searches independently and returns its own top results. Properties can still rank well overall even if they only match via one or two strategies."
- **Adaptive Mode:** "Not every property matches all three strategies! A visual style query might only use image kNN. A keyword query might only use BM25. That's intentional - each strategy specializes in different query types."

---

### 2. Added Raw Listing Data Viewer

**Feature:** New button in the score breakdown modal that opens a popup showing complete listing data in JSON format.

#### Implementation:

**Button Location (Lines 1190-1192):**
```html
<button onclick="showRawListingData()" style="...">
    📄 View Raw Listing Data (JSON)
</button>
```

**Features:**
- **Copy to Clipboard:** Quick copy of entire JSON
- **Download as JSON:** Save as `listing_{zpid}_raw_data.json`
- **Syntax Highlighted:** Dark theme with monospace font
- **Full Data:** Includes all property fields, scoring details, images, tags, embeddings metadata

**Data Included:**
```json
{
  "property": {...},           // Full property object
  "zpid": "...",
  "score": 0.123456,
  "address": "...",
  "city": "...",
  "state": "...",
  "price": 500000,
  "beds": 3,
  "baths": 2,
  "description": "...",
  "visual_features_text": "...",  // AI-generated from images
  "feature_tags": [...],
  "image_tags": [...],
  "architecture_style": "...",
  "image_vectors_count": 21,
  "images": [...],
  "_scoring_details": {           // Complete RRF breakdown
    "bm25": {...},
    "knn_text": {...},
    "knn_image": {...},
    "rrf_total": 0.123456
  },
  "_all_fields": {...}            // Every field from OpenSearch
}
```

**Functions Added:**
- `showRawListingData()` - Creates modal and populates with JSON (lines 1671-1726)
- `closeRawDataModal()` - Closes the modal (lines 1728-1730)
- `copyRawData()` - Copies JSON to clipboard (lines 1732-1739)
- `downloadRawData()` - Downloads JSON file (lines 1741-1752)

---

## Testing Checklist

### Standard Mode Testing:
- [x] Explanations mention "Standard mode" and k=60
- [x] No references to query-type-specific strategies
- [x] "Not found in top results" explanation appropriate for equal weighting
- [x] RRF description mentions equal weighting

### Adaptive Mode Testing:
- [x] Query type classification shows correctly
- [x] k-values reflect query type (color → BM25 boosted, visual_style → image boosted)
- [x] Explanations match the actual k-values used
- [x] Strategy highlights show which methods matched

### Raw Data Viewer Testing:
- [x] Button appears in score breakdown
- [x] Modal opens with formatted JSON
- [x] Copy to clipboard works
- [x] Download as JSON works
- [x] All property fields included
- [x] Scoring details included
- [x] Modal closes on X or outside click

---

## User Benefits

### 1. Clearer Understanding of Search Modes
Users can now see exactly what's different between Standard and Adaptive modes in the detailed breakdown, not just the selector tooltip.

### 2. Better Debugging Capability
The raw JSON viewer allows users to:
- Inspect all property fields without opening OpenSearch
- Verify what data is actually indexed
- Check if visual_features_text is present
- See exact scoring details for diagnostics
- Share complete property data with developers
- Download for offline analysis

### 3. Accurate Expectations
Mode-specific explanations help users understand why certain strategies show "Not found in top results" based on whether they're using Standard or Adaptive mode.

---

## Example Use Cases

### Use Case 1: Comparing Search Modes
**Scenario:** User searches "modern kitchen" in both Standard and Adaptive modes.

**Before:** Explanations always talked about query types and adaptive weighting, even in Standard mode.

**After:**
- **Standard mode:** Sees "all strategies weighted equally (k=60)"
- **Adaptive mode:** Sees "visual_style query prioritizes image kNN (k=40)"

### Use Case 2: Debugging Missing Visual Features
**Scenario:** Property ranks poorly despite matching keywords.

**Process:**
1. Click "Detailed Score Breakdown"
2. Click "📄 View Raw Listing Data (JSON)"
3. Search for `visual_features_text`
4. If null/missing → property needs re-indexing with image analysis
5. If present → can inspect exact AI-generated description

### Use Case 3: Understanding "Not Found" Messages
**Scenario:** User sees "Not found in top results" for kNN image.

**Standard Mode Explanation:**
"Even in Standard mode with equal weighting, not every property appears in all three strategy results. Each strategy searches independently..."

**Adaptive Mode Explanation:**
"Not every property matches all three strategies! A visual style query might only use image kNN. A keyword query might only use BM25. That's intentional..."

---

## Technical Details

### Context-Aware Explanations Implementation

Used JavaScript template literals with conditional logic:
```javascript
${selectedSearchMode === 'adaptive'
    ? 'Adaptive mode explanation...'
    : 'Standard mode explanation...'}
```

This ensures explanations always match the current search mode without requiring page reload.

### Raw Data Modal Architecture

- **Lazy Creation:** Modal only created on first use
- **Reusable:** Same modal instance used for all properties
- **Self-Contained:** Includes all controls (copy, download, close)
- **Accessible:** Can close via X button, outside click, or ESC key
- **Performance:** JSON stringified on-demand, not stored in DOM

---

## Files Modified

- [ui/search.html](ui/search.html#L1278-L1316) - Query type explanation logic
- [ui/search.html](ui/search.html#L1339-L1344) - RRF description
- [ui/search.html](ui/search.html#L1343-L1351) - "Why not found is normal" explanation
- [ui/search.html](ui/search.html#L1190-L1192) - Raw data button
- [ui/search.html](ui/search.html#L1671-L1752) - Raw data viewer functions

---

## Deployment

**Deployed to:** EC2 instance i-03e61f15aa312c332
**Deployment Date:** October 16, 2024
**Method:** S3 upload → SSM command to sync to nginx
**Status:** ✓ Successfully deployed

---

## Next Steps

### Potential Future Enhancements:

1. **Collapsible Raw Data Sections**
   - Collapse large arrays (images, tags) by default
   - Add expand/collapse controls for nested objects

2. **Field-Specific Viewers**
   - "View All Image Vectors" button showing each image's embedding
   - "View Visual Features History" if property has multiple analyses

3. **Comparison Mode**
   - View raw data for multiple properties side-by-side
   - Highlight differences in scoring/features

4. **Search Within JSON**
   - Filter/highlight specific fields
   - Search for keywords within the raw data

5. **Export Options**
   - CSV export for tabular data (tags, scores)
   - Share link that opens raw data viewer directly

---

## Related Documentation

- [AWS_BEDROCK_COST_INVESTIGATION.md](AWS_BEDROCK_COST_INVESTIGATION.md) - Cost analysis and optimization
- [search.py](search.py#L786-L792) - Backend search mode implementation
- [search_debug.py](search_debug.py#L819-L825) - Debug endpoint search mode logic

---

**Last Updated:** October 16, 2024
**Status:** ✅ Complete and deployed
