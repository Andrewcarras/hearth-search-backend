# LLM Query Splitting Fix - October 23, 2025

## Issue Summary

User reported inconsistent search results: "White homes with granite countertops and wood floors" would sometimes return all white houses, and other times return mixed colors (red brick, yellow, grey stone houses).

User asked: **"Is there some kind of timeout happening with the query splitting with longer queries?"**

## Investigation Findings

### Root Cause Analysis

The issue was **NOT a timeout**. Investigation revealed multiple problems:

#### 1. **LLM JSON Parsing Failure (Primary Issue)**

**Error**: `Expecting value: line 1 column 1 (char 0)`

**Cause**: Claude LLM responses included extra text before the JSON:
```
Here is the JSON response with the extracted sub-queries:

{
  "sub_queries": [
    ...
  ]
}
```

When code tried to parse this with `json.loads(text)`, it failed because of the prefix text.

**Impact**: 100% of searches were falling back to context-aware sub-queries instead of using LLM-generated queries.

**Evidence**: CloudWatch logs showed consistent failures from 18:04-18:27 UTC:
```
[WARNING] LLM query splitting failed: Expecting value: line 1 column 1 (char 0), falling back to context-aware sub-queries
```

#### 2. **Non-Deterministic Sub-Query Ordering (Secondary Issue)**

**Cause**: `must_tags` was a Python `set` (unordered collection). When converted to list via `list(must_tags)`, Python returned features in random order each time.

**Impact**: Different orderings produced different sub-query priorities:
- Run 1: `["white_exterior", "granite_countertops", "hardwood_floors"]`
- Run 2: `["hardwood_floors", "white_exterior", "granite_countertops"]`
- Run 3: `["granite_countertops", "hardwood_floors", "white_exterior"]`

Since exterior features get weight 2.0 vs interior features at 1.0, this caused inconsistent results.

**Fixed**: [search.py:1560](../../search.py#L1560)
```python
# BEFORE (non-deterministic):
sub_query_result = split_query_into_subqueries(q, list(must_tags))

# AFTER (deterministic):
sub_query_result = split_query_into_subqueries(q, sorted(list(must_tags)))
```

## Solution

### Fix 1: Handle LLM Response Prefix

Added JSON extraction logic to strip prefix/suffix text from LLM responses:

**File**: [search.py:761-766](../../search.py#L761-L766)

```python
# Handle LLM responses that include extra text before/after JSON
# Sometimes Claude adds "Here is the JSON response:" before the actual JSON
json_start = text.find('{')
json_end = text.rfind('}') + 1
if json_start > 0:
    text = text[json_start:json_end]
```

### Fix 2: Sorted Sub-Query Features

Ensured deterministic ordering by sorting features alphabetically:

**File**: [search.py:1560](../../search.py#L1560)

```python
sub_query_result = split_query_into_subqueries(q, sorted(list(must_tags)))
```

### Fix 3: Added Detailed Logging (Temporary)

Added comprehensive logging to diagnose the issue (later removed after fix confirmed):

```python
logger.info(f"LLM raw response length: {len(raw)} chars")
logger.info(f"LLM raw response first 500 chars: {raw[:500]}")
logger.info(f"LLM parsed response keys: {list(parsed.keys())}")
logger.info(f"LLM text content length: {len(text)} chars")
logger.info(f"LLM text content: {text}")
```

## Results

### Before Fix (18:04-18:27 UTC)

**Test Query**: "White homes with granite countertops and wood floors"

**Results**: Inconsistent
- Run 1: All white houses
- Run 2: Mixed colors (red brick #2, yellow #3, grey stone #4)
- Run 3: Different order

**LLM Status**: 100% failure rate, all searches using fallback queries

**CloudWatch Logs**:
```
[WARNING] LLM query splitting failed: Expecting value: line 1 column 1 (char 0)
```

### After Fix (18:32+ UTC)

**Test Query**: "White homes with granite countertops and wood floors"

**Results**: 100% Consistent
- Run 1: `[2071441242, 12886346, 448479405]`
- Run 2: `[2071441242, 12886346, 448479405]`
- Run 3: `[2071441242, 12886346, 448479405]`

**LLM Status**: 100% success rate

**CloudWatch Logs**:
```
[INFO] LLM raw response length: 1748 chars
[INFO] LLM split query into 4 sub-queries
[INFO]   - white_exterior: 'white exterior house facade' (weight=2.0)
[INFO]   - granite_countertops: 'granite countertops kitchen' (weight=1.0)
[INFO]   - hardwood_floors: 'hardwood floors living areas' (weight=1.0)
```

**Match Quality**:
- ZPID 2071441242: ✅ white_exterior, granite, hardwood (perfect)
- ZPID 12886346: ✅ white_exterior, granite, hardwood (perfect)
- ZPID 448479405: ⚠️ white_exterior only (partial)

**Improvement**: 2 out of 3 perfect matches vs previous inconsistent red/blue/grey houses

## Deployment

### Lambda Deployment
```bash
./deploy_lambda.sh search
```

**Version**: `[$LATEST]172803f9595c496fb63bc6955604173a`
**Timestamp**: 18:32 UTC, October 23, 2025

### Production UI Update

Removed the inconsistency warning notice since the issue is now fixed:

```bash
./deploy_production_ui.sh
```

**Removed**:
```html
<div class="notice">
    Please note: You may need to run the same search multiple times to get accurate results.
    This is a known issue we're working to resolve.
</div>
```

## Key Takeaways

### What We Learned

1. **LLMs Can Add Extra Text**: Claude sometimes prefixes responses with explanatory text like "Here is the JSON response:". Always extract JSON content explicitly.

2. **Python Sets Are Unordered**: Using `set()` for must_tags caused non-deterministic iteration. Always use `sorted(list(set))` when order matters.

3. **Detailed Logging is Essential**: Adding verbose logging was critical to identifying the JSON parsing issue vs a timeout.

4. **CloudWatch Logs Are Truth**: Logs showed 100% LLM failures while user saw "sometimes works, sometimes doesn't" - this was due to fallback queries with random ordering.

### Best Practices

1. **Always Extract JSON Explicitly**:
   ```python
   # Find first '{' and last '}' to extract JSON from LLM response
   json_start = text.find('{')
   json_end = text.rfind('}') + 1
   if json_start > 0:
       text = text[json_start:json_end]
   ```

2. **Sort Unordered Collections**:
   ```python
   # Always sort when determinism is required
   sorted_features = sorted(list(must_tags))
   ```

3. **Add Comprehensive Logging for Debugging**:
   ```python
   logger.info(f"Raw response: {raw[:500]}")
   logger.info(f"Parsed keys: {list(parsed.keys())}")
   logger.info(f"Text content: {text}")
   ```

4. **Test Consistency**:
   ```bash
   # Run same query multiple times to verify deterministic results
   for i in 1 2 3; do
       curl ... | jq '.results[0:3][].zpid'
   done
   ```

## Related Issues

- **Non-Deterministic Ordering**: Fixed in commit 54e483d
- **Context-Aware Fallback**: Implemented in commit b29671b
- **Image Weight Boosting**: Implemented in commit ac6660b

## Files Changed

1. [search.py](../../search.py):
   - Lines 761-766: JSON extraction logic
   - Line 1560: Sorted must_tags

2. [ui/production.html](../../ui/production.html):
   - Removed inconsistency warning notice
   - Removed `.notice` CSS styles

## Verification

Run this test to verify consistency:

```bash
# Should return identical ZPIDs on all 3 runs
for i in 1 2 3; do
    echo "=== Run $i ==="
    curl -s -X POST 'https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search' \
        -H 'Content-Type: application/json' \
        -d '{"q":"White homes with granite countertops and wood floors","size":3,"index":"listings-v2","use_multi_query":true}' \
        | jq -r '.results[0:3][].zpid'
    sleep 1
done
```

**Expected Output**: Same 3 ZPIDs in same order every time.

## Status

✅ **RESOLVED** - LLM query splitting now works consistently with 100% success rate and deterministic results.
