# Admin UI Setup Instructions

## Quick Start

### Option 1: Open Locally
1. Open `index.html` in your browser:
   ```bash
   open admin_ui/index.html
   # or
   cd admin_ui && python3 -m http.server 8000
   # Then visit http://localhost:8000
   ```

### Option 2: Deploy to S3
```bash
# Upload to S3 for hosted access
aws s3 cp admin_ui/index.html s3://demo-hearth-data/admin/index.html --acl public-read
# Access at: https://demo-hearth-data.s3.amazonaws.com/admin/index.html
```

## API Gateway Configuration Required

The Lambda functions are created but need to be connected to API Gateway endpoints.

### Current Status
✅ Lambda Functions Created:
- hearth-crud-update (update_listing_handler)
- hearth-crud-create (add_listing_handler)
- hearth-crud-delete (delete_listing_handler)
- hearth-search (search + get listing handlers)

✅ API Gateway Configuration:
- Base URL: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`
- GET /listings/{zpid} → hearth-search
- PATCH /listings/{zpid} → hearth-crud-update
- POST /listings → hearth-crud-create
- DELETE /listings/{zpid} → hearth-crud-delete
- POST /search → hearth-search

### Configure API Gateway (AWS Console)

1. **Go to API Gateway Console**
   - Navigate to API Gateway (hearth-api)
   - Current API ID: `mwf1h5nbxe`

2. **Create /listings resource (if not exists)**
   - Actions → Create Resource
   - Resource Name: `listings`
   - Resource Path: `/listings`
   - Enable CORS: ✓

3. **Create /listings/{zpid} resource**
   - Select `/listings`
   - Actions → Create Resource
   - Resource Name: `{zpid}`
   - Resource Path: `/{zpid}`
   - Enable CORS: ✓

4. **Add Methods:**

   **GET /listings/{zpid}**
   - Select `/listings/{zpid}`
   - Actions → Create Method → GET
   - Integration type: Lambda Function
   - Lambda Function: `hearth-search`
   - Use Lambda Proxy integration: ✓
   - Save

   **PATCH /listings/{zpid}**
   - Select `/listings/{zpid}`
   - Actions → Create Method → PATCH
   - Integration type: Lambda Function
   - Lambda Function: `hearth-crud-update`
   - Use Lambda Proxy integration: ✓
   - Save

   **DELETE /listings/{zpid}**
   - Select `/listings/{zpid}`
   - Actions → Create Method → DELETE
   - Integration type: Lambda Function
   - Lambda Function: `hearth-crud-delete`
   - Use Lambda Proxy integration: ✓
   - Save

   **POST /listings**
   - Select `/listings`
   - Actions → Create Method → POST
   - Integration type: Lambda Function
   - Lambda Function: `hearth-crud-create`
   - Use Lambda Proxy integration: ✓
   - Save

5. **Enable CORS for each method**
   - Select each method
   - Actions → Enable CORS
   - Click "Enable CORS and replace existing CORS headers"

6. **Deploy API**
   - Actions → Deploy API
   - Deployment stage: `prod`
   - Deploy

### Configure Search Lambda for Multiple Handlers

The `hearth-search` Lambda now has two handlers but API Gateway can only call one. We need to route based on the request:

**Option A: Update search.py to route internally** (Recommended)

Add a router function to search.py:
```python
def lambda_handler(event, context):
    """Router that dispatches to correct handler based on path"""
    path = event.get('path', '')
    method = event.get('httpMethod', '')

    if method == 'POST' and path == '/search':
        return handler(event, context)
    elif method == 'GET' and '/listings/' in path:
        return get_listing_handler(event, context)
    else:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Not found"})
        }
```

Then update Lambda handler to: `search.lambda_handler`

**Option B: Keep separate**
Create a separate Lambda for GET listings endpoint.

## Testing the UI

### 1. Test Search (Should work now)
```
Query: "granite countertops"
Limit: 5
Index: listings-v2
```
Should return existing Salt Lake City listings.

### 2. Get Listing Details
```
ZPID: [use zpid from search results]
Include Full Data: ✓
```
Should return complete listing details.

### 3. Update Listing
```
ZPID: [existing zpid]
Price: 475000
Status: pending
Custom: {"hoa_fees": 250}
```
Should update the listing.

### 4. Create Test Listing
```
ZPID: test_12345
Price: 500000
Beds: 3
Baths: 2
Address: 123 Test Street
Description: Test listing for CRUD verification
```
Should create a new listing.

### 5. Verify Creation
Search for "test listing" - should find your new listing.

### 6. Delete Test Listing
```
ZPID: test_12345
Type: Soft Delete
```
Should mark as deleted.

### 7. Verify Deletion
Search for "test listing" - should NOT appear (soft deleted).

## Troubleshooting

### "Missing zpid in path" Error
- API Gateway path parameter not configured correctly
- Ensure {zpid} is defined in resource path

### CORS Errors
- Enable CORS on all methods
- Ensure OPTIONS method exists for each resource
- Deploy API after CORS changes

### Lambda Permission Errors
- API Gateway needs permission to invoke Lambda
- Usually auto-added when creating method
- Manually add if needed:
  ```bash
  aws lambda add-permission \
    --function-name hearth-crud-update \
    --statement-id apigateway-access \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:us-east-1:692859949078:mqgsb4xb2g/*/*"
  ```

### Check CloudWatch Logs
```bash
# View logs for each Lambda
aws logs tail /aws/lambda/hearth-crud-update --follow
aws logs tail /aws/lambda/hearth-crud-create --follow
aws logs tail /aws/lambda/hearth-crud-delete --follow
aws logs tail /aws/lambda/hearth-search --follow
```

## Next Steps After Setup

1. ✅ Test all CRUD operations via UI
2. ✅ Create a test listing
3. ✅ Update it
4. ✅ Verify changes in search
5. ✅ Delete test listing
6. 🚀 Ready to start indexing!

## Security Note

This admin UI has no authentication. For production:
- Add API key requirement
- Use AWS Cognito for user auth
- Restrict access by IP
- Add request signing

Current setup is for testing only!
