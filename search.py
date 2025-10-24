"""
search.py - Lambda function for natural language property search

This Lambda implements a sophisticated hybrid search strategy combining:
1. BM25 full-text search on property descriptions
2. kNN vector similarity search on text embeddings
3. kNN vector similarity search on image embeddings (multi-vector support)
4. Reciprocal Rank Fusion (RRF) to combine results with adaptive weighting
5. On-demand geolocation enrichment with nearby places (cached in DynamoDB)

Search Pipeline:
1. Parse natural language query using Claude LLM to extract:
   - Required features (must_have tags like "pool", "garage")
   - Numeric filters (price range, bedroom/bathroom minimums)
   - Architecture style (modern, craftsman, etc.)
   - Proximity requirements (near school, gym, etc.)
2. Generate query embedding vector via Bedrock Titan
3. Execute three parallel OpenSearch queries:
   - BM25: Traditional keyword search with field boosting
   - kNN text: Semantic similarity on description embeddings
   - kNN image: Visual similarity on property photo embeddings (nested for multi-vector)
4. Fuse results using adaptive RRF algorithm (dynamic k-values based on query type)
5. Apply tag-based boosting (2.0x for 100% match, 1.5x for 75%, etc.)
6. Optionally fetch complete listing data from S3 (166+ Zillow fields)
7. Enrich with nearby places from Google Places API (on-demand, cached)
8. Return ranked, enriched results

Geolocation Enrichment:
- Enriches EACH result with nearby places using Google Places API
- DynamoDB caching prevents duplicate API calls (~100m precision)
- Cost: ~$0.017 per cache miss, $0 per hit
- 100x cheaper than pre-filtering all listings by proximity

Example Queries:
- "3 bedroom house with pool under $500k"
- "Modern home with open floor plan and mountain views"
- "Show me homes near a grocery store" (returns best matches, each shows nearby places)
"""

import json
import logging
import os
import base64
import time
from typing import Any, Dict, List, Optional

import boto3
import math

from common import (
    os_client, OS_INDEX, embed_text_multimodal, embed_image_bytes,
    extract_query_constraints, AWS_REGION
)
from search_logger import generate_query_id, log_search_query

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

# Feature terms that should be treated as required when mentioned in query
# These are concrete property features, not stylistic attributes
REQUIRED_FEATURE_TERMS = {
    "pool", "pools", "swimming pool", "hot tub", "spa",
    "garage", "attached garage", "detached garage", "2 car garage", "3 car garage",
    "fireplace", "brick fireplace", "stone fireplace", "gas fireplace",
    "basement", "finished basement", "walkout basement",
    "deck", "patio", "balcony", "porch", "sunroom",
    "fence", "fenced yard", "privacy fence",
    "ac", "air conditioning", "central air",
    "hardwood floors", "hardwood flooring",
}

# Construction indicators that should be filtered out for normal searches
CONSTRUCTION_INDICATORS = [
    "floor plan", "floorplan", "rendering", "to be built", "not yet built",
    "under construction", "pre-construction", "coming soon", "model home",
    "architectural rendering", "artist rendering", "conceptual"
]


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
    geo = listing.get("geo") or {}
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


def _detect_required_features(query: str) -> List[str]:
    """
    Detect required feature terms in the query that should be mandatory filters.

    Args:
        query: User search query

    Returns:
        List of required feature terms found in query
    """
    query_lower = query.lower()
    required_features = []

    for feature in REQUIRED_FEATURE_TERMS:
        if feature in query_lower:
            required_features.append(feature)

    return required_features


def _is_construction_listing(listing: Dict[str, Any]) -> bool:
    """
    Detect if a listing is under construction, not built, or showing renderings.

    Args:
        listing: OpenSearch hit document

    Returns:
        True if listing appears to be under construction or not built
    """
    source = listing.get("_source", {})
    description = source.get("description", "").lower()

    # Check description for construction indicators
    for indicator in CONSTRUCTION_INDICATORS:
        if indicator in description:
            return True

    return False


def _build_required_feature_filter(required_features: List[str]) -> List[Dict[str, Any]]:
    """
    Build OpenSearch filter clauses to require certain features.

    For features like "pool", we need to ensure the listing actually has a pool
    by matching against description, image_tags, or feature_tags.

    Args:
        required_features: List of feature terms that must be present

    Returns:
        List of filter clauses for OpenSearch bool query
    """
    filters = []

    for feature in required_features:
        # Create normalized versions of the feature term
        feature_normalized = feature.replace(" ", "_")
        feature_spaced = feature.replace("_", " ")

        # Each required feature must match in at least ONE of these fields:
        # - description text
        # - image_tags array
        # - feature_tags array
        filters.append({
            "bool": {
                "should": [
                    # Match in description using match_phrase for exact phrase matching
                    {"match_phrase": {"description": feature_spaced}},
                    # Match in image_tags
                    {"term": {"image_tags": feature_spaced}},
                    {"term": {"image_tags": feature_normalized}},
                    # Match in feature_tags
                    {"term": {"feature_tags": feature_spaced}},
                    {"term": {"feature_tags": feature_normalized}},
                ],
                "minimum_should_match": 1
            }
        })

    return filters


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


def _os_search(body: Dict[str, Any], size: int = 50, index: str = None) -> List[Dict[str, Any]]:
    """
    Execute an OpenSearch query and return hits.

    Args:
        body: OpenSearch query body
        size: Maximum number of results to return
        index: Target index name (defaults to OS_INDEX if not specified)

    Returns:
        List of hit dictionaries from OpenSearch response
    """
    body["size"] = size
    target_index = index or OS_INDEX
    res = os_client.search(index=target_index, body=body)
    return res.get("hits", {}).get("hits", [])


def _rrf(*ranked_lists: List[List[Dict[str, Any]]], k: int = 60, k_values: List[int] = None, top: int = 50, include_scoring_details: bool = False) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion - Combine multiple ranked result lists into one.

    RRF is a simple but effective algorithm for fusing results from different
    search strategies (BM25, kNN text, kNN image). It works by:
    1. For each document, sum scores based on rank position in each list
    2. Score formula: 1 / (k + rank), where k controls weight (lower k = higher weight)
    3. Higher ranks in any list contribute more to final score

    ADAPTIVE SCORING: k_values can be provided to give different weights to each list.
    Lower k = higher impact on final score. Example:
    - k=30 for BM25 (high weight for color/material queries)
    - k=120 for image kNN (low weight when images don't help)

    Reference: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf

    Args:
        *ranked_lists: Variable number of result lists (each is list of OpenSearch hits)
        k: Default RRF constant if k_values not provided (default 60)
        k_values: List of k values per result list for adaptive weighting (e.g., [30, 60, 120])
        top: Number of top results to return after fusion
        include_scoring_details: If True, attach detailed scoring breakdown to each document

    Returns:
        Fused and re-ranked list of documents
    """
    scores: Dict[str, Dict[str, Any]] = {}

    # Use provided k_values or default k for all lists
    if k_values is None:
        k_values = [k] * len(ranked_lists)
    elif len(k_values) != len(ranked_lists):
        logger.warning(f"k_values length ({len(k_values)}) != ranked_lists length ({len(ranked_lists)}), using default k={k}")
        k_values = [k] * len(ranked_lists)

    # Strategy names for debugging
    strategy_names = ["bm25", "knn_text", "knn_image"]

    def add(listing, rank, k_val, strategy_idx):
        """Add a listing's score based on its rank in a result list."""
        _id = listing["_id"]
        entry = scores.setdefault(_id, {
            "doc": listing,
            "score": 0.0,
            "scoring_details": {
                "bm25": {"rank": None, "original_score": None, "rrf_contribution": 0.0, "k": k_values[0] if len(k_values) > 0 else k},
                "knn_text": {"rank": None, "original_score": None, "rrf_contribution": 0.0, "k": k_values[1] if len(k_values) > 1 else k},
                "knn_image": {"rank": None, "original_score": None, "rrf_contribution": 0.0, "k": k_values[2] if len(k_values) > 2 else k},
                "rrf_total": 0.0
            } if include_scoring_details else None
        })

        # RRF formula: score += 1 / (k + rank)
        # Lower k = higher weight for that result list
        rrf_contribution = 1.0 / (k_val + rank)
        entry["score"] += rrf_contribution

        # Store scoring details if requested
        if include_scoring_details and strategy_idx < len(strategy_names):
            strategy_name = strategy_names[strategy_idx]
            entry["scoring_details"][strategy_name]["rank"] = rank
            entry["scoring_details"][strategy_name]["original_score"] = listing.get("_score", 0.0)
            entry["scoring_details"][strategy_name]["rrf_contribution"] = rrf_contribution

    # Process each ranked list with its corresponding k value
    for strategy_idx, (lst, k_val) in enumerate(zip(ranked_lists, k_values)):
        for i, h in enumerate(lst):
            add(h, i + 1, k_val, strategy_idx)  # rank is 1-indexed

    # ALWAYS attach RRF score to document (needed for tag boosting)
    for entry in scores.values():
        entry["doc"]["_rrf_score"] = entry["score"]

    # Update RRF totals in scoring details and attach to document
    if include_scoring_details:
        for entry in scores.values():
            entry["scoring_details"]["rrf_total"] = entry["score"]
            # Attach scoring details to the document
            entry["doc"]["scoring_details"] = entry["scoring_details"]

    # Sort by fused score (descending) and return top results
    fused = list(scores.values())
    fused.sort(key=lambda x: x["score"], reverse=True)
    return [x["doc"] for x in fused[:top]]


def calculate_adaptive_k(must_have_features):
    """
    Determine K (number of top images to sum) based on query complexity:
    - 0 features (general query): k=1 (best match only)
    - 1-2 features: k=2 (top 2 images)
    - 3+ features: k=3 (top 3 images)

    Args:
        must_have_features: List of required features from query

    Returns:
        int: Number of top images to sum
    """
    feature_count = len(must_have_features)
    if feature_count == 0:
        return 1
    elif feature_count <= 2:
        return 2
    else:
        return 3


def calculate_adaptive_k_for_images(must_have_features):
    """
    Calculate adaptive K for top-k image scoring based on query complexity.

    Multi-feature queries need to aggregate multiple images to capture all features,
    while single-feature queries should use best single match (like max).

    Args:
        must_have_features: List of required feature tags from LLM extraction

    Returns:
        int: K value (number of top images to sum)
    """
    feature_count = len(must_have_features)

    # General queries (no specific features) - use best single match
    if feature_count == 0:
        return 1  # Equivalent to max behavior

    # Single feature queries - best single match is appropriate
    elif feature_count == 1:
        return 1  # Kitchen query → kitchen photo wins

    # Two feature queries - sum top 2 to capture both
    elif feature_count == 2:
        return 2  # "white house with granite" → exterior + kitchen

    # Three or more features - sum top 3
    else:
        return 3  # "modern white kitchen with stainless and hardwood" → multiple rooms

    # Note: For very complex queries with 5+ features, might want k=4 or 5,
    # but most real estate queries have 2-3 concrete visual features


def calculate_top_k_image_score(inner_hits, k):
    """
    Extract scores from inner_hits and sum top K image scores.

    This replaces OpenSearch's score_mode: "max" with a Python-based
    top-k summation to better handle multi-feature queries.

    Args:
        inner_hits: OpenSearch inner_hits response from nested query
        k: Number of top scores to sum

    Returns:
        float: Sum of top K image scores
    """
    if not inner_hits or "image_vectors" not in inner_hits:
        return 0.0

    # Extract all image scores from inner_hits
    hits = inner_hits["image_vectors"].get("hits", {}).get("hits", [])
    scores = [hit.get("_score", 0.0) for hit in hits]

    if not scores:
        return 0.0

    # Sort descending and take top K
    scores.sort(reverse=True)
    top_k_scores = scores[:k]

    # Sum the top K scores
    total = sum(top_k_scores)

    logger.debug(f"Top-K scoring: k={k}, available={len(scores)}, top_scores={top_k_scores[:5]}, sum={total:.4f}")
    return total


# ===============================================
# LLM-BASED QUERY SPLITTING FOR MULTI-FEATURE SEARCH
# ===============================================

def split_query_into_subqueries(query_text: str, must_have_features: List[str]) -> Dict[str, Any]:
    """
    Use Claude LLM to intelligently split multi-feature query into context-specific sub-queries.

    This solves the problem where a single embedding can't distinguish "white exterior" from
    "white cabinets". By creating separate embeddings for each feature context, we get better
    matches for multi-feature queries.

    Args:
        query_text: Original user query
        must_have_features: Extracted feature tags (e.g., ["white_exterior", "granite_countertops"])

    Returns:
        {
            "sub_queries": [
                {
                    "query": "white exterior house facade outside",
                    "feature": "white_exterior",
                    "context": "exterior_primary",
                    "weight": 2.0,
                    "search_strategy": "max",
                    "rationale": "Exterior color is primary feature"
                },
                ...
            ],
            "primary_feature": "white_exterior",
            "combination_strategy": "weighted_sum"
        }
    """
    from common import brt, LLM_MODEL_ID

    prompt = f"""You are helping optimize visual search for real estate properties. Given a user's query,
split it into separate sub-queries that can be individually embedded and compared to property images.

GOAL: Each sub-query should be optimized to match SPECIFIC property images (exterior, kitchen, flooring, etc.)

RULES:
1. **Exterior features** (colors, architecture) → Create sub-query focused on exterior/facade
   - Add context: "exterior", "facade", "house exterior", "outside of house"
   - Weight: 2.0 (PRIMARY - most important)
   - Strategy: "max" (best single exterior photo wins)

2. **Interior room features** (kitchen, bathroom) → Create sub-query for that room type
   - Add context: "kitchen", "bathroom", "living room"
   - Weight: 1.0 (SECONDARY)
   - Strategy: "max" (best single room photo wins)

3. **Material/finish features** (granite, hardwood, tile) → Create sub-query with room context
   - Infer likely room: granite → kitchen, hardwood → floors/living areas, tile → bathroom
   - Weight: 1.0 (SECONDARY)
   - Strategy: "max"

4. **Architectural style** (modern, craftsman) → Create sub-query emphasizing overall appearance
   - Add context: "architectural style", "exterior design", "overall appearance"
   - Weight: 1.5 (MODERATE PRIMARY)
   - Strategy: "max"

IMPORTANT DISTINCTIONS:
- "White house" → "white exterior house facade" (NOT "white kitchen" or "white walls")
- "Blue exterior" → "blue exterior house outside facade" (emphasize OUTSIDE)
- "Granite countertops" → "granite countertops kitchen" (specify KITCHEN)
- "Modern home" → "modern architecture exterior design contemporary style"

User Query: "{query_text}"
Extracted Features: {json.dumps(must_have_features)}

Return strict JSON:
{{
  "sub_queries": [
    {{
      "query": "detailed sub-query text optimized for image matching",
      "feature": "white_exterior",
      "context": "exterior_primary" | "interior_secondary" | "architectural_style",
      "weight": 2.0 | 1.5 | 1.0,
      "search_strategy": "max",
      "rationale": "brief explanation"
    }}
  ],
  "combination_strategy": "weighted_sum",
  "primary_feature": "white_exterior"
}}"""

    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0,  # Deterministic
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        }

        resp = brt.invoke_model(modelId=LLM_MODEL_ID, body=json.dumps(body))
        raw = resp["body"].read().decode("utf-8")
        parsed = json.loads(raw)
        text = parsed["content"][0]["text"]

        # Handle LLM responses that include extra text before/after JSON
        # Sometimes Claude adds "Here is the JSON response:" before the actual JSON
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        if json_start > 0:
            text = text[json_start:json_end]

        result = json.loads(text)

        logger.info(f"LLM split query into {len(result.get('sub_queries', []))} sub-queries")
        for sq in result.get("sub_queries", []):
            logger.info(f"  - {sq['feature']}: '{sq['query']}' (weight={sq['weight']})")

        return result

    except Exception as e:
        logger.warning(f"LLM query splitting failed: {e}, falling back to context-aware sub-queries")
        # Fallback: create context-aware sub-queries from features
        sub_queries = []
        for feature in must_have_features[:3]:  # Limit to 3
            # Make exterior color queries more specific to avoid matching interior items
            if '_exterior' in feature or feature.endswith('_exterior'):
                color = feature.replace('_exterior', '')
                query = f"{color} house exterior facade outside building"
                context = "exterior_primary"
                weight = 2.0  # Exterior features are primary
            # Make countertop queries specific to kitchen
            elif 'countertops' in feature or 'countertop' in feature:
                material = feature.replace('_countertops', '').replace('_countertop', '')
                query = f"{material} kitchen countertops counter surfaces"
                context = "interior_secondary"
                weight = 1.0
            # Make flooring queries specific to floor views
            elif 'floors' in feature or 'flooring' in feature:
                material = feature.replace('_floors', '').replace('_flooring', '')
                query = f"{material} floors flooring room floor surface"
                context = "interior_secondary"
                weight = 1.0
            # Default: simple replacement for other features
            else:
                query = f"{feature.replace('_', ' ')}"
                context = "general"
                weight = 1.0

            sub_queries.append({
                "query": query,
                "feature": feature,
                "context": context,
                "weight": weight,
                "search_strategy": "max",
                "rationale": "fallback"
            })

        return {
            "sub_queries": sub_queries,
            "combination_strategy": "weighted_sum",
            "primary_feature": must_have_features[0] if must_have_features else None
        }


def calculate_multi_query_image_score(inner_hits: Dict, sub_query_embeddings: List[Dict]) -> float:
    """
    Score property images using multiple sub-query embeddings with greedy diversification.

    Uses greedy selection to ensure each sub-query selects a different image for RRF contribution.
    This prevents one feature (e.g., hardwood floors) from dominating all top-K images.

    Algorithm:
    1. Calculate similarity scores for all (sub-query, image) pairs
    2. Greedily select best match, then exclude that sub-query
    3. Each sub-query contributes exactly 1 image to the final score

    Args:
        inner_hits: OpenSearch inner_hits response with image vectors
        sub_query_embeddings: List of {embedding, weight, strategy, feature}

    Returns:
        float: Combined weighted score from diversified image selection
    """
    if not inner_hits or "image_vectors" not in inner_hits:
        return 0.0

    hits = inner_hits["image_vectors"].get("hits", {}).get("hits", [])
    if not hits:
        return 0.0

    # Extract all image vectors with indices
    image_vectors = []
    for idx, hit in enumerate(hits):
        vec = hit.get("_source", {}).get("vector")
        if vec:
            image_vectors.append({"index": idx, "vector": vec})

    if not image_vectors:
        return 0.0

    # Calculate all (sub-query, image) pair similarities
    all_matches = []
    for sq_idx, sq_embed in enumerate(sub_query_embeddings):
        query_vec = sq_embed["embedding"]
        weight = sq_embed["weight"]
        feature = sq_embed.get("feature", "unknown")

        for img_obj in image_vectors:
            img_vec = img_obj["vector"]
            img_idx = img_obj["index"]

            # Cosine similarity
            dot_product = sum(a * b for a, b in zip(query_vec, img_vec))
            mag_q = math.sqrt(sum(a * a for a in query_vec))
            mag_i = math.sqrt(sum(b * b for b in img_vec))

            if mag_q > 0 and mag_i > 0:
                similarity = dot_product / (mag_q * mag_i)
                all_matches.append({
                    "sub_query_index": sq_idx,
                    "image_index": img_idx,
                    "score": similarity,
                    "weight": weight,
                    "feature": feature
                })

    if not all_matches:
        return 0.0

    # Greedy selection: each sub-query gets exactly 1 image (its best match that hasn't been taken)
    # Sort all matches by score descending
    all_matches.sort(key=lambda x: x["score"], reverse=True)

    selected_matches = []
    used_sub_queries = set()

    for match in all_matches:
        # Skip if we've already selected an image for this sub-query
        if match["sub_query_index"] in used_sub_queries:
            continue

        # Select this image for this sub-query
        selected_matches.append(match)
        used_sub_queries.add(match["sub_query_index"])

        logger.info(f"  RRF scoring: Selected sub-query '{match['feature']}': image #{match['image_index']}, score={match['score']:.4f}, weight={match['weight']}")

        # Stop when all sub-queries have contributed an image
        if len(selected_matches) >= len(sub_query_embeddings):
            break

    # Calculate final score from selected matches
    total_score = 0.0
    total_weight = 0.0

    for match in selected_matches:
        weighted_score = match["score"] * match["weight"]
        total_score += weighted_score
        total_weight += match["weight"]

    # Normalize by total weight
    final_score = total_score / total_weight if total_weight > 0 else 0.0
    logger.info(f"Multi-query RRF image score (diversified): {final_score:.4f} (total={total_score:.4f}, weight={total_weight}, selected={len(selected_matches)} images)")

    return final_score


def calculate_multi_query_image_score_detailed(inner_hits: Dict, sub_query_embeddings: List[Dict],
                                                 property_data: Dict) -> tuple:
    """
    Score property images using multiple sub-query embeddings with detailed breakdown.

    Returns both the final score AND per-image details showing which sub-query matched best.
    This is used when include_scoring_details=True.

    Args:
        inner_hits: OpenSearch inner_hits response (not used - kept for compatibility)
        sub_query_embeddings: List of {embedding, weight, strategy, feature, query}
        property_data: Property source data with image_vectors

    Returns:
        tuple: (final_score: float, image_details: List[Dict])
               image_details contains: {index, url, score, sub_query_index, sub_query_feature}
    """
    # Get ALL image vectors from property data (not just inner_hits which is limited)
    if "image_vectors" not in property_data or not property_data["image_vectors"]:
        return 0.0, []

    # Extract all image vectors with their indices from property data
    image_vectors = []
    for idx, img_vec_obj in enumerate(property_data["image_vectors"]):
        vec = img_vec_obj.get("vector")
        if vec:
            image_vectors.append({"vector": vec, "index": idx})

    if not image_vectors:
        return 0.0, []

    # Get image URLs from image_vectors (which has image_url for each vector)
    image_urls = []
    for img_vec_obj in property_data["image_vectors"]:
        url = img_vec_obj.get("image_url", "")
        image_urls.append(url)  # Append even if empty to maintain index alignment

    # GREEDY SELECTION FOR DIVERSIFICATION
    # Calculate ALL (sub-query, image) pair similarities
    all_matches = []  # List of {sq_idx, feature, weight, img_idx, score, url}

    for sq_idx, sq_embed in enumerate(sub_query_embeddings):
        query_vec = sq_embed["embedding"]
        weight = sq_embed["weight"]
        feature = sq_embed.get("feature", "unknown")
        query_text = sq_embed.get("query", "")

        for img_data in image_vectors:
            img_vec = img_data["vector"]
            img_index = img_data["index"]

            # Cosine similarity
            dot_product = sum(a * b for a, b in zip(query_vec, img_vec))
            mag_q = math.sqrt(sum(a * a for a in query_vec))
            mag_i = math.sqrt(sum(b * b for b in img_vec))

            if mag_q > 0 and mag_i > 0:
                similarity = dot_product / (mag_q * mag_i)
                url = image_urls[img_index] if img_index < len(image_urls) else ""

                all_matches.append({
                    "sub_query_index": sq_idx,
                    "sub_query_feature": feature,
                    "sub_query_weight": weight,
                    "sub_query_text": query_text,
                    "image_index": img_index,
                    "score": similarity,
                    "url": url
                })

    # GREEDY SELECTION: Pick best match, then exclude that sub-query
    # This ensures each sub-query contributes AT MOST 1 image to top-K
    selected_images = []
    used_sub_queries = set()

    # Sort all matches by similarity score descending
    all_matches.sort(key=lambda x: x["score"], reverse=True)

    for match in all_matches:
        # Skip if we've already selected an image for this sub-query
        if match["sub_query_index"] in used_sub_queries:
            continue

        # Select this image
        selected_images.append(match)
        used_sub_queries.add(match["sub_query_index"])

        # Stop when all sub-queries have contributed an image
        if len(selected_images) >= len(sub_query_embeddings):
            break

    # Calculate final score as weighted average of selected images
    total_score = 0.0
    total_weight = 0.0
    for img in selected_images:
        total_score += img["score"] * img["sub_query_weight"]
        total_weight += img["sub_query_weight"]

    final_score = total_score / total_weight if total_weight > 0 else 0.0

    # Build detailed image scores list with ALL images (for UI transparency)
    # For images that were SELECTED for scoring, show which sub-query they were selected for
    # For non-selected images, show their best sub-query match

    # Create lookup of selected images: {image_index: {sq_idx, feature, score}}
    selected_lookup = {img["image_index"]: img for img in selected_images}

    # Find best match for each image (for non-selected images)
    image_best_matches = {}
    for match in all_matches:
        img_idx = match["image_index"]
        if img_idx not in image_best_matches or match["score"] > image_best_matches[img_idx]["score"]:
            image_best_matches[img_idx] = match

    # Build image details list - SELECTED images first (ensures top-K diversity)
    # Then non-selected images sorted by score
    image_details = []

    # Add selected images FIRST (sorted by their selection order for consistency)
    for sel_img in selected_images:
        image_details.append({
            "index": sel_img["image_index"],
            "url": sel_img["url"],
            "score": sel_img["score"],
            "sub_query_index": sel_img["sub_query_index"],
            "sub_query_feature": sel_img["sub_query_feature"],
            "selected_for_scoring": True
        })

    # Add non-selected images (sorted by score descending)
    selected_indices = set(img["image_index"] for img in selected_images)
    non_selected = [(idx, match) for idx, match in image_best_matches.items()
                    if idx not in selected_indices]

    for img_idx, match in sorted(non_selected, key=lambda x: x[1]["score"], reverse=True):
        image_details.append({
            "index": match["image_index"],
            "url": match["url"],
            "score": match["score"],
            "sub_query_index": match["sub_query_index"],
            "sub_query_feature": match["sub_query_feature"],
            "selected_for_scoring": False
        })

    logger.info(f"Greedy selection: {len(selected_images)} images selected from {len(sub_query_embeddings)} sub-queries")
    for i, img in enumerate(selected_images, 1):
        logger.info(f"  Selected #{i}: Image {img['image_index']} for SQ{img['sub_query_index']} ({img['sub_query_feature']}, score={img['score']:.4f})")

    logger.info(f"Image details list order (first 5):")
    for i, img in enumerate(image_details[:5], 1):
        sel_flag = "SELECTED" if img["selected_for_scoring"] else "non-sel"
        logger.info(f"  Position {i}: Image {img['index']} SQ{img['sub_query_index']} ({img['score']:.4f}) {sel_flag}")

    return final_score, image_details


# ===============================================
# FEATURE CLASSIFICATION FOR ADAPTIVE SCORING
# ===============================================

# Features that are primarily VISUAL (boost image search)
# These are things you can SEE in property photos
VISUAL_DOMINANT_FEATURES = {
    # Exterior colors - the whole house looks this color
    'white_exterior', 'gray_exterior', 'grey_exterior', 'blue_exterior',
    'brick_exterior', 'stone_exterior', 'beige_exterior', 'brown_exterior',
    'red_exterior', 'tan_exterior', 'yellow_exterior', 'green_exterior',
    'siding', 'stucco_exterior', 'wood_exterior',

    # Architectural styles - visible design characteristics
    'mid_century_modern', 'mid-century', 'craftsman', 'contemporary', 'colonial',
    'ranch', 'victorian', 'mediterranean', 'tudor', 'cape_cod', 'farmhouse',
    'traditional', 'transitional', 'bungalow', 'cottage', 'modern',

    # Outdoor structures - visible in exterior photos
    'white_fence', 'stone_patio', 'brick_walkway', 'deck', 'porch',
    'front_porch', 'covered_patio', 'pergola', 'balcony', 'fence',

    # Environmental/views - visible surroundings
    'mountain_views', 'lake_views', 'ocean_views', 'city_views', 'water_views',
    'wooded_lot', 'corner_lot', 'cul_de_sac', 'waterfront', 'golf_course_view',
}

# Features that are primarily TEXT-based (boost BM25/text search)
# These are mentioned in descriptions but rarely visible in main photos
TEXT_DOMINANT_FEATURES = {
    # Interior specifics - rarely photographed or only in detail shots
    'granite_countertops', 'quartz_countertops', 'marble_countertops',
    'stainless_appliances', 'gas_range', 'double_oven', 'convection_oven',

    # Interior colors - specific color mentions for cabinets/fixtures
    'blue_cabinets', 'white_cabinets', 'gray_cabinets', 'espresso_cabinets',
    'pink_bathroom', 'colored_bathroom',

    # Room features - described but not always visible in listing photos
    'walk_in_closet', 'double_vanity', 'soaking_tub', 'jetted_tub',
    'kitchen_island', 'breakfast_nook', 'pantry', 'butler_pantry',
    'laundry_room', 'mudroom', 'office', 'den',

    # Systems/infrastructure - never visible
    'central_air', 'forced_air_heating', 'radiant_heat', 'heat_pump',
    'tankless_water_heater', 'smart_home', 'security_system', 'solar_panels',
}

# Features that work well with BOTH visual and text (balanced)
HYBRID_FEATURES = {
    # Flooring - visible in interior shots and described
    'hardwood_floors', 'tile_floors', 'carpet', 'laminate', 'vinyl_flooring',
    'wood_floors', 'ceramic_tile', 'porcelain_tile',

    # Common amenities - both visible and tagged
    'pool', 'swimming_pool', 'garage', 'fireplace', 'backyard', 'patio',
    'hot_tub', 'spa',

    # Space features - both visual and descriptive
    'open_floorplan', 'vaulted_ceilings', 'high_ceilings', 'cathedral_ceilings',
    'large_yard', 'finished_basement', 'bonus_room', 'loft',

    # Windows/light - both visual and described
    'lots_of_windows', 'natural_light', 'skylights', 'bay_windows',
    'french_doors', 'sliding_doors',
}


def calculate_adaptive_weights_v2(must_have_tags, query_type):
    """
    Calculate adaptive RRF k-values based on feature context classification.
    Lower k = higher weight for that search strategy.

    This version classifies individual features by their search behavior:
    - VISUAL_DOMINANT: Features best found via image similarity (exterior colors, styles)
    - TEXT_DOMINANT: Features best found via BM25/text search (interior specifics)
    - HYBRID: Features that work well with both approaches (flooring, pools)

    Returns: [bm25_k, text_knn_k, image_knn_k]
    """
    if not must_have_tags:
        logger.info("⚖️  No features - using balanced weights")
        return [60, 60, 60]

    # Classify each feature
    visual_count = sum(1 for tag in must_have_tags if tag in VISUAL_DOMINANT_FEATURES)
    text_count = sum(1 for tag in must_have_tags if tag in TEXT_DOMINANT_FEATURES)
    hybrid_count = sum(1 for tag in must_have_tags if tag in HYBRID_FEATURES)

    total_classified = visual_count + text_count + hybrid_count

    # Log unclassified features for monitoring
    unclassified = [tag for tag in must_have_tags
                    if tag not in VISUAL_DOMINANT_FEATURES
                    and tag not in TEXT_DOMINANT_FEATURES
                    and tag not in HYBRID_FEATURES]
    if unclassified:
        logger.info(f"ℹ️  Unclassified features: {unclassified}")

    if total_classified == 0:
        # All features unknown - use balanced weights
        logger.info("⚖️  Unknown features - using balanced weights")
        return [60, 60, 60]

    # Calculate feature ratios (ignoring unclassified)
    visual_ratio = visual_count / total_classified
    text_ratio = text_count / total_classified
    hybrid_ratio = hybrid_count / total_classified

    # Determine weights based on feature distribution
    # Lower k = higher weight (more important for ranking)
    # UPDATED: Increased image weight across all scenarios (lower k values)
    if visual_ratio >= 0.6:
        # Heavy visual: boost images significantly
        bm25_k, text_k, image_k = 60, 50, 20  # Was 30, now 20 (stronger image weight)
        logger.info(f"👁️  Visual-heavy query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid ({visual_ratio:.0%} visual)")
    elif visual_ratio >= 0.4:
        # Balanced with visual tilt: boost images moderately
        bm25_k, text_k, image_k = 55, 55, 28  # Was 40, now 28 (stronger image weight)
        logger.info(f"🎨 Visual-balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid ({visual_ratio:.0%} visual)")
    elif text_ratio >= 0.6:
        # Heavy text: boost BM25/text, de-emphasize images
        bm25_k, text_k, image_k = 40, 50, 65  # Was 75, now 65 (still lower priority but more weight)
        logger.info(f"📝 Text-heavy query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid ({text_ratio:.0%} text)")
    elif text_ratio >= 0.4:
        # Balanced with text tilt
        bm25_k, text_k, image_k = 45, 52, 55  # Was 65, now 55 (more balanced)
        logger.info(f"📄 Text-balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid ({text_ratio:.0%} text)")
    else:
        # Mixed/hybrid dominated: Check if any visual features present
        # If there are visual features, give images a boost since they're critical
        if visual_count > 0:
            # Has visual features: boost images to ensure visual matches rank well
            bm25_k, text_k, image_k = 60, 55, 25  # Was 35, now 25 (much stronger image weight)
            logger.info(f"🖼️  Mixed query with visual features: {visual_count} visual, {text_count} text, {hybrid_count} hybrid - boosting images")
        else:
            # Pure hybrid/text: balanced weights
            bm25_k, text_k, image_k = 55, 55, 45  # Was 55, now 45 (slightly favor images)
            logger.info(f"⚖️  Balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid")

    logger.info(f"📊 Feature-context weights: BM25={bm25_k}, Text={text_k}, Image={image_k}")
    return [bm25_k, text_k, image_k]


def calculate_adaptive_weights(must_have_tags, query_type):
    """
    OLD VERSION - Calculate adaptive RRF k-values based on query characteristics.
    Lower k = higher weight for that search strategy.

    DEPRECATED: This version incorrectly de-boosts images for ALL color queries.
    Use calculate_adaptive_weights_v2() instead.

    Returns: [bm25_k, text_knn_k, image_knn_k]
    """
    # Define tag categories for analysis
    COLOR_KEYWORDS = ['white', 'gray', 'grey', 'blue', 'beige', 'brown', 'red', 'tan', 'black', 'yellow', 'green', 'cream']
    MATERIAL_KEYWORDS = ['brick', 'stone', 'wood', 'granite', 'marble', 'quartz', 'vinyl', 'stucco', 'hardwood', 'tile', 'concrete']

    # Analyze must_have tags for specific attributes
    has_color = any(any(color in tag.lower() for color in COLOR_KEYWORDS) for tag in must_have_tags)
    has_material = any(any(mat in tag.lower() for mat in MATERIAL_KEYWORDS) for tag in must_have_tags)

    # Start with balanced weights
    bm25_k = 60
    text_k = 60
    image_k = 60

    # ADAPTIVE LOGIC:
    # - Color queries: BM25 works best (tags), images fail (embeddings don't capture color)
    # - Material queries: BM25 works well (tags), text moderate, images less reliable
    # - Visual style: Images work best, text moderate
    # - Specific features: All strategies work (balanced)

    if has_color:
        bm25_k = 30      # BOOST BM25 (tags have exact color info)
        image_k = 120    # DE-BOOST images (embeddings don't distinguish colors)
        logger.info(f"🎨 COLOR detected in tags - boosting BM25 (k=30), de-boosting images (k=120)")

    if has_material:
        bm25_k = int(bm25_k * 0.7)  # Further boost BM25 if not already boosted
        text_k = 45      # Moderate boost for text (descriptions mention materials)
        logger.info(f"🧱 MATERIAL detected in tags - boosting BM25 (k={bm25_k}) and text (k=45)")

    if query_type == "visual_style":
        image_k = 40     # BOOST images for architectural/visual queries
        text_k = 45      # Moderate boost text (descriptions have style info)
        logger.info(f"🏛️ VISUAL_STYLE query - boosting images (k=40) and text (k=45)")

    logger.info(f"📊 OLD adaptive weights: BM25={bm25_k}, Text kNN={text_k}, Image kNN={image_k}")
    return [bm25_k, text_k, image_k]


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

    # Override index if specified in payload (for UI index switching)
    target_index = payload.get("index", OS_INDEX)

    # Boost mode for A/B testing visual features weight
    boost_mode = payload.get("boost_mode", "standard")  # standard | conservative | aggressive

    # Search mode for A/B testing adaptive vs standard scoring
    search_mode = payload.get("search_mode", "adaptive")  # adaptive | standard

    # Strategy selector for individual strategy evaluation
    strategy = payload.get("strategy", "hybrid")  # hybrid | bm25 | knn_text | knn_image
    logger.info("Search query: '%s', size=%d, index=%s, boost_mode=%s, search_mode=%s, strategy=%s", q, size, target_index, boost_mode, search_mode, strategy)

    # Generate query_id and start timing
    query_id = generate_query_id()
    start_time = time.time()
    timing_data = {}
    errors = []
    warnings = []

    # Constraint extraction timing
    t0 = time.time()
    constraints = extract_query_constraints(q)
    timing_data["constraint_extraction_ms"] = (time.time() - t0) * 1000
    hard_filters = constraints.get("hard_filters", {})
    must_tags = set(constraints.get("must_have", []))
    architecture_style = constraints.get("architecture_style")
    proximity = constraints.get("proximity")
    query_type = constraints.get("query_type", "general")
    logger.info("Extracted constraints: %s", constraints)

    # Apply intelligent style mapping if architecture style detected
    style_mapping_info = None
    if architecture_style:
        from architecture_style_mappings import map_user_style_to_supported, get_user_friendly_message

        style_mapping = map_user_style_to_supported(architecture_style)
        logger.info(f"Style mapping: {style_mapping}")

        if style_mapping['confidence'] >= 0.7 and style_mapping['styles']:
            # Use mapped styles for search
            mapped_styles = style_mapping['styles']
            style_mapping_info = {
                'original_query': architecture_style,
                'mapped_styles': mapped_styles,
                'method': style_mapping['method'],
                'confidence': style_mapping['confidence'],
                'user_message': get_user_friendly_message(architecture_style, mapped_styles)
            }
            logger.info(f"Using mapped styles: {mapped_styles}")
        else:
            logger.info(f"Style '{architecture_style}' has no mapping, using semantic search only")

    # Store constraints for logging
    original_constraints = constraints.copy()

    # Detect required features that should be mandatory (pool, garage, etc.)
    required_features = _detect_required_features(q)
    if required_features:
        logger.info("Required features detected (will be mandatory): %s", required_features)

    # Merge explicit filters from payload
    if "filters" in payload:
        hard_filters.update(payload["filters"])
        logger.info("Applied additional filters from payload: %s", payload["filters"])

    # Architecture style is now a SOFT SIGNAL (not a hard filter)
    # It works through:
    # 1. BM25 matching on visual_features_text (which includes "modern style", etc.)
    # 2. Text embeddings capturing semantic similarity between styles
    # 3. Image embeddings capturing visual similarity
    # This allows users to see stylistically similar homes (e.g., contemporary when searching modern)
    if architecture_style:
        logger.info("Architecture style preference detected: %s (soft signal, not filter)", architecture_style)

    # Determine if we need vector search (kNN) based on query characteristics
    # We can skip embeddings requirement if:
    # 1. Query is primarily location-based (has proximity but no feature requirements)
    # 2. Query is simple numeric filters (price, beds, baths)
    # This allows results to show during indexing for geo/filter-only queries
    is_geo_focused = proximity is not None and not must_tags
    needs_semantic_search = bool(must_tags) or not proximity

    # Only require embeddings when we're doing semantic/vector search
    require_embeddings = needs_semantic_search

    if is_geo_focused:
        logger.info("Geo-focused query detected - allowing results without embeddings")
    else:
        logger.info("Semantic search required - filtering for valid embeddings")

    # CRITICAL FIX: Use multimodal embedding to match image embedding space
    t0 = time.time()
    q_vec = embed_text_multimodal(q)
    timing_data["embedding_generation_ms"] = (time.time() - t0) * 1000
    timing_data["bedrock_embedding_calls"] = 1
    filter_clauses = _filters_to_bool(hard_filters, require_embeddings=require_embeddings)["bool"]["filter"]

    # Add required feature filters (pool, garage, etc. must be present)
    if required_features:
        feature_filters = _build_required_feature_filter(required_features)
        filter_clauses.extend(feature_filters)
        logger.info("Added %d required feature filters to query", len(feature_filters))

    # Filter out construction/rendering listings by default
    # These are properties that aren't built yet or only show floorplans/renderings
    filter_clauses.append({
        "bool": {
            "must_not": [
                {"match_phrase": {"description": indicator}}
                for indicator in CONSTRUCTION_INDICATORS
            ]
        }
    })
    logger.info("Added construction listing filter (excluding %d indicators)", len(CONSTRUCTION_INDICATORS))

    # Note: Architecture style is NOT filtered here - it's a soft ranking signal
    # The style preference naturally influences ranking through:
    # - BM25 text match on visual_features_text (contains "modern style", "craftsman style", etc.)
    # - kNN text embeddings (semantic similarity between "modern" and "contemporary")
    # - kNN image embeddings (visual similarity between architecturally similar homes)

    # Note: Proximity filtering uses on-demand place enrichment per listing result
    # Previous approach filtered by pre-computed POI locations (see git history)
    # Current approach is 100x cheaper and works better for user experience

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
    # Boost modes for A/B testing visual features weight:
    # - standard: description^3, visual_features_text^2.5 (original)
    # - conservative: description^3, visual_features_text^3.5 (slight visual boost)
    # - aggressive: description^3, visual_features_text^5 (strong visual boost)
    if boost_mode == "conservative":
        desc_boost = 3
        visual_boost = 3.5
    elif boost_mode == "aggressive":
        desc_boost = 3
        visual_boost = 5
    else:  # standard
        desc_boost = 3
        visual_boost = 2.5

    bm25_query = {
        "query": {
            "bool": {
                "filter": filter_clauses,  # Pass the list directly
                "should": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": [
                                f"description^{desc_boost}",           # Original Zillow description
                                f"visual_features_text^{visual_boost}", # AI-generated from image analysis
                                "llm_profile^2",           # Deprecated, always empty (kept for compatibility)
                                "address^0.5",             # Street address (low weight)
                                "city^0.3",                # City name (low weight)
                                "state^0.2"                # State (low weight)
                            ],
                            "type": "cross_fields",  # CHANGED: Sum scores from all fields (better for multi-field queries)
                            "operator": "or",
                            "minimum_should_match": "50%"  # Require at least half of query terms to match
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

    # Execute BM25 if strategy is hybrid or bm25
    bm25_hits: List[Dict[str, Any]] = []
    if strategy in ["hybrid", "bm25"]:
        t0 = time.time()
        bm25_hits = _os_search(bm25_query, size=size * 3, index=target_index)
        timing_data["bm25_ms"] = (time.time() - t0) * 1000
        logger.info("BM25 returned %d hits", len(bm25_hits))
    else:
        logger.info("Skipping BM25 search (strategy=%s)", strategy)

    # 2) kNN on text vector (only if semantic search is needed)
    # For geo-focused queries, skip kNN to avoid filtering out partially-indexed docs
    knn_text_hits: List[Dict[str, Any]] = []
    if require_embeddings and strategy in ["hybrid", "knn_text"]:
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
            t0 = time.time()
            knn_text_hits = _os_search(knn_text_body, size=size * 3, index=target_index)
            timing_data["knn_text_ms"] = (time.time() - t0) * 1000
            logger.info("kNN text returned %d hits", len(knn_text_hits))
        except Exception as e:
            logger.warning("kNN text search failed: %s", e)
            errors.append({
                "component": "knn_text_search",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "fallback_used": False,
                "impact": "high"
            })
    elif not require_embeddings:
        logger.info("Skipping kNN text search (geo-focused query)")
    else:
        logger.info("Skipping kNN text search (strategy=%s)", strategy)

    # 3) kNN on image vector (only if semantic search is needed)
    knn_img_hits: List[Dict[str, Any]] = []
    # Initialize these variables outside the block so they're accessible in scoring_details
    is_multi_vector = target_index.endswith("-v2")
    image_k = 1  # Default value

    # Check if multi-query splitting mode is enabled
    use_multi_query = payload.get("use_multi_query", False)
    sub_query_data = None  # Will store sub-queries and embeddings if multi-query mode

    if require_embeddings and strategy in ["hybrid", "knn_image"]:
        # Check if we should use multi-query splitting
        if use_multi_query and len(must_tags) >= 2:
            logger.info("🔀 MULTI-QUERY mode enabled - splitting query into sub-queries")

            # Split query using LLM
            # IMPORTANT: Sort must_tags to ensure deterministic ordering
            # must_tags is a set (unordered), so we need to sort for consistency
            t0 = time.time()
            sub_query_result = split_query_into_subqueries(q, sorted(list(must_tags)))
            timing_data["llm_query_split_ms"] = (time.time() - t0) * 1000

            # Check if LLM succeeded
            if "error" in sub_query_result or not sub_query_result.get("sub_queries"):
                errors.append({
                    "component": "llm_query_splitter",
                    "error_type": sub_query_result.get("error_type", "UnknownError"),
                    "error_message": sub_query_result.get("error", "No sub-queries generated"),
                    "fallback_used": True,
                    "impact": "medium"
                })

            # Generate embeddings for each sub-query
            t0 = time.time()
            sub_query_embeddings = []
            for sq in sub_query_result.get("sub_queries", []):
                sq_embedding = embed_text_multimodal(sq["query"])
                sub_query_embeddings.append({
                    "embedding": sq_embedding,
                    "weight": sq["weight"],
                    "strategy": sq["search_strategy"],
                    "feature": sq["feature"],
                    "query": sq["query"]
                })
                logger.info(f"  Generated embedding for: '{sq['query']}'")

            multi_query_embed_ms = (time.time() - t0) * 1000
            timing_data["multi_query_embeddings_ms"] = multi_query_embed_ms
            timing_data["bedrock_embedding_calls"] += len(sub_query_embeddings)

            sub_query_data = {
                "sub_queries": sub_query_result.get("sub_queries", []),
                "embeddings": sub_query_embeddings,
                "primary_feature": sub_query_result.get("primary_feature")
            }

            # Use first sub-query embedding for initial OpenSearch retrieval
            if sub_query_embeddings:
                q_vec = sub_query_embeddings[0]["embedding"]
                logger.info(f"Using first sub-query for retrieval: '{sub_query_embeddings[0]['query']}'")

        # Calculate adaptive K for top-k image scoring (only used in standard mode)
        image_k = calculate_adaptive_k_for_images(must_tags)
        if image_k < 1:
            logger.warning(f"Invalid image_k={image_k}, defaulting to 1")
            image_k = 1

        if not use_multi_query:
            logger.info(f"🖼️  Adaptive K for images: k={image_k} (features={len(must_tags)}, type={query_type})")
        elif sub_query_data:
            logger.info(f"🖼️  Multi-query mode: {len(sub_query_data['embeddings'])} sub-queries")
        else:
            logger.info(f"🖼️  Multi-query mode requested but not applied (requires 2+ features, found {len(must_tags)})")

        try:
            if is_multi_vector:
                # PHASE 2: Query nested image_vectors array
                # We use score_mode="sum" to get access to all image scores,
                # then apply our custom top-k scoring in Python
                knn_img_body = {
                    "size": size * 3,
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "nested": {
                                        "path": "image_vectors",
                                        "score_mode": "sum",  # Sum all images (we'll apply top-k later)
                                        "query": {
                                            "knn": {
                                                "image_vectors.vector": {
                                                    "vector": q_vec,
                                                    "k": topK
                                                }
                                            }
                                        },
                                        "inner_hits": {
                                            "size": 100,  # Maximum allowed by OpenSearch
                                            "_source": True  # Return full nested document
                                        }
                                    }
                                }
                            ],
                            "filter": filter_clauses
                        }
                    }
                }
                logger.info("Using MULTI-VECTOR image search with top-k scoring (listings-v2)")
            else:
                # LEGACY: Single averaged vector
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
                logger.info("Using LEGACY single-vector image search")

            t0 = time.time()
            raw_img_hits = _os_search(knn_img_body, size=size * 3, index=target_index)
            timing_data["knn_image_ms"] = (time.time() - t0) * 1000
            logger.info("kNN image returned %d raw hits", len(raw_img_hits))

            # Apply scoring based on mode
            if is_multi_vector:
                if use_multi_query and sub_query_data:
                    # MULTI-QUERY MODE: Score each property with all sub-query embeddings
                    logger.info("Applying multi-query scoring to results")
                    for hit in raw_img_hits:
                        inner_hits = hit.get("inner_hits", {})
                        multi_query_score = calculate_multi_query_image_score(
                            inner_hits,
                            sub_query_data["embeddings"]
                        )
                        # Override OpenSearch score with multi-query score
                        hit["_score"] = multi_query_score
                        logger.debug(f"  zpid={hit['_id']}: multi-query score={multi_query_score:.4f}")
                    logger.info(f"Applied multi-query scoring to {len(raw_img_hits)} results")
                else:
                    # STANDARD MODE: Recalculate scores using top-k sum
                    for hit in raw_img_hits:
                        inner_hits = hit.get("inner_hits", {})
                        top_k_score = calculate_top_k_image_score(inner_hits, image_k)
                        # Override OpenSearch score with our top-k sum
                        hit["_score"] = top_k_score
                        logger.debug(f"  zpid={hit['_id']}: top-{image_k} score={top_k_score:.4f}")
                    logger.info(f"Applied top-{image_k} scoring to {len(raw_img_hits)} results")

            knn_img_hits = raw_img_hits
        except Exception as e:
            logger.warning("Image kNN skipped (no mapping or field): %s", e)
            errors.append({
                "component": "knn_image_search",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "fallback_used": False,
                "impact": "high"
            })
    elif not require_embeddings:
        logger.info("Skipping kNN image search (geo-focused query)")
    else:
        logger.info("Skipping kNN image search (strategy=%s)", strategy)

    # Calculate adaptive RRF weights based on query characteristics
    if search_mode == "standard":
        # Standard mode: equal weighting for all strategies
        k_values = [60, 60, 60]
        logger.info("📊 STANDARD mode - equal weighting: BM25=60, Text kNN=60, Image kNN=60")
    else:
        # Adaptive mode: feature-context-aware weighting
        k_values = calculate_adaptive_weights_v2(must_tags, query_type)

    # Check if client wants detailed scoring breakdown
    include_scoring_details = payload.get("include_scoring_details", False)

    # Create a mapping of zpid -> original kNN image hit (for inner_hits access)
    knn_img_map = {}
    if include_scoring_details:
        for hit in knn_img_hits:
            knn_img_map[hit["_id"]] = hit

    # Fuse results using RRF with adaptive weights (only includes non-empty result lists)
    # For single-strategy mode, skip fusion and use results directly
    if strategy == "hybrid":
        t0 = time.time()
        fused = _rrf(bm25_hits, knn_text_hits, knn_img_hits, k_values=k_values, top=size * 3, include_scoring_details=include_scoring_details)
        timing_data["rrf_fusion_ms"] = (time.time() - t0) * 1000
        logger.info("RRF fusion produced %d results", len(fused))
    else:
        # Single strategy mode - use results directly
        if strategy == "bm25":
            fused = bm25_hits[:size * 3]
        elif strategy == "knn_text":
            fused = knn_text_hits[:size * 3]
        elif strategy == "knn_image":
            fused = knn_img_hits[:size * 3]
        else:
            fused = []
        logger.info("Single strategy mode (%s) produced %d results", strategy, len(fused))

    # Check if client wants full Zillow data from S3
    include_full_data = payload.get("include_full_data", False)
    include_nearby = payload.get("include_nearby_places", False)  # TEMPORARILY DISABLED for testing

    # Post-RRF tag boosting: Boost results matching exact must_have tags
    # More aggressive boosting for color/material queries where exact matches matter
    t0 = time.time()
    final = []
    for h in fused:
        src = h.get("_source", {}) or {}
        # Use feature_tags for boosting, with image_tags as fallback
        # If feature_tags is empty, use image_tags (visual features detected by CLIP)
        # Visual matching is also handled by kNN image search on embeddings
        feature_tags = set(src.get("feature_tags") or [])
        image_tags = set(src.get("image_tags") or [])

        # Calculate boost based on tag match percentage
        boost = 1.0
        matched_tags = set()
        match_ratio = 0.0  # Initialize to 0
        if expanded_must_tags:
            # First check feature_tags (structured)
            matched_tags = expanded_must_tags.intersection(feature_tags)

            # If feature_tags is empty or incomplete, check image_tags as fallback
            if not matched_tags or len(feature_tags) == 0:
                matched_tags = expanded_must_tags.intersection(image_tags)

            # Normalize matched tags to count unique features (not both underscore and space versions)
            # If we matched both "granite_countertops" and "granite countertops", count as 1 feature
            normalized_matched = set()
            for tag in matched_tags:
                normalized_tag = tag.replace("_", " ")  # Convert to space format
                normalized_matched.add(normalized_tag)

            # Match ratio = unique features matched / total unique features required
            match_ratio = len(normalized_matched) / len(must_tags) if must_tags else 0

            # Progressive boosting based on feature match percentage:
            # - 100% match: 2.0x boost (all required features present)
            # - 75% match: 1.5x boost (most features present)
            # - 50% match: 1.25x boost (half features present)
            # - <50% match: no boost
            if match_ratio >= 1.0:
                boost = 2.0
            elif match_ratio >= 0.75:
                boost = 1.5
            elif match_ratio >= 0.5:
                boost = 1.25

            if boost > 1.0:
                logger.info(f"🎯 Boosting zpid={h['_id']}: {len(normalized_matched)}/{len(must_tags)} features matched ({match_ratio:.0%}) -> {boost}x")

        # ADDITIONAL BOOST: Prioritize properties where first image (exterior photo) matches well
        # Image #0 is typically the main exterior shot on Zillow
        first_image_boost = 1.0
        if strategy in ["hybrid", "knn_image"] and "image_vectors" in src and src["image_vectors"]:
            # Compute score for first image only
            first_img_vec_obj = src["image_vectors"][0]
            first_img_vec = first_img_vec_obj.get("vector")

            if first_img_vec and q_vec and len(first_img_vec) == len(q_vec):
                # Calculate cosine similarity for first image
                dot_product = sum(q * i for q, i in zip(q_vec, first_img_vec))
                q_magnitude = math.sqrt(sum(q * q for q in q_vec)) + 1e-10
                i_magnitude = math.sqrt(sum(i * i for i in first_img_vec)) + 1e-10
                cosine_sim = dot_product / (q_magnitude * i_magnitude)
                first_image_score = (1.0 + float(cosine_sim)) / 2.0

                # Apply boost if first image scores highly (>0.73 = top quartile)
                if first_image_score >= 0.75:
                    first_image_boost = 1.2  # Strong boost for excellent exterior match
                    logger.info(f"🏠 Exterior boost for zpid={h['_id']}: first image score {first_image_score:.3f} -> 1.2x")
                elif first_image_score >= 0.72:
                    first_image_boost = 1.1  # Moderate boost for good exterior match
                    logger.info(f"🏠 Exterior boost for zpid={h['_id']}: first image score {first_image_score:.3f} -> 1.1x")

        zpid = h["_id"]

        # Build result from OpenSearch data
        # Use RRF score (not original OpenSearch _score)
        rrf_score = h.get("_rrf_score", h.get("_score", 0.0))
        result = {
            "zpid": zpid,
            "id": zpid,
            "score": rrf_score * boost * first_image_boost,  # Apply both tag and first-image boosts
            "boosted": boost > 1.0 or first_image_boost > 1.0
        }

        # Add scoring details if requested
        if include_scoring_details:
            # Get scoring details from RRF (stored in document by _rrf function)
            scoring_details = h.get("scoring_details", {})

            # Deduplicate tags for display (remove underscore variants, keep space format)
            # expanded_must_tags contains both "kitchen_island" and "kitchen island"
            # We only want to show "kitchen island" in the UI to avoid confusion
            unique_required_tags = set()
            unique_matched_tags = set()

            for tag in expanded_must_tags:
                # Prefer space format (what's actually stored in index)
                if "_" in tag:
                    space_version = tag.replace("_", " ")
                    if space_version not in expanded_must_tags:
                        unique_required_tags.add(tag)  # Only underscore version exists
                    else:
                        pass  # Skip underscore version, space version will be added
                else:
                    unique_required_tags.add(tag)  # Space version

            for tag in matched_tags:
                # Matched tags should already be in the correct format, but deduplicate anyway
                if "_" in tag:
                    space_version = tag.replace("_", " ")
                    if space_version not in matched_tags:
                        unique_matched_tags.add(tag)
                else:
                    unique_matched_tags.add(tag)

            # Add tag boosting details with deduplicated tags
            scoring_details["tag_boosting"] = {
                "matched_tags": list(unique_matched_tags),
                "required_tags": list(unique_required_tags),
                "match_ratio": match_ratio,  # Use normalized match_ratio calculated earlier
                "boost_factor": boost,
                "first_image_boost": first_image_boost,
                "score_before_boost": rrf_score,
                "score_after_boost": rrf_score * boost * first_image_boost
            }

            # Add query context
            scoring_details["query_context"] = {
                "query_type": query_type,
                "k_values": {
                    "bm25": k_values[0] if len(k_values) > 0 else 60,
                    "knn_text": k_values[1] if len(k_values) > 1 else 60,
                    "knn_image": k_values[2] if len(k_values) > 2 else 60
                },
                "adaptive_scoring_applied": k_values != [60, 60, 60],
                "adaptive_k": image_k,
                "is_multi_vector": is_multi_vector
            }

            # Add image vector count and individual scores if multi-vector
            if "image_vectors" in src:
                scoring_details["image_vectors_count"] = len(src["image_vectors"])

            # Extract individual image vector scores from ALL images in the property
            # For multi-vector index, compute similarity score for each image
            # NOTE: This requires accessing image_vectors from src BEFORE we filter it out
            if "image_vectors" in src and src["image_vectors"]:
                # Check if we're in multi-query mode and should use detailed scoring
                if use_multi_query and sub_query_data and zpid in knn_img_map:
                    # MULTI-QUERY MODE: Use detailed scoring that tracks which sub-query matched each image
                    inner_hits = knn_img_map[zpid].get("inner_hits", {})
                    _, image_scores = calculate_multi_query_image_score_detailed(
                        inner_hits,
                        sub_query_data["embeddings"],
                        src  # Pass source data for responsivePhotos URLs
                    )

                    # NOTE: Do NOT sort here - function returns images in correct order:
                    # Selected images first (for diversity), then non-selected by score
                    scoring_details["individual_image_scores"] = image_scores

                    if image_scores:
                        logger.info(f"Computed {len(image_scores)} multi-query individual image scores for zpid={zpid}, top score: {image_scores[0]['score']:.6f}")
                else:
                    # STANDARD MODE: Use single query vector
                    # Get the query vector (already computed earlier in handler)
                    # q_vec is the text embedding of the search query
                    query_vec = q_vec

                    image_scores = []
                    for idx, img_vec_obj in enumerate(src["image_vectors"]):
                        # Each image_vectors element has: image_url, vector, etc.
                        img_vec = img_vec_obj.get("vector")
                        img_url = img_vec_obj.get("image_url")  # Field is "image_url" not "url"

                        if img_vec and len(img_vec) == len(query_vec):
                            # Compute cosine similarity manually (pure Python, no numpy)
                            # OpenSearch kNN score formula: score = (1 + cosine_similarity) / 2

                            # Calculate dot product
                            dot_product = sum(q * i for q, i in zip(query_vec, img_vec))

                            # Calculate magnitudes
                            q_magnitude = math.sqrt(sum(q * q for q in query_vec)) + 1e-10
                            i_magnitude = math.sqrt(sum(i * i for i in img_vec)) + 1e-10

                            # Cosine similarity
                            cosine_sim = dot_product / (q_magnitude * i_magnitude)

                            # Apply OpenSearch kNN score transformation
                            score = (1.0 + float(cosine_sim)) / 2.0

                            image_scores.append({
                                "index": idx,
                                "url": img_url,
                                "score": score
                            })

                    # Sort by score descending to show best matches first
                    image_scores.sort(key=lambda x: x["score"], reverse=True)
                    scoring_details["individual_image_scores"] = image_scores

                    if image_scores:
                        logger.info(f"Computed {len(image_scores)} individual image scores for zpid={zpid}, top score: {image_scores[0]['score']:.6f}")

            result["_scoring_details"] = scoring_details

        # Add all OpenSearch fields (except vectors)
        # This automatically includes ANY custom fields added via CRUD API
        for k, v in src.items():
            if k not in ("vector_text", "vector_image", "image_vectors"):
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

        # Append with complete score including all boost factors for proper sorting
        final.append((rrf_score * boost * first_image_boost, result))

    final.sort(key=lambda x: x[0], reverse=True)
    results = [x[1] for x in final[:size]]
    timing_data["tag_boosting_ms"] = (time.time() - t0) * 1000

    logger.info("Returning %d final results", len(results))

    # Calculate total time
    total_time_ms = (time.time() - start_time) * 1000
    timing_data["total_ms"] = total_time_ms

    # Track result counts
    result_counts = {
        "bm25_hits": len(bm25_hits),
        "knn_text_hits": len(knn_text_hits),
        "knn_image_hits": len(knn_img_hits),
        "rrf_fused": len(fused),
        "final_returned": len(results)
    }

    # Calculate result overlap
    bm25_ids = set(h["_id"] for h in bm25_hits)
    text_ids = set(h["_id"] for h in knn_text_hits)
    image_ids = set(h["_id"] for h in knn_img_hits)

    result_overlap = {
        "bm25_text_overlap": len(bm25_ids & text_ids),
        "bm25_image_overlap": len(bm25_ids & image_ids),
        "text_image_overlap": len(text_ids & image_ids),
        "all_three_overlap": len(bm25_ids & text_ids & image_ids)
    }

    # Check for warnings
    if expanded_must_tags:
        # Count how many results have empty feature_tags
        empty_tags_count = sum(1 for r in results if not r.get("feature_tags"))
        if empty_tags_count == len(results):
            warnings.append({
                "component": "tag_boosting",
                "message": f"feature_tags empty for {empty_tags_count}/{len(results)} results",
                "impact": "high"
            })

    # Log the search query
    try:
        log_search_query(
            query_id=query_id,
            query_text=q,
            payload=payload,
            constraints=original_constraints,
            timing_data=timing_data,
            results=results,
            result_counts=result_counts,
            result_overlap=result_overlap,
            multi_query_data=sub_query_data,
            errors=errors,
            warnings=warnings,
            total_time_ms=total_time_ms
        )
    except Exception as e:
        logger.error(f"Failed to log search query: {e}")
        # Don't fail the request if logging fails

    response_data = {
        "ok": True,
        "query_id": query_id,
        "results": results,
        "total": len(results),
        "must_have": list(must_tags)
    }

    # Include architecture_style filter in response if it was used
    if architecture_style:
        response_data["architecture_style"] = architecture_style

    # Include style mapping info for user feedback
    if style_mapping_info:
        response_data["style_mapping"] = style_mapping_info

    # Include debug info for multi-query mode
    if sub_query_data:
        response_data["debug_info"] = {
            "sub_queries": sub_query_data.get("sub_queries", []),
            "query": {
                "original": q,
                "extracted_constraints": {
                    "must_tags": list(must_tags),
                    "query_type": query_type,
                    "architecture_style": architecture_style
                }
            }
        }

    return {
        "statusCode": 200,
        "headers": cors_headers,
        "body": json.dumps(response_data)
    }


def get_listing_handler(event, context):
    """
    Get a single listing by zpid.

    Endpoint: GET /listings/{zpid}
    Query Parameters:
        - include_full_data (bool): If true, merges complete Zillow data from S3
        - include_nearby_places (bool): If true, enriches with Google Places data (default: true)
        - index (str): Target index name (default: listings)

    Returns:
        Complete listing with all OpenSearch fields, optionally merged with
        full Zillow data from S3 and enriched with nearby places.

    Example:
        GET /listings/12345?include_full_data=true&include_nearby_places=true
    """
    # CORS headers for all responses
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
    }

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
    target_index = query_params.get("index", OS_INDEX)

    logger.info(f"Fetching listing zpid={zpid}, include_full_data={include_full_data}, include_nearby={include_nearby}, index={target_index}")

    try:
        # Fetch from OpenSearch
        response = os_client.get(index=target_index, id=str(zpid))

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
            if k not in ("vector_text", "vector_image", "image_vectors"):
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


def embed_text_handler(event, context):
    """
    Handler for generating text embeddings via Bedrock Titan.
    Used by test UI pages to validate kNN text search independently.

    Payload format:
      {
        "action": "embed_text",
        "text": "Property description text to embed..."
      }

    Returns:
      {
        "embedding": [0.123, 0.456, ...],  # 1024-dimensional vector
        "dimensions": 1024
      }
    """
    # Note: CORS headers NOT needed here - Lambda Function URL handles CORS automatically

    # Parse body
    body = event.get("body") if isinstance(event, dict) else None
    if body and isinstance(body, str):
        try:
            payload = json.loads(body)
        except Exception:
            payload = event
    else:
        payload = event if isinstance(event, dict) else {}

    text = (payload.get("text") or "").strip()
    if not text:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "missing 'text' parameter"})
        }

    try:
        # Generate embedding using Bedrock Titan
        embedding = embed_text_multimodal(text)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "embedding": embedding,
                "dimensions": len(embedding)
            })
        }

    except Exception as e:
        logger.error(f"Error generating embedding: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


def embed_image_handler(event, context):
    """
    Handler for generating image embeddings via Bedrock Titan.
    Used by test UI pages to validate kNN image search independently.

    Payload format:
      {
        "action": "embed_image",
        "image": "base64-encoded-image-data..."
      }

    Returns:
      {
        "embedding": [0.123, 0.456, ...],  # 1024-dimensional vector
        "dimensions": 1024
      }
    """
    # Note: CORS headers NOT needed here - Lambda Function URL handles CORS automatically

    # Parse body
    body = event.get("body") if isinstance(event, dict) else None
    if body and isinstance(body, str):
        try:
            payload = json.loads(body)
        except Exception:
            payload = event
    else:
        payload = event if isinstance(event, dict) else {}

    image_b64 = (payload.get("image") or "").strip()
    if not image_b64:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "missing 'image' parameter (base64-encoded)"})
        }

    try:
        # Decode base64 image
        image_bytes = base64.b64decode(image_b64)

        # Generate embedding using Bedrock Titan
        embedding = embed_image_bytes(image_bytes)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "embedding": embedding,
                "dimensions": len(embedding)
            })
        }

    except Exception as e:
        logger.error(f"Error generating image embedding: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


def lambda_handler(event, context):
    """
    Router function that dispatches to correct handler based on HTTP method and path.

    This allows a single Lambda to handle multiple endpoints:
    - POST /search → handler() for search
    - GET /listings/{zpid} → get_listing_handler() for single listing retrieval
    - POST with action=embed_text → embed_text_handler() for text embedding generation
    - POST with action=embed_image → embed_image_handler() for image embedding generation

    API Gateway uses Lambda Proxy integration, so all request details are in event.
    """
    # CORS headers for all responses
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
    }

    # Support both API Gateway v1.0 and v2.0 formats
    path = event.get('path') or event.get('rawPath', '')
    method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', '')

    # Check for action parameter in body (for direct Lambda invocation)
    body = event.get("body") if isinstance(event, dict) else None
    if body and isinstance(body, str):
        try:
            payload = json.loads(body)
        except Exception:
            payload = event
    else:
        payload = event if isinstance(event, dict) else {}

    action = payload.get('action')

    # Handle action-based routing for direct Lambda invocations
    if action == 'embed_text':
        logger.info("Action: embed_text")
        return embed_text_handler(event, context)
    elif action == 'embed_image':
        logger.info("Action: embed_image")
        return embed_image_handler(event, context)

    # If no path/method (direct Lambda invocation), check for query in either event or payload
    if not path and not method:
        if 'q' in payload or 'query' in payload:
            logger.info("Direct Lambda invocation - routing to search handler")
            return handler(event, context)
        elif 'q' in event or 'query' in event:
            logger.info("Direct Lambda invocation (event) - routing to search handler")
            return handler(event, context)

    logger.info(f"Router: {method} {path}")

    # POST /search → Search listings
    if method == 'POST' and path == '/search':
        return handler(event, context)

    # POST /search/debug → Search with debug info (same as regular search, UI handles it)
    elif method == 'POST' and path == '/search/debug':
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
