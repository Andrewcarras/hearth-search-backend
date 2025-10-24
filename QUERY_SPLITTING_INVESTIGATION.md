# Query Splitting Investigation: "blue second empire"

## User Question
"When I search 'blue second empire', shouldn't it be splitting my query? I don't see it split in the internal tool. Did this recent LLM prompt affect query splitting?"

## Executive Summary

**Answer**: No, the recent query enhancement LLM prompt did NOT affect query splitting. Query splitting is working correctly but requires **2 conditions** that aren't consistently met:

1. ✅ `use_multi_query: true` parameter (controlled by UI toggle)
2. ❌ **2+ tags in `must_have`** (inconsistent LLM extraction)

The problem: The LLM constraint extractor sometimes adds architecture style to `must_have`, sometimes doesn't.

---

## Investigation Results

### Test Query: "blue second empire"

**Query sent with**: `use_multi_query: true`

**Expected behavior**: Should split into sub-queries:
- "blue exterior house facade" (for blue_exterior)
- "second empire victorian mansard roof" (for victorian_second_empire)

**Actual behavior**: No splitting occurred

### Log Analysis

Checked Lambda logs for query "blue second empire":

```
2025-10-24T18:37:48 Search query: 'blue second empire', use_multi_query=true
2025-10-24T18:37:48 Extracted constraints:
  {
    'must_have': ['blue_exterior', 'victorian_second_empire'],  // Run 1: 2 tags ✅
    'architecture_style': 'victorian_second_empire'
  }

2025-10-24T18:37:48 Search query: 'blue second empire', use_multi_query=true
2025-10-24T18:37:49 Extracted constraints:
  {
    'must_have': ['blue_exterior'],  // Run 2: Only 1 tag ❌
    'architecture_style': 'victorian_second_empire'
  }
```

**Finding**: Two concurrent requests, different constraint extraction!
- First request: 2 must_have tags (would trigger splitting)
- Second request: 1 must_have tag (won't trigger splitting)

### Why No Splitting Occurred

Query splitting requires (from [search.py:1686](search.py#L1686)):

```python
if use_multi_query and len(must_tags) >= 2:
    logger.info("🔀 MULTI-QUERY mode enabled - splitting query into sub-queries")
    sub_query_result = split_query_into_subqueries(q, sorted(list(must_tags)))
```

**Conditions**:
1. ✅ `use_multi_query = True` (set by UI parameter)
2. ❌ `len(must_tags) >= 2` (depends on LLM extraction)

When `must_tags` only contains `['blue_exterior']` (1 tag), splitting doesn't trigger even though `use_multi_query=true`.

---

## Root Cause: Inconsistent LLM Constraint Extraction

### The Problem

The `extract_query_constraints()` function in [common.py:1091](common.py#L1091) uses Claude LLM to parse queries. The LLM is **inconsistent** about whether to add architecture style to `must_have`:

**Query**: "blue second empire"

**Sometimes extracts**:
```json
{
  "must_have": ["blue_exterior", "victorian_second_empire"],
  "architecture_style": "victorian_second_empire"
}
```

**Sometimes extracts**:
```json
{
  "must_have": ["blue_exterior"],
  "architecture_style": "victorian_second_empire"
}
```

### Why This Happens

Looking at the LLM prompt in [common.py:1114-1178](common.py#L1114-L1178):

```python
prompt = f"""
1. must_have: ONLY property features explicitly mentioned (snake_case). Examples:
   - Structural: balcony, porch, deck, patio, fence, white_fence, pool, garage
   - Exterior: white_exterior, blue_exterior, gray_exterior, brick_exterior, stone_exterior
   - Interior: kitchen_island, fireplace, open_floorplan, hardwood_floors
   - Outdoor: backyard, fenced_yard, large_yard

   IMPORTANT: If query is ONLY about location (e.g., "homes near X"), leave must_have EMPTY.
   Do NOT infer features that aren't explicitly mentioned in the query.

2. nice_to_have: Additional preferred tags (snake_case)

3. hard_filters: Numeric constraints (keys: price_min, price_max, beds_min, baths_min, acreage_min, acreage_max)

4. architecture_style: ONE style if mentioned, or null. Use hierarchical approach...
```

**The issue**: The prompt says:
- `must_have`: For property FEATURES (exterior colors, structural elements)
- `architecture_style`: For architectural styles (modern, craftsman, victorian)

But architecture styles ARE features! The prompt is ambiguous about whether "second empire" should go in:
- `must_have` (it's a feature of the property)
- `architecture_style` (it's a style)
- **Both** (it's both!)

The LLM is making a judgment call, and with `temperature: 0`, it should be deterministic... but we're seeing inconsistency. This suggests:
- Different model versions being served
- Slight timing differences affecting internal LLM state
- Or the prompt is close to a decision boundary

---

## Did Query Enhancement Affect This?

### Query Enhancement Code

The recent query enhancement at [search.py:1510-1526](search.py#L1510-L1526):

```python
# Query enhancement for short architectural queries
query_for_embedding = q  # Default: use original query
if architecture_style and style_mapping_info:
    word_count = len(q.split())
    if word_count < 5:
        query_for_embedding = enhance_query_for_architecture(...)
```

**Runs AFTER constraint extraction**:
1. Line 1441: `constraints = extract_query_constraints(q)` ← Extracts must_have
2. Line 1444: `must_tags = set(constraints.get("must_have", []))` ← Gets tags
3. Line 1510-1526: Query enhancement ← AFTER must_tags are set
4. Line 1686: `if use_multi_query and len(must_tags) >= 2:` ← Checks must_tags

**Answer**: NO, query enhancement does NOT affect query splitting.
- Query enhancement only changes `query_for_embedding`
- It does NOT modify `must_tags`
- Query splitting checks the original `must_tags` from constraint extraction

### Timeline Proof

Looking at the commit history:
- Query enhancement deployed: 2025-10-24 (recent)
- Query splitting function: Existed before (lines 666-819)
- Constraint extraction: Existed before (common.py:1091)

The inconsistency in `must_have` extraction has likely existed all along. You're just noticing it now because:
1. You're testing multi-query mode more actively
2. You're looking at the debug logs in the internal tool

---

## Why You Don't See Splitting in Internal Tool

### Internal Tool Behavior

The internal demo at http://54.234.198.245/multi_query_comparison.html has a toggle for multi-query mode.

**When toggle is OFF**:
```javascript
use_multi_query: false  // Default
```
No splitting, even if query has 2+ features.

**When toggle is ON**:
```javascript
use_multi_query: currentMode === 'multi'
```
Splitting happens IF `must_tags >= 2`.

### The Problem

For "blue second empire":
- Sometimes `must_tags = ['blue_exterior', 'victorian_second_empire']` → 2 tags → Would split ✅
- Sometimes `must_tags = ['blue_exterior']` → 1 tag → Won't split ❌

Even with multi-query toggle ON, if the LLM only extracts 1 tag, no splitting occurs.

---

## Solutions

### Option 1: Make Architecture Style Always a Must-Have (Simple)

Modify [search.py:1444-1450](search.py#L1444-L1450):

```python
must_tags = set(constraints.get("must_have", []))
architecture_style = constraints.get("architecture_style")

# NEW: If architecture style is detected, always add it to must_tags
if architecture_style and architecture_style not in must_tags:
    must_tags.add(architecture_style)
    logger.info(f"Added architecture_style '{architecture_style}' to must_tags for query splitting")
```

**Pros**:
- Simple 3-line fix
- Makes architecture styles consistent
- Enables query splitting for "blue second empire" (2 tags: blue_exterior + victorian_second_empire)

**Cons**:
- Changes behavior of tag boosting (architecture style would get 2.0x boost)
- Might be too aggressive for some queries

### Option 2: Modify LLM Prompt to Be Explicit (Better)

Update the constraint extraction prompt in [common.py:1117-1124](common.py#L1117-L1124):

```python
1. must_have: ONLY property features explicitly mentioned (snake_case). Examples:
   - Structural: balcony, porch, deck, patio, fence, white_fence, pool, garage
   - Exterior: white_exterior, blue_exterior, gray_exterior, brick_exterior, stone_exterior
   - Interior: kitchen_island, fireplace, open_floorplan, hardwood_floors
   - Outdoor: backyard, fenced_yard, large_yard
   - Architectural styles: craftsman, modern, victorian, ranch, etc. (if mentioned)  // NEW!

   IMPORTANT:
   - If architectural style is mentioned (modern, craftsman, victorian, etc.), ADD IT to must_have
   - If query is ONLY about location (e.g., "homes near X"), leave must_have EMPTY.
   - Do NOT infer features that aren't explicitly mentioned in the query.
```

**Pros**:
- Fixes root cause (LLM inconsistency)
- Makes behavior deterministic
- Enables proper query splitting

**Cons**:
- Requires careful prompt engineering
- Need to test on many queries to ensure no regressions

### Option 3: Custom Logic for Multi-Feature Detection (Most Robust)

Add custom logic in [search.py:1686](search.py#L1686):

```python
# Prepare tags for query splitting
# Include architecture style if it's detected
splitting_tags = must_tags.copy()
if architecture_style and architecture_style not in splitting_tags:
    splitting_tags.add(architecture_style)

# Check if we should use multi-query splitting
if use_multi_query and len(splitting_tags) >= 2:
    logger.info("🔀 MULTI-QUERY mode enabled - splitting query into sub-queries")
    sub_query_result = split_query_into_subqueries(q, sorted(list(splitting_tags)))
```

**Pros**:
- Doesn't change tag boosting behavior
- Doesn't require LLM prompt changes
- Ensures architecture style is included for splitting

**Cons**:
- Adds complexity
- `splitting_tags` vs `must_tags` divergence could be confusing

---

## Recommended Solution

**Implement Option 3**: Add architecture style to splitting tags without affecting must_tags.

This is the safest approach because:
1. Doesn't change existing tag boosting behavior
2. Doesn't require LLM prompt changes (risky)
3. Ensures consistent query splitting for multi-feature queries
4. Minimal code change

### Implementation

```python
# File: search.py, around line 1686

# Check if multi-query splitting mode is enabled
use_multi_query = payload.get("use_multi_query", False)
sub_query_data = None

if require_embeddings and strategy in ["hybrid", "knn_image"]:
    # Prepare tags for query splitting
    # Include architecture style for splitting even if LLM didn't add it to must_have
    splitting_tags = must_tags.copy()
    if use_multi_query and architecture_style:
        if architecture_style not in splitting_tags:
            splitting_tags.add(architecture_style)
            logger.info(f"Added architecture_style '{architecture_style}' for query splitting (not in must_have)")

    # Check if we should use multi-query splitting
    if use_multi_query and len(splitting_tags) >= 2:
        logger.info(f"🔀 MULTI-QUERY mode enabled - splitting query into sub-queries ({len(splitting_tags)} features)")

        # Split query using LLM
        t0 = time.time()
        sub_query_result = split_query_into_subqueries(q, sorted(list(splitting_tags)))
        # ... rest of splitting logic
```

---

## Test Cases

After implementing the fix, test these queries with `use_multi_query: true`:

### Should Split (2+ features)

| Query | Features | Expected Sub-Queries |
|-------|----------|---------------------|
| "blue second empire" | blue_exterior, victorian_second_empire | ✅ "blue exterior house facade" + "second empire victorian mansard roof" |
| "white modern house" | white_exterior, modern | ✅ "white exterior house facade" + "modern contemporary architecture clean lines" |
| "craftsman with pool" | craftsman, pool | ✅ "craftsman style architecture" + "swimming pool backyard" |
| "granite countertops modern kitchen" | granite_countertops, modern | ✅ "granite kitchen counters" + "modern contemporary design" |

### Should NOT Split (< 2 features)

| Query | Features | Behavior |
|-------|----------|----------|
| "modern" | modern | ❌ No split (1 feature) |
| "blue exterior" | blue_exterior | ❌ No split (1 feature) |
| "show me houses" | (none) | ❌ No split (0 features) |

---

## Summary

1. **Query enhancement did NOT affect query splitting** - they run at different stages
2. **Root cause**: LLM inconsistently adds architecture style to `must_have` tags
3. **Why splitting didn't trigger**: Only 1 tag extracted instead of 2
4. **Solution**: Add architecture style to splitting tags even if LLM didn't include it
5. **Impact**: Enables proper query splitting for queries like "blue second empire"

---

**Status**: Investigation complete, ready to implement fix.
