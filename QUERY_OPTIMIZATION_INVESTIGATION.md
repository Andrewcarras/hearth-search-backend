# Query Optimization Investigation: LLM-Based Query Enhancement

## Executive Summary

Investigation into using LLM prompt at query time to transform short, ambiguous queries into optimized queries that better leverage our search infrastructure. This is a temporary workaround for the underlying ranking issue where `architecture_style` field isn't being used as a strong ranking signal.

## Problem Statement

### Current Issue
Short queries like "arts and crafts" or "craftsman" return poor results despite:
- 95% of properties having `architecture_style` field populated
- Architectural styles properly classified via vision analysis
- Synonym mappings in place (`"arts and crafts"` → `craftsman`)

### Why Short Queries Fail

**Query**: "arts and crafts" (3 words)
- **BM25 Problem**: Searches raw text fields (`visual_features_text`, `description`)
  - Matches token "crafts" in descriptions like "The home features beautiful crafts..."
  - Does NOT boost on `architecture_style: "craftsman"` field
  - Keyword noise drowns out relevant results

- **Semantic Search Problem**:
  - 3-word embedding lacks context
  - Ambiguous: Could mean art galleries, craft stores, or architectural style
  - Embedding space isn't focused on architecture

**Query**: "Show me arts and crafts style homes" (7 words)
- More context for semantic embedding
- Words "style homes" clarify intent = architectural style
- Better but still not optimal

### Root Cause
The `architecture_style` field exists but isn't being used as a **ranking signal** in our hybrid search:
1. BM25 doesn't boost on `architecture_style` field
2. Field boosting is only on `visual_features_text` (contains "craftsman style" as text)
3. Token mismatch: field stores `craftsman`, query has `arts and crafts`
4. Even with synonym mapping, BM25 tokenization creates noise

---

## Current Query Processing Pipeline

### Step 1: Constraint Extraction (common.py:1091)
```python
extract_query_constraints(query_text: str) -> Dict
```

**LLM Prompt**: Extracts structured constraints from natural language
- **Input**: "arts and crafts"
- **Output**:
  ```json
  {
    "must_have": [],
    "nice_to_have": [],
    "hard_filters": {},
    "architecture_style": "arts_and_crafts",
    "proximity": null,
    "query_type": "visual_style"
  }
  ```

**Purpose**: Convert natural language to structured filters
**Current Use**: Architecture style is a SOFT SIGNAL (not a hard filter)

### Step 2: Style Mapping (search.py:1366-1386)
```python
from architecture_style_mappings import map_user_style_to_supported
style_mapping = map_user_style_to_supported(architecture_style)
```

**Input**: `architecture_style: "arts_and_crafts"`
**Output**:
```json
{
  "styles": ["craftsman"],
  "method": "synonym",
  "confidence": 1.0
}
```

**Purpose**: Map user terms to our taxonomy
**Current Use**: Logged but not directly used in ranking

### Step 3: Embedding Generation (search.py:1426)
```python
q_vec = embed_text_multimodal(q)  # Uses original query text!
```

**CRITICAL ISSUE**: Embeddings are generated from **ORIGINAL QUERY**, not optimized query!
- Query: "arts and crafts" → embedding lacks architectural context
- Does NOT use style mapping results
- Does NOT expand query with architectural keywords

### Step 4: Search Execution
Three parallel searches using **ORIGINAL QUERY**:
1. **BM25**: Matches "arts and crafts" against all text fields
2. **kNN Text**: Uses generic "arts and crafts" embedding
3. **kNN Image**: Uses same generic embedding for image search

### Step 5: Tag Boosting (search.py:1838-1868)
```python
if must_tags and must_tags.issubset(property_tags):
    boost = 2.0  # 100% match
elif must_tags and len(must_tags & property_tags) >= len(must_tags) * 0.75:
    boost = 1.5  # 75% match
```

**Problem**: `must_tags` is EMPTY for "arts and crafts" query!
- LLM extracted `architecture_style: "arts_and_crafts"`
- But did NOT add to `must_have` tags
- So craftsman homes get NO BOOST

---

## Multi-Query Mode (Currently Disabled)

### Description
The codebase has an existing LLM-based query optimization system at [search.py:666-819](search.py#L666-L819):

```python
def split_query_into_subqueries(query_text: str, must_have_features: List[str]) -> Dict:
```

### How It Works
1. Takes original query + extracted features
2. Uses Claude LLM to create context-specific sub-queries
3. Creates separate embeddings for each sub-query
4. Searches with multiple embeddings and combines scores

### Example
**Input**: "white exterior house with granite countertops"
**Output**:
```json
{
  "sub_queries": [
    {
      "query": "white exterior house facade outside building",
      "feature": "white_exterior",
      "context": "exterior_primary",
      "weight": 2.0
    },
    {
      "query": "granite kitchen countertops counter surfaces",
      "feature": "granite_countertops",
      "context": "interior_secondary",
      "weight": 1.0
    }
  ]
}
```

### Why It's Disabled
- **Default setting**: `use_multi_query: false` in config
- **Purpose**: Solves multi-feature ambiguity ("white" could be exterior OR cabinets)
- **Not designed for**: Short single-feature queries like "arts and crafts"
- **Complexity**: Requires extracted features, multiple embeddings, complex scoring

---

## Proposed Solution: Query Enhancement at Entry Point

### Concept
Add a lightweight LLM prompt BEFORE embedding generation that:
1. Detects short, ambiguous queries (< 5 words, architectural style detected)
2. Enhances query with architectural keywords and context
3. Uses enhanced query for embedding generation
4. Preserves original query for logging/display

### Implementation Location
**File**: [search.py](search.py), in `handler()` function, after constraint extraction
**Line**: Between line 1386 (style mapping) and line 1426 (embedding generation)

### Proposed Flow

```python
# search.py, after line 1386
optimized_query = q  # Default: use original

# If short query with architectural style, enhance it
if len(q.split()) < 5 and architecture_style:
    optimized_query = enhance_query_for_architecture(q, architecture_style, style_mapping)
    logger.info(f"Query enhanced: '{q}' → '{optimized_query}'")

# Use optimized query for embeddings (line 1426)
q_vec = embed_text_multimodal(optimized_query)  # Not q!
```

### Enhancement Function

```python
def enhance_query_for_architecture(
    original_query: str,
    architecture_style: str,
    style_mapping: Dict
) -> str:
    """
    Enhance short architectural queries with context for better search.

    Uses LLM to expand short queries like "arts and crafts" into
    "arts and crafts craftsman style architecture exterior design home"

    Args:
        original_query: User's original query (e.g., "arts and crafts")
        architecture_style: Extracted style (e.g., "arts_and_crafts")
        style_mapping: Mapped styles from our taxonomy (e.g., {"styles": ["craftsman"]})

    Returns:
        Enhanced query string optimized for hybrid search
    """
```

### LLM Prompt Design

```python
prompt = f"""You are optimizing a real estate search query for a hybrid search system that combines:
- BM25 keyword search on property descriptions
- Semantic similarity on text embeddings
- Visual similarity on image embeddings

The user searched for: "{original_query}"

This query is about architectural style: {architecture_style}
Our system maps this to: {style_mapping['styles']}

TASK: Enhance the query to improve search relevance WITHOUT changing user intent.

RULES:
1. Keep original query terms intact
2. Add 3-5 architectural keywords that:
   - Clarify this is about HOME ARCHITECTURE (not art/crafts)
   - Include related architectural terms
   - Add visual descriptors
   - Include synonyms for the style

3. Prioritize keywords that appear in property descriptions:
   - "architecture", "style", "exterior", "design", "home", "house"
   - Architectural era: "historical", "period", "classic"
   - Visual traits: "tapered columns", "exposed beams", "handcrafted details"

4. Target length: 8-12 words total

EXAMPLES:
- "arts and crafts" → "arts and crafts craftsman style architecture handcrafted details home"
- "craftsman" → "craftsman style architecture tapered columns exposed beams exterior"
- "modern" → "modern contemporary architecture clean lines minimalist design home"
- "second empire" → "second empire victorian mansard roof architecture historical exterior"

Enhanced query (keywords only, no explanation):
"""
```

### Example Transformations

| Original Query | Enhanced Query | Rationale |
|---------------|---------------|-----------|
| `"arts and crafts"` | `"arts and crafts craftsman style architecture handcrafted details tapered columns home exterior"` | Adds architectural context, includes craftsman (mapped style), adds visual descriptors |
| `"craftsman"` | `"craftsman style architecture exposed beams tapered columns exterior design home"` | Adds architectural keywords and visual traits of craftsman homes |
| `"modern"` | `"modern contemporary architecture clean lines flat roof large windows minimalist design"` | Adds visual characteristics and related styles |
| `"second empire"` | `"second empire victorian style mansard roof architecture historical period home exterior"` | Adds parent style, key visual feature (mansard roof), architectural context |

### Benefits

1. **Improved Semantic Search**
   - Enhanced query embedding has architectural context
   - Better matches against property embeddings
   - Clarifies intent: architecture, not arts/crafts stores

2. **Better BM25 Keyword Matching**
   - Added keywords likely appear in `visual_features_text`
   - Example: "exposed beams" matches craftsman descriptions
   - "architecture style home" common in property descriptions

3. **Visual Search Enhancement**
   - Visual descriptors improve image embedding matching
   - "tapered columns" helps match craftsman porch photos
   - "clean lines" helps match modern architecture photos

4. **Minimal Latency**
   - Single LLM call (~200ms)
   - Only for short queries (< 5 words)
   - Parallel with other operations (can run during style mapping)

5. **Preserves User Intent**
   - Keeps original query terms
   - Only adds clarifying context
   - Does NOT change fundamental meaning

---

## Alternative Approaches Considered

### 1. ❌ Boost architecture_style field in BM25
**Pros**: Direct solution to root cause
**Cons**:
- Requires OpenSearch index settings change
- Would need reindexing (all 100K+ listings)
- Doesn't help with token mismatch (underscores vs spaces)

### 2. ❌ Add architecture_style as a hard filter
**Pros**: Guaranteed relevance
**Cons**:
- Too restrictive (excludes similar styles)
- Breaks fallback system we just built
- Poor UX: "No results" instead of similar homes

### 3. ❌ Use multi-query mode for all queries
**Pros**: Existing system, well-tested
**Cons**:
- Overkill for single-feature queries
- Multiple embeddings = higher cost + latency
- Designed for multi-feature disambiguation

### 4. ❌ Client-side query expansion
**Pros**: No backend changes
**Cons**:
- Visible to user (confusing UX)
- Can't leverage style mappings
- Breaks analytics (logged query ≠ searched query)

### 5. ✅ LLM Query Enhancement (RECOMMENDED)
**Pros**:
- Lightweight, fast (~200ms)
- Invisible to user
- Leverages existing LLM infrastructure
- Works with current search pipeline
- Temporary workaround until proper field boosting

**Cons**:
- Adds LLM cost ($0.00025 per query)
- Doesn't fix root cause (architecture_style field not boosted)
- Could introduce edge cases if LLM enhances poorly

---

## Implementation Plan

### Phase 1: Prototype (No Code Yet)
1. Design LLM prompt for query enhancement
2. Test prompt manually with example queries:
   - "arts and crafts"
   - "craftsman"
   - "modern"
   - "second empire"
   - "Show me modern homes" (shouldn't enhance - already good)
3. Validate enhanced queries improve results

### Phase 2: Implementation
1. Add `enhance_query_for_architecture()` function
2. Add condition: only enhance short queries (< 5 words) with architecture_style
3. Call between style mapping and embedding generation
4. Log original → enhanced query
5. Deploy to Lambda

### Phase 3: Testing & Validation
1. Test queries in production UI
2. Compare results before/after:
   - "arts and crafts" → should show craftsman homes ranked higher
   - "craftsman" → should show craftsman homes ranked higher
   - "modern" → should show modern homes ranked higher
3. Monitor Lambda logs for enhancement quality
4. Check for any edge cases (queries enhanced poorly)

### Phase 4: Monitoring & Iteration
1. Track success metrics:
   - % queries enhanced
   - Search latency impact (~200ms expected)
   - Result quality (manual spot checks)
2. Iterate on LLM prompt based on edge cases
3. Consider expanding to other query types (colors, materials)

---

## Success Metrics

### Query Coverage
- **Target**: 20-30% of queries enhanced
- **Measure**: Log enhancement rate

### Latency Impact
- **Target**: < 250ms added latency
- **Measure**: Time enhancement function

### Result Quality
- **Test Cases**:
  - "arts and crafts" → craftsman home in top 3
  - "craftsman" → craftsman home in top 3
  - "modern" → modern home in top 3
  - "second empire" → victorian_second_empire in top 3
- **Measure**: Manual testing on demo UI

### Cost Impact
- **Current**: ~$0.002 per search (embedding generation)
- **Additional**: ~$0.00025 per enhanced query (Haiku LLM)
- **Expected**: 20-30% queries enhanced = +$0.00005 per search average
- **Verdict**: Negligible cost increase

---

## Long-Term Solution (Future Work)

### Root Cause Fix: Field Boosting
Eventually, we should properly boost the `architecture_style` field:

1. **Update OpenSearch Index Mapping**:
   ```json
   {
     "architecture_style": {
       "type": "keyword",
       "boost": 3.0  // Strong boost for exact style matches
     }
   }
   ```

2. **Add architecture_style to BM25 Query**:
   ```python
   {
     "multi_match": {
       "query": "craftsman",
       "fields": [
         "description^1.0",
         "visual_features_text^2.0",
         "architecture_style^3.0"  // New!
       ]
     }
   }
   ```

3. **Benefits**:
   - Exact style matches rank highest
   - No LLM enhancement needed
   - Cleaner architecture
   - Better performance

4. **Effort**:
   - 1 day: Update index mapping, modify BM25 query
   - Requires full reindex (can do incremental with alias swap)

---

## Recommendation

**Implement LLM Query Enhancement as temporary workaround:**
- Fast to implement (1-2 hours)
- Immediate improvement for short architectural queries
- Minimal risk (only enhances short queries)
- Low cost impact (~$0.00005 per search)
- Buys time to plan proper field boosting solution

**Then plan proper field boosting:**
- Schedule index mapping update
- Test with copy of production index
- Implement BM25 query changes
- Deploy with alias swap (zero downtime)

---

## Questions for User

1. **Should we proceed with LLM query enhancement?**
   - Implement now as temporary fix?
   - Or wait and do proper field boosting?

2. **Query length threshold**: Enhance queries < 5 words?
   - Or only queries < 3 words?

3. **Should we enhance other query types?**
   - Just architectural styles?
   - Or also colors ("white exterior"), materials ("brick home")?

4. **Monitoring**: How to measure success?
   - Manual testing on demo UI sufficient?
   - Or add analytics tracking?

---

## Appendix: Current Architecture Issues

### Issue 1: Style Field Not Boosted
**File**: [search.py:1496-1541](search.py#L1496-L1541) - BM25 query construction
**Problem**: `architecture_style` field not included in `multi_match` query
**Current Fields**: `description^1.0`, `visual_features_text^2.0`
**Should Include**: `architecture_style^3.0`

### Issue 2: Style Detection But No Tag Boost
**File**: [search.py:1366-1386](search.py#L1366-L1386) - Style mapping
**Problem**: Architecture style detected but not added to `must_tags`
**Result**: Craftsman homes don't get 2.0x tag boost
**Should Do**: Add detected style to `must_tags` for boosting

### Issue 3: Original Query Used for Embeddings
**File**: [search.py:1426](search.py#L1426) - Embedding generation
**Problem**: Uses original query `q`, not enhanced query
**Result**: Short queries produce weak embeddings
**Should Do**: Enhance query before embedding (this proposal!)

### Issue 4: Token Mismatch in visual_features_text
**File**: [upload_listings.py](upload_listings.py) - Where visual_features_text is created
**Problem**: Stores "craftsman_style" with underscores
**Result**: BM25 tokenizes to ["craftsman", "style"], matches noise like "style kitchen"
**Should Do**: Store as "craftsman style" (spaces) OR boost architecture_style field

---

## Status
**Investigation Complete** - Awaiting user decision on implementation approach.
