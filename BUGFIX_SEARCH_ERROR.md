# Bug Fix: Search "Load Failed" Error

## Issue
When searching on the new UI (http://54.227.66.148), users encountered:
```
Error: load failed
```

## Root Cause
In `search.py`, the `enrich_with_nearby_places()` function had a bug on line 130:

```python
geo = listing.get("geo", {})  # This returns None for some listings
latitude = listing.get("latitude") or geo.get("lat")  # ❌ Crashes when geo is None
```

When `listing.get("geo")` returned `None` (instead of a dict), calling `.get("lat")` on `None` caused:
```
AttributeError: 'NoneType' object has no attribute 'get'
```

## Fix Applied
Changed line 130 in `search.py`:
```python
# Before
geo = listing.get("geo", {})

# After
geo = listing.get("geo") or {}
```

This ensures `geo` is always a dict, even when the listing has `geo: null`.

## Resolution
- ✅ Fixed `search.py` line 130
- ✅ Updated hearth-search Lambda function
- ✅ Tested search API - working perfectly
- ✅ UI search now functional

## Test Results
```bash
# Test 1: Pool search
curl -X POST 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search' \
  -H 'Content-Type: application/json' \
  -d '{"q":"pool","size":2}'

# Result: ✅ 2 properties returned

# Test 2: Granite countertops search
curl -X POST 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search' \
  -H 'Content-Type: application/json' \
  -d '{"q":"granite countertops","size":3}'

# Result: ✅ 3 properties returned
```

## Lessons Learned
When using `.get()` with a default value on potentially null fields, use `or {}` pattern instead of default parameter:

```python
# ❌ Bad - default parameter doesn't help if value is explicitly None
dict.get("field", {})

# ✅ Good - handles both missing and None
dict.get("field") or {}
```

## Files Modified
- `/tmp/lambda_package/search.py` (line 130)
- Lambda function: `hearth-search` (redeployed)

## Status
✅ **RESOLVED** - Search functionality fully operational on http://54.227.66.148
