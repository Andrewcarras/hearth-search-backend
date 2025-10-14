# API Quick Reference

**Base URL:** `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod`

## Endpoints

### 🔍 Search Listings
```bash
POST /search
{
  "q": "3 bedroom house with granite countertops",
  "size": 10,
  "include_full_data": false,
  "include_nearby_places": true
}
```

### 📖 Get Single Listing
```bash
GET /listings/{zpid}?include_full_data=true&include_nearby_places=true
```

### ➕ Create Listing
```bash
POST /listings
{
  "listing": {
    "zpid": "custom_12345",  # optional - auto-generated if not provided
    "description": "Beautiful property",
    "price": 350000,
    "bedrooms": 3,
    "bathrooms": 2.5,
    ...any fields...
  },
  "options": {
    "source": "manual",
    "process_images": false  # set true to generate embeddings
  }
}
```

### ✏️ Update Listing
```bash
PATCH /listings/{zpid}
{
  "updates": {
    "price": 400000,
    "custom_field": "any value",
    ...any fields...
  },
  "options": {
    "remove_fields": ["field_to_delete"]  # optional
  }
}
```

### 🗑️ Delete Listing
```bash
# Soft delete (mark as deleted, keep data)
DELETE /listings/{zpid}?soft=true

# Hard delete (permanent removal)
DELETE /listings/{zpid}?soft=false
```

## cURL Examples

### Search
```bash
curl -X POST 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search' \
  -H 'Content-Type: application/json' \
  -d '{"q":"granite countertops","size":5}'
```

### Get Listing
```bash
curl 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12753836'
```

### Create Listing
```bash
curl -X POST 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings' \
  -H 'Content-Type: application/json' \
  -d '{
    "listing": {
      "description": "Test property",
      "price": 350000
    },
    "options": {"source": "manual"}
  }'
```

### Update Listing
```bash
curl -X PATCH 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345' \
  -H 'Content-Type: application/json' \
  -d '{"updates":{"price":400000}}'
```

### Delete Listing
```bash
# Soft delete
curl -X DELETE 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345?soft=true'

# Hard delete
curl -X DELETE 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345?soft=false'
```

## JavaScript/Frontend Examples

### Search
```javascript
const response = await fetch('https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    q: 'modern home with pool',
    size: 10,
    include_nearby_places: true
  })
});
const data = await response.json();
```

### Get Listing
```javascript
const response = await fetch(
  'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345?include_full_data=true'
);
const { listing } = await response.json();
```

### Create Listing
```javascript
const response = await fetch('https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    listing: {
      description: 'Beautiful property',
      price: 350000,
      bedrooms: 3,
      bathrooms: 2
    },
    options: { source: 'manual' }
  })
});
const data = await response.json();
```

### Update Listing
```javascript
const response = await fetch('https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345', {
  method: 'PATCH',
  headers: { 'Content-Type': application/json' },
  body: JSON.stringify({
    updates: {
      price: 400000,
      status: 'sold'
    }
  })
});
const data = await response.json();
```

### Delete Listing
```javascript
// Soft delete
const response = await fetch(
  'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345?soft=true',
  { method: 'DELETE' }
);

// Hard delete
const response = await fetch(
  'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345?soft=false',
  { method: 'DELETE' }
);
```

## Response Formats

### Search Response
```json
{
  "ok": true,
  "results": [
    {
      "zpid": "12345",
      "price": 350000,
      "bedrooms": 3,
      "description": "...",
      "image_tags": ["granite", "hardwood", ...],
      "nearby_places": [{...}, ...],
      "score": 4.5
    },
    ...
  ],
  "total": 150,
  "must_have": ["granite"]
}
```

### Get Listing Response
```json
{
  "ok": true,
  "listing": {
    "zpid": "12345",
    "price": 350000,
    ...all fields...,
    "nearby_places": [...],
    "original_listing": {...}  // if include_full_data=true
  }
}
```

### Create Response
```json
{
  "ok": true,
  "zpid": "12345",
  "indexed": true,
  "processing_cost": 0.0001,
  "images_processed": 0
}
```

### Update Response
```json
{
  "ok": true,
  "zpid": "12345",
  "updated_fields": ["price", "custom_field"],
  "removed_fields": []
}
```

### Delete Response
```json
{
  "ok": true,
  "zpid": "12345",
  "deleted": true,
  "soft_delete": true
}
```

## Admin UI

**Location:** `/Users/andrewcarras/hearth_backend_new/admin_ui/index.html`

Open in browser to test all endpoints with a beautiful UI!

```bash
open /Users/andrewcarras/hearth_backend_new/admin_ui/index.html
```
