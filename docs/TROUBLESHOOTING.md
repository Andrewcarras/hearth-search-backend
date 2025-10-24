# Troubleshooting Guide

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [DEPLOYMENT.md](DEPLOYMENT.md), [API.md](API.md)

Common issues and solutions for Hearth Search.

---

## Table of Contents

1. [Search Issues](#search-issues)
2. [Data Issues](#data-issues)
3. [Deployment Issues](#deployment-issues)
4. [Index Issues](#index-issues)
5. [UI Issues](#ui-issues)
6. [API Issues](#api-issues)

---

## Search Issues

### Search Returns No Results

**Symptoms**: All searches return empty results or 0 properties found

#### Cause 1: Wrong Index Configuration

**Check**:
```bash
aws lambda get-function-configuration --function-name hearth-search-v2 \
  --query 'Environment.Variables.OS_INDEX'
```

**Should return**: `"listings-v2"`

**If it returns** `"listings"` **or something else**:

**Fix**:
```bash
# Update Lambda environment variable
aws lambda update-function-configuration \
  --function-name hearth-search-v2 \
  --environment 'Variables={OS_INDEX=listings-v2,OS_HOST=your-endpoint,...}'

# Verify change
aws lambda get-function-configuration --function-name hearth-search-v2 \
  --query 'Environment.Variables.OS_INDEX'
```

#### Cause 2: Architecture Style Not Mapped

**Example**: Searching "mid century modern homes" returns no results

**Check**:
```python
# Test synonym mapping
python3 architecture_style_mappings.py
```

**Fix**: Add missing synonym to architecture_style_mappings.py

```python
# Edit architecture_style_mappings.py
STYLE_SYNONYMS = {
    # ... existing synonyms ...
    "mid century modern homes": ["mid_century_modern"],
}
```

**Deploy**:
```bash
./deploy_lambda.sh
```

#### Cause 3: No Properties with That Style

**Check**:
```bash
# Count properties with specific style
curl -X POST "your-opensearch-endpoint/listings-v2/_count" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "term": {"architecture_style": "mid_century_modern"}
    }
  }'
```

**If count is 0**: Properties need to be classified

**Fix**: Run architecture style update
```bash
python3 update_architecture_fast.py
```

---

### Search Returns Wrong Results

**Symptoms**: Results don't match query intent

#### Cause 1: Query Classification Wrong

**Check CloudWatch logs**:
```bash
aws logs tail /aws/lambda/hearth-search-v2 --follow --filter-pattern "classification"
```

**Look for**: `"primary_intent": "..."`

**If classification is wrong**: Adjust multi-query prompt or query classification logic

#### Cause 2: Strategy Weights Imbalanced

**Check**: Look at score breakdown in response
```json
{
  "search_strategies": {
    "bm25_score": 0.001,
    "text_knn_score": 0.045,
    "image_knn_score": 0.002
  }
}
```

**If one strategy dominates**: Adjust k-values in search Lambda code

**Fix**: Tune RRF k-values
- Lower k = more weight to top results
- Higher k = spread weight more evenly

---

### Architecture Style Search Not Working

**Example**: "Eichler homes" returns no results

**Check synonym mapping**:
```python
from architecture_style_mappings import map_user_style_to_supported

result = map_user_style_to_supported("Eichler")
print(result)
# Should return: {"styles": ["mid_century_modern"], ...}
```

**If no mapping found**:

**Fix**:
```python
# Add to architecture_style_mappings.py
STYLE_SYNONYMS = {
    # ... existing ...
    "eichler": ["mid_century_modern"],
    "eichler homes": ["mid_century_modern"],
}
```

**Deploy**:
```bash
./deploy_lambda.sh
```

**Verify**:
```bash
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=eichler+homes"
```

---

## Data Issues

### Wrong Square Footage Displayed

**Symptoms**: Properties showing 40,000+ sqft for livingArea

**Cause**: livingArea field contained lot size instead of house size (FIXED 2025-10-24)

**Check**:
```bash
# Search for property
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=zpid:123456"

# Check livingArea vs lotSize
# livingArea should be ~1,000-5,000 sqft (house)
# lotSize should be ~5,000-50,000 sqft (lot)
```

**If still wrong**:

**Fix**: Re-run livingArea fix script
```bash
python3 fix_living_area.py slc_listings.json 50
```

**Verify**:
- Check CloudWatch logs: `/tmp/living_area_update.log`
- Should see: "✅ Updated X properties successfully"

---

### Missing Architecture Styles

**Symptoms**: Properties have `architecture_style: null` or empty

**Check count**:
```bash
# Count properties without architecture_style
curl -X POST "your-opensearch-endpoint/listings-v2/_count" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "bool": {
        "must_not": {
          "exists": {"field": "architecture_style"}
        }
      }
    }
  }'
```

**Fix**: Run batch architecture update
```bash
python3 update_architecture_fast.py
```

**Progress**: Check logs
```bash
tail -f /tmp/architecture_update.log
```

---

### Missing Embeddings

**Symptoms**: Properties have null text_embedding or image_embedding

**Causes**:
1. Property added via CRUD API without embeddings
2. Embedding generation failed during upload
3. Bedrock API error during ingestion

**Check**:
```bash
# Search for property and check embeddings
curl "your-opensearch-endpoint/listings-v2/_search" \
  -d '{"query": {"term": {"zpid": "123456"}}}'

# Look for:
# "text_embedding": [array of 1024 numbers]
# "image_embedding": [array of 512 numbers]
```

**Fix**: Re-upload property to regenerate embeddings
```bash
# Update via CRUD API with regenerate option
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": {},
    "options": {"preserve_embeddings": false}
  }'
```

Or re-run upload_listings.py for that property.

---

## Deployment Issues

### Lambda Deployment Fails

**Error**: "No such file or directory: deployment.zip"

**Cause**: Not in project root directory

**Fix**:
```bash
cd /path/to/hearth-search-backend-main
./deploy_lambda.sh
```

---

**Error**: "Function not found: hearth-search-v2"

**Cause**: Lambda function doesn't exist

**Fix**: Create Lambda function via AWS Console first, then deploy code.

---

**Error**: "Insufficient permissions"

**Cause**: IAM role lacks Lambda:UpdateFunctionCode

**Fix**: Add permission to IAM user/role
```json
{
  "Effect": "Allow",
  "Action": "lambda:UpdateFunctionCode",
  "Resource": "arn:aws:lambda:us-east-1:*:function:hearth-search-v2"
}
```

---

### Production UI Not Updating

**Symptoms**: Changes to ui/production.html not visible on http://54.226.26.203/

#### Cause 1: Deployed to S3 Instead of EC2

**Check**:
```bash
# Check if file was updated on EC2
ssh -i your-key.pem ec2-user@54.226.26.203 "stat /var/www/html/index.html"
```

**If file timestamp is old**:

**Fix**:
```bash
./deploy_production_ui.sh  # Deploys to EC2

# NOT: aws s3 cp ui/production.html s3://...
```

#### Cause 2: Browser Cache

**Fix**: Hard refresh browser
- Chrome/Firefox: Ctrl+Shift+R (Cmd+Shift+R on Mac)
- Clear browser cache

#### Cause 3: Nginx Not Restarted

**Fix**:
```bash
ssh -i your-key.pem ec2-user@54.226.26.203
sudo systemctl restart nginx
```

---

### deploy_lambda.sh Using Wrong Index

**Symptoms**: After deployment, searches fail or return stale data

**Check deploy_lambda.sh**:
```bash
grep "OS_INDEX" deploy_lambda.sh
```

**Should show**: `OS_INDEX=listings-v2`

**If it shows** `OS_INDEX=listings`:

**Fix**:
```bash
# Edit deploy_lambda.sh line 17
OS_INDEX=listings-v2  # Change from 'listings' to 'listings-v2'

# Redeploy
./deploy_lambda.sh
```

---

## Index Issues

### listings vs listings-v2 Mismatch

**Symptoms**: Inconsistent results, some searches work, others don't

**Diagnosis**:
```bash
# Check Lambda config
aws lambda get-function-configuration --function-name hearth-search-v2 \
  --query 'Environment.Variables.OS_INDEX'

# Check both indexes
curl "your-opensearch-endpoint/listings/_count"
curl "your-opensearch-endpoint/listings-v2/_count"
```

**Expected**:
- Lambda using: `listings-v2`
- listings index: 3,104 docs (OLD, stale)
- listings-v2 index: 3,902 docs (CURRENT)

**Fix**: Update all Lambda functions to use listings-v2
```bash
# Update search Lambda
aws lambda update-function-configuration \
  --function-name hearth-search-v2 \
  --environment 'Variables={OS_INDEX=listings-v2,...}'

# Update CRUD Lambda
aws lambda update-function-configuration \
  --function-name hearth-crud-listings \
  --environment 'Variables={OS_INDEX=listings-v2,...}'
```

---

### Delete Old "listings" Index?

**Question**: Can we delete the old "listings" index?

**Answer**: Yes, but verify first:

**Checklist**:
1. ✅ All Lambdas using listings-v2
2. ✅ All scripts using listings-v2
3. ✅ Testing UI updated to remove "listings" option
4. ✅ No production traffic to listings index

**Verify**:
```bash
# Check Lambda configs
aws lambda get-function-configuration --function-name hearth-search-v2 | grep OS_INDEX
aws lambda get-function-configuration --function-name hearth-crud-listings | grep OS_INDEX

# Check CloudWatch logs for "listings" (not listings-v2)
aws logs filter-log-events \
  --log-group-name /aws/lambda/hearth-search-v2 \
  --filter-pattern '"listings"' \
  --start-time $(date -u +%s -d '1 hour ago')000
```

**If all clear, delete**:
```bash
curl -X DELETE "your-opensearch-endpoint/listings"
```

---

## UI Issues

### "Rate This Search" Button Not Visible

**Symptoms**: Button doesn't appear after search

**Check**:
1. Search has been executed (button only shows after search)
2. Search returned results (button hidden if 0 results)
3. Button not already submitted (hidden after submission)

**Debug**:
```javascript
// Open browser console (F12)
// Check button element
const button = document.getElementById('searchFeedbackButton');
console.log('Button:', button);
console.log('Style:', button.style.visibility, button.style.opacity);

// Should show: visibility: visible, opacity: 1
```

**Fix**: Verify showSearchFeedbackButton() is called

Check ui/production.html:2290:
```javascript
function showSearchFeedbackButton() {
    const button = document.getElementById('searchFeedbackButton');
    if (button && !searchQualitySubmitted) {
        button.style.visibility = 'visible';
        button.style.opacity = '1';
    }
}
```

Called after search completes (after `displayResults()`).

---

### Search API CORS Error

**Symptoms**: Browser console shows CORS error

**Error**:
```
Access to fetch at 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search'
from origin 'http://54.226.26.203' has been blocked by CORS policy
```

**Cause**: API Gateway CORS not configured

**Fix**: Enable CORS in API Gateway
```bash
# Via AWS Console:
# API Gateway → mqgsb4xb2g → Resources → /search → Enable CORS
# Allow Origins: *
# Allow Headers: Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token
# Allow Methods: GET,OPTIONS
```

---

### Example Queries Not Working

**Symptoms**: Clicking example query chips doesn't fill search bar

**Debug**:
```javascript
// Check fillExample function exists
console.log(typeof fillExample);  // Should be "function"

// Check onclick handlers
document.querySelectorAll('.example-chip').forEach(chip => {
  console.log(chip.getAttribute('onclick'));
});
```

**Fix**: Ensure fillExample function is defined
```javascript
function fillExample(text) {
    document.getElementById('searchInput').value = text;
    performSearch();  // Or trigger search manually
}
```

---

## API Issues

### CRUD API Returns 500 Error

**Symptoms**: All CRUD operations fail with 500 Internal Server Error

**Check CloudWatch Logs**:
```bash
aws logs tail /aws/lambda/hearth-crud-listings --follow
```

**Common causes**:

#### Cause 1: OpenSearch Connection Failed

**Error in logs**: "Failed to connect to OpenSearch"

**Fix**: Check OpenSearch endpoint and security group
```bash
# Verify endpoint
aws lambda get-function-configuration --function-name hearth-crud-listings \
  --query 'Environment.Variables.OS_HOST'

# Test connectivity
curl "https://your-opensearch-endpoint/"
```

#### Cause 2: Bedrock Permission Denied

**Error in logs**: "AccessDeniedException: User is not authorized to perform: bedrock:InvokeModel"

**Fix**: Add Bedrock permission to Lambda IAM role
```json
{
  "Effect": "Allow",
  "Action": "bedrock:InvokeModel",
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/*"
}
```

#### Cause 3: Invalid Request Payload

**Error in logs**: "KeyError: 'updates'" or similar

**Fix**: Ensure request body has correct structure
```json
{
  "updates": {
    "price": 500000
  },
  "options": {
    "preserve_embeddings": true
  }
}
```

---

### Search API Timeout

**Symptoms**: Search takes > 30 seconds and times out

**Causes**:
1. Multi-query generating too many subqueries
2. kNN search on large index
3. Bedrock API slow response

**Check**:
```bash
# Check CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=hearth-search-v2 \
  --statistics Average \
  --start-time $(date -u +%s -d '1 hour ago') \
  --end-time $(date -u +%s) \
  --period 300
```

**Fix**:
- Increase Lambda timeout (max 900 seconds)
- Reduce kNN k-value (fewer neighbors = faster)
- Cache common queries

---

### Wrong API Endpoint

**Symptoms**: 404 Not Found or wrong Lambda invoked

**Check**:
```bash
# Verify API Gateway routes
aws apigateway get-resources --rest-api-id mqgsb4xb2g
aws apigateway get-resources --rest-api-id mwf1h5nbxe
```

**Common mistakes**:
- Using CRUD endpoint (mwf1h5nbxe) for search
- Using search endpoint (mqgsb4xb2g) for CRUD
- Typo in API ID

**Correct endpoints**:
- Search: `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search`
- CRUD: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}`
- Analytics: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-*`

---

## Quick Diagnostic Commands

### Check System Health

```bash
# Lambda configs
aws lambda get-function-configuration --function-name hearth-search-v2 | grep OS_INDEX
aws lambda get-function-configuration --function-name hearth-crud-listings | grep OS_INDEX

# Index counts
curl "your-opensearch-endpoint/listings-v2/_count"

# Test search
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=test"

# Test CRUD
curl "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2"

# Recent Lambda errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/hearth-search-v2 \
  --filter-pattern "ERROR" \
  --start-time $(date -u +%s -d '1 hour ago')000 \
  --limit 10
```

---

## Getting Help

### Check Logs First

```bash
# Search Lambda
aws logs tail /aws/lambda/hearth-search-v2 --follow

# CRUD Lambda
aws logs tail /aws/lambda/hearth-crud-listings --follow

# Analytics Lambda
aws logs tail /aws/lambda/hearth-production-analytics --follow
```

### Common Log Patterns

**Search for errors**:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/hearth-search-v2 \
  --filter-pattern "ERROR"
```

**Search for specific zpid**:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/hearth-crud-listings \
  --filter-pattern "123456"
```

---

## See Also

- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment procedures
- [API.md](API.md) - API reference
- [AWS_INFRASTRUCTURE.md](AWS_INFRASTRUCTURE.md) - Infrastructure details
