# API Reference

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [SEARCH_SYSTEM.md](SEARCH_SYSTEM.md), [DEPLOYMENT.md](DEPLOYMENT.md)

Complete API documentation for all Hearth Search endpoints.

---

## Table of Contents

1. [Search API](#search-api)
2. [CRUD API](#crud-api)
3. [Analytics API](#analytics-api)
4. [Common Responses](#common-responses)
5. [Error Handling](#error-handling)

---

## Search API

**Endpoint**: `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search`
**Lambda**: `hearth-search-v2`
**Method**: GET

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query (e.g., "modern homes with pool") |
| `minPrice` | number | No | Minimum price filter |
| `maxPrice` | number | No | Maximum price filter |
| `minBedrooms` | number | No | Minimum bedrooms filter |
| `minBathrooms` | number | No | Minimum bathrooms filter |
| `minLivingArea` | number | No | Minimum square footage (house, not lot) |
| `maxLivingArea` | number | No | Maximum square footage |
| `propertyTypes` | string | No | Comma-separated property types (e.g., "SINGLE_FAMILY,CONDO") |
| `limit` | number | No | Results per page (default: 20, max: 100) |
| `search_after` | string | No | Pagination token from previous response |

### Example Requests

#### Basic Search

**curl**:
```bash
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=modern+homes"
```

**Python**:
```python
import requests

def search_properties(query, limit=20):
    """Basic property search"""
    url = "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search"
    params = {
        "query": query,
        "limit": limit
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        print(f"Found {data['total']} properties")
        return data
    else:
        print(f"Search failed: {response.status_code}")
        return None

# Usage
results = search_properties("modern homes")
for prop in results['properties']:
    print(f"{prop['address']}: ${prop['price']:,}")
```

#### Search with Filters

**curl**:
```bash
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=craftsman+homes&minPrice=300000&maxPrice=600000&minBedrooms=3&minBathrooms=2"
```

**Python**:
```python
import requests

def search_with_filters(query, min_price=None, max_price=None, min_bedrooms=None, min_bathrooms=None):
    """Search properties with price and spec filters"""
    url = "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search"

    params = {"query": query}

    if min_price:
        params["minPrice"] = min_price
    if max_price:
        params["maxPrice"] = max_price
    if min_bedrooms:
        params["minBedrooms"] = min_bedrooms
    if min_bathrooms:
        params["minBathrooms"] = min_bathrooms

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        print(f"Found {data['total']} properties matching filters")
        return data
    else:
        print(f"Search failed: {response.status_code}")
        return None

# Usage
results = search_with_filters(
    query="craftsman homes",
    min_price=300000,
    max_price=600000,
    min_bedrooms=3,
    min_bathrooms=2
)
```

#### Architecture Style Search

**curl**:
```bash
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=mid+century+modern+homes"
```

**Python**:
```python
import requests

def search_by_architecture_style(style):
    """Search properties by architectural style"""
    url = "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search"
    params = {"query": style}

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        print(f"Found {data['total']} {style} properties")

        for prop in data['properties'][:5]:  # Show first 5
            print(f"  - {prop['address']}")
            print(f"    Style: {prop.get('architecture_style', 'N/A')}")
            print(f"    Price: ${prop['price']:,}")

        return data
    else:
        print(f"Search failed: {response.status_code}")
        return None

# Usage
results = search_by_architecture_style("mid century modern homes")
```

#### Pagination

**curl**:
```bash
# First page
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=modern&limit=20"

# Next page (use search_after from previous response)
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=modern&limit=20&search_after=eyJ2YWx1ZXMiOlsxLjIzLCAiMTIzNDUiXX0="
```

**Python**:
```python
import requests

def search_all_pages(query, max_results=100):
    """Search and paginate through all results"""
    url = "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search"
    all_properties = []
    search_after = None

    while len(all_properties) < max_results:
        params = {
            "query": query,
            "limit": 20
        }

        if search_after:
            params["search_after"] = search_after

        response = requests.get(url, params=params)

        if response.status_code != 200:
            print(f"Search failed: {response.status_code}")
            break

        data = response.json()
        all_properties.extend(data['properties'])

        print(f"Fetched {len(data['properties'])} properties (total: {len(all_properties)})")

        if not data.get('has_more') or not data.get('search_after'):
            break

        search_after = data['search_after']

    print(f"\n✅ Retrieved {len(all_properties)} total properties")
    return all_properties

# Usage
all_results = search_all_pages("modern homes", max_results=100)
```

### Response Format

```json
{
  "properties": [
    {
      "zpid": "123456",
      "address": "123 Main St",
      "city": "Salt Lake City",
      "state": "UT",
      "zipcode": "84101",
      "price": 450000,
      "bedrooms": 3,
      "bathrooms": 2.5,
      "livingArea": 2100,
      "lotSize": 5000,
      "propertyType": "SINGLE_FAMILY",
      "yearBuilt": 2015,
      "architecture_style": "modern",
      "architecture_substyle": "contemporary",
      "property_features": ["granite countertops", "hardwood floors", "stainless steel appliances"],
      "exterior_materials": ["brick", "vinyl siding"],
      "image_urls": ["https://photos.zillowstatic.com/..."],
      "score": 0.0523,
      "matched_tags": ["granite countertops"],
      "search_strategies": {
        "bm25_score": 0.045,
        "text_knn_score": 0.032,
        "image_knn_score": 0.028
      }
    }
  ],
  "total": 156,
  "query_info": {
    "original_query": "modern homes with granite",
    "subqueries": [
      "modern architecture",
      "granite countertops"
    ],
    "classification": {
      "primary_intent": "visual_style",
      "secondary_intents": ["specific_feature"]
    }
  },
  "search_after": "eyJ2YWx1ZXMiOlsxLjIzLCAiMTIzNDUiXX0=",
  "has_more": true
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `properties` | array | Array of property objects |
| `total` | number | Total matching properties |
| `query_info` | object | Query decomposition and classification |
| `search_after` | string | Pagination token for next page |
| `has_more` | boolean | Whether more results exist |

### Property Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `zpid` | string | Zillow property ID (unique) |
| `address` | string | Street address |
| `city` | string | City name |
| `state` | string | State abbreviation |
| `price` | number | Listing price (USD) |
| `bedrooms` | number | Number of bedrooms |
| `bathrooms` | number | Number of bathrooms |
| `livingArea` | number | House square footage (NOT lot size) |
| `lotSize` | number | Lot size in square feet |
| `architecture_style` | string | Tier 1 style (e.g., "modern", "craftsman") |
| `architecture_substyle` | string | Tier 2 style (e.g., "mid_century_modern") |
| `property_features` | array | Interior features (tags) |
| `exterior_materials` | array | Exterior materials (tags) |
| `homeStatus` | string | Original Zillow status (FOR_SALE, SOLD, etc.) |
| `listingStatus` | string | **Custom status** (for_sale, sold, pending, etc.) - your pipeline tracking |
| `soldDate` | string | Date property was marked sold (YYYY-MM-DD) |
| `listedDate` | string | Date property was listed for sale (YYYY-MM-DD) |
| `yearBuilt` | number | Year property was built |
| `score` | number | RRF score (higher = better, 0.05+ is excellent) |
| `matched_tags` | array | Tags that matched query |

---

## CRUD API

**Endpoint**: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`
**Lambda**: `hearth-crud-listings`

### Create Property

**Method**: POST
**Path**: `/listings`

**Request Body**:
```json
{
  "zpid": "123456",
  "address": "123 Main St",
  "city": "Salt Lake City",
  "state": "UT",
  "price": 450000,
  "bedrooms": 3,
  "bathrooms": 2.5,
  "livingArea": 2100,
  "lotSize": 5000,
  "propertyType": "SINGLE_FAMILY",
  "image_urls": ["https://photos.zillowstatic.com/..."],
  "options": {
    "generate_embeddings": true
  }
}
```

**curl Example**:
```bash
curl -X POST "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings?index=listings-v2" \
  -H "Content-Type: application/json" \
  -d @property.json
```

**Python Example**:
```python
import requests

url = "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings"
params = {"index": "listings-v2"}

property_data = {
    "zpid": "123456",
    "address": "123 Main St",
    "city": "Salt Lake City",
    "state": "UT",
    "price": 450000,
    "bedrooms": 3,
    "bathrooms": 2.5,
    "livingArea": 2100,
    "lotSize": 5000,
    "propertyType": "SINGLE_FAMILY",
    "image_urls": ["https://photos.zillowstatic.com/fp/...jpg"],
    "options": {
        "generate_embeddings": True
    }
}

response = requests.post(url, params=params, json=property_data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

### Update Property

**Method**: PATCH
**Path**: `/listings/{zpid}`

**Query Parameters**:
- `index`: OpenSearch index (default: listings-v2)

**Request Body**:
```json
{
  "updates": {
    "price": 475000,
    "livingArea": 2200
  },
  "options": {
    "preserve_embeddings": true
  }
}
```

**Options**:
- `preserve_embeddings`: If true, keeps existing embeddings (faster, recommended for price/area updates)
- `preserve_embeddings`: If false, regenerates embeddings (use for major property changes)

**curl Example**:
```bash
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": {"price": 475000},
    "options": {"preserve_embeddings": true}
  }'
```

**Python Example**:
```python
import requests

zpid = "123456"
url = f"https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}"
params = {"index": "listings-v2"}

payload = {
    "updates": {
        "price": 475000,
        "livingArea": 2200
    },
    "options": {
        "preserve_embeddings": True
    }
}

response = requests.patch(url, params=params, json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

---

### Mark Property as Sold

**Method**: PATCH
**Path**: `/listings/{zpid}`

Use this to mark a specific property as sold using its ZPID.

**curl Example**:
```bash
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": {
      "listingStatus": "sold",
      "soldDate": "2025-10-24"
    },
    "options": {"preserve_embeddings": true}
  }'
```

**Python Example**:
```python
import requests
from datetime import datetime

def mark_property_sold(zpid):
    """Mark a property as sold by ZPID"""
    url = f"https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}"
    params = {"index": "listings-v2"}

    payload = {
        "updates": {
            "listingStatus": "sold",
            "soldDate": datetime.now().strftime("%Y-%m-%d")
        },
        "options": {
            "preserve_embeddings": True  # Keep embeddings, faster update
        }
    }

    response = requests.patch(url, params=params, json=payload)

    if response.status_code == 200:
        print(f"✅ Property {zpid} marked as sold")
        return response.json()
    else:
        print(f"❌ Failed to mark {zpid} as sold: {response.status_code}")
        print(f"Error: {response.text}")
        return None

# Usage
result = mark_property_sold("123456")
```

---

### Mark Property as For Sale

**Method**: PATCH
**Path**: `/listings/{zpid}`

Use this to mark a specific property as available for sale using its ZPID.

**curl Example**:
```bash
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": {
      "listingStatus": "for_sale",
      "listedDate": "2025-10-24"
    },
    "options": {"preserve_embeddings": true}
  }'
```

**Python Example**:
```python
import requests
from datetime import datetime

def mark_property_for_sale(zpid, price=None):
    """Mark a property as for sale by ZPID"""
    url = f"https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}"
    params = {"index": "listings-v2"}

    updates = {
        "listingStatus": "for_sale",
        "listedDate": datetime.now().strftime("%Y-%m-%d")
    }

    # Optionally update price when listing
    if price:
        updates["price"] = price

    payload = {
        "updates": updates,
        "options": {
            "preserve_embeddings": True
        }
    }

    response = requests.patch(url, params=params, json=payload)

    if response.status_code == 200:
        print(f"✅ Property {zpid} marked as for sale")
        return response.json()
    else:
        print(f"❌ Failed to mark {zpid} as for sale: {response.status_code}")
        print(f"Error: {response.text}")
        return None

# Usage
result = mark_property_for_sale("123456", price=475000)
```

**Custom listingStatus Values** (independent from Zillow data):
- `for_sale` - Available for purchase
- `sold` - Property sold
- `pending` - Sale pending
- `under_contract` - Under contract with buyer
- `off_market` - Temporarily off market
- `coming_soon` - Will be listed soon

**Note**: This is a custom field separate from Zillow's `homeStatus`. Use `listingStatus` to track your own sales pipeline independent of the original Zillow data

---

### Batch Update - Mark Multiple Properties as Sold

**Python Example**:
```python
import requests
from datetime import datetime

def mark_properties_sold(zpid_list):
    """Mark multiple properties as sold by ZPID list"""
    url_base = "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings"
    params = {"index": "listings-v2"}
    sold_date = datetime.now().strftime("%Y-%m-%d")

    results = {
        "success": [],
        "failed": []
    }

    for zpid in zpid_list:
        url = f"{url_base}/{zpid}"
        payload = {
            "updates": {
                "listingStatus": "sold",
                "soldDate": sold_date
            },
            "options": {"preserve_embeddings": True}
        }

        try:
            response = requests.patch(url, params=params, json=payload, timeout=30)

            if response.status_code == 200:
                print(f"✅ {zpid}: Marked as sold on {sold_date}")
                results["success"].append(zpid)
            else:
                print(f"❌ {zpid}: Failed ({response.status_code})")
                results["failed"].append({"zpid": zpid, "error": response.text})

        except Exception as e:
            print(f"❌ {zpid}: Exception - {e}")
            results["failed"].append({"zpid": zpid, "error": str(e)})

    print(f"\n📊 Summary: {len(results['success'])} succeeded, {len(results['failed'])} failed")
    return results

# Usage
properties_to_mark_sold = ["123456", "789012", "345678"]
results = mark_properties_sold(properties_to_mark_sold)
```

**Filter Search by Custom Status**:
```bash
# Search only for properties currently for sale (custom field)
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=modern+homes&listingStatus=for_sale"

# Exclude sold properties from search results
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=craftsman&excludeStatus=sold"
```

---

### Delete Property

**Method**: DELETE
**Path**: `/listings/{zpid}`

**Query Parameters**:
- `index`: OpenSearch index (default: listings-v2)

**curl Example**:
```bash
curl -X DELETE "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2"
```

**Python Example**:
```python
import requests

def delete_property(zpid):
    """Delete a property by ZPID"""
    url = f"https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}"
    params = {"index": "listings-v2"}

    response = requests.delete(url, params=params)

    if response.status_code == 200:
        print(f"✅ Property {zpid} deleted successfully")
        return response.json()
    else:
        print(f"❌ Failed to delete {zpid}: {response.status_code}")
        print(f"Error: {response.text}")
        return None

# Usage
result = delete_property("123456")
```

### Response Format

**Success (200)**:
```json
{
  "success": true,
  "zpid": "123456",
  "operation": "update",
  "message": "Property updated successfully"
}
```

**Error (400/500)**:
```json
{
  "error": "Invalid request",
  "message": "livingArea must be a number",
  "zpid": "123456"
}
```

---

## Analytics API

**Endpoint**: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod` (same as CRUD)
**Lambda**: `hearth-production-analytics`

### Log Search Query

**Method**: POST
**Path**: `/log-search`

**Request Body**:
```json
{
  "session_id": "abc123",
  "query": "modern homes with pool",
  "filters": {
    "minPrice": 300000,
    "maxPrice": 600000
  },
  "total_results": 42,
  "search_time_ms": 234
}
```

**Python Example**:
```python
import requests
import time

def log_search(session_id, query, filters=None, total_results=0):
    """Log a search query to analytics"""
    url = "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-search"

    payload = {
        "session_id": session_id,
        "query": query,
        "filters": filters or {},
        "total_results": total_results,
        "search_time_ms": int(time.time() * 1000)
    }

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        print(f"✅ Search logged: {query}")
        return response.json()
    else:
        print(f"❌ Failed to log search: {response.status_code}")
        return None

# Usage
log_search(
    session_id="user_session_123",
    query="modern homes with pool",
    filters={"minPrice": 300000, "maxPrice": 600000},
    total_results=42
)
```

---

### Log Property Rating

**Method**: POST
**Path**: `/log-rating`

**Request Body**:
```json
{
  "session_id": "abc123",
  "query_id": "query_xyz",
  "zpid": "123456",
  "rating": 4,
  "comment": "Great property!"
}
```

**Rating Scale**: 1-5 stars

**Python Example**:
```python
import requests

def log_property_rating(session_id, zpid, rating, comment="", query_id=None):
    """Log a property rating"""
    url = "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-rating"

    payload = {
        "session_id": session_id,
        "zpid": zpid,
        "rating": rating,
        "comment": comment
    }

    if query_id:
        payload["query_id"] = query_id

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        print(f"✅ Rating logged for property {zpid}: {rating} stars")
        return response.json()
    else:
        print(f"❌ Failed to log rating: {response.status_code}")
        return None

# Usage
log_property_rating(
    session_id="user_session_123",
    zpid="123456",
    rating=5,
    comment="Perfect home for our family!",
    query_id="query_abc"
)
```

---

### Log Search Quality Feedback

**Method**: POST
**Path**: `/log-search-quality`

**Request Body**:
```json
{
  "session_id": "abc123",
  "query_id": "query_xyz",
  "search_query": "modern homes",
  "rating": 4,
  "feedback_text": "Results were relevant but missing some options",
  "feedback_categories": ["relevant", "missing_options"],
  "total_results": 42,
  "properties_viewed": 5,
  "time_on_results": 120000
}
```

**Feedback Categories**:
- `relevant` - Results matched query well
- `irrelevant` - Results didn't match query
- `missing_options` - Expected properties not shown
- `too_many_results` - Too many results to browse
- `poor_quality` - Low quality properties shown

**Python Example**:
```python
import requests

def log_search_quality(session_id, search_query, rating, feedback_text="",
                       feedback_categories=None, total_results=0, properties_viewed=0):
    """Log search quality feedback"""
    url = "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-search-quality"

    payload = {
        "session_id": session_id,
        "search_query": search_query,
        "rating": rating,
        "feedback_text": feedback_text,
        "feedback_categories": feedback_categories or [],
        "total_results": total_results,
        "properties_viewed": properties_viewed
    }

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        print(f"✅ Search quality feedback logged: {rating} stars")
        return response.json()
    else:
        print(f"❌ Failed to log feedback: {response.status_code}")
        return None

# Usage
log_search_quality(
    session_id="user_session_123",
    search_query="mid century modern homes",
    rating=4,
    feedback_text="Good results, would like more options",
    feedback_categories=["relevant", "missing_options"],
    total_results=42,
    properties_viewed=8
)
```

### Response Format

All analytics endpoints return:

```json
{
  "success": true,
  "id": "log_abc123",
  "message": "Logged successfully"
}
```

---

## Common Responses

### Success Response

```json
{
  "success": true,
  "data": { /* response data */ }
}
```

### Error Response

```json
{
  "error": "Error type",
  "message": "Detailed error message",
  "details": { /* additional context */ }
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Invalid parameters, missing required fields |
| 404 | Not Found | Property zpid doesn't exist |
| 500 | Server Error | Lambda error, OpenSearch error, timeout |

### Common Errors

**Search API Errors**:

```json
// No query provided
{
  "error": "Missing required parameter",
  "message": "query parameter is required"
}

// Invalid filter
{
  "error": "Invalid filter",
  "message": "minPrice must be a number"
}

// Index not found
{
  "error": "Index error",
  "message": "Index listings-v2 not found"
}
```

**CRUD API Errors**:

```json
// Property not found
{
  "error": "Not found",
  "message": "Property 123456 not found in index listings-v2"
}

// Invalid update field
{
  "error": "Invalid field",
  "message": "Field 'invalid_field' is not allowed"
}

// Embedding generation failed
{
  "error": "Embedding error",
  "message": "Failed to generate embeddings for property",
  "details": {"bedrock_error": "Rate limit exceeded"}
}
```

### Error Handling Best Practices

**Retry Logic**:
```python
import time
import requests

def search_with_retry(query, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(
                "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search",
                params={"query": query},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
```

**Validation**:
```python
def validate_filters(filters):
    if "minPrice" in filters and not isinstance(filters["minPrice"], (int, float)):
        raise ValueError("minPrice must be a number")
    if "maxPrice" in filters and filters["maxPrice"] < filters.get("minPrice", 0):
        raise ValueError("maxPrice must be greater than minPrice")
```

---

## Rate Limits

- **Search API**: No hard limit, but recommend < 100 req/sec
- **CRUD API**: Recommended batch size 50 requests
- **Analytics API**: No limit

---

## API Usage Examples

### Complete Search Flow

```python
import requests

# 1. Search for properties
response = requests.get(
    "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search",
    params={
        "query": "modern homes with pool",
        "minPrice": 300000,
        "maxPrice": 600000,
        "limit": 20
    }
)

results = response.json()

# 2. Log the search
requests.post(
    "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-search",
    json={
        "session_id": "user_session_123",
        "query": "modern homes with pool",
        "total_results": results["total"]
    }
)

# 3. User views a property and rates it
zpid = results["properties"][0]["zpid"]
requests.post(
    "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-rating",
    json={
        "session_id": "user_session_123",
        "zpid": zpid,
        "rating": 5
    }
)

# 4. Paginate to next page
if results["has_more"]:
    next_page = requests.get(
        "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search",
        params={
            "query": "modern homes with pool",
            "limit": 20,
            "search_after": results["search_after"]
        }
    )
```

---

## Testing APIs

### Using curl

```bash
# Search
curl -X GET "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=test"

# Update property
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2" \
  -H "Content-Type: application/json" \
  -d '{"updates": {"price": 500000}, "options": {"preserve_embeddings": true}}'

# Log search
curl -X POST "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-search" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "query": "test"}'
```

### Using Python requests

```python
import requests

# Search
response = requests.get(
    "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search",
    params={"query": "modern homes"}
)
print(response.json())

# Update
response = requests.patch(
    "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456",
    params={"index": "listings-v2"},
    json={"updates": {"price": 500000}, "options": {"preserve_embeddings": True}}
)
print(response.json())
```

---

## See Also

- [SEARCH_SYSTEM.md](SEARCH_SYSTEM.md) - How search works internally
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common API issues
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deploying API changes
