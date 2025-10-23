# Analytics Dashboard - CORS Duplicate Headers Fix

**Date:** October 22, 2025
**Issue:** Multiple `Access-Control-Allow-Origin` headers causing CORS error
**Status:** ✅ Fixed

---

## Problem

The analytics dashboard was still failing with a CORS error:
```
Access-Control-Allow-Origin cannot contain more than one origin.
Fetch API cannot load https://...lambda-url.us-east-1.on.aws/?limit=100
```

**Root Cause:**
Both the Lambda function URL configuration AND the Lambda handler code were adding CORS headers, resulting in duplicate `Access-Control-Allow-Origin` headers in the response.

**Evidence:**
```bash
$ curl -X OPTIONS "https://...lambda-url.us-east-1.on.aws/" -H "Origin: http://..." -I

access-control-allow-origin: *
access-control-allow-origin: http://ec2-54-234-198-245.compute-1.amazonaws.com
# ^^^ TWO HEADERS! ^^^
```

---

## Solution

**Removed CORS headers from Lambda handler code** - Let the function URL configuration handle all CORS automatically.

### Changes to `analytics_proxy.py`

**Before:**
```python
# CORS headers
cors_headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Content-Type': 'application/json'
}

return {
    'statusCode': 200,
    'headers': cors_headers,
    'body': json.dumps(...)
}
```

**After:**
```python
# Only set Content-Type header (CORS handled by function URL config)
headers = {
    'Content-Type': 'application/json'
}

return {
    'statusCode': 200,
    'headers': headers,
    'body': json.dumps(...)
}
```

**Key Changes:**
- Removed `Access-Control-Allow-Origin` from handler
- Removed `Access-Control-Allow-Headers` from handler
- Removed `Access-Control-Allow-Methods` from handler
- Kept only `Content-Type` header
- Function URL CORS config automatically adds appropriate CORS headers

---

## Deployment

```bash
# Update Lambda code
zip -j analytics_proxy.zip analytics_proxy.py
aws lambda update-function-code \
  --function-name hearth-analytics-proxy \
  --zip-file fileb://analytics_proxy.zip

# Wait for update
aws lambda wait function-updated --function-name hearth-analytics-proxy
```

---

## Verification

### OPTIONS Preflight (Correct - Single Origin)
```bash
$ curl -X OPTIONS "https://...lambda-url.us-east-1.on.aws/" \
  -H "Origin: http://ec2-54-234-198-245.compute-1.amazonaws.com" -I

Access-Control-Allow-Origin: http://ec2-54-234-198-245.compute-1.amazonaws.com
# ✅ Only ONE header now!
```

### GET Request (Correct - Single Origin)
```bash
$ curl "https://...lambda-url.us-east-1.on.aws/?limit=1" \
  -H "Origin: http://ec2-54-234-198-245.compute-1.amazonaws.com" -I

Access-Control-Allow-Origin: http://ec2-54-234-198-245.compute-1.amazonaws.com
Vary: Origin
# ✅ Correct CORS headers
```

### Data Response (Correct)
```bash
$ curl "https://...lambda-url.us-east-1.on.aws/?limit=1" | jq '.ok, .count'
true
1
# ✅ Returns valid data
```

---

## How Lambda Function URL CORS Works

When you configure CORS on a Lambda function URL, AWS automatically:

1. **Handles OPTIONS preflight requests**
   - Returns 200 with appropriate CORS headers
   - No need to handle OPTIONS in your code

2. **Adds CORS headers to all responses**
   - `Access-Control-Allow-Origin` (based on Origin header + your config)
   - `Access-Control-Allow-Methods`
   - `Access-Control-Allow-Headers`
   - `Vary: Origin` (if AllowOrigins is not `["*"]`)

3. **Your handler should NOT add CORS headers**
   - Only return your business logic headers (e.g., Content-Type)
   - Function URL adds CORS headers automatically

---

## Function URL CORS Configuration

Current configuration:
```json
{
  "AllowOrigins": ["*"],
  "AllowMethods": ["GET"],
  "AllowHeaders": ["*"],
  "MaxAge": 86400
}
```

This allows:
- Any origin to access the endpoint
- Only GET requests
- Any headers
- Preflight cache for 24 hours

---

## Files Modified

1. **[analytics_proxy.py](analytics_proxy.py)**
   - Removed CORS headers from all return statements
   - Changed `cors_headers` to `headers` with only `Content-Type`
   - Updated all 7 return statements

---

## Testing Checklist

Dashboard should now work correctly:

- [x] Lambda proxy returns valid data
- [x] CORS headers are correct (single origin)
- [x] OPTIONS preflight succeeds
- [x] GET requests include CORS headers
- [ ] Browser analytics dashboard loads without errors (user to verify)

---

## Summary

✅ **CORS Issue Resolved**

**What Was Wrong:**
- Lambda handler was adding CORS headers manually
- Function URL config was also adding CORS headers
- Result: Duplicate headers causing browser CORS error

**What Was Fixed:**
- Removed all CORS headers from Lambda handler code
- Let function URL configuration handle CORS automatically
- Now only one set of CORS headers in responses

**Result:**
- No more duplicate `Access-Control-Allow-Origin` headers
- Browser should accept responses without CORS errors
- Analytics dashboard should load successfully

**Live URL:** http://ec2-54-234-198-245.compute-1.amazonaws.com/analytics.html

The analytics dashboard is now ready to use!
