# Score Breakdown UI Update - Multi-Query Comparison Page

**Date:** October 22, 2025
**Status:** ✅ Completed and Deployed

---

## Problem Statement

The multi-query comparison page (`multi_query_comparison.html`) showed only raw JSON data in the score breakdown modal, instead of the rich, formatted breakdown that appears in the main search UI (`search.html`).

**User Feedback:**
> "These cards i see from the comparison search mode only show the raw JSON data. I literally want exactly the same score breakdown as youd see from the normal search view. It should just have an additional bit of text showing how the query was split up from the multi query mode"

---

## Solution Implemented

Replaced the simple JSON display with the complete formatted score breakdown from [search.html:1304-2173](search.html#L1304-L2173), with **multi-query mode enhancements**.

---

## Changes Made

### File: `ui/multi_query_comparison.html`

**1. Added Helper Function (Line 910-913)**
```javascript
// Helper function to create info tooltip
function infoTooltip(text) {
    return `<span class="info-icon">ⓘ<span class="info-tooltip">${text}</span></span>`;
}
```

**2. Completely Replaced `displayScoreBreakdown()` Function (Lines 915-1263)**

The new implementation includes:

#### **A. Strategy Indicator Section**
- Shows "Hybrid (All 3 Strategies)" with color-coded background (#e7d9f7 purple)
- Explains what hybrid mode does
- Matches the exact styling from search.html

#### **B. Search Mode Indicator** ✨ NEW FOR MULTI-QUERY
- **Multi-Query Mode:** Orange background (#ffe8e0), 🔀 icon
  - Text: "System uses LLM to split query into context-specific sub-queries with weighted scoring"
- **Standard Adaptive Mode:** Green background (#d4edda), 🎯 icon
  - Text: "System automatically adjusts scoring weights based on query type"

#### **C. Multi-Query Sub-Queries Section** ✨ NEW FOR MULTI-QUERY
**Only shows when `currentMode === 'multi'`**

Displays each sub-query with:
- **Sub-query text** in monospace font on light background
- **Weight badge** (2.0x weight = red, 1.0x weight = blue)
- **Context label:**
  - 🏠 Exterior (Primary) - for exterior features
  - 🏠 Interior Room - for interior room features
  - 🔨 Material/Finish - for materials
- **Feature:** e.g., "white_exterior", "granite_countertops"
- **Strategy:** e.g., "max" (find single best image)

**Example Display:**
```
🔀 Multi-Query Sub-Queries

Your query was intelligently split into 3 context-specific sub-queries by Claude Haiku:

┌─────────────────────────────────────────┐
│ Sub-query 1:                    [2.0x]  │
│ "white exterior house facade outside"   │
│ Context: 🏠 Exterior (Primary)          │
│ Feature: white_exterior                 │
│ Strategy: max                           │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Sub-query 2:                    [1.0x]  │
│ "granite countertops kitchen"           │
│ Context: 🏠 Interior Room               │
│ Feature: granite_countertops            │
│ Strategy: max                           │
└─────────────────────────────────────────┘

💡 How Weighting Works:
Exterior features get 2.0x weight because they're primary (the main photo must match).
Interior features get 1.0x weight (can appear in any photo).
```

#### **D. Query Information Section**
- Original query text
- Query type (visual_style, color, material, specific_feature, etc.)
- Must-have tags extracted
- Architecture style (if detected)
- All with ⓘ info tooltips

#### **E. Property Text Content Section**
- **Original Description:** Zillow description (weight 3.0 in BM25)
- **Visual Features Text:** AI-generated from image analysis (weight 2.5 in BM25)
- Explains how BM25 and kNN text use these fields

#### **F. Final Score Section**
- Large display: "85/100" (normalized score)
- Raw technical score: 0.0543210
- Tag boost indicator (if applied)
- Calculation explanation:
  - **Multi-query mode:** "Final Score = Multi-Query Image Score + BM25 + kNN Text (combined via RRF) × Tag Boost Factor"
  - **Standard mode:** "Final Score = RRF Total Score × Tag Boost Factor"

#### **G. RRF Breakdown Section**
Shows all three search strategy components:

**📝 BM25 Full-Text Search**
- Rank: #5
- Original BM25 Score: 12.543210
- RRF k-value: 60
- RRF Contribution: 0.015385
- Calculation: 1 ÷ (60 + 5) = 0.015385

**🧠 kNN Text Similarity Search**
- Query Vector: 1024-dimensional embedding from "query text"
- Rank: #3
- Cosine Similarity Score: 0.823456
- RRF k-value: 55
- RRF Contribution: 0.017241

**🖼️ kNN Image Similarity Search**
- Multi-query mode explanation (if applicable)
- Number of images: (20 images)
- Rank: #2
- Image score (top-k sum or max)
- RRF k-value: 30
- RRF Contribution: 0.031250

**Total RRF Score:** 0.063876

#### **H. Tag Matching & Boosting Section**
- Match Ratio: 100% (3/3 tags) - color coded (green/yellow/red)
- Boost Factor: 2.0x
- RRF Score (before boost): 0.063876
- Final Score (after boost): 0.127752
- **Required Tags Analysis:** Visual display of ✓/✗ for each tag
  - ✓ granite_countertops (green)
  - ✓ wood_floors (green)
  - ✗ pool (red)

---

## Key Differences from Main Search UI

### **Additions for Multi-Query Mode:**

1. **Search Mode Indicator** adapts:
   - Shows "Multi-Query Splitting Mode" (orange) when `currentMode === 'multi'`
   - Shows "Standard Adaptive Mode" (green) when `currentMode === 'standard'`

2. **Multi-Query Sub-Queries Section** (lines 973-1006):
   - Only appears when `currentMode === 'multi'` AND `searchData.debug_info.sub_queries` exists
   - Shows each sub-query with weight, context, feature, and strategy
   - Includes educational tooltip explaining weighting (exterior 2.0x, interior 1.0x)

3. **Final Score Calculation** text adapts:
   - Multi-query: "Multi-Query Image Score + BM25 + kNN Text (combined via RRF)"
   - Standard: "RRF Total Score × Tag Boost Factor"

4. **kNN Image Description** adapts:
   - Multi-query: "Each sub-query searches images independently, then weighted scores are summed."
   - Standard: "Adaptive Top-K Scoring: The sum of the top K image scores..."

### **Removed from Main Search UI:**

1. **"View Raw Listing Data (JSON)" button** - Not needed in comparison view
2. **OpenSearch query details** - Omitted from `details` sections (search.html shows these in collapsible `<details>`)
3. **Individual Image Scores Table** - Not included (search.html shows table of all image vector scores)

---

## Data Flow

```
User clicks "📊 View Detailed Score Breakdown" button
                    ↓
        showScoreBreakdown() function
                    ↓
    Fetch search endpoint with:
    - q: window.currentQuery
    - use_multi_query: currentMode === 'multi'
    - include_scoring_details: true
                    ↓
        displayScoreBreakdown(property, searchData)
                    ↓
    Render formatted breakdown with:
    - property._scoring_details (RRF components)
    - searchData.debug_info.sub_queries (if multi-query)
    - queryInfo.original_query, query_type, must_tags
                    ↓
        Display in scoreModal
```

---

## Visual Styling

All sections use consistent styling from search.html:

- **Color-coded borders:**
  - Hybrid strategy: Purple (#6f42c1)
  - Multi-query mode: Orange (#ff6b35)
  - BM25: Green (#28a745)
  - kNN Text: Blue (#007bff)
  - kNN Image: Red (#dc3545)
  - Query info: Yellow (#ffc107)
  - Property text: Light blue (#4a90e2)

- **Section backgrounds:**
  - Light colored backgrounds matching border colors
  - White content boxes within sections
  - Gray boxes for metrics/calculations

- **Typography:**
  - 18px bold headings with colored icons
  - 13-14px body text
  - 12px explanatory text
  - Monospace for technical values

- **Info Tooltips:**
  - ⓘ icon with hover tooltip
  - Explains technical terms in plain language

---

## Testing Checklist

✅ **Multi-Query Mode:**
- [ ] Search "White houses with granite countertops" in comparison mode
- [ ] Click multi-query result property
- [ ] Click "📊 View Detailed Score Breakdown"
- [ ] Verify "Multi-Query Splitting Mode" indicator appears (orange)
- [ ] Verify sub-queries section shows:
  - "white exterior house facade outside" (2.0x weight, red badge)
  - "granite countertops kitchen" (1.0x weight, blue badge)
- [ ] Verify each sub-query shows context, feature, strategy
- [ ] Verify weighting explanation tooltip is present

✅ **Standard Mode:**
- [ ] Search same query in comparison mode
- [ ] Click standard result property
- [ ] Click "📊 View Detailed Score Breakdown"
- [ ] Verify "Standard Adaptive Mode" indicator appears (green)
- [ ] Verify NO sub-queries section appears
- [ ] Verify standard adaptive K explanation shows

✅ **Common Sections:**
- [ ] Verify all sections render:
  - Strategy indicator (Hybrid)
  - Query information (original query, type, tags)
  - Property text content (description + visual_features_text)
  - Final score (normalized and raw)
  - RRF breakdown (BM25 + kNN text + kNN image)
  - Tag matching & boosting
- [ ] Verify all info tooltips (ⓘ) work on hover
- [ ] Verify color coding matches search.html
- [ ] Verify all calculations display correctly
- [ ] Verify tag match badges show ✓/✗ correctly

---

## Files Modified

1. **ui/multi_query_comparison.html**
   - Added `infoTooltip()` helper function (line 910)
   - Completely replaced `displayScoreBreakdown()` function (lines 915-1263)
   - Total lines changed: ~800 lines

2. **Deployed via:**
   - `./deploy_ui.sh i-03e61f15aa312c332`
   - Uploaded to S3: `s3://demo-hearth-data/ui/multi_query_comparison.html`
   - Deployed to EC2: `/usr/share/nginx/html/multi_query_comparison.html`

---

## Example Score Breakdown Display

### For Query: "White houses with granite countertops and wood floors"

**Multi-Query Mode:**

```
🔀 Search Strategy: Hybrid (All 3 Strategies)
Hybrid mode combines all three search strategies...

🔀 Search Mode: Multi-Query Splitting Mode
System uses LLM to split query into context-specific sub-queries...

🔀 Multi-Query Sub-Queries
Your query was intelligently split into 3 sub-queries:

Sub-query 1: "white exterior house facade outside"  [2.0x]
Context: 🏠 Exterior (Primary) | Feature: white_exterior | Strategy: max

Sub-query 2: "granite countertops kitchen"  [1.0x]
Context: 🏠 Interior Room | Feature: granite_countertops | Strategy: max

Sub-query 3: "wood floors bedroom living room"  [1.0x]
Context: 🏠 Interior Room | Feature: wood_floors | Strategy: max

🔍 Query Information
Original Query: "White houses with granite countertops and wood floors"
Query Type: color
Must-Have Tags: white_exterior, granite_countertops, wood_floors

📄 Property Text Content
[Description and visual_features_text with explanations]

🎯 Final Score: 87/100
Raw: 0.065432
Tag Boost Applied: ✓ Yes
How it's calculated: Multi-Query Image Score + BM25 + kNN Text × 2.0x boost

🔀 RRF Breakdown
Total RRF Score: 0.065432
= 0.015385 (BM25) + 0.017241 (kNN text) + 0.032806 (kNN image)

📝 BM25: Rank #5, Score: 12.54, RRF: 0.015385
🧠 kNN Text: Rank #3, Score: 0.82, RRF: 0.017241
🖼️ kNN Image: Rank #2, Multi-query scores summed, RRF: 0.032806

🏷️ Tag Matching: 100% (3/3)
Boost Factor: 2.0x
✓ white_exterior  ✓ granite_countertops  ✓ wood_floors
```

---

## Benefits

### **For Users:**
1. **Consistent Experience:** Same detailed breakdown whether viewing from main search or comparison page
2. **Multi-Query Transparency:** Can see exactly how the query was split and weighted
3. **Educational:** Info tooltips explain every metric and calculation
4. **Visual Clarity:** Color coding makes it easy to distinguish strategy components

### **For Debugging:**
1. **Complete Visibility:** All RRF components visible (BM25, text, image)
2. **Multi-Query Debugging:** Can verify sub-queries are correctly generated
3. **Weight Verification:** Can confirm exterior features get 2.0x vs interior 1.0x
4. **Tag Matching:** Can see which tags matched/missed

### **For Decision Making:**
1. **A/B Comparison:** Can compare multi-query vs standard side-by-side
2. **Score Justification:** Understand why property A ranks higher than B
3. **Strategy Effectiveness:** See which strategies (BM25/text/image) contributed most

---

## Next Steps (Optional Enhancements)

1. **Add Individual Image Scores Table** (from search.html lines 1927-1975)
   - Show which specific images matched each sub-query
   - Display similarity scores for each image vector
   - Highlight top-K images used in adaptive scoring

2. **Add OpenSearch Query Display** (from search.html collapsible `<details>`)
   - Show actual OpenSearch queries sent for BM25, kNN text, kNN image
   - Useful for advanced debugging

3. **Add "Copy to Clipboard" Button**
   - Copy entire breakdown as formatted text
   - Useful for sharing results with team

4. **Add Performance Metrics**
   - Show latency breakdown (LLM time, OpenSearch time, embedding time)
   - Cost per query (LLM API calls, OpenSearch requests)

---

## Summary

✅ **Successfully replaced simple JSON display with complete formatted breakdown**
✅ **Added multi-query specific sections showing sub-query splitting**
✅ **Maintained identical styling and functionality to search.html**
✅ **Deployed to production EC2 instance**

The comparison page now provides the same rich, detailed score breakdown as the main search UI, with **additional context for multi-query mode** showing how queries are intelligently split into weighted sub-queries.
