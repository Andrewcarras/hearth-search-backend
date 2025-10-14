# Hearth Real Estate Search API - Complete Documentation

## Overview

The Hearth API provides comprehensive property search and management capabilities with:
- ✅ Advanced hybrid search (BM25 + kNN text + kNN image embeddings)
- ✅ Full CRUD operations for listing management
- ✅ Automatic field propagation (any new field is immediately searchable)
- ✅ Optional full Zillow data merging from S3
- ✅ Geolocation enrichment with nearby places

## Base URL

```
Production: https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod
```

## Authentication

Currently using API Gateway without authentication. Add API key or Cognito in production.

---

## Search & Retrieval Endpoints

### 1. Search Listings

**Endpoint:** `POST /search`

**Description:** Natural language property search with hybrid ranking

**Request Body:**
```json
{
  "q": "modern home with granite countertops",
  "size": 15,
  "include_full_data": false,
  "include_nearby_places": true,
  "filters": {
    "price_min": 300000,
    "price_max": 600000,
    "beds_min": 3,
    "architecture_style": "modern"
  }
}
```

**Parameters:**
- `q` (required): Search query string
- `size` (optional): Number of results (default: 15)
- `include_full_data` (optional): Merge full Zillow JSON from S3 (default: false)
- `include_nearby_places` (optional): Add nearby places enrichment (default: true)
- `filters` (optional): Hard filters for price, beds, baths, etc.

**Response:**
```json
{
  "ok": true,
  "results": [
    {
      "zpid": "12345",
      "score": 8.5,
      "boosted": true,

      // OpenSearch fields (always included)
      "price": 500000,
      "beds": 3,
      "baths": 2,
      "address": "123 Main St",
      "city": "Salt Lake City",
      "description": "Beautiful home...",
      "image_tags": ["granite countertops", "hardwood floors"],
      "architecture_style": "modern",

      // Custom fields (if added via CRUD)
      "hoa_fees": 250,
      "virtual_tour_url": "https://...",

      // Full Zillow data (if include_full_data=true)
      "original_listing": {
        "responsivePhotos": [...],
        "zestimate": 485000,
        "taxHistory": [...]
      },

      // Nearby places (if include_nearby_places=true)
      "nearby_places": [
        {"name": "Whole Foods", "distance": 0.8}
      ]
    }
  ],
  "total": 15,
  "must_have": ["granite", "modern"]
}
```

**Status Codes:**
- `200`: Success
- `400`: Missing or invalid query parameter

---

### 2. Get Single Listing

**Endpoint:** `GET /listings/{zpid}`

**Description:** Fetch complete data for a specific listing

**Query Parameters:**
- `include_full_data` (optional): Include S3 Zillow data (default: false)
- `include_nearby_places` (optional): Add geolocation data (default: true)

**Example:**
```
GET /listings/12345?include_full_data=true&include_nearby_places=true
```

**Response:**
```json
{
  "ok": true,
  "listing": {
    "zpid": "12345",
    "price": 500000,
    // ... all OpenSearch fields ...
    "original_listing": { /* Zillow data */ },
    "nearby_places": [ /* geolocation */ ]
  }
}
```

**Status Codes:**
- `200`: Success
- `404`: Listing not found
- `400`: Missing zpid

**Use Cases:**
- Property detail page
- Edit form pre-fill
- Data export

---

## CRUD Endpoints (Admin/Agent Operations)

### 3. Update Listing

**Endpoint:** `PATCH /listings/{zpid}`

**Description:** Update any fields in an existing listing

**Request Body:**
```json
{
  "updates": {
    "price": 450000,
    "status": "sold",
    "hoa_fees": 250,
    "custom_tags": ["motivated seller"],
    "virtual_tour_url": "https://tour.example.com"
  },
  "options": {
    "preserve_embeddings": true,
    "remove_fields": ["old_field"]
  }
}
```

**Parameters:**
- `updates` (required): Object with fields to update/add
  - Can update ANY existing field
  - Can add completely NEW fields
  - New fields automatically become searchable
- `options.preserve_embeddings` (optional): Don't regenerate vectors (default: true)
- `options.remove_fields` (optional): Array of field names to delete

**Response:**
```json
{
  "ok": true,
  "zpid": "12345",
  "updated_fields": ["price", "status", "hoa_fees"],
  "removed_fields": ["old_field"]
}
```

**Status Codes:**
- `200`: Success
- `404`: Listing not found
- `400`: Invalid request

**Cost:** ~$0 (no LLM calls unless regenerating embeddings)

**Use Cases:**
- Update price
- Mark as sold/pending
- Add HOA fees, virtual tours, agent notes
- Bulk price adjustments

---

### 4. Create Listing

**Endpoint:** `POST /listings`

**Description:** Add a new listing to the index

**Request Body:**
```json
{
  "listing": {
    "zpid": "optional_custom_id",
    "price": 500000,
    "beds": 3,
    "baths": 2,
    "address": "123 New St",
    "city": "Salt Lake City",
    "state": "UT",
    "zip": "84101",
    "description": "Beautiful new listing...",
    "images": [
      "https://example.com/photo1.jpg",
      "https://example.com/photo2.jpg"
    ],
    "source": "user",
    "custom_field": "any_value"
  },
  "options": {
    "process_images": true,
    "generate_embeddings": true,
    "source": "user"
  }
}
```

**Parameters:**
- `listing` (required): All listing data
  - `zpid` (optional): Auto-generated if not provided
  - Include ANY fields you want
- `options.process_images` (optional): Run vision analysis (default: false)
  - Downloads images, generates embeddings, extracts features
  - Cost: ~$0.0105 per listing (10 images)
- `options.generate_embeddings` (optional): Generate text embeddings (default: true)
  - Cost: ~$0.0001
- `options.source` (optional): Track origin (user/zillow/mls)

**Response:**
```json
{
  "ok": true,
  "zpid": "custom_abc123def456",
  "indexed": true,
  "processing_cost": 0.0106,
  "images_processed": 10
}
```

**Status Codes:**
- `201`: Created successfully
- `409`: Listing already exists
- `400`: Invalid request

**Cost Breakdown:**
```
Without image processing: $0.0001 (text embedding only)
With image processing:    $0.0106 (10 images + embeddings + vision)
```

**Use Cases:**
- Agent uploads new listing
- Import from external source
- Manual data entry

---

### 5. Delete Listing

**Endpoint:** `DELETE /listings/{zpid}`

**Description:** Remove listing from search results

**Query Parameters:**
- `soft` (optional): Soft delete vs hard delete (default: true)

**Examples:**
```
DELETE /listings/12345?soft=true   # Mark as deleted (default)
DELETE /listings/12345?soft=false  # Permanently remove
```

**Response:**
```json
{
  "ok": true,
  "zpid": "12345",
  "deleted": true,
  "soft_delete": true
}
```

**Soft Delete:**
- Sets `status: "deleted"` and `searchable: false`
- Keeps document in index
- Can be restored by updating status
- Preserves history

**Hard Delete:**
- Permanently removes from OpenSearch
- Cannot be recovered
- Use with caution

**Status Codes:**
- `200`: Success
- `404`: Listing not found
- `400`: Missing zpid

**Cost:** ~$0

---

## Lambda Function Mapping

### Existing Functions

1. **hearth-search** (`search.py`)
   - Handler: `search.handler` → POST /search
   - Handler: `search.get_listing_handler` → GET /listings/{zpid}

2. **hearth-upload-listings** (`upload_listings.py`)
   - Handler: `upload_listings.handler` → Batch indexing (internal)

### New Functions (To Be Created)

3. **hearth-crud-update** (`crud_listings.py`)
   - Handler: `crud_listings.update_listing_handler` → PATCH /listings/{zpid}

4. **hearth-crud-create** (`crud_listings.py`)
   - Handler: `crud_listings.add_listing_handler` → POST /listings

5. **hearth-crud-delete** (`crud_listings.py`)
   - Handler: `crud_listings.delete_listing_handler` → DELETE /listings/{zpid}

---

## API Gateway Configuration Needed

```
Resource: /listings
├─ POST → hearth-crud-create (add_listing_handler)
├─ GET → (list all - future)

Resource: /listings/{zpid}
├─ GET → hearth-search (get_listing_handler)
├─ PATCH → hearth-crud-update (update_listing_handler)
├─ DELETE → hearth-crud-delete (delete_listing_handler)

Resource: /search
├─ POST → hearth-search (handler)
```

---

## Automatic Field Propagation

**Key Feature:** ANY field added via CRUD is automatically searchable!

**How it works:**
```python
# search.py line 693-695
for k, v in src.items():
    if k not in ("vector_text", "vector_image"):
        result[k] = v  # ← Includes ALL fields
```

**Example:**
```javascript
// 1. Add custom field
PATCH /listings/12345
{
  "updates": { "virtual_tour_url": "https://tour.example.com" }
}

// 2. Search automatically returns it
POST /search { "q": "modern home" }
→ Results include "virtual_tour_url" field!

// 3. Frontend uses it immediately
<a href={listing.virtual_tour_url}>Take Virtual Tour</a>
```

**No backend code changes needed for new fields!**

---

## Frontend Integration Examples

### React/Next.js Examples

#### Search with Options
```javascript
const searchListings = async (query, options = {}) => {
  const response = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      q: query,
      size: options.size || 20,
      include_full_data: options.fullData || false,
      include_nearby_places: options.nearby ?? true,
      filters: options.filters || {}
    })
  });

  return await response.json();
};

// Lightweight search for list view
const results = await searchListings("granite countertops", {
  size: 20,
  fullData: false  // Fast
});

// Detailed search for map view
const detailedResults = await searchListings("granite countertops", {
  size: 10,
  fullData: true,  // Includes 166+ Zillow fields
  nearby: true
});
```

#### Get Listing Detail
```javascript
const getListingDetail = async (zpid) => {
  const response = await fetch(
    `${API_BASE}/listings/${zpid}?include_full_data=true`,
    { method: 'GET' }
  );
  return await response.json();
};

// Use in detail page
const DetailPage = ({ zpid }) => {
  const { listing } = await getListingDetail(zpid);

  return (
    <div>
      <h1>{listing.address}</h1>
      <Price>{listing.price}</Price>

      {/* Custom fields automatically available */}
      {listing.virtual_tour_url && (
        <TourButton href={listing.virtual_tour_url} />
      )}

      {/* Full Zillow data */}
      <Gallery photos={listing.original_listing?.responsivePhotos} />
    </div>
  );
};
```

#### Update Listing (Admin Panel)
```javascript
const updateListing = async (zpid, updates) => {
  const response = await fetch(`${API_BASE}/listings/${zpid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates })
  });
  return await response.json();
};

// Update price
await updateListing("12345", { price: 450000 });

// Mark as sold
await updateListing("12345", { status: "sold" });

// Add custom field
await updateListing("12345", {
  virtual_tour_url: "https://...",
  agent_notes: "Motivated seller"
});
```

#### Create Listing
```javascript
const createListing = async (listingData, processImages = false) => {
  const response = await fetch(`${API_BASE}/listings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      listing: listingData,
      options: {
        process_images: processImages,
        generate_embeddings: true,
        source: "user"
      }
    })
  });
  return await response.json();
};

// Quick add (no image processing)
const result = await createListing({
  price: 500000,
  beds: 3,
  baths: 2,
  address: "123 New St",
  description: "Beautiful home..."
}, false);
```

#### Delete Listing
```javascript
const deleteListing = async (zpid, permanent = false) => {
  const response = await fetch(
    `${API_BASE}/listings/${zpid}?soft=${!permanent}`,
    { method: 'DELETE' }
  );
  return await response.json();
};

// Soft delete (hide from search)
await deleteListing("12345", false);

// Hard delete (permanent)
if (confirm('Permanently delete?')) {
  await deleteListing("12345", true);
}
```

---

## Cost Summary

| Operation | Cost | Notes |
|-----------|------|-------|
| **Search (without S3)** | ~$0 | Just OpenSearch query |
| **Search (with S3 data)** | ~$0 | S3 cached in DynamoDB |
| **Get listing** | ~$0 | OpenSearch + S3 lookup |
| **Update listing** | ~$0 | No LLM calls |
| **Delete listing** | ~$0 | Just OpenSearch update |
| **Create (no images)** | ~$0.0001 | Text embedding only |
| **Create (with 10 images)** | ~$0.0106 | Full processing |

**Monthly estimates:**
- 10,000 searches: ~$0
- 100 new listings (full processing): ~$1.06
- 1,000 updates: ~$0

---

## Testing

### cURL Examples

```bash
# Search
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \
  -H "Content-Type: application/json" \
  -d '{"q":"granite countertops","size":5}'

# Get listing
curl https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345?include_full_data=true

# Update listing
curl -X PATCH https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345 \
  -H "Content-Type: application/json" \
  -d '{"updates":{"price":450000,"status":"sold"}}'

# Create listing
curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings \
  -H "Content-Type: application/json" \
  -d '{"listing":{"price":500000,"beds":3,"address":"123 Test St"}}'

# Delete listing
curl -X DELETE https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/listings/12345?soft=true
```

---

## Next Steps

### Phase 1: Lambda Setup (Current)
✅ Enhanced search.py with S3 merging
✅ Added get_listing_handler for GET endpoint
✅ Created crud_listings.py with update/create/delete handlers
✅ Deployed updated search Lambda

### Phase 2: API Gateway Configuration (Next)
- [ ] Create hearth-crud-update Lambda function
- [ ] Create hearth-crud-create Lambda function
- [ ] Create hearth-crud-delete Lambda function
- [ ] Configure API Gateway routes
- [ ] Test all endpoints

### Phase 3: Frontend Integration
- [ ] Build admin panel UI
- [ ] Test CRUD operations
- [ ] Add authentication
- [ ] Production deployment

---

## Support

For questions or issues:
1. Check CloudWatch logs for Lambda functions
2. Test with cURL first before frontend integration
3. Verify OpenSearch index health
4. Check DynamoDB cache tables

**Remember:** Any field you add via CRUD automatically becomes searchable. No backend code changes needed!
