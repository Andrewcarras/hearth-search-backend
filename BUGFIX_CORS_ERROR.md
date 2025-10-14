# Bug Fix: CORS Preflight Error (HTTP 500)

## Issue
When searching on the new UI (http://54.227.66.148), browser console showed:
```
[Error] Preflight response is not successful. Status code: 500
[Error] Fetch API cannot load https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search due to access control checks.
Error: load failed
```

## Root Cause
API Gateway's OPTIONS method (CORS preflight) was misconfigured:
- OPTIONS method existed with MOCK integration
- **Missing integration response** for status code 200
- This caused API Gateway to return 500 for all OPTIONS requests
- Browser blocked all POST requests due to failed preflight check

## What is CORS Preflight?
When a browser makes a cross-origin request (UI at one domain calling API at another), it first sends an OPTIONS request to check if the request is allowed. This is called a "preflight" check.

```
Browser                API Gateway
   |                       |
   |---OPTIONS /search---->|  (Preflight check)
   |<----200 OK + CORS-----|  (Must return 200 with CORS headers)
   |                       |
   |---POST /search------->|  (Actual request - only if preflight succeeds)
   |<----200 + results-----|
```

If OPTIONS returns anything other than 200, the browser blocks the actual POST request.

## Fixes Applied

### 1. Fixed Lambda Router (search.py)
Added OPTIONS handling in `lambda_handler()` (line 840-845):

```python
# Handle OPTIONS preflight requests (CORS)
if method == 'OPTIONS':
    return {
        "statusCode": 200,
        "headers": cors_headers,
        "body": ""
    }
```

### 2. Fixed API Gateway OPTIONS Method
Recreated OPTIONS method with proper MOCK integration:

```bash
# Delete broken OPTIONS
aws apigateway delete-method --rest-api-id mqgsb4xb2g --resource-id okrs2n --http-method OPTIONS

# Create new OPTIONS with MOCK integration
aws apigateway put-method --rest-api-id mqgsb4xb2g --resource-id okrs2n --http-method OPTIONS --authorization-type NONE

# Configure MOCK integration
aws apigateway put-integration --rest-api-id mqgsb4xb2g --resource-id okrs2n --http-method OPTIONS --type MOCK --request-templates '{"application/json":"{\"statusCode\":200}"}'

# Add method response
aws apigateway put-method-response --rest-api-id mqgsb4xb2g --resource-id okrs2n --http-method OPTIONS --status-code 200 --response-parameters '{...CORS headers...}'

# Add integration response (THIS WAS MISSING!)
aws apigateway put-integration-response --rest-api-id mqgsb4xb2g --resource-id okrs2n --http-method OPTIONS --status-code 200 --response-templates '{"application/json":""}' --response-parameters '{
  "method.response.header.Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
  "method.response.header.Access-Control-Allow-Methods": "POST,OPTIONS",
  "method.response.header.Access-Control-Allow-Origin": "*"
}'

# Deploy changes
aws apigateway create-deployment --rest-api-id mqgsb4xb2g --stage-name prod
```

### 3. Fixed geo.get() Bug (from earlier)
Also fixed line 130 in `search.py`:
```python
geo = listing.get("geo") or {}  # Prevents NoneType error
```

## Test Results

### OPTIONS Preflight (CORS Check)
```bash
curl -X OPTIONS 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search' \
  -H 'Origin: http://54.227.66.148' \
  -H 'Access-Control-Request-Method: POST'

# Response:
HTTP/2 200 ✅
access-control-allow-origin: *
access-control-allow-methods: POST,OPTIONS
access-control-allow-headers: Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token
```

### POST Request (Actual Search)
```bash
curl -X POST 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search' \
  -H 'Content-Type: application/json' \
  -H 'Origin: http://54.227.66.148' \
  -d '{"q":"pool","size":2}'

# Response:
HTTP/2 200 ✅
access-control-allow-origin: *
access-control-allow-methods: GET, POST, PATCH, DELETE, OPTIONS
{"ok": true, "results": [...2 properties...]}
```

## Verification
1. ✅ OPTIONS returns 200 with CORS headers
2. ✅ POST returns 200 with results and CORS headers
3. ✅ Browser can now make cross-origin requests
4. ✅ UI search works without errors

## Files Modified
- `/tmp/lambda_package/search.py` (lines 130, 840-845)
- Lambda function: `hearth-search` (redeployed)
- API Gateway: OPTIONS method for /search endpoint
- API Gateway: Deployed to prod stage

## Lessons Learned

### API Gateway OPTIONS Configuration Checklist
For OPTIONS to work, you need ALL of these:

1. ✅ PUT method (OPTIONS)
2. ✅ PUT integration (MOCK with statusCode:200)
3. ✅ PUT method-response (status 200 with CORS header parameters)
4. ✅ PUT integration-response (status 200 with CORS header values) ← **Often forgotten!**
5. ✅ CREATE deployment (push changes to stage)

Missing the integration-response causes 500 errors!

### CORS Headers Needed
```javascript
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST,OPTIONS
Access-Control-Allow-Headers: Content-Type
```

## Status
✅ **RESOLVED** - All CORS issues fixed

**UI now fully functional:** http://54.227.66.148
- ✅ Search works
- ✅ Admin panel works
- ✅ No browser console errors
