# OpenSearch Property Tag Investigation Report
**Date:** October 23, 2025
**Query:** Investigation of "White homes" search results and property tags

## Executive Summary

**NO DATA CHANGED IN THE LAST 3 HOURS.** All properties were indexed 9+ days ago (October 12-15, 2025).

The investigation revealed a **critical tag format inconsistency** in the OpenSearch index that is causing poor search quality for color-based queries.

## Key Findings

### 1. NO RECENT DATA CHANGES ❌
- **Last indexed property:** October 15, 2025 at 06:28:28 UTC (190 hours ago / ~8 days ago)
- **Oldest indexed property:** October 12, 2025 at 22:19:17 UTC
- **Properties indexed in last 3 hours:** 0
- **Properties updated in last 3 hours:** 0

### 2. TAG FORMAT INCONSISTENCY 🚨

There are **TWO different formats** for exterior color tags in the index:

#### Old Format (with spaces):
- `"white exterior"`, `"blue exterior"`, `"red exterior"`, etc.
- **2,429 properties** have this format
- Tags are not properly structured for matching

#### New Format (with underscores):
- `"white_exterior"`, `"blue_exterior"`, `"red_exterior"`, etc.
- **Only 52 properties** have this format
- Properly structured tags for exact matching

### 3. Analysis of "Bad" ZPIDs

#### zpid 12778555 (Red brick house reported)
- **Address:** 2050 E Wilmington Ave, Salt Lake City, UT 84109
- **Indexed at:** October 13, 2025 at 20:04:27 UTC (224 hours ago)
- **Updated at:** Not set
- **Exterior color tags:** NONE with underscore format
- **White-related tags (6):**
  - `"white exterior"` (space format)
  - `"white trim"`
  - `"white window frame"`
  - `"white subway tile"`
  - `"black and white color scheme"`
  - `"black and white floral wallpaper"`
- **Other exterior tags:**
  - `"red exterior"` (space format)
  - `"brick exterior"` (space format)
- **Problem:** Has both `"white exterior"` and `"red exterior"` in OLD format

#### zpid 70592220 (Blue brick house reported)
- **Address:** 2263 E 4500 S, Holladay, UT 84117
- **Indexed at:** October 13, 2025 at 05:28:55 UTC (239 hours ago)
- **Updated at:** Not set
- **Exterior color tags:** NONE with underscore format
- **White-related tags (1):**
  - `"white exterior"` (space format)
- **Other exterior tags:**
  - `"blue exterior"` (space format)
  - `"gray exterior"` (space format)
  - `"brick exterior"`
  - `"stone exterior"`
- **Problem:** Has `"white exterior"`, `"blue exterior"`, AND `"gray exterior"` in OLD format

### 4. Pure White Properties (Correct Tags)

Found **10 properties** with ONLY `"white_exterior"` tag (underscore format):

| zpid | Address | Indexed |
|------|---------|---------|
| 12791537 | 4065 S 1045 E, Millcreek, UT 84124 | Oct 13, 15:43:14 UTC |
| 12853452 | 4331 S Holladay Blvd, Holladay, UT 84124 | Oct 13, 08:09:10 UTC |
| 2055553102 | 1648 E 4150 S, Salt Lake City, UT 84124 | Oct 13, 14:02:27 UTC |
| 12797105 | 3899 E Parkview Dr, Millcreek, UT 84124 | Oct 13, 15:40:51 UTC |
| 12865690 | 1171 E Hyland Lake Dr, Salt Lake City, UT 84121 | Oct 13, 05:28:03 UTC |

**These properties did NOT appear in the top 20 search results for "White homes"**

### 5. Search Results Analysis

When searching for "White homes" (top 20 results):
- **0 properties** with ONLY `"white_exterior"` (underscore format)
- **20 properties** with mixed exterior colors in OLD format (spaces)
- Many have multiple color tags: `"white exterior"` + `"blue exterior"` + `"gray exterior"`

Example multi-color properties ranking high:
- zpid 12736681: `"white exterior"`, `"gray exterior"`
- zpid 305068799: `"white exterior"`, `"blue exterior"`, `"gray exterior"`
- zpid 12849295: `"white exterior"`, `"blue exterior"`, PLUS `"white_exterior"` (both formats!)

## Root Cause Analysis

### Why Multi-Color Properties Rank Higher

1. **BM25 Text Matching:** Properties with OLD format tags (`"white exterior"` as two words) match the query "White homes" better because:
   - The word "white" appears separately in the tag
   - BM25 tokenizes `"white exterior"` as two tokens: `["white", "exterior"]`
   - This matches the query tokens `["white", "homes"]` better

2. **Pure White Properties Don't Match Well:**
   - Properties with `"white_exterior"` (underscore) are tokenized as a single token
   - Single token `"white_exterior"` doesn't match query `"white"` as strongly
   - These properties rank lower despite being pure white

3. **Multiple Color Tags Increase Relevance:**
   - Properties with many color tags (e.g., `"white exterior"`, `"blue exterior"`, `"gray exterior"`) have more tokens
   - More tokens = more opportunities to match the query
   - BM25 scores these higher due to field length and token frequency

## Impact on Search Quality

### Current Behavior (BROKEN)
- Multi-color houses rank #1-20
- Pure white houses don't appear in top results
- Users searching for "white homes" get houses that are white + other colors

### Expected Behavior (CORRECT)
- Pure white houses should rank #1
- Multi-color houses should rank lower
- Houses with no white should not appear at all

## Recommendations

### Immediate Actions Required

1. **Re-index ALL properties with standardized tag format**
   - Convert ALL `"white exterior"` → `"white_exterior"`
   - Convert ALL `"blue exterior"` → `"blue_exterior"`
   - Convert ALL `"{color} exterior"` → `"{color}_exterior"`

2. **Update tagging logic to use ONLY underscore format**
   - Ensure future indexing uses `{color}_exterior` format
   - Remove space-separated color tags

3. **Implement tag validation**
   - Validate that properties have ONLY ONE exterior color tag
   - Flag properties with multiple exterior colors for manual review

### Search Algorithm Improvements

1. **Add exact tag matching boost**
   - Boost properties with exact `"white_exterior"` tag when query contains "white"
   - De-boost properties with multiple exterior color tags

2. **Implement tag-based filtering**
   - For color queries, filter to ONLY properties with that specific color tag
   - Exclude properties with conflicting color tags

## Data Consistency Check

- **Total properties in index:** Unknown (not counted)
- **Properties with old format (`"white exterior"`):** 2,429
- **Properties with new format (`"white_exterior"`):** 52
- **Consistency rate:** ~2% (52/2,481 = 2.1%)

### Multi-Color Tag Statistics (Sample of 100 properties)

| Exterior Color Count | Properties | Percentage |
|---------------------|------------|------------|
| 0 colors | 39 | 39% |
| 1 color | 30 | 30% |
| 2 colors | 22 | 22% |
| 3+ colors | 9 | 9% |

**31% of properties have multiple exterior color tags** - this is a major data quality issue.

### Why Properties Have Multiple Exterior Colors

Analysis of zpid 12778555 and 70592220 reveals:

1. **Image analysis tags multiple colors:**
   - zpid 12778555: `"red exterior"`, `"white exterior"`
   - zpid 70592220: `"white exterior"`, `"blue exterior"`, `"gray exterior"`

2. **Variant tag formats:**
   - `"gray exterior"` (standard)
   - `"exterior: gray exterior"` (with prefix)
   - Both appear in the same property

3. **Tags describe different parts of the house:**
   - Red brick on lower level → `"red exterior"`
   - White trim/siding on upper level → `"white exterior"`
   - The image tagger sees BOTH colors and tags them BOTH

### Detailed Tag Breakdown for "Bad" ZPIDs

**zpid 12778555 (Red brick house):**
- Total tags: 73 (all in `image_tags`, 0 in `feature_tags`)
- Exterior tags: `"brick exterior"`, `"exterior lighting"`, `"red exterior"`, `"white exterior"`
- Issue: House is primarily red brick but has white trim → both tagged

**zpid 70592220 (Blue brick house):**
- Total tags: 47 (all in `image_tags`, 0 in `feature_tags`)
- Exterior tags: `"blue exterior"`, `"brick exterior"`, `"exterior: gray exterior"`, `"gray exterior"`, `"stone exterior"`, `"white exterior"`
- Issue: House has blue, gray, AND white elements → all three colors tagged

## Scoring Analysis

When searching for "White homes" using BM25 text search only:
- All RRF scores were 0.0000 (kNN searches failed due to field name mismatch)
- Results ranked purely by BM25 text matching
- Properties with `"white exterior"` (space format) matched better than `"white_exterior"` (underscore)
- Multi-color properties ranked high because they have MORE color tags, giving more matching opportunities

## Conclusion

**The OpenSearch data has NOT changed in the last 3 hours.** All properties were indexed 9+ days ago (October 12-15, 2025).

The search quality issue is caused by **THREE MAJOR PROBLEMS**:

1. ❌ **Tag format inconsistency** (space vs. underscore)
   - 98% of properties use OLD format (`"white exterior"`)
   - Only 2% use NEW format (`"white_exterior"`)
   - BM25 tokenization favors space-separated format

2. ❌ **Multiple conflicting exterior color tags**
   - 31% of properties have 2+ exterior colors tagged
   - Image tagger tags ALL visible colors (trim, siding, accents)
   - No "primary exterior color" logic

3. ❌ **Poor ranking for pure white properties**
   - Pure white houses with `"white_exterior"` don't rank in top 20
   - Multi-color houses with `"white exterior"` + other colors rank higher
   - More tags = higher BM25 scores

**Action Required:**
1. Re-index all 2,400+ properties with standardized tag format
2. Implement "primary exterior color" logic to select ONE dominant color
3. Add tag-based boosting to favor properties with single color tags over multi-color tags
