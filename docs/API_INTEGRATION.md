# Hearth Property Search API - Complete Integration Guide

**Last Updated:** 2025-10-13
**API Version:** 1.0
**Base URL:** `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod`

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [API Endpoints](#api-endpoints)
3. [Request Format](#request-format)
4. [Response Format](#response-format)
5. [Search Features](#search-features)
6. [Filters](#filters)
7. [Error Handling](#error-handling)
8. [Code Examples](#code-examples)
9. [Rate Limits & Performance](#rate-limits--performance)
10. [CORS Configuration](#cors-configuration)

---

## Quick Start

### Test the API

```bash
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"granite countertops","size":10}'
```

### Live Demo

**UI:** http://34.228.111.56/

Try these searches:
- "granite countertops"
- "blue house"
- "vaulted ceilings"
- "3 bedroom homes under $500k"

---

## API Endpoints

### POST /search

Natural language property search with AI-powered semantic understanding and image recognition.

**Endpoint:** `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search`

**Method:** `POST`

**Content-Type:** `application/json`

**Authentication:** None (public API)

---

## Request Format

### Basic Request

```json
{
  "q": "granite countertops",
  "size": 10
}
```

### Request with Filters

```json
{
  "q": "modern homes with open floor plan",
  "size": 20,
  "filters": {
    "price_min": 300000,
    "price_max": 600000,
    "beds_min": 3,
    "baths_min": 2
  }
}
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | Yes | - | Natural language search query |
| `size` | integer | No | 15 | Number of results (max: 50) |
| `filters` | object | No | {} | Filter criteria (see below) |

### Filter Options

| Filter | Type | Description | Example |
|--------|------|-------------|---------|
| `price_min` | integer | Minimum price in USD | `300000` |
| `price_max` | integer | Maximum price in USD | `600000` |
| `beds_min` | integer | Minimum bedrooms | `3` |
| `baths_min` | integer | Minimum bathrooms | `2` |
| `acreage_min` | float | Minimum lot size in acres | `0.25` |
| `acreage_max` | float | Maximum lot size in acres | `1.0` |

---

## Response Format

### Success Response

```json
{
  "ok": true,
  "results": [
    {
      "zpid": "456567015",
      "id": "456567015",
      "score": 4.67,
      "boosted": false,
      "description": "Wow...this home has everything!!! Beautifully Updated Throughout! Kitchen with Granite Counters...",
      "has_description": true,
      "price": 369900,
      "bedrooms": 2.0,
      "bathrooms": 3.0,
      "livingArea": 435.0,
      "address": {
        "streetAddress": "4738 S Woodduck Ln E",
        "city": "Salt Lake City",
        "state": "UT",
        "zipcode": "84117"
      },
      "city": "Salt Lake City",
      "state": "UT",
      "zip_code": "84117",
      "geo": {
        "lat": 40.66717,
        "lon": -111.86042
      },
      "llm_profile": "",
      "feature_tags": [],
      "image_tags": [
        "granite countertops",
        "stainless steel appliances",
        "vaulted ceilings",
        "hardwood floors",
        "large windows"
      ],
      "images": [
        "https://photos.zillowstatic.com/fp/59c1d865ef02fd6d8cfdf897aa3442f2-cc_ft_1536.jpg",
        "https://photos.zillowstatic.com/fp/659d31c6acd745578ead522c95019eda-cc_ft_1536.jpg"
      ],
      "has_valid_embeddings": true,
      "status": "active",
      "indexed_at": 1760330421
    }
  ],
  "total": 5,
  "must_have": []
}
```

### Response Fields

#### Root Level

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Request success status |
| `results` | array | Array of property listings |
| `total` | integer | Number of results returned |
| `must_have` | array | Required features extracted from query |

#### Listing Object

| Field | Type | Description |
|-------|------|-------------|
| `zpid` | string | Zillow Property ID (unique identifier) |
| `id` | string | Same as zpid |
| `score` | float | Relevance score (higher = better match) |
| `boosted` | boolean | Whether result matched all required features |
| `description` | string | Full property description |
| `has_description` | boolean | Whether description exists |
| `price` | integer | Listing price in USD |
| `bedrooms` | float | Number of bedrooms |
| `bathrooms` | float | Number of bathrooms |
| `livingArea` | float | Square footage |
| `address` | object | Structured address (see below) |
| `city` | string | City name |
| `state` | string | State code (e.g., "UT") |
| `zip_code` | string | ZIP code |
| `geo` | object | Coordinates (lat, lon) |
| `feature_tags` | array | AI-detected features from text |
| `image_tags` | array | AI-detected features from photos |
| `images` | array | Array of image URLs (all photos) |
| `has_valid_embeddings` | boolean | Whether AI embeddings exist |
| `status` | string | Listing status ("active") |
| `indexed_at` | integer | Unix timestamp of indexing |

#### Address Object

```json
{
  "streetAddress": "4738 S Woodduck Ln E",
  "city": "Salt Lake City",
  "state": "UT",
  "zipcode": "84117"
}
```

#### Geo Object

```json
{
  "lat": 40.66717,
  "lon": -111.86042
}
```

---

## Search Features

### Natural Language Processing

The API understands natural language queries and extracts:
- **Features:** "granite countertops", "pool", "garage"
- **Price ranges:** "under $500k", "between 300k and 600k"
- **Bedrooms/bathrooms:** "3 bedroom", "2.5 bath"
- **Descriptors:** "modern", "spacious", "updated"

### Visual Search

AI analyzes property photos to detect:
- **Exterior:** Blue house, brick exterior, stucco, wood siding
- **Kitchen:** Granite countertops, stainless steel appliances, kitchen island
- **Interior:** Vaulted ceilings, hardwood floors, fireplace, open floor plan
- **Features:** 2-car garage, fenced backyard, large windows

### Hybrid Search Algorithm

Results are ranked using:
1. **BM25 Text Search** - Keyword matching on descriptions
2. **kNN Text Embeddings** - Semantic similarity (1024-dim vectors)
3. **kNN Image Embeddings** - Visual similarity (1024-dim vectors)
4. **Reciprocal Rank Fusion** - Combines all three rankings
5. **Feature Boost** - Properties matching all required tags get +50% score

---

## Filters

### Price Filtering

```json
{
  "q": "homes",
  "filters": {
    "price_min": 300000,
    "price_max": 600000
  }
}
```

**Note:** API automatically filters out listings with `price=0` (invalid prices)

### Bedroom/Bathroom Filtering

```json
{
  "q": "family homes",
  "filters": {
    "beds_min": 3,
    "baths_min": 2
  }
}
```

### Combined Filters

```json
{
  "q": "granite countertops with large windows",
  "size": 20,
  "filters": {
    "price_min": 400000,
    "price_max": 700000,
    "beds_min": 4,
    "baths_min": 2.5
  }
}
```

---

## Error Handling

### Error Response Format

```json
{
  "error": "Error message here"
}
```

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Missing or invalid parameters |
| 500 | Server Error | Internal server error |

### Common Errors

**Missing Query Parameter:**
```json
{
  "error": "missing 'q'"
}
```

**Solution:** Always include `q` parameter in request body.

---

## Code Examples

### JavaScript (Fetch API)

```javascript
async function searchProperties(query, filters = {}) {
  const API_URL = 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search';

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        q: query,
        size: 20,
        filters: filters
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.results;
  } catch (error) {
    console.error('Search failed:', error);
    return [];
  }
}

// Usage
const results = await searchProperties('granite countertops', {
  price_max: 500000,
  beds_min: 3
});

console.log(`Found ${results.length} properties`);
results.forEach(property => {
  console.log(`${property.address.streetAddress} - $${property.price.toLocaleString()}`);
});
```

### JavaScript (Axios)

```javascript
const axios = require('axios');

async function searchProperties(query, options = {}) {
  const API_URL = 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search';

  const payload = {
    q: query,
    size: options.size || 20
  };

  if (options.filters) {
    payload.filters = options.filters;
  }

  try {
    const response = await axios.post(API_URL, payload);
    return response.data;
  } catch (error) {
    console.error('Search error:', error.response?.data || error.message);
    throw error;
  }
}

// Usage
searchProperties('modern homes with pool', {
  size: 10,
  filters: {
    price_min: 400000,
    beds_min: 3,
    baths_min: 2
  }
}).then(data => {
  console.log(`Total results: ${data.total}`);
  data.results.forEach(prop => {
    console.log(`${prop.bedrooms}bd/${prop.bathrooms}ba - $${prop.price}`);
  });
});
```

### Python

```python
import requests
import json

def search_properties(query, filters=None, size=20):
    """Search properties using natural language query."""
    API_URL = 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search'

    payload = {
        'q': query,
        'size': size
    }

    if filters:
        payload['filters'] = filters

    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Search failed: {e}")
        return None

# Usage
results = search_properties(
    'granite countertops with vaulted ceilings',
    filters={
        'price_max': 600000,
        'beds_min': 3,
        'baths_min': 2
    },
    size=15
)

if results and results['ok']:
    print(f"Found {results['total']} properties")
    for prop in results['results']:
        print(f"{prop['address']['streetAddress']}: ${prop['price']:,}")
        print(f"  {prop['bedrooms']}bd/{prop['bathrooms']}ba - {prop.get('livingArea', 0):,} sqft")
        print(f"  Features: {', '.join(prop['image_tags'][:5])}")
        print()
```

### React Component

```jsx
import React, { useState } from 'react';

const PropertySearch = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const API_URL = 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search';

  const handleSearch = async () => {
    if (!query.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ q: query, size: 12 })
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      setResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="property-search">
      <div className="search-input">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="Search properties..."
        />
        <button onClick={handleSearch} disabled={loading}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {error && <div className="error">Error: {error}</div>}

      <div className="results-grid">
        {results.map((property) => (
          <div key={property.zpid} className="property-card">
            <img src={property.images[0]} alt="Property" />
            <div className="property-info">
              <div className="price">${property.price.toLocaleString()}</div>
              <div className="address">{property.address.streetAddress}</div>
              <div className="features">
                {property.bedrooms} bd | {property.bathrooms} ba
                {property.livingArea && ` | ${property.livingArea.toLocaleString()} sqft`}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default PropertySearch;
```

### cURL

```bash
# Basic search
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"granite countertops","size":10}'

# With filters
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{
    "q": "modern homes with pool",
    "size": 20,
    "filters": {
      "price_min": 400000,
      "price_max": 800000,
      "beds_min": 3,
      "baths_min": 2
    }
  }' | jq '.'

# Extract specific fields
curl -s -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"q":"vaulted ceilings","size":5}' \
  | jq '.results[] | {price, address: .address.streetAddress, beds: .bedrooms}'
```

---

## Rate Limits & Performance

### Performance Metrics

| Metric | Value |
|--------|-------|
| **Average Response Time** | 1-3 seconds |
| **P95 Response Time** | <5 seconds |
| **Indexed Listings** | 1,358+ properties |
| **Max Results Per Request** | 50 |
| **Timeout** | 30 seconds |

### Rate Limits

**Current:** No hard rate limits

**Recommendations:**
- Client-side debouncing for search-as-you-type
- Cache results when possible
- Use reasonable `size` parameter (10-20 is optimal)

### Best Practices

1. **Debounce user input** - Wait 300-500ms after typing stops
2. **Show loading state** - Users expect 1-3 second response
3. **Handle errors gracefully** - Display user-friendly error messages
4. **Cache results** - Store recent searches client-side
5. **Lazy load images** - Use `loading="lazy"` for property images

---

## CORS Configuration

### Allowed Origins

`*` (All origins allowed for public API)

### Allowed Methods

- `POST`
- `OPTIONS`

### Allowed Headers

- `Content-Type`

### Browser Usage

No special configuration needed. API works directly from browser:

```javascript
// Works from any domain
fetch('https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ q: 'granite countertops', size: 10 })
})
.then(res => res.json())
.then(data => console.log(data.results));
```

---

## Image URLs

### Image Format

All images are Zillow CDN URLs with resolution suffix:

```
https://photos.zillowstatic.com/fp/{hash}-cc_ft_1536.jpg
```

### Available Resolutions

Change the resolution by replacing the suffix:

| Suffix | Resolution | Use Case |
|--------|------------|----------|
| `_384` | 384px | Thumbnails |
| `_576` | 576px | Cards |
| `_768` | 768px | Modal previews |
| `_1536` | 1536px | Full size |
| `uncropped_scaled_within_1536_1152` | High-res | Original aspect ratio |

### Example

```javascript
// Get high-res version of image
function getHighResImage(url) {
  return url.replace(/-cc_ft_\d+\./, '-uncropped_scaled_within_1536_1152.');
}

const thumbnailUrl = listing.images[0]; // _1536 version
const highResUrl = getHighResImage(thumbnailUrl); // uncropped version
```

---

## Example Queries

### Feature-Based Searches

```javascript
// Granite countertops
{"q": "granite countertops", "size": 10}

// Blue exterior
{"q": "blue house", "size": 10}

// Vaulted ceilings
{"q": "vaulted ceilings", "size": 10}

// Large windows
{"q": "large windows", "size": 10}

// Open floor plan
{"q": "open floor plan", "size": 10}
```

### Complex Searches

```javascript
// Multiple features
{"q": "granite countertops with stainless steel appliances and hardwood floors", "size": 10}

// With price filter
{
  "q": "modern homes with pool",
  "size": 15,
  "filters": {"price_max": 600000}
}

// Bedroom + bathroom requirements
{
  "q": "family homes",
  "filters": {"beds_min": 4, "baths_min": 2.5}
}
```

---

## Support & Issues

### Questions

For API questions or integration help, refer to:
- This documentation
- `/docs/BACKEND_ARCHITECTURE.md` - How the system works
- `/docs/CODE_REFERENCE.md` - Python code details

### Reporting Issues

Include in your report:
1. Query string used
2. Filters applied
3. Expected vs actual results
4. Timestamp of request

---

## Changelog

### Version 1.0 (2025-10-13)
- Initial production release
- 1,358+ listings indexed
- AI vision analysis active
- CORS enabled
- Full natural language support
