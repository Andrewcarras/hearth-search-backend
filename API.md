# Hearth Property Search API - Complete Integration Guide

**Last Updated:** 2025-10-15
**API Version:** 2.0 (Multi-Vector Image Search)
**Base URL:** `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`
**Default Index:** `listings-v2` (multi-vector kNN enabled)

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [API Endpoints](#api-endpoints)
   - [Search Properties (POST /search)](#post-search)
   - [Debug Search (POST /search/debug)](#post-searchdebug)
   - [Utility Endpoints](#utility-endpoints)
     - [Generate Text Embedding](#generate-text-embedding)
     - [Generate Image Embedding](#generate-image-embedding)
   - [Get Single Listing (GET /listings/{zpid})](#get-listingszpid)
   - [Update Listing (PATCH /listings/{zpid})](#patch-listingszpid)
   - [Create Listing (POST /listings)](#post-listings)
   - [Delete Listing (DELETE /listings/{zpid})](#delete-listingszpid)
3. [Request Format](#request-format)
4. [Response Format](#response-format)
5. [Search Features](#search-features)
6. [Filters](#filters)
7. [CRUD Operations](#crud-operations)
   - [Managing For Sale/Sold Status](#managing-for-salesold-status)
8. [Error Handling](#error-handling)
9. [Code Examples](#code-examples)
10. [Rate Limits & Performance](#rate-limits--performance)
11. [CORS Configuration](#cors-configuration)

---

## Quick Start

### Test the API

```bash
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"granite countertops","limit":10,"index":"listings-v2"}'
```

### Live Demo

**UI:** http://54.234.198.245/

Try these searches:
- "granite countertops"
- "blue house"
- "vaulted ceilings"
- "modern 3 bedroom homes"

---

## API Endpoints

### POST /search

Natural language property search with AI-powered semantic understanding and image recognition.

**Endpoint:** `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search`

**Method:** `POST`

**Content-Type:** `application/json`

**Authentication:** None (public API)

---

### POST /search/debug

Enhanced search endpoint with detailed scoring breakdown for debugging and optimization.

**Endpoint:** `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search/debug`

**Method:** `POST`

**Content-Type:** `application/json`

**Authentication:** None (public API)

**Request:** Same as POST /search

**Response Includes:**
- All standard search results
- Detailed scoring information for each result:
  - Individual search strategy scores (BM25, kNN text, kNN image)
  - Rank in each strategy
  - RRF contribution from each strategy
  - Adaptive weight calculations (k-values)
  - Tag matching breakdown
  - Per-image similarity scores (for multi-vector search)
- Query analysis details
- Feature classification results

**Example:**
```bash
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search/debug \
  -H 'Content-Type: application/json' \
  -d '{"query":"white house with pool","limit":5,"index":"listings-v2"}'
```

**Use Cases:**
- Understanding why a property ranked where it did
- Debugging unexpected search results
- Optimizing query formulation
- Validating adaptive weight logic
- Testing new features before deployment

---

### Utility Endpoints

#### Generate Text Embedding

Generate a 1024-dimensional embedding vector for any text using AWS Bedrock Titan.

**Endpoint:** `https://qz7qstyzzqracgry5iq6ehiy540reeqx.lambda-url.us-east-1.on.aws/`

**Method:** `POST`

**Content-Type:** `application/json`

**Request:**
```json
{
  "action": "embed_text",
  "text": "Beautiful modern home with open floor plan"
}
```

**Response:**
```json
{
  "embedding": [0.123, 0.456, ...],  // 1024 values
  "dimensions": 1024
}
```

**Use Cases:**
- Testing semantic similarity
- Validating kNN text search behavior
- Pre-computing embeddings for caching

---

#### Generate Image Embedding

Generate a 1024-dimensional embedding vector for an image using AWS Bedrock Titan.

**Endpoint:** `https://qz7qstyzzqracgry5iq6ehiy540reeqx.lambda-url.us-east-1.on.aws/`

**Method:** `POST`

**Content-Type:** `application/json`

**Request:**
```json
{
  "action": "embed_image",
  "image": "base64-encoded-image-data..."
}
```

**Response:**
```json
{
  "embedding": [0.789, 0.234, ...],  // 1024 values
  "dimensions": 1024
}
```

**Use Cases:**
- Testing visual similarity
- Validating kNN image search behavior
- Image-to-image search experiments

---

### GET /listings/{zpid}

Retrieve a single property listing by Zillow Property ID (zpid).

**Endpoint:** `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}`

**Method:** `GET`

**Query Parameters:**
- `include_full_data` (boolean, optional): Include complete Zillow data from S3 (166+ fields)
- `include_nearby_places` (boolean, optional, default: true): Include nearby places from Google Places API
- `index` (string, optional, default: "listings-v2"): Target index name

**Example:**
```bash
GET /listings/448383785?include_full_data=true&index=listings-v2
```

---

### PATCH /listings/{zpid}

Update any fields in an existing listing. Supports adding custom fields dynamically.

**Endpoint:** `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}`

**Method:** `PATCH`

**Content-Type:** `application/json`

**Query Parameters:**
- `index` (string, optional, default: "listings-v2"): Target index name

**Request Body:**
```json
{
  "updates": {
    "field_name": "new_value",
    "another_field": 12345
  },
  "options": {
    "preserve_embeddings": true,
    "remove_fields": ["field_to_delete"]
  }
}
```

---

### POST /listings

Create a new listing with optional image processing and AI analysis.

**Endpoint:** `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings`

**Method:** `POST`

**Content-Type:** `application/json`

**Query Parameters:**
- `index` (string, optional, default: "listings-v2"): Target index name

**Request Body:**
```json
{
  "listing": {
    "zpid": "optional_custom_id",
    "price": 500000,
    "bedrooms": 3,
    "bathrooms": 2,
    "address": "123 Main St",
    "city": "Salt Lake City",
    "state": "UT",
    "description": "Beautiful home...",
    "images": ["url1", "url2"]
  },
  "options": {
    "process_images": true,
    "generate_embeddings": true,
    "source": "user"
  }
}
```

---

### DELETE /listings/{zpid}

Delete a listing (soft or hard delete).

**Endpoint:** `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}`

**Method:** `DELETE`

**Query Parameters:**
- `soft` (boolean, optional, default: true): If true, marks as deleted but keeps in index. If false, permanently removes.
- `index` (string, optional, default: "listings-v2"): Target index name

**Example:**
```bash
# Soft delete (mark as deleted, keep in index)
DELETE /listings/456567015?soft=true

# Hard delete (permanently remove)
DELETE /listings/456567015?soft=false
```

---

## Request Format

### Basic Request

```json
{
  "query": "granite countertops",
  "limit": 10,
  "index": "listings-v2"
}
```

### Request with Filters

```json
{
  "query": "modern homes with open floor plan",
  "limit": 20,
  "index": "listings-v2",
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
| `query` | string | Yes | - | Natural language search query |
| `limit` | integer | No | 15 | Number of results (max: 50) |
| `index` | string | No | listings-v2 | Target OpenSearch index name |
| `boost_mode` | boolean | No | false | Enable A/B testing boost mode |
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
      "llm_profile": "",  // Reserved field (always empty)
      "feature_tags": [],  // Deprecated (features now in image_tags)
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
  "query": "homes",
  "index": "listings-v2",
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
  "query": "family homes",
  "index": "listings-v2",
  "filters": {
    "beds_min": 3,
    "baths_min": 2
  }
}
```

### Combined Filters

```json
{
  "query": "granite countertops with large windows",
  "limit": 20,
  "index": "listings-v2",
  "filters": {
    "price_min": 400000,
    "price_max": 700000,
    "beds_min": 4,
    "baths_min": 2.5
  }
}
```

---

## CRUD Operations

The API provides full CRUD (Create, Read, Update, Delete) capabilities for managing property listings. All operations support **dynamic fields**, meaning you can add any custom field to any listing without predefined schema restrictions.

### Key Features

- ✅ **Schema-less**: Add any field to any listing
- ✅ **Dynamic mapping**: OpenSearch auto-detects field types
- ✅ **Immediate retrieval**: All fields returned in GET and search responses
- ✅ **No code changes**: Add custom fields without redeploying

---

### Managing For Sale/Sold Status

One of the most common use cases is managing listing status (for sale, pending, sold, etc.). Here's how to implement this:

#### Recommended Status Fields

```json
{
  "listing_status": "for_sale" | "pending" | "sold" | "off_market",
  "list_date": "2025-01-14",
  "sold_date": "2025-03-01",
  "asking_price": 500000,
  "sold_price": 525000,
  "days_on_market": 45,
  "listing_agent": "Jane Smith",
  "listing_agent_email": "jane@realty.com",
  "mls_number": "MLS123456"
}
```

#### Example: Mark Property as For Sale

```bash
curl -X PATCH https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/448383785?index=listings-v2 \
  -H 'Content-Type: application/json' \
  -d '{
    "updates": {
      "listing_status": "for_sale",
      "list_date": "2025-01-14",
      "asking_price": 500000,
      "listing_agent": "Jane Smith",
      "mls_number": "MLS123456"
    }
  }'
```

**Response:**
```json
{
  "ok": true,
  "zpid": "448383785",
  "updated_fields": ["listing_status", "list_date", "asking_price", "listing_agent", "mls_number"],
  "removed_fields": []
}
```

#### Example: Mark Property as Sold

```bash
curl -X PATCH https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/448383785?index=listings-v2 \
  -H 'Content-Type: application/json' \
  -d '{
    "updates": {
      "listing_status": "sold",
      "sold_date": "2025-03-01",
      "sold_price": 525000,
      "days_on_market": 45
    }
  }'
```

#### Example: Retrieve Listing with Status

```bash
curl https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/448383785?index=listings-v2
```

**Response includes all custom fields:**
```json
{
  "ok": true,
  "listing": {
    "zpid": "448383785",
    "price": 500000,
    "bedrooms": 3,
    "bathrooms": 2,
    "description": "Beautiful home...",

    // ✅ Custom fields automatically returned
    "listing_status": "sold",
    "list_date": "2025-01-14",
    "sold_date": "2025-03-01",
    "asking_price": 500000,
    "sold_price": 525000,
    "days_on_market": 45,
    "listing_agent": "Jane Smith",
    "mls_number": "MLS123456",

    "images": [...],
    "geo": {...}
  }
}
```

#### Example: Search Results Include Custom Fields

When you search, all custom fields are automatically included:

```bash
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"modern homes","limit":10,"index":"listings-v2"}'
```

**Each result includes custom fields:**
```json
{
  "ok": true,
  "results": [
    {
      "zpid": "448383785",
      "score": 4.5,
      "price": 500000,

      // ✅ Custom fields in search results
      "listing_status": "sold",
      "sold_date": "2025-03-01",
      "sold_price": 525000,

      // ... other fields
    }
  ]
}
```

---

### UI Implementation Example

```javascript
// Display listing status badge in UI
function renderStatusBadge(listing) {
  switch (listing.listing_status) {
    case 'sold':
      return `
        <div class="badge badge-sold">
          SOLD ${listing.sold_date}
          <br>
          Sale Price: $${listing.sold_price.toLocaleString()}
          <br>
          ${listing.days_on_market} days on market
        </div>
      `;

    case 'pending':
      return `
        <div class="badge badge-pending">
          PENDING SALE
          <br>
          Listed: ${listing.list_date}
        </div>
      `;

    case 'for_sale':
      return `
        <div class="badge badge-for-sale">
          FOR SALE
          <br>
          $${listing.asking_price.toLocaleString()}
          <br>
          Listed: ${listing.list_date}
        </div>
      `;

    default:
      return '';
  }
}

// Usage in React/Vue/vanilla JS
listings.forEach(listing => {
  const statusBadge = renderStatusBadge(listing);
  // Render badge in property card
});
```

---

### Additional Custom Field Examples

#### Example: Add Agent Contact Information

```bash
curl -X PATCH https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/448383785?index=listings-v2 \
  -H 'Content-Type: application/json' \
  -d '{
    "updates": {
      "listing_agent": "Jane Smith",
      "listing_agent_email": "jane@realty.com",
      "listing_agent_phone": "555-1234",
      "brokerage": "Premier Realty"
    }
  }'
```

#### Example: Add Open House Information

```bash
curl -X PATCH https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/448383785?index=listings-v2 \
  -H 'Content-Type: application/json' \
  -d '{
    "updates": {
      "open_house_dates": ["2025-01-20", "2025-01-21"],
      "open_house_times": "1:00 PM - 4:00 PM",
      "open_house_notes": "Refreshments served"
    }
  }'
```

#### Example: Add Property Highlights

```bash
curl -X PATCH https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/448383785?index=listings-v2 \
  -H 'Content-Type: application/json' \
  -d '{
    "updates": {
      "highlights": [
        "Recently renovated kitchen",
        "New HVAC system (2024)",
        "Solar panels installed"
      ],
      "virtual_tour_url": "https://...",
      "property_video_url": "https://..."
    }
  }'
```

---

### Important Notes

1. **All custom fields are immediately searchable** via OpenSearch (depending on field type)
2. **Field types are auto-detected**: strings become `text`, numbers become `long`/`float`, etc.
3. **Embeddings are preserved** by default when updating (no need to regenerate expensive AI vectors)
4. **Updates are atomic** - each property updated independently
5. **No schema conflicts** - dynamic fields don't conflict with predefined fields

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
  const API_URL = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search';

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query: query,
        limit: 20,
        index: 'listings-v2',
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
  const API_URL = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search';

  const payload = {
    query: query,
    limit: options.limit || 20,
    index: options.index || 'listings-v2'
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
  limit: 10,
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

def search_properties(query, filters=None, limit=20, index='listings-v2'):
    """Search properties using natural language query."""
    API_URL = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search'

    payload = {
        'query': query,
        'limit': limit,
        'index': index
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
    limit=15
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

  const API_URL = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search';

  const handleSearch = async () => {
    if (!query.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query, limit: 12, index: 'listings-v2' })
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
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"granite countertops","limit":10,"index":"listings-v2"}'

# With filters
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "modern homes with pool",
    "limit": 20,
    "index": "listings-v2",
    "filters": {
      "price_min": 400000,
      "price_max": 800000,
      "beds_min": 3,
      "baths_min": 2
    }
  }' | jq '.'

# Extract specific fields
curl -s -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"vaulted ceilings","limit":5,"index":"listings-v2"}' \
  | jq '.results[] | {price, address: .address.streetAddress, beds: .bedrooms}'
```

---

## Rate Limits & Performance

### Performance Metrics

| Metric | Value |
|--------|-------|
| **Average Response Time** | 2-5 seconds |
| **P95 Response Time** | <8 seconds |
| **Indexed Listings** | 3,904 properties (Salt Lake City, UT) |
| **Max Results Per Request** | 100 |
| **Lambda Timeout** | 300 seconds (5 minutes) |
| **API Gateway Timeout** | 30 seconds (hard limit) |

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
fetch('https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: 'granite countertops', limit: 10, index: 'listings-v2' })
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
{"query": "granite countertops", "limit": 10, "index": "listings-v2"}

// Blue exterior
{"query": "blue house", "limit": 10, "index": "listings-v2"}

// Vaulted ceilings
{"query": "vaulted ceilings", "limit": 10, "index": "listings-v2"}

// Large windows
{"query": "large windows", "limit": 10, "index": "listings-v2"}

// Open floor plan
{"query": "open floor plan", "limit": 10, "index": "listings-v2"}
```

### Complex Searches

```javascript
// Multiple features
{"query": "granite countertops with stainless steel appliances and hardwood floors", "limit": 10, "index": "listings-v2"}

// With price filter
{
  "query": "modern homes with pool",
  "limit": 15,
  "index": "listings-v2",
  "filters": {"price_max": 600000}
}

// Bedroom + bathroom requirements
{
  "query": "family homes",
  "index": "listings-v2",
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

### Version 2.0 (2025-10-15)
- ✨ **NEW**: Multi-vector image search (listings-v2 index)
- ✨ **NEW**: Unified caching system (hearth-vision-cache, hearth-text-embeddings)
- ✨ **NEW**: Parallel image processing (20x faster indexing)
- ✨ **NEW**: Salt Lake City dataset (3,904 listings)
- ✨ **NEW**: Boost mode A/B testing for visual features
- 🔧 Changed parameter names: `q` → `query`, `size` → `limit`
- 🔧 Added `index` parameter (default: listings-v2)
- 🔧 Increased Lambda timeout to 300s for complex queries
- 🔧 Enhanced Bedrock throttling protection (semaphore + retry)
- 📊 Comprehensive score breakdown with visual features
- 🚀 Performance optimizations: 50-60 listings/min indexing

### Version 1.1 (2025-01-14)
- ✨ Enhanced visual feature matching - Text embeddings now include image analysis
- ✨ `visual_features_text` field - AI-generated description from photo analysis
- 📚 Complete CRUD API documentation
- 📚 For Sale/Sold status management guide
- 🔧 Improved BM25 search with visual features (weight: 2.5)
- 🔧 Enhanced kNN text search includes visual characteristics

### Version 1.0 (2025-10-13)
- Initial production release
- 1,588 listings indexed (Murray, UT)
- AI vision analysis active
- CORS enabled
- Full natural language support
