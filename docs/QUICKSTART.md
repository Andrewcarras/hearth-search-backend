# Frontend Integration - Quick Start

## API Endpoint
```
https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search
```

## Simplest Example (1 minute setup)

### JavaScript/TypeScript
```javascript
// Search for homes
const response = await fetch(
  'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search',
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      q: "homes with a pool and mountain views",
      size: 20
    })
  }
);

const data = await response.json();
console.log(data.results); // Array of matching homes
```

### What You Get Back
```javascript
{
  ok: true,
  results: [
    {
      id: "2059116964",
      score: 13.055,
      address: "3883 S Komenda Ct #1",
      city: "Salt Lake City",
      state: "UT",
      zip_code: "84124",
      price: 2400,
      beds: 2.0,
      baths: 4.0,
      description: "BEAUTIFUL 3-level condo...",
      llm_profile: "Beautiful 3-level condo with...",
      feature_tags: ["fireplace", "garage", "mountain_view"],
      architecture_style: "modern",
      geo: { lat: 40.68745, lon: -111.85004 }
    },
    // ... more results
  ]
}
```

## Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | Yes | - | Natural language search query |
| `size` | number | No | 30 | Number of results (max 100) |

## Example Queries

```javascript
// Simple search
{ q: "2 bedroom apartments", size: 10 }

// Feature search
{ q: "homes with a balcony and fireplace", size: 15 }

// Architecture search
{ q: "craftsman style homes", size: 20 }

// Price filter
{ q: "homes under $500k with 3 bedrooms", size: 25 }

// Proximity search
{ q: "homes near elementary schools", size: 20 }

// Complex search
{ q: "modern homes with a pool, mountain views, and attached garage", size: 10 }
```

## React Hook Example

```typescript
// hooks/useHearthSearch.ts
import { useState } from 'react';

interface SearchResult {
  id: string;
  address: string;
  city: string;
  state: string;
  price: number;
  beds: number;
  baths: number;
  description: string;
  llm_profile: string;
  feature_tags: string[];
  architecture_style: string | null;
}

export function useHearthSearch() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async (query: string, size: number = 20) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ q: query, size })
        }
      );

      if (!response.ok) {
        throw new Error('Search failed');
      }

      const data = await response.json();
      setResults(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return { results, loading, error, search };
}

// Usage in component
function SearchPage() {
  const { results, loading, error, search } = useHearthSearch();

  return (
    <div>
      <input
        type="text"
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            search(e.currentTarget.value);
          }
        }}
        placeholder="Search homes..."
      />

      {loading && <p>Searching...</p>}
      {error && <p>Error: {error}</p>}

      {results.map((home) => (
        <div key={home.id}>
          <h3>{home.address}, {home.city}</h3>
          <p>{home.llm_profile}</p>
          <p>${home.price} • {home.beds} beds • {home.baths} baths</p>
          {home.architecture_style && (
            <span>Style: {home.architecture_style}</span>
          )}
          <div>
            {home.feature_tags.map(tag => (
              <span key={tag} className="tag">{tag}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

## Search Understanding

The AI understands natural language and extracts:

### Architecture Styles
Modern, Craftsman, Victorian, Colonial, Ranch, Mediterranean, Tudor, Contemporary, and 20+ more

### Visual Features
- Balconies, porches, decks, patios
- Fences (wood, white, iron, chain-link)
- Garages (attached, detached, 1-car, 2-car)
- Windows, shutters, columns

### Property Features
Pools, fireplaces, mountain views, hardwood floors, granite counters, vaulted ceilings, open floor plans, and 100+ more

### Smart Filters
- Price: "under $500k", "between $300k and $600k"
- Beds/Baths: "3 bedrooms", "at least 2 baths"
- Proximity: "near schools", "within 10 minutes of downtown"

## CORS

CORS is enabled for all origins - no special configuration needed.

## Need More?

See [docs/API.md](./API.md) for complete documentation.

## Test It Now

```bash
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H "Content-Type: application/json" \
  -d '{"q": "craftsman homes with a front porch", "size": 5}'
```
