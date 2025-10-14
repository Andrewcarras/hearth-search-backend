"""
search.py - Lambda function for natural language property search

This Lambda implements a sophisticated hybrid search strategy that combines:
1. BM25 full-text search on property descriptions
2. kNN vector similarity search on text embeddings
3. kNN vector similarity search on image embeddings
4. Reciprocal Rank Fusion (RRF) to combine results
5. On-demand geolocation enrichment with nearby places

The search pipeline:
1. Parse natural language query using Claude LLM to extract:
   - Required features (must_have tags like "pool", "garage")
   - Numeric filters (price range, bedroom/bathroom minimums)
   - Proximity mentions (for logging only - not used for filtering)
2. Generate query embedding vector
3. Execute three parallel searches:
   - BM25: Traditional keyword search with field boosting
   - kNN text: Semantic similarity on description embeddings
   - kNN image: Visual similarity on property photo embeddings
4. Fuse results using RRF algorithm (combines rankings from multiple sources)
5. Apply soft boost for properties matching all required tags
6. Fetch complete listing data from S3 for top results
7. Enrich each result with nearby places from Google Places API (New)
8. Return ranked, enriched results with all original Zillow data + nearby_places

On-Demand Geolocation Approach:
- OLD: Find one grocery store, filter all 1,588 listings, return those within 5km (~$27/search)
- NEW: Return best matches, enrich each with ITS OWN nearby places (~$0.26/search)
- 100x more cost-effective and provides better UX (each home shows what's near IT)

Example queries:
- "3 bedroom house with pool under $500k"
- "Modern home with open floor plan and mountain views"
- "Show me homes near a grocery store" (returns all matches, each shows nearby places)
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3

from common import (
    os_client, OS_INDEX, embed_text,
    extract_query_constraints, AWS_REGION
)

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# S3 client for fetching complete listing data
s3 = boto3.client("s3", region_name=AWS_REGION)

# DynamoDB client for caching (geolocation + S3 listings)
dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)
GEOLOCATION_CACHE_TABLE = "hearth-geolocation-cache"
S3_LISTING_CACHE_TABLE = "hearth-s3-listing-cache"
S3_CACHE_TTL = 3600  # 1 hour in seconds

# Google Places API configuration (set via Lambda environment variable)
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")


# ===============================================
# ON-DEMAND GEOLOCATION ENRICHMENT
# ===============================================

def _get_location_key(lat: float, lon: float, radius_meters: int = 1000) -> str:
    """
    Create cache key for geolocation lookup.
    Rounds coordinates to ~100m precision to improve cache hit rate.
    """
    # Round to 3 decimal places = ~111m precision
    lat_rounded = round(lat, 3)
    lon_rounded = round(lon, 3)
    return f"{lat_rounded},{lon_rounded},{radius_meters}"


def _get_cached_nearby_places(location_key: str) -> List[Dict[str, Any]]:
    """Check DynamoDB cache for nearby places."""
    try:
        response = dynamodb.get_item(
            TableName=GEOLOCATION_CACHE_TABLE,
            Key={"location_key": {"S": location_key}}
        )
        if "Item" in response and "places" in response["Item"]:
            return json.loads(response["Item"]["places"]["S"])
    except Exception as e:
        logger.warning(f"Geolocation cache read failed: {e}")
    return None


def _cache_nearby_places(location_key: str, places: List[Dict[str, Any]]):
    """Store nearby places in DynamoDB cache."""
    try:
        dynamodb.put_item(
            TableName=GEOLOCATION_CACHE_TABLE,
            Item={
                "location_key": {"S": location_key},
                "places": {"S": json.dumps(places)},
                "cached_at": {"N": str(int(__import__('time').time()))}
            }
        )
    except Exception as e:
        logger.warning(f"Geolocation cache write failed: {e}")


def enrich_with_nearby_places(listing: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a single listing with nearby places from Google Places API.
    Uses DynamoDB cache to avoid duplicate API calls.

    Cost: ~$0.017 per cache miss (first time seeing this location)
          $0 per cache hit (subsequent lookups)
    """
    if not GOOGLE_PLACES_API_KEY:
        return listing  # API key not configured

    # Extract coordinates from listing (handle both formats)
    # OpenSearch stores as geo.lat/geo.lon, raw Zillow JSON uses latitude/longitude
    geo = listing.get("geo", {})
    latitude = listing.get("latitude") or geo.get("lat")
    longitude = listing.get("longitude") or geo.get("lon")

    if not latitude or not longitude:
        return listing  # No coordinates available

    # Check cache first
    location_key = _get_location_key(latitude, longitude, radius_meters=1000)
    cached_places = _get_cached_nearby_places(location_key)

    if cached_places is not None:
        logger.debug(f"✓ Geolocation cache hit for {location_key}")
        listing["nearby_places"] = cached_places
        return listing

    # Cache miss - call Google Places API (New)
    try:
        import requests

        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": "places.displayName,places.types,places.location"
        }
        payload = {
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude
                    },
                    "radius": 1000.0  # 1km radius
                }
            },
            "maxResultCount": 10
        }

        response = requests.post(url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()

        if "places" in data:
            # Extract relevant place info
            places = []
            for place in data.get("places", [])[:10]:
                places.append({
                    "name": place.get("displayName", {}).get("text", "Unknown"),
                    "types": place.get("types", []),
                    "distance_meters": None  # Could calculate if needed
                })

            # Cache the results
            _cache_nearby_places(location_key, places)
            listing["nearby_places"] = places
            logger.info(f"✓ Fetched {len(places)} nearby places for {listing.get('zpid')}")
        else:
            logger.warning(f"Google Places API (New): No places returned")

    except Exception as e:
        logger.warning(f"Failed to fetch nearby places: {e}")

    return listing


# ===============================================
# S3 LISTING CACHE
# ===============================================

def _get_cached_s3_listing(zpid: str) -> Optional[Dict[str, Any]]:
    """
    Check DynamoDB cache for previously fetched S3 listing data.

    Returns None if cache miss, expired, or error.
    Cache TTL: 1 hour (listings don't change frequently).
    """
    try:
        response = dynamodb.get_item(
            TableName=S3_LISTING_CACHE_TABLE,
            Key={"zpid": {"S": str(zpid)}}
        )

        if "Item" not in response:
            return None

        # Check if cache expired
        import time
        cached_at = int(response["Item"].get("cached_at", {}).get("N", "0"))
        age = int(time.time()) - cached_at

        if age > S3_CACHE_TTL:
            logger.debug(f"S3 cache expired for zpid={zpid} (age={age}s)")
            return None

        # Cache hit!
        logger.debug(f"✓ S3 cache hit: zpid={zpid} (age={age}s)")
        return json.loads(response["Item"]["data"]["S"])

    except Exception as e:
        logger.warning(f"S3 cache read failed for zpid={zpid}: {e}")
        return None


def _cache_s3_listing(zpid: str, data: Dict[str, Any]):
    """
    Store S3 listing data in DynamoDB cache.

    Stores complete listing JSON for fast retrieval.
    """
    try:
        import time
        dynamodb.put_item(
            TableName=S3_LISTING_CACHE_TABLE,
            Item={
                "zpid": {"S": str(zpid)},
                "data": {"S": json.dumps(data)},
                "cached_at": {"N": str(int(time.time()))}
            }
        )
        logger.debug(f"✓ Cached S3 listing: zpid={zpid}")
    except Exception as e:
        logger.warning(f"S3 cache write failed for zpid={zpid}: {e}")


# ===============================================
# SEARCH HELPER FUNCTIONS
# ===============================================

def _fetch_listing_from_s3(zpid: str) -> Dict[str, Any]:
    """
    Fetch complete Zillow listing JSON from S3 with DynamoDB caching.

    Flow:
    1. Check DynamoDB cache first (30ms if cached)
    2. If cache miss → fetch from S3 (400ms)
    3. Store in cache for next time

    Returns all 166+ Zillow fields. With reduced page size (15 results),
    this stays under Lambda's 6MB limit while preserving all data.

    Args:
        zpid: Zillow property ID

    Returns:
        Complete listing dictionary with all Zillow fields
    """
    # Check cache first
    cached_listing = _get_cached_s3_listing(zpid)
    if cached_listing is not None:
        return cached_listing

    # Cache miss - fetch from S3
    try:
        response = s3.get_object(
            Bucket="demo-hearth-data",
            Key=f"listings/{zpid}.json"
        )
        data = json.loads(response["Body"].read().decode("utf-8"))

        # Cache for next time
        _cache_s3_listing(zpid, data)

        return data
    except Exception as e:
        logger.warning("Failed to fetch listing %s from S3: %s", zpid, e)
        return {}


def _filters_to_bool(filter_obj: Dict[str, Any], require_embeddings: bool = True) -> Dict[str, Any]:
    """
    Convert high-level filter dict to OpenSearch bool query filters.

    This builds the filter clause for OpenSearch queries, handling:
    - Range filters (price, beds, baths, acreage)
    - Default filtering of invalid listings (price=0, missing embeddings)

    Args:
        filter_obj: Dictionary with filter keys like price_min, price_max, beds_min, etc.
        require_embeddings: If True, only return documents with valid embeddings (for kNN searches)

    Returns:
        OpenSearch bool query dict with filter clause
    """
    f = []
    if not filter_obj:
        filter_obj = {}

    def rng(name, lo, hi):
        """Helper to build range filter for min/max values."""
        if lo is None and hi is None:
            return {}

        range_query = {}
        if lo is not None:
            range_query["gte"] = lo
        if hi is not None:
            range_query["lte"] = hi

        return {"range": {name: range_query}}

    # Price filter with automatic filtering of zero-price listings
    if "price_min" in filter_obj or "price_max" in filter_obj:
        price_filter = rng("price", filter_obj.get("price_min"), filter_obj.get("price_max"))
        if price_filter:  # Only append if not empty
            f.append(price_filter)
    else:
        # Default: exclude price=0 (sold/unlisted properties)
        f.append({"range": {"price": {"gt": 0}}})

    # Bedroom minimum
    if "beds_min" in filter_obj and filter_obj["beds_min"] is not None:
        f.append({"range": {"bedrooms": {"gte": filter_obj["beds_min"]}}})

    # Bathroom minimum
    if "baths_min" in filter_obj and filter_obj["baths_min"] is not None:
        f.append({"range": {"bathrooms": {"gte": filter_obj["baths_min"]}}})

    # Lot size range
    if "acreage_min" in filter_obj or "acreage_max" in filter_obj:
        acreage_filter = rng("acreage", filter_obj.get("acreage_min"), filter_obj.get("acreage_max"))
        if acreage_filter:  # Only append if not empty
            f.append(acreage_filter)

    # Only require embeddings when doing vector/semantic search (kNN)
    # For geo-distance or pure text queries, listings can be found while still indexing
    if require_embeddings:
        f.append({"term": {"has_valid_embeddings": True}})

    return {"bool": {"filter": f}}


def _os_search(body: Dict[str, Any], size: int = 50) -> List[Dict[str, Any]]:
    """
    Execute an OpenSearch query and return hits.

    Args:
        body: OpenSearch query body
        size: Maximum number of results to return

    Returns:
        List of hit dictionaries from OpenSearch response
    """
    body["size"] = size
    res = os_client.search(index=OS_INDEX, body=body)
    return res.get("hits", {}).get("hits", [])


def _rrf(*ranked_lists: List[List[Dict[str, Any]]], k: int = 60, top: int = 50) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion - Combine multiple ranked result lists into one.

    RRF is a simple but effective algorithm for fusing results from different
    search strategies (BM25, kNN text, kNN image). It works by:
    1. For each document, sum scores based on rank position in each list
    2. Score formula: 1 / (k + rank), where k=60 is a constant
    3. Higher ranks in any list contribute more to final score

    This approach gives equal weight to all search strategies and handles
    cases where documents appear in some lists but not others.

    Reference: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf

    Args:
        *ranked_lists: Variable number of result lists (each is list of OpenSearch hits)
        k: RRF constant (controls score decay with rank, default 60)
        top: Number of top results to return after fusion

    Returns:
        Fused and re-ranked list of documents
    """
    scores: Dict[str, Dict[str, Any]] = {}

    def add(listing, rank, weight=1.0):
        """Add a listing's score based on its rank in a result list."""
        _id = listing["_id"]
        entry = scores.setdefault(_id, {"doc": listing, "score": 0.0})
        # RRF formula: score += 1 / (k + rank)
        entry["score"] += weight * (1.0 / (k + rank))

    # Process each ranked list
    for lst in ranked_lists:
        for i, h in enumerate(lst):
            add(h, i + 1, 1.0)  # rank is 1-indexed

    # Sort by fused score (descending) and return top results
    fused = list(scores.values())
    fused.sort(key=lambda x: x["score"], reverse=True)
    return [x["doc"] for x in fused[:top]]


# ===============================================
# LAMBDA HANDLER
# ===============================================

def handler(event, context):
    """
    AWS Lambda handler for natural language property search.

    Implements hybrid search combining BM25 keyword search with kNN vector
    similarity search on both text and images, fused using RRF algorithm.

    Payload format:
      {
        "q": "3 bedroom house with pool and mountain views",
        "size": 30,
        "filters": {"price_max": 750000, "beds_min": 3}  # Optional explicit filters
      }

    The handler:
    1. Parses natural language query to extract constraints
    2. Generates query embedding vector
    3. Executes 3 parallel searches (BM25, kNN text, kNN image)
    4. Fuses results with RRF
    5. Applies tag-based boosting
    6. Returns ranked results

    Args:
        event: Lambda event with query payload
        context: Lambda context (unused)

    Returns:
        Response dict with results array and metadata
    """
    # CORS headers for all responses
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS"
    }

    # Handle OPTIONS preflight request
    if event.get("httpMethod") == "OPTIONS" or event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": ""
        }

    body = event.get("body") if isinstance(event, dict) else None
    if body and isinstance(body, str):
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}
    else:
        payload = event if isinstance(event, dict) else {}

    q = (payload.get("q") or "").strip()
    if not q:
        return {"statusCode": 400, "headers": cors_headers, "body": json.dumps({"error": "missing 'q'"})}
    size = int(payload.get("size", 15))  # Reduced from 30 to stay under 6MB with full S3 data

    logger.info("Search query: '%s', size=%d", q, size)

    constraints = extract_query_constraints(q)
    hard_filters = constraints.get("hard_filters", {})
    must_tags = set(constraints.get("must_have", []))
    architecture_style = constraints.get("architecture_style")
    proximity = constraints.get("proximity")
    logger.info("Extracted constraints: %s", constraints)

    # Merge explicit filters from payload
    if "filters" in payload:
        hard_filters.update(payload["filters"])
        logger.info("Applied additional filters from payload: %s", payload["filters"])

    # Add architecture style as a filter if detected
    if architecture_style:
        logger.info("Filtering by architecture style: %s", architecture_style)

    # Determine if we need vector search (kNN) based on query characteristics
    # We can skip embeddings requirement if:
    # 1. Query is primarily location-based (has proximity but no feature requirements)
    # 2. Query is simple numeric filters (price, beds, baths)
    # This allows results to show during indexing for geo/filter-only queries
    is_geo_focused = proximity is not None and not must_tags and not architecture_style
    needs_semantic_search = bool(must_tags) or bool(architecture_style) or not proximity

    # Only require embeddings when we're doing semantic/vector search
    require_embeddings = needs_semantic_search

    if is_geo_focused:
        logger.info("Geo-focused query detected - allowing results without embeddings")
    else:
        logger.info("Semantic search required - filtering for valid embeddings")

    q_vec = embed_text(q)
    filter_clauses = _filters_to_bool(hard_filters, require_embeddings=require_embeddings)["bool"]["filter"]

    # Add architecture style filter
    if architecture_style:
        filter_clauses.append({"term": {"architecture_style": architecture_style}})

    # DISABLED OLD PROXIMITY FILTERING: Now using on-demand enrichment instead!
    # The old approach was: find a grocery store, filter listings within 5km
    # The new approach: return all matching listings, enrich each with nearby places
    # This is 100x cheaper and works better (every listing gets its own nearby places)
    #
    # if proximity:
    #     poi_type = proximity.get("poi_type")
    #     max_distance_km = proximity.get("max_distance_km")
    #     max_drive_time_min = proximity.get("max_drive_time_min")
    #
    #     logger.info("Proximity requirement detected: poi_type=%s, max_distance_km=%s, max_drive_time_min=%s",
    #                poi_type, max_distance_km, max_drive_time_min)
    #
    #     # Geocode the POI type using Salt Lake City as reference
    #     # This ensures we find businesses near the listings, not in other states
    #     slc_center = {"lat": 40.7608, "lon": -111.891}
    #     poi_location = geocode_location(poi_type, reference_location=slc_center)
    #
    #     if poi_location:
    #         # Estimate distance from drive time (if specified): ~40km in 10 minutes = 4km/min average
    #         if max_drive_time_min and not max_distance_km:
    #             max_distance_km = max_drive_time_min * 4  # Conservative estimate
    #
    #         # Default to 10km if not specified (reasonable for suburban "near")
    #         if not max_distance_km:
    #             max_distance_km = 10
    #
    #         logger.info("Using POI location: %s, max_distance: %s km", poi_location, max_distance_km)
    #
    #         # Add geo_distance filter (uses "geo" field from listings)
    #         filter_clauses.append({
    #             "geo_distance": {
    #                 "distance": f"{max_distance_km}km",
    #                 "geo": {
    #                     "lat": poi_location["lat"],
    #                     "lon": poi_location["lon"]
    #                 }
    #             }
    #         })
    #     else:
    #         logger.warning("Could not geocode POI: %s - skipping proximity filter", poi_type)

    if proximity:
        poi_type = proximity.get("poi_type")
        logger.info("Proximity requirement detected: poi_type=%s - will enrich results with nearby places", poi_type)

    logger.info("Filter clauses: %s", json.dumps(filter_clauses))
    topK = max(100, size * 3)

    # Convert must_tags to both space and underscore formats for compatibility
    # Image tags are stored as "blue exterior" but query parser extracts "blue_exterior"
    # This ensures we match both formats until we normalize everything
    expanded_must_tags = set()
    for tag in must_tags:
        expanded_must_tags.add(tag)  # Original format (e.g., "blue_exterior")
        expanded_must_tags.add(tag.replace("_", " "))  # Space format (e.g., "blue exterior")

    # 1) BM25 over text fields (tags as soft boosts via terms)
    bm25_query = {
        "query": {
            "bool": {
                "filter": filter_clauses,  # Pass the list directly
                "should": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": [
                                "description^3",
                                "llm_profile^2",
                                "address^0.5",
                                "city^0.3",
                                "state^0.2"
                            ],
                            "type": "best_fields"
                        }
                    },
                    *([{"terms": {"feature_tags": list(expanded_must_tags)}}] if expanded_must_tags else []),
                    *([{"terms": {"image_tags": list(expanded_must_tags)}}] if expanded_must_tags else []),
                ],
                "minimum_should_match": 1
            }
        }
    }
    logger.info("BM25 query: %s", json.dumps(bm25_query))
    bm25_hits = _os_search(bm25_query, size=size * 3)
    logger.info("BM25 returned %d hits", len(bm25_hits))

    # 2) kNN on text vector (only if semantic search is needed)
    # For geo-focused queries, skip kNN to avoid filtering out partially-indexed docs
    knn_text_hits: List[Dict[str, Any]] = []
    if require_embeddings:
        knn_text_body = {
            "size": size * 3,
            "query": {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                "vector_text": {
                                    "vector": q_vec,
                                    "k": topK
                                }
                            }
                        }
                    ],
                    "filter": filter_clauses  # Use the same filter list
                }
            }
        }
        try:
            knn_text_hits = _os_search(knn_text_body, size=size * 3)
            logger.info("kNN text returned %d hits", len(knn_text_hits))
        except Exception as e:
            logger.warning("kNN text search failed: %s", e)
    else:
        logger.info("Skipping kNN text search (geo-focused query)")

    # 3) kNN on image vector (only if semantic search is needed)
    knn_img_hits: List[Dict[str, Any]] = []
    if require_embeddings:
        try:
            knn_img_body = {
                "size": size * 3,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "knn": {
                                    "vector_image": {
                                        "vector": q_vec,
                                        "k": topK
                                    }
                                }
                            }
                        ],
                        "filter": filter_clauses  # Use the same filter list
                    }
                }
            }
            knn_img_hits = _os_search(knn_img_body, size=size * 3)
            logger.info("kNN image returned %d hits", len(knn_img_hits))
        except Exception as e:
            logger.warning("Image kNN skipped (no mapping or field): %s", e)
    else:
        logger.info("Skipping kNN image search (geo-focused query)")

    # Fuse results using RRF (only includes non-empty result lists)
    fused = _rrf(bm25_hits, knn_text_hits, knn_img_hits, top=size * 3)
    logger.info("RRF fusion produced %d results", len(fused))

    # Check if client wants full Zillow data from S3
    include_full_data = payload.get("include_full_data", False)
    include_nearby = payload.get("include_nearby_places", True)

    # Final soft boost if all must-have tags are present
    # Check both original format and space-converted format for compatibility
    final = []
    for h in fused:
        src = h.get("_source", {}) or {}
        tags = set((src.get("feature_tags") or []) + (src.get("image_tags") or []))
        # Check if expanded tags (both formats) are satisfied
        satisfied = expanded_must_tags.issubset(tags) if expanded_must_tags else True
        boost = 1.0 + (0.5 if satisfied and expanded_must_tags else 0.0)

        zpid = h["_id"]

        # Build result from OpenSearch data
        result = {
            "zpid": zpid,
            "id": zpid,
            "score": h.get("_score", 0.0),
            "boosted": boost > 1.0
        }

        # Add all OpenSearch fields (except vectors)
        # This automatically includes ANY custom fields added via CRUD API
        for k, v in src.items():
            if k not in ("vector_text", "vector_image"):
                result[k] = v

        # Optionally merge full Zillow listing data from S3
        # This adds 166+ original Zillow fields (responsivePhotos, zestimate, etc.)
        if include_full_data:
            try:
                s3_listing = _fetch_listing_from_s3(zpid)
                if s3_listing:
                    result["original_listing"] = s3_listing
                    logger.debug(f"Merged S3 data for zpid={zpid}")
            except Exception as e:
                logger.warning(f"Failed to fetch S3 data for zpid={zpid}: {e}")
                # Continue without S3 data - don't fail the whole request

        # Enrich with nearby places on-demand (cached in DynamoDB)
        if include_nearby:
            result = enrich_with_nearby_places(result)

        final.append((h.get("_score", 0.0) * boost, result))

    final.sort(key=lambda x: x[0], reverse=True)
    results = [x[1] for x in final[:size]]

    logger.info("Returning %d final results", len(results))

    response_data = {
        "ok": True,
        "results": results,
        "total": len(results),
        "must_have": list(must_tags)
    }

    # Include architecture_style filter in response if it was used
    if architecture_style:
        response_data["architecture_style"] = architecture_style

    return {
        "statusCode": 200,
        "headers": cors_headers,
        "body": json.dumps(response_data)
    }


def get_listing_handler(event, context):
    """
    Get a single listing by zpid.

    Supports GET /listings/{zpid}?include_full_data=true

    Returns complete listing with all OpenSearch fields, optionally merged with
    full Zillow data from S3, and enriched with nearby places.

    Example:
        GET /listings/12345?include_full_data=true&include_nearby_places=true
    """
    logger.info("get_listing_handler invoked")

    # Extract zpid from path parameters
    zpid = event.get("pathParameters", {}).get("zpid")
    if not zpid:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "Missing zpid in path"})
        }

    # Extract query parameters
    query_params = event.get("queryStringParameters") or {}
    include_full_data = query_params.get("include_full_data", "false").lower() == "true"
    include_nearby = query_params.get("include_nearby_places", "true").lower() == "true"

    logger.info(f"Fetching listing zpid={zpid}, include_full_data={include_full_data}, include_nearby={include_nearby}")

    try:
        # Fetch from OpenSearch
        response = os_client.get(index=OS_INDEX, id=str(zpid))

        if not response.get("found"):
            return {
                "statusCode": 404,
                "headers": cors_headers,
                "body": json.dumps({"error": f"Listing {zpid} not found"})
            }

        src = response["_source"]

        # Build result with all OpenSearch fields
        result = {
            "zpid": zpid,
            "id": zpid
        }

        # Add all fields except vectors
        for k, v in src.items():
            if k not in ("vector_text", "vector_image"):
                result[k] = v

        # Optionally merge full Zillow data from S3
        if include_full_data:
            try:
                s3_listing = _fetch_listing_from_s3(zpid)
                if s3_listing:
                    result["original_listing"] = s3_listing
                    logger.info(f"Merged S3 data for zpid={zpid}")
            except Exception as e:
                logger.warning(f"Failed to fetch S3 data for zpid={zpid}: {e}")

        # Optionally enrich with nearby places
        if include_nearby:
            result = enrich_with_nearby_places(result)

        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps({
                "ok": True,
                "listing": result
            })
        }

    except Exception as e:
        logger.error(f"Error fetching listing {zpid}: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": str(e)})
        }


def lambda_handler(event, context):
    """
    Router function that dispatches to correct handler based on HTTP method and path.

    This allows a single Lambda to handle multiple endpoints:
    - POST /search → handler() for search
    - GET /listings/{zpid} → get_listing_handler() for single listing retrieval

    API Gateway uses Lambda Proxy integration, so all request details are in event.
    """
    path = event.get('path', '')
    method = event.get('httpMethod', '')

    logger.info(f"Router: {method} {path}")

    # POST /search → Search listings
    if method == 'POST' and path == '/search':
        return handler(event, context)

    # GET /listings/{zpid} → Get single listing
    elif method == 'GET' and '/listings/' in path:
        return get_listing_handler(event, context)

    # Unknown route
    else:
        return {
            "statusCode": 404,
            "headers": cors_headers,
            "body": json.dumps({
                "error": "Not found",
                "path": path,
                "method": method
            })
        }
