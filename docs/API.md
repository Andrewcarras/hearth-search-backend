# Hearth Search API Documentation

## Base URL
```
https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod
```

## Endpoints

### 1. Search Listings

**Endpoint:** `POST /search`

**Description:** Natural language search for real estate listings with AI-powered understanding of user intent.

**Request Body:**
```json
{
  "q": "Show me homes with a balcony and modern architecture",
  "size": 10
}
```

**Parameters:**
- `q` (string, required): Natural language search query
- `size` (number, optional): Number of results to return (default: 30, max: 100)

**Response:**
```json
{
  "ok": true,
  "results": [
    {
      "id": "2059116964",
      "score": 13.055,
      "boosted": false,
      "address": "3883 S Komenda Ct #1",
      "city": "Salt Lake City",
      "state": "UT",
      "zip_code": "84124",
      "price": 2400,
      "beds": 2.0,
      "baths": 4.0,
      "acreage": null,
      "description": "BEAUTIFUL 3-level condo...",
      "llm_profile": "Beautiful 3-level condo with...",
      "feature_tags": ["fireplace", "garage", "mountain_view"],
      "image_tags": [],
      "architecture_style": "modern",
      "geo": {
        "lat": 40.68745,
        "lon": -111.85004
      }
    }
  ]
}
```

**Response Fields:**
- `ok` (boolean): Success indicator
- `results` (array): Array of matching listings
  - `id` (string): Zillow property ID (zpid)
  - `score` (number): Relevance score
  - `boosted` (boolean): Whether result was boosted for having required features
  - `address`, `city`, `state`, `zip_code`: Property location
  - `price` (number): Monthly rent or sale price
  - `beds`, `baths` (number): Number of bedrooms and bathrooms
  - `acreage` (number|null): Lot size in acres
  - `description` (string): Full property description
  - `llm_profile` (string): AI-generated concise summary
  - `feature_tags` (array): Extracted features (fireplace, garage, pool, etc.)
  - `image_tags` (array): Visual features from image analysis
  - `architecture_style` (string|null): Detected architecture style
  - `geo` (object): Geographic coordinates

**Example Queries:**
```javascript
// Simple text search
{
  "q": "2 bedroom apartments in Salt Lake City",
  "size": 20
}

// Feature-based search
{
  "q": "homes with a pool and mountain views",
  "size": 10
}

// Architecture style search
{
  "q": "craftsman style homes with a front porch",
  "size": 15
}

// Proximity search
{
  "q": "homes near elementary schools",
  "size": 25
}

// Combined search
{
  "q": "modern homes with a balcony, white fence, and attached garage under $500k",
  "size": 10
}
```

---

### 2. Upload Listings

**Endpoint:** `POST /upload`

**Description:** Index new listings or re-index existing listings with multimodal embeddings.

**Request Body (S3 Source):**
```json
{
  "bucket": "my-bucket",
  "key": "listings.json",
  "start": 0,
  "limit": 500
}
```

**Request Body (Direct Listings):**
```json
{
  "listings": [
    {
      "zpid": "123456789",
      "address": "123 Main St",
      "city": "Salt Lake City",
      "state": "UT",
      "price": 350000,
      "beds": 3,
      "baths": 2,
      "description": "Beautiful home...",
      "imgSrc": ["https://example.com/img1.jpg"]
    }
  ],
  "start": 0,
  "limit": 100
}
```

**Parameters:**
- **S3 Mode:**
  - `bucket` (string): S3 bucket name
  - `key` (string): S3 object key (JSON file)
  - `start` (number, optional): Starting index (default: 0)
  - `limit` (number, optional): Max listings to process (default: 500)

- **Direct Mode:**
  - `listings` (array): Array of listing objects
  - `start` (number, optional): Starting index within array
  - `limit` (number, optional): Max listings to process

**Response:**
```json
{
  "statusCode": 200,
  "body": {
    "ok": true,
    "index": "listings",
    "batch": {
      "start": 0,
      "processed": 500,
      "limit": 500
    },
    "next_start": 500,
    "total": 1588,
    "has_more": true
  }
}
```

**Response Fields:**
- `ok` (boolean): Success indicator
- `index` (string): OpenSearch index name
- `batch` (object): Batch processing details
  - `start`: Starting index of this batch
  - `processed`: Number of listings processed
  - `limit`: Requested batch size
- `next_start` (number|null): Starting index for next batch (if has_more)
- `total` (number): Total listings in dataset
- `has_more` (boolean): Whether more listings remain

**Notes:**
- Lambda auto-invokes itself for large datasets exceeding 15-minute timeout
- Each listing is processed with:
  - Text embeddings (Bedrock Titan)
  - Image embeddings (Bedrock Titan Multimodal)
  - Architecture style classification (Claude Vision)
  - Visual feature detection (balconies, fences, porches, etc.)
- Listings are upserted by zpid (duplicates update existing records)

---

## CORS Configuration

The API has CORS enabled with the following settings:
- **Allowed Origins:** `*` (all origins)
- **Allowed Methods:** `GET`, `POST`, `OPTIONS`
- **Allowed Headers:** `*` (all headers)

---

## Error Responses

**400 Bad Request:**
```json
{
  "error": "missing 'q'"
}
```

**500 Internal Server Error:**
```json
{
  "error": "Internal server error message"
}
```

---

## Frontend Integration Examples

### React/TypeScript Example

```typescript
// api/hearth.ts
const API_BASE = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod';

export interface SearchResult {
  id: string;
  score: number;
  boosted: boolean;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  price: number;
  beds: number;
  baths: number;
  acreage: number | null;
  description: string;
  llm_profile: string;
  feature_tags: string[];
  image_tags: string[];
  architecture_style: string | null;
  geo: {
    lat: number;
    lon: number;
  };
}

export interface SearchResponse {
  ok: boolean;
  results: SearchResult[];
}

export async function searchListings(
  query: string,
  size: number = 20
): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ q: query, size }),
  });

  if (!response.ok) {
    throw new Error(`Search failed: ${response.statusText}`);
  }

  return response.json();
}

// Usage in component
import { searchListings } from './api/hearth';

function SearchComponent() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (query: string) => {
    setLoading(true);
    try {
      const data = await searchListings(query, 20);
      setResults(data.results);
    } catch (error) {
      console.error('Search error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="text"
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            handleSearch(e.currentTarget.value);
          }
        }}
        placeholder="Search homes..."
      />
      {loading && <p>Searching...</p>}
      {results.map((result) => (
        <div key={result.id}>
          <h3>{result.address}</h3>
          <p>{result.llm_profile}</p>
          <p>${result.price} • {result.beds} beds • {result.baths} baths</p>
          {result.architecture_style && (
            <span>Style: {result.architecture_style}</span>
          )}
        </div>
      ))}
    </div>
  );
}
```

### Vanilla JavaScript Example

```javascript
// Simple search function
async function searchHomes(query) {
  const response = await fetch(
    'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        q: query,
        size: 20
      })
    }
  );

  const data = await response.json();
  return data.results;
}

// Usage
searchHomes('homes with a pool and mountain views')
  .then(results => {
    results.forEach(home => {
      console.log(`${home.address} - $${home.price}`);
      console.log(`Features: ${home.feature_tags.join(', ')}`);
    });
  })
  .catch(error => console.error('Search failed:', error));
```

### cURL Example

```bash
# Search for listings
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H "Content-Type: application/json" \
  -d '{
    "q": "craftsman homes with a front porch",
    "size": 10
  }'

# Upload listings from S3
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/upload \
  -H "Content-Type: application/json" \
  -d '{
    "bucket": "my-bucket",
    "key": "listings.json",
    "start": 0,
    "limit": 500
  }'
```

---

## Search Capabilities

The search API understands natural language queries and can extract:

### Architecture Styles
- Modern, Contemporary, Craftsman, Victorian, Colonial
- Ranch, Mediterranean, Tudor, Georgian
- Mid-century modern, Farmhouse, Cape Cod
- And 15+ more styles

### Visual Features
- Balconies, porches, decks, patios
- Fences (wood, white, iron, vinyl, chain-link)
- Garages (attached, detached, 1-car, 2-car, 3-car)
- Exterior colors and materials
- Windows, shutters, columns

### Property Features
- Pool, fireplace, mountain views
- Hardwood floors, granite counters
- Open floor plan, vaulted ceilings
- And 100+ more features

### Proximity Search
- "near elementary schools"
- "within 10 minutes of downtown"
- "close to grocery stores and gyms"

### Price & Size Filters
- "under $500k"
- "3 bedrooms"
- "at least 2 baths"

---

## Rate Limits

- No enforced rate limits currently
- Recommended: Max 10 requests/second per client
- Upload endpoint: Use for batch processing only (not user-triggered)

---

## Support

For API issues or questions:
- GitHub: [hearth-search-backend](https://github.com/Andrewcarras/hearth-search-backend)
- Issues: [Report an issue](https://github.com/Andrewcarras/hearth-search-backend/issues)
