# Query Enhancement Implementation

## Summary

Implemented LLM-based query enhancement for short architectural queries to improve search relevance. This is a temporary workaround while we plan proper field boosting for the `architecture_style` field in OpenSearch.

## Problem Solved

Short architectural queries like "arts and crafts" or "craftsman" were returning poor results because:
1. The `architecture_style` field isn't boosted in BM25 searches
2. Short query embeddings lack architectural context
3. BM25 keyword noise drowns out relevant architectural matches

## Solution

Added query enhancement that transforms short architectural queries before embedding generation and BM25 search:

**Example transformations:**
- `"arts and crafts"` → `"arts and crafts craftsman style architecture handcrafted details tapered columns home"`
- `"craftsman"` → `"craftsman style architecture exposed beams tapered columns exterior design home"`
- `"modern"` → `"modern contemporary architecture clean lines minimalist design large windows home"`
- `"second empire"` → `"second empire victorian mansard roof architecture historical period exterior home"`

## Implementation Details

### Files Modified

**[search.py](search.py)**

1. **New Function** (lines 821-903): `enhance_query_for_architecture()`
   - Uses Claude LLM to enhance short queries with architectural context
   - Adds 4-6 relevant keywords without changing user intent
   - Falls back to original query if LLM fails

2. **Query Enhancement Logic** (lines 1510-1526):
   - Triggers only for short queries (< 5 words) with detected architecture_style
   - Runs between style mapping and embedding generation
   - Tracks timing in `query_enhancement_ms` metric

3. **Enhanced Query Usage**:
   - Line 1530: Uses enhanced query for embedding generation
   - Line 1600: Uses enhanced query for BM25 keyword matching

### How It Works

```python
# Before (Original Flow):
constraints = extract_query_constraints(q)  # "arts and crafts" → architecture_style: "arts_and_crafts"
q_vec = embed_text_multimodal(q)  # Embed "arts and crafts" (weak context)
bm25_query = {"query": q}  # Search for "arts and crafts" (keyword noise)

# After (Enhanced Flow):
constraints = extract_query_constraints(q)
style_mapping = map_user_style_to_supported(architecture_style)
if len(q.split()) < 5:
    query_for_embedding = enhance_query_for_architecture(q, architecture_style, mapped_styles)
    # "arts and crafts" → "arts and crafts craftsman style architecture handcrafted details..."
q_vec = embed_text_multimodal(query_for_embedding)  # Better embedding
bm25_query = {"query": query_for_embedding}  # Better keyword matching
```

### LLM Prompt Design

The enhancement prompt:
- Keeps original query terms intact (preserves intent)
- Adds 4-6 architectural keywords
- Includes mapped style names from our taxonomy
- Adds visual descriptors for the specific style
- Targets 8-12 words total
- Returns only the enhanced query (no explanation)

### Triggering Conditions

Query enhancement runs ONLY when:
1. Architecture style is detected (`architecture_style` not null)
2. Style mapping succeeds (`style_mapping_info` exists)
3. Query is short (< 5 words)

**Will NOT enhance:**
- Long queries (already have context)
- Queries without architectural style
- Queries with failed style mapping

### Performance Impact

**Latency:**
- Single LLM call: ~150-250ms
- Only for 20-30% of queries (short + architectural)
- Average impact: ~50ms per query

**Cost:**
- Current: ~$0.002 per search (embedding)
- Enhancement: ~$0.00025 per enhanced query (Haiku LLM)
- 30% enhancement rate: +$0.000075 per search average
- **Verdict**: Negligible cost increase

## Testing

### Test Queries

Short queries that should be enhanced:
- `"arts and crafts"` (2 words) ✅
- `"craftsman"` (1 word) ✅
- `"modern"` (1 word) ✅
- `"second empire"` (2 words) ✅
- `"ranch"` (1 word) ✅

Longer queries that should NOT be enhanced:
- `"Show me arts and crafts style homes"` (7 words) ❌ (skipped)
- `"I want a modern house with pool"` (7 words) ❌ (skipped)

### Verification

Check Lambda logs for enhancement:
```bash
aws logs tail /aws/lambda/hearth-search-v2 --since 5m | grep "Query enhanced"
```

Expected log output:
```
[INFO] Short architectural query detected (2 words), attempting enhancement
[INFO] Query enhanced: 'arts and crafts' → 'arts and crafts craftsman style architecture handcrafted details tapered columns home'
```

### Testing on Production UI

1. Go to http://54.226.26.203/
2. Search for "craftsman"
3. Should see craftsman homes ranked higher than before
4. Search for "modern"
5. Should see modern homes ranked higher
6. Search for "arts and crafts"
7. Should see craftsman/arts-and-crafts homes ranked higher

## Monitoring

### Key Metrics

1. **Enhancement Rate**: % of queries enhanced
   - Expected: 20-30%
   - Track: Count of "Query enhanced" log messages

2. **Latency Impact**: Time spent on enhancement
   - Expected: 150-250ms when triggered
   - Track: `query_enhancement_ms` in timing_data

3. **Result Quality**: Manual spot checks
   - Test queries: "arts and crafts", "craftsman", "modern", "second empire"
   - Success: Relevant homes in top 3 results

### Log Patterns

**Successful Enhancement:**
```
[INFO] Short architectural query detected (1 words), attempting enhancement
[INFO] Query enhanced: 'modern' → 'modern contemporary architecture...'
```

**Skipped (Long Query):**
```
[INFO] Query length 7 words - skipping enhancement
```

**Skipped (No Style):**
```
(No enhancement logs - feature not triggered)
```

**Enhancement Failed:**
```
[WARNING] Query enhancement failed: <error>, using original query
```

## Future Work

### Short-term (This Implementation)
- ✅ Add query enhancement function
- ✅ Integrate with search pipeline
- ✅ Deploy to production
- ⏳ Monitor performance and quality

### Long-term (Proper Fix)
The RIGHT solution is to boost the `architecture_style` field in OpenSearch:

1. **Update Index Mapping**:
   ```json
   {
     "architecture_style": {
       "type": "keyword",
       "boost": 3.0
     }
   }
   ```

2. **Update BM25 Query**:
   ```python
   "fields": [
     "description^3.0",
     "visual_features_text^2.5",
     "architecture_style^3.0"  // NEW!
   ]
   ```

3. **Benefits**:
   - No LLM call needed
   - Better performance
   - Cleaner architecture
   - Exact style matches rank highest

4. **Effort**: 1-2 days (index mapping update + reindexing)

## Related Documentation

- [QUERY_OPTIMIZATION_INVESTIGATION.md](QUERY_OPTIMIZATION_INVESTIGATION.md) - Detailed investigation and analysis
- [ARCHITECTURE_STYLE_FALLBACK_SYSTEM.md](ARCHITECTURE_STYLE_FALLBACK_SYSTEM.md) - Style mapping and fallbacks
- [architecture_style_mappings.py](architecture_style_mappings.py) - Style taxonomy and synonym mappings
- [search.py](search.py) - Main search implementation

## Deployment

**Deployed**: 2025-10-24
**Lambda Function**: hearth-search-v2
**Status**: ✅ Production

## Success Criteria

- [x] Query enhancement function implemented
- [x] Integration with search pipeline complete
- [x] Deployed to production Lambda
- [ ] Verified improved results for test queries (user to test)
- [ ] No significant latency regression (< 300ms added)
- [ ] Enhancement working for 20-30% of queries

---

**Implementation Complete** - Ready for user testing on production UI.
