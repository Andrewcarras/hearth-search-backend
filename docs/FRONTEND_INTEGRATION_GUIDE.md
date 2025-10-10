# Frontend Integration Guide

Quick start guide for integrating the Hearth Search API into your frontend application.

## TL;DR - Copy & Paste

```typescript
// 1. API endpoint
const API_URL = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search';

// 2. Search function
async function searchHomes(query: string, size: number = 20) {
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q: query, size })
  });
  return response.json();
}

// 3. Use it
const data = await searchHomes('3 bedroom homes near a grocery store', 20);
console.log(data.results); // Array of listings with nearby_places
```

## What You Get Back

Each search result contains:

1. **Complete Zillow Data** (214 fields) - all original listing info
2. **Hearth AI Tags** - detected features, architecture style, image analysis
3. **Nearby Places** - grocery stores, gyms, schools, restaurants within ~1km

### Example Result Object

```json
{
  "id": "2059116964",
  "zpid": "2059116964",
  "price": 450000,
  "bedrooms": 3,
  "bathrooms": 2,
  "address": {
    "streetAddress": "123 Main St",
    "city": "Salt Lake City",
    "state": "UT",
    "zipcode": "84124"
  },
  "images": ["https://...jpg", "https://...jpg"],
  "description": "Beautiful home...",

  // Hearth AI
  "feature_tags": ["pool", "garage", "fireplace"],
  "architecture_style": "modern",
  "nearby_places": [
    {"name": "Smith's Grocery", "types": ["grocery_store", "supermarket"]},
    {"name": "Gold's Gym", "types": ["gym", "fitness_center"]},
    {"name": "Holladay Elementary", "types": ["school"]}
  ]
}
```

## React Component Example

```tsx
import React, { useState } from 'react';

const API_URL = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search';

interface NearbyPlace {
  name: string;
  types: string[];
}

interface SearchResult {
  id: string;
  price: number;
  bedrooms?: number;
  beds?: number;
  bathrooms?: number;
  baths?: number;
  address?: any;
  images?: string[];
  feature_tags?: string[];
  architecture_style?: string;
  nearby_places?: NearbyPlace[];
}

export function PropertySearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;

    setLoading(true);
    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ q: query, size: 20 })
      });

      const data = await response.json();
      setResults(data.results || []);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="search-bar">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="Search homes (e.g., '3 bedroom homes near a grocery store')"
        />
        <button onClick={handleSearch} disabled={loading}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      <div className="results">
        {results.map((home) => (
          <PropertyCard key={home.id} home={home} />
        ))}
      </div>
    </div>
  );
}

function PropertyCard({ home }: { home: SearchResult }) {
  // Handle field name variations
  const beds = home.bedrooms || home.beds || 0;
  const baths = home.bathrooms || home.baths || 0;
  const address = typeof home.address === 'string'
    ? home.address
    : home.address?.streetAddress || '';

  // Get nearby grocery stores
  const groceryStores = home.nearby_places?.filter(p =>
    p.types.includes('grocery_store') || p.types.includes('supermarket')
  ) || [];

  return (
    <div className="property-card">
      {home.images?.[0] && (
        <img src={home.images[0]} alt={address} />
      )}

      <h3>{address}</h3>
      <p className="price">${home.price.toLocaleString()}</p>
      <p>{beds} beds • {baths} baths</p>

      {home.architecture_style && (
        <span className="badge">{home.architecture_style}</span>
      )}

      {home.feature_tags && home.feature_tags.length > 0 && (
        <div className="features">
          {home.feature_tags.slice(0, 5).map(tag => (
            <span key={tag} className="tag">{tag}</span>
          ))}
        </div>
      )}

      {groceryStores.length > 0 && (
        <div className="nearby">
          <strong>🛒 Nearby Groceries:</strong>
          {groceryStores.slice(0, 2).map((store, idx) => (
            <span key={idx}> {store.name}</span>
          ))}
        </div>
      )}
    </div>
  );
}
```

## Common Use Cases

### 1. Search with Filters

```typescript
const response = await fetch(API_URL, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    q: 'modern homes with pool',
    size: 20,
    filters: {
      price_min: 300000,
      price_max: 750000,
      beds_min: 3,
      baths_min: 2
    }
  })
});
```

### 2. Show Homes with Specific Nearby Places

```typescript
// Filter results that have grocery stores nearby
const homesNearGrocery = results.filter(home =>
  home.nearby_places?.some(p =>
    p.types.includes('grocery_store') || p.types.includes('supermarket')
  )
);

// Count nearby amenities
const amenityCounts = {
  grocery: result.nearby_places?.filter(p =>
    p.types.includes('grocery_store')).length || 0,
  gym: result.nearby_places?.filter(p =>
    p.types.includes('gym')).length || 0,
  school: result.nearby_places?.filter(p =>
    p.types.includes('school')).length || 0,
};
```

### 3. Display Nearby Places by Category

```typescript
function categorizeNearbyPlaces(places: NearbyPlace[]) {
  const categories = {
    grocery: [] as NearbyPlace[],
    fitness: [] as NearbyPlace[],
    education: [] as NearbyPlace[],
    dining: [] as NearbyPlace[],
    other: [] as NearbyPlace[]
  };

  places?.forEach(place => {
    if (place.types.includes('grocery_store') || place.types.includes('supermarket')) {
      categories.grocery.push(place);
    } else if (place.types.includes('gym') || place.types.includes('fitness_center')) {
      categories.fitness.push(place);
    } else if (place.types.includes('school')) {
      categories.education.push(place);
    } else if (place.types.includes('restaurant') || place.types.includes('cafe')) {
      categories.dining.push(place);
    } else {
      categories.other.push(place);
    }
  });

  return categories;
}

// Usage
const categories = categorizeNearbyPlaces(home.nearby_places);
```

### 4. Debounced Search Input

```typescript
import { useState, useCallback } from 'react';
import debounce from 'lodash/debounce';

function SearchInput() {
  const [results, setResults] = useState([]);

  const debouncedSearch = useCallback(
    debounce(async (query: string) => {
      if (query.length < 3) return;

      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ q: query, size: 20 })
      });
      const data = await response.json();
      setResults(data.results);
    }, 500),
    []
  );

  return (
    <input
      type="text"
      onChange={(e) => debouncedSearch(e.target.value)}
      placeholder="Search..."
    />
  );
}
```

## Important Field Mappings

### Address (can be string OR object)

```typescript
// Safe way to get address components
function getAddress(result: SearchResult) {
  if (typeof result.address === 'string') {
    return {
      full: result.address,
      city: result.city || '',
      state: result.state || '',
      zip: result.zip_code || ''
    };
  }

  return {
    full: result.address?.streetAddress || '',
    city: result.address?.city || result.city || '',
    state: result.address?.state || result.state || '',
    zip: result.address?.zipcode || result.zip_code || ''
  };
}
```

### Images (multiple sources)

```typescript
function getImages(result: SearchResult): string[] {
  // Priority 1: Hearth's deduplicated images
  if (result.images && result.images.length > 0) {
    return result.images;
  }

  // Priority 2: Zillow carousel
  if (result.carouselPhotosComposable) {
    return result.carouselPhotosComposable
      .map(p => p.image || p.url)
      .filter(Boolean);
  }

  // Priority 3: Main thumbnail
  if (result.imgSrc) {
    return [result.imgSrc];
  }

  return [];
}
```

### Beds/Baths (inconsistent field names)

```typescript
const beds = result.bedrooms || result.beds || 0;
const baths = result.bathrooms || result.baths || 0;
```

## Performance Best Practices

1. **Debounce user input** - Wait 300-500ms after user stops typing
2. **Use reasonable page sizes** - Default 20-30 results (max 100)
3. **Cache results** - Store in React state/Redux to avoid re-fetching
4. **Show loading states** - Search takes 300-800ms depending on cache
5. **Handle errors gracefully** - Network issues, API errors, etc.

## TypeScript Type Definitions

```typescript
export interface NearbyPlace {
  name: string;
  types: string[];
}

export interface SearchResult {
  // Metadata
  id: string;
  score: number;
  boosted: boolean;

  // Zillow core (50+ more fields available)
  zpid: string;
  price: number;
  bedrooms?: number;
  beds?: number;
  bathrooms?: number;
  baths?: number;
  livingArea?: number;
  lotSize?: number;
  yearBuilt?: number;
  description?: string;
  hdpUrl?: string;

  // Address (can be string or object!)
  address?: string | {
    streetAddress?: string;
    city?: string;
    state?: string;
    zipcode?: string;
  };

  // Images
  imgSrc?: string;
  images?: string[];
  carouselPhotosComposable?: Array<{
    image?: string;
    url?: string;
  }>;

  // Hearth AI
  llm_profile?: string;
  feature_tags?: string[];
  image_tags?: string[];
  architecture_style?: string;
  nearby_places?: NearbyPlace[];

  // Geo
  geo?: {
    lat: number;
    lon: number;
  };

  // Fallback fields
  city?: string;
  state?: string;
  zip_code?: string;
}

export interface SearchResponse {
  ok: boolean;
  results: SearchResult[];
  total: number;
  must_have?: string[];
  error?: string;
}
```

## Testing the API

### Quick cURL Test

```bash
curl -X POST https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search \
  -H "Content-Type: application/json" \
  -d '{"q":"homes near a grocery store","size":5}'
```

### Browser Console Test

```javascript
fetch('https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ q: '3 bedroom homes', size: 5 })
})
  .then(r => r.json())
  .then(data => console.log(data.results));
```

## Common Questions

**Q: How do I filter by nearby places?**
A: Filter client-side after getting results. Example:
```typescript
results.filter(r => r.nearby_places?.some(p =>
  p.types.includes('grocery_store')
))
```

**Q: Why are some fields missing?**
A: Not all Zillow listings have all fields. Always use optional chaining (`?.`) and fallbacks.

**Q: How long does search take?**
A: 300-800ms. First search with nearby places ~800ms, cached searches ~300ms.

**Q: Can I paginate results?**
A: The API doesn't support offset pagination yet. Use the `size` parameter to get more results (max 100).

**Q: How accurate are the nearby places?**
A: Within ~1km radius using Google Places API (New). Data is cached in DynamoDB for performance.

**Q: What if a field has both `bedrooms` and `beds`?**
A: Use `bedrooms` first, fallback to `beds`: `result.bedrooms || result.beds`

## Need Help?

- **API Documentation**: [docs/API.md](./API.md)
- **Example Queries**: [docs/EXAMPLE_QUERIES.md](./EXAMPLE_QUERIES.md)
- **Live UI Demo**: http://50.17.10.169
- **API Endpoint**: https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search

## Quick Tips

✅ **DO**:
- Use debounced search inputs
- Handle both string and object address formats
- Check for `nearby_places` existence before rendering
- Use fallback values for optional fields
- Cache results to avoid duplicate API calls

❌ **DON'T**:
- Don't assume all fields are present
- Don't request more than 100 results at once
- Don't ignore the `ok` field in responses
- Don't make API calls on every keystroke (use debounce!)
