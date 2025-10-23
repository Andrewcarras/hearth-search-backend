"""
search_debug.py - DEBUG Lambda for comprehensive search diagnostics

This is a testing/diagnostic version of search.py that returns extensive
debugging information about search execution. NOT for production use.

Unlike the production search Lambda, this returns:
- Original query and extracted constraints (must_have, hard_filters, architecture_style, etc.)
- All intermediate search results (BM25, kNN text, kNN image) with top results
- Complete OpenSearch query bodies for each strategy
- Individual image vector scores with URLs (from inner_hits)
- RRF fusion details (k-values, adaptive scoring applied)
- Tag matching analysis (matched tags, boost factors)
- Full scoring breakdowns for every result

Purpose:
- Understand why specific properties rank higher/lower
- Debug query parsing and constraint extraction
- Validate adaptive RRF scoring logic
- Inspect individual image vector contributions
- Diagnose search quality issues

Example Usage:
    POST /search/debug
    Body: {
        "q": "modern home with pool",
        "size": 10,
        "index": "listings-v2"
    }
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
import math

from common import (
    os_client, OS_INDEX, embed_text_multimodal,
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


# ===============================================
# FEATURE CLASSIFICATION FOR ADAPTIVE SCORING
# ===============================================

# Features that are primarily VISUAL (boost image search)
VISUAL_DOMINANT_FEATURES = {
    'white_exterior', 'gray_exterior', 'grey_exterior', 'blue_exterior',
    'brick_exterior', 'stone_exterior', 'beige_exterior', 'brown_exterior',
    'red_exterior', 'tan_exterior', 'yellow_exterior', 'green_exterior',
    'siding', 'stucco_exterior', 'wood_exterior',
    'mid_century_modern', 'mid-century', 'craftsman', 'contemporary', 'colonial',
    'ranch', 'victorian', 'mediterranean', 'tudor', 'cape_cod', 'farmhouse',
    'traditional', 'transitional', 'bungalow', 'cottage', 'modern',
    'white_fence', 'stone_patio', 'brick_walkway', 'deck', 'porch',
    'front_porch', 'covered_patio', 'pergola', 'balcony', 'fence',
    'mountain_views', 'lake_views', 'ocean_views', 'city_views', 'water_views',
    'wooded_lot', 'corner_lot', 'cul_de_sac', 'waterfront', 'golf_course_view',
}

# Features that are primarily TEXT-based (boost BM25/text search)
TEXT_DOMINANT_FEATURES = {
    'granite_countertops', 'quartz_countertops', 'marble_countertops',
    'stainless_appliances', 'gas_range', 'double_oven', 'convection_oven',
    'blue_cabinets', 'white_cabinets', 'gray_cabinets', 'espresso_cabinets',
    'pink_bathroom', 'colored_bathroom',
    'walk_in_closet', 'double_vanity', 'soaking_tub', 'jetted_tub',
    'kitchen_island', 'breakfast_nook', 'pantry', 'butler_pantry',
    'laundry_room', 'mudroom', 'office', 'den',
    'central_air', 'forced_air_heating', 'radiant_heat', 'heat_pump',
    'tankless_water_heater', 'smart_home', 'security_system', 'solar_panels',
}

# Features that work well with BOTH visual and text (balanced)
HYBRID_FEATURES = {
    'hardwood_floors', 'tile_floors', 'carpet', 'laminate', 'vinyl_flooring',
    'wood_floors', 'ceramic_tile', 'porcelain_tile',
    'pool', 'swimming_pool', 'garage', 'fireplace', 'backyard', 'patio',
    'hot_tub', 'spa',
    'open_floorplan', 'vaulted_ceilings', 'high_ceilings', 'cathedral_ceilings',
    'large_yard', 'finished_basement', 'bonus_room', 'loft',
    'lots_of_windows', 'natural_light', 'skylights', 'bay_windows',
    'french_doors', 'sliding_doors',
}


def calculate_adaptive_weights_v2(must_have_tags, query_type):
    """
    Calculate adaptive RRF k-values based on feature context classification.
    Lower k = higher weight for that search strategy.

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

    # Log unclassified features
    unclassified = [tag for tag in must_have_tags
                    if tag not in VISUAL_DOMINANT_FEATURES
                    and tag not in TEXT_DOMINANT_FEATURES
                    and tag not in HYBRID_FEATURES]
    if unclassified:
        logger.info(f"ℹ️  Unclassified features: {unclassified}")

    if total_classified == 0:
        logger.info("⚖️  Unknown features - using balanced weights")
        return [60, 60, 60]

    # Calculate feature ratios
    visual_ratio = visual_count / total_classified
    text_ratio = text_count / total_classified

    # Determine weights based on feature distribution
    if visual_ratio >= 0.6:
        bm25_k, text_k, image_k = 60, 50, 30
        logger.info(f"👁️  Visual-heavy query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid ({visual_ratio:.0%} visual)")
    elif visual_ratio >= 0.4:
        bm25_k, text_k, image_k = 55, 55, 40
        logger.info(f"🎨 Visual-balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid ({visual_ratio:.0%} visual)")
    elif text_ratio >= 0.6:
        bm25_k, text_k, image_k = 40, 50, 75
        logger.info(f"📝 Text-heavy query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid ({text_ratio:.0%} text)")
    elif text_ratio >= 0.4:
        bm25_k, text_k, image_k = 45, 52, 65
        logger.info(f"📄 Text-balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid ({text_ratio:.0%} text)")
    else:
        bm25_k, text_k, image_k = 55, 55, 55
        logger.info(f"⚖️  Balanced query: {visual_count} visual, {text_count} text, {hybrid_count} hybrid")

    logger.info(f"📊 Feature-context weights: BM25={bm25_k}, Text={text_k}, Image={image_k}")
    return [bm25_k, text_k, image_k]


def calculate_adaptive_weights(must_have_tags, query_type):
    """
    OLD VERSION - Calculate adaptive RRF k-values based on query characteristics.
    DEPRECATED: Use calculate_adaptive_weights_v2() instead.

    Returns: [bm25_k, text_knn_k, image_knn_k]
    """
    COLOR_KEYWORDS = ['white', 'gray', 'grey', 'blue', 'beige', 'brown', 'red', 'tan', 'black', 'yellow', 'green', 'cream']
    MATERIAL_KEYWORDS = ['brick', 'stone', 'wood', 'granite', 'marble', 'quartz', 'vinyl', 'stucco', 'hardwood', 'tile', 'concrete']

    has_color = any(any(color in tag.lower() for color in COLOR_KEYWORDS) for tag in must_have_tags)
    has_material = any(any(mat in tag.lower() for mat in MATERIAL_KEYWORDS) for tag in must_have_tags)

    bm25_k = 60
    text_k = 60
    image_k = 60

    if has_color:
        bm25_k = 30
        image_k = 120
        logger.info(f"🎨 COLOR detected in tags - boosting BM25 (k=30), de-boosting images (k=120)")

    if has_material:
        bm25_k = int(bm25_k * 0.7)
        text_k = 45
        logger.info(f"🧱 MATERIAL detected in tags - boosting BM25 (k={bm25_k}) and text (k=45)")

    if query_type == "visual_style":
        if not has_color:
            image_k = 40
        text_k = 45
        logger.info(f"🏛️ VISUAL_STYLE query - boosting text (k=45)" + (f", images (k=40)" if not has_color else " (keeping color-based image de-boost)"))

    logger.info(f"📊 OLD adaptive weights: BM25={bm25_k}, Text kNN={text_k}, Image kNN={image_k}")
    return [bm25_k, text_k, image_k]


def calculate_adaptive_k_for_images(must_have_features):
    """
    Calculate adaptive K for top-k image scoring based on query complexity.

    Multi-feature queries need to aggregate multiple images to capture all features,
    while single-feature queries should use best single match (like max).

    Args:
        must_have_features: List of required feature tags from LLM extraction

    Returns:
        int: K value (number of top images to sum)

    Examples:
        - "modern kitchen" → k=1 (single feature, best kitchen photo)
        - "white house with granite countertops" → k=2 (exterior + kitchen)
        - "modern white kitchen with stainless and hardwood" → k=3 (multiple rooms)
    """
    feature_count = len(must_have_features)

    if feature_count == 0:
        # General query without specific features
        # Use k=1 to maintain max-like behavior (best single match)
        return 1
    elif feature_count == 1:
        # Single feature query (e.g., "modern kitchen")
        # Use k=1 - we want the BEST kitchen photo, not sum of all rooms
        return 1
    elif feature_count == 2:
        # Two features (e.g., "white house with granite countertops")
        # Use k=2 - sum top 2 images to capture both exterior and interior
        return 2
    else:
        # Three or more features (e.g., "modern white kitchen with stainless appliances and hardwood floors")
        # Use k=3 - sum top 3 images to capture multiple rooms/features
        return 3


def calculate_top_k_image_score(inner_hits, k):
    """
    Extract image scores from inner_hits and sum the top K scores.

    This function processes the nested image_vectors inner_hits returned by OpenSearch
    and calculates a final score by summing the top K image scores.

    Args:
        inner_hits: The inner_hits section from OpenSearch nested query response
        k: Number of top images to sum

    Returns:
        float: Sum of top K image scores

    Example:
        Property with 5 images: [0.85, 0.72, 0.68, 0.22, 0.15]
        k=1 → 0.85 (best single match, like max)
        k=2 → 1.57 (0.85 + 0.72, captures two features)
        k=3 → 2.25 (0.85 + 0.72 + 0.68, captures three features)
    """
    if not inner_hits or "image_vectors" not in inner_hits:
        return 0.0

    # Extract all image scores from inner hits
    hits = inner_hits["image_vectors"].get("hits", {}).get("hits", [])
    scores = [hit.get("_score", 0.0) for hit in hits]

    if not scores:
        return 0.0

    # Sort scores descending and take top K
    scores.sort(reverse=True)
    top_k_scores = scores[:k]

    # Sum the top K scores
    total = sum(top_k_scores)

    logger.debug(f"Top-K scoring: k={k}, available={len(scores)}, top_scores={top_k_scores[:5]}, sum={total:.4f}")

    return total


# ===============================================
# LAMBDA HANDLER
# ===============================================

def handler(event, context):
    """
    DEBUG Lambda handler for comprehensive search diagnostics.

    This is a testing/diagnostic version of the search Lambda that returns
    EVERYTHING about how the search was executed, scored, and ranked.

    Returns extensive diagnostic information including:
    - Original query and extracted constraints
    - All intermediate search results (BM25, kNN text, kNN image)
    - Individual image vector scores with URLs
    - OpenSearch query bodies
    - RRF fusion details
    - Tag matching analysis
    - Full scoring breakdowns

    This Lambda is NOT optimized for production use - it prioritizes
    diagnostic information over response size and speed.

    Args:
        event: Lambda event with query payload
        context: Lambda context (unused)

    Returns:
        Comprehensive diagnostic response with all search internals
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

    # DEBUG: Start collecting diagnostic information
    debug_info = {
        "query": {
            "original_query": q,
            "size_requested": size,
            "index": target_index,
            "boost_mode": boost_mode
        }
    }

    # Extract query constraints with error handling
    try:
        constraints = extract_query_constraints(q)
        hard_filters = constraints.get("hard_filters", {})
        must_tags = set(constraints.get("must_have", []))
        architecture_style = constraints.get("architecture_style")
        proximity = constraints.get("proximity")
        query_type = constraints.get("query_type", "general")
        logger.info("Extracted constraints: %s", constraints)
    except Exception as e:
        logger.error(f"Query constraint extraction failed: {e}", exc_info=True)
        # Fallback to empty constraints so search can still proceed
        constraints = {
            "must_have": [],
            "nice_to_have": [],
            "hard_filters": {},
            "architecture_style": None,
            "proximity": None,
            "query_type": "general"
        }
        hard_filters = {}
        must_tags = set()
        architecture_style = None
        proximity = None
        query_type = "general"
        debug_info["query"]["constraint_extraction_error"] = str(e)

    # DEBUG: Store extracted constraints
    debug_info["query"]["extracted_constraints"] = constraints
    debug_info["query"]["must_tags"] = list(must_tags)
    debug_info["query"]["hard_filters"] = hard_filters
    debug_info["query"]["architecture_style"] = architecture_style
    debug_info["query"]["proximity"] = proximity

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

    # Generate query embedding with error handling
    try:
        q_vec = embed_text_multimodal(q)

        # Validate embedding quality
        import math
        vec_magnitude = math.sqrt(sum(v * v for v in q_vec)) if q_vec else 0
        vec_nonzero = sum(1 for v in q_vec if abs(v) > 1e-10) if q_vec else 0

        debug_info["query"]["embedding_stats"] = {
            "dimension": len(q_vec) if q_vec else 0,
            "magnitude": vec_magnitude,
            "nonzero_count": vec_nonzero,
            "is_zero_vector": vec_magnitude < 1e-6
        }

        if vec_magnitude < 1e-6:
            logger.warning("Query embedding is a zero vector! kNN search will return random results.")

    except Exception as e:
        logger.error(f"Failed to generate query embedding: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({
                "error": "Failed to generate query embedding",
                "details": str(e),
                "debug_info": debug_info
            })
        }

    filter_clauses = _filters_to_bool(hard_filters, require_embeddings=require_embeddings)["bool"]["filter"]

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
        bm25_hits = _os_search(bm25_query, size=size * 3, index=target_index)
        logger.info("BM25 returned %d hits", len(bm25_hits))

        # DEBUG: Store BM25 query and results
        debug_info["bm25"] = {
            "query": bm25_query,
            "hits_count": len(bm25_hits),
            "top_results": [{"zpid": h["_id"], "score": h.get("_score", 0.0)} for h in bm25_hits[:10]]
        }
    else:
        logger.info("Skipping BM25 search (strategy=%s)", strategy)
        debug_info["bm25"] = {"skipped": True, "reason": f"strategy={strategy}"}

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
            knn_text_hits = _os_search(knn_text_body, size=size * 3, index=target_index)
            logger.info("kNN text returned %d hits", len(knn_text_hits))

            # DEBUG: Store kNN text query and results
            debug_info["knn_text"] = {
                "query": knn_text_body,
                "hits_count": len(knn_text_hits),
                "top_results": [{"zpid": h["_id"], "score": h.get("_score", 0.0)} for h in knn_text_hits[:10]]
            }
        except Exception as e:
            logger.warning("kNN text search failed: %s", e)
            debug_info["knn_text"] = {"error": str(e)}
    elif not require_embeddings:
        logger.info("Skipping kNN text search (geo-focused query)")
        debug_info["knn_text"] = {"skipped": True, "reason": "geo-focused query"}
    else:
        logger.info("Skipping kNN text search (strategy=%s)", strategy)
        debug_info["knn_text"] = {"skipped": True, "reason": f"strategy={strategy}"}

    # 3) kNN on image vector (only if semantic search is needed)
    knn_img_hits: List[Dict[str, Any]] = []
    if require_embeddings and strategy in ["hybrid", "knn_image"]:
        # Detect if using multi-vector schema
        is_multi_vector = target_index.endswith("-v2")

        # Calculate adaptive K for top-k image scoring
        image_k = calculate_adaptive_k_for_images(must_tags)
        if image_k < 1:
            logger.warning(f"Invalid image_k={image_k}, defaulting to 1")
            image_k = 1
        logger.info(f"🖼️  Adaptive K for images: k={image_k} (features={len(must_tags)}, type={query_type})")

        try:
            if is_multi_vector:
                # TOP-K IMAGES SUM: Query nested image_vectors array with sum aggregation
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
                logger.info("Using MULTI-VECTOR image search with adaptive top-k scoring (listings-v2)")
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

            raw_img_hits = _os_search(knn_img_body, size=size * 3, index=target_index)
            logger.info("kNN image returned %d raw hits", len(raw_img_hits))

            # Apply top-k scoring to multi-vector results
            # Even when k=1, we need to recalculate because we changed score_mode from "max" to "sum"
            if is_multi_vector:
                # Recalculate scores using top-k sum instead of OpenSearch's score_mode
                for hit in raw_img_hits:
                    inner_hits = hit.get("inner_hits", {})
                    top_k_score = calculate_top_k_image_score(inner_hits, image_k)
                    # Override OpenSearch score with our top-k sum
                    hit["_score"] = top_k_score
                    logger.debug(f"  zpid={hit['_id']}: top-{image_k} score={top_k_score:.4f}")
                logger.info(f"Applied top-{image_k} scoring to {len(raw_img_hits)} results")

            knn_img_hits = raw_img_hits

            # DEBUG: Store kNN image query and results (including inner_hits)
            debug_info["knn_image"] = {
                "query": knn_img_body,
                "hits_count": len(knn_img_hits),
                "top_results": [{"zpid": h["_id"], "score": h.get("_score", 0.0), "has_inner_hits": "inner_hits" in h} for h in knn_img_hits[:10]],
                "is_multi_vector": is_multi_vector,
                "adaptive_k": image_k
            }
        except Exception as e:
            logger.warning("Image kNN skipped (no mapping or field): %s", e)
            debug_info["knn_image"] = {"error": str(e)}
    elif not require_embeddings:
        logger.info("Skipping kNN image search (geo-focused query)")
        debug_info["knn_image"] = {"skipped": True, "reason": "geo-focused query"}
    else:
        logger.info("Skipping kNN image search (strategy=%s)", strategy)
        debug_info["knn_image"] = {"skipped": True, "reason": f"strategy={strategy}"}

    # Calculate adaptive RRF weights based on query characteristics
    if search_mode == "standard":
        # Standard mode: equal weighting for all strategies
        k_values = [60, 60, 60]
        logger.info("📊 STANDARD mode - equal weighting: BM25=60, Text kNN=60, Image kNN=60")
    else:
        # Adaptive mode: feature-context-aware weighting
        k_values = calculate_adaptive_weights_v2(must_tags, query_type)

    # Check if client wants detailed scoring breakdown (always True for debug Lambda)
    include_scoring_details = True

    # Create a mapping of zpid -> original kNN image hit (for inner_hits access)
    knn_img_map = {}
    for hit in knn_img_hits:
        knn_img_map[hit["_id"]] = hit

    # Fuse results using RRF with adaptive weights (only includes non-empty result lists)
    # For single-strategy mode, skip fusion and use results directly
    if strategy == "hybrid":
        fused = _rrf(bm25_hits, knn_text_hits, knn_img_hits, k_values=k_values, top=size * 3, include_scoring_details=True)  # Always get scoring details for debug
        logger.info("RRF fusion produced %d results", len(fused))
    else:
        # Single strategy mode - use results directly with scoring details
        if strategy == "bm25":
            fused = bm25_hits[:size * 3]
        elif strategy == "knn_text":
            fused = knn_text_hits[:size * 3]
        elif strategy == "knn_image":
            fused = knn_img_hits[:size * 3]
        else:
            fused = []
        # Add basic scoring details for single-strategy results
        for hit in fused:
            hit["scoring_details"] = {
                "bm25": {"rank": None, "original_score": hit.get("_score", 0.0) if strategy == "bm25" else None, "rrf_contribution": 0.0, "k": k_values[0] if len(k_values) > 0 else 60},
                "knn_text": {"rank": None, "original_score": hit.get("_score", 0.0) if strategy == "knn_text" else None, "rrf_contribution": 0.0, "k": k_values[1] if len(k_values) > 1 else 60},
                "knn_image": {"rank": None, "original_score": hit.get("_score", 0.0) if strategy == "knn_image" else None, "rrf_contribution": 0.0, "k": k_values[2] if len(k_values) > 2 else 60},
                "rrf_total": 0.0
            }
            hit["_rrf_score"] = hit.get("_score", 0.0)  # For single strategy, use OpenSearch score directly
        logger.info("Single strategy mode (%s) produced %d results", strategy, len(fused))

    # DEBUG: Store RRF configuration and adaptive weights
    debug_info["rrf"] = {
        "strategy": strategy,
        "k_values": {
            "bm25": k_values[0] if len(k_values) > 0 else None,
            "knn_text": k_values[1] if len(k_values) > 1 else None,
            "knn_image": k_values[2] if len(k_values) > 2 else None
        },
        "query_type": query_type,
        "adaptive_scoring_applied": k_values != [60, 60, 60],
        "fusion_result_count": len(fused)
    }

    # Check if client wants full Zillow data from S3
    include_full_data = payload.get("include_full_data", False)
    include_nearby = payload.get("include_nearby_places", True)

    # Post-RRF tag boosting: Boost results matching exact must_have tags
    # More aggressive boosting for color/material queries where exact matches matter
    final = []
    for h in fused:
        src = h.get("_source", {}) or {}
        # Use only feature_tags for boosting (not image_tags)
        # image_tags are auto-generated and often inaccurate (e.g., "white_exterior" from interior photos)
        # Visual matching is handled by kNN image search on embeddings
        tags = set(src.get("feature_tags") or [])

        # Calculate boost based on tag match percentage
        boost = 1.0
        matched_tags = set()
        if expanded_must_tags:
            matched_tags = expanded_must_tags.intersection(tags)
            match_ratio = len(matched_tags) / len(expanded_must_tags)

            # Progressive boosting (REDUCED to prevent overriding semantic quality):
            # - 100% match: 1.3x boost (all tags present)
            # - 75% match: 1.15x boost
            # - 50% match: 1.08x boost
            # - <50% match: no boost
            if match_ratio >= 1.0:
                boost = 1.3
            elif match_ratio >= 0.75:
                boost = 1.15
            elif match_ratio >= 0.5:
                boost = 1.08

            if boost > 1.0:
                logger.info(f"🎯 Boosting zpid={h['_id']}: {len(matched_tags)}/{len(expanded_must_tags)} tags matched ({match_ratio:.0%}) -> {boost}x")

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
                "match_ratio": len(matched_tags) / len(expanded_must_tags) if expanded_must_tags else 0.0,
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
                "adaptive_scoring_applied": k_values != [60, 60, 60]
            }

            # Add image vector count and individual scores if multi-vector
            if "image_vectors" in src:
                scoring_details["image_vectors_count"] = len(src["image_vectors"])

            # Extract individual image vector scores from ALL images in the property
            # For multi-vector index, compute similarity score for each image
            # NOTE: This requires accessing image_vectors from src BEFORE we filter it out
            if "image_vectors" in src and src["image_vectors"]:
                # Get the query vector (already computed earlier in handler)
                # q_vec is the text embedding of the search query
                query_vec = q_vec

                image_scores = []
                for idx, img_vec_obj in enumerate(src["image_vectors"]):
                    # Each image_vectors element has: image_url, vector, etc.
                    img_vec = img_vec_obj.get("vector")
                    img_url = img_vec_obj.get("image_url")  # Field is "image_url" not "url"

                    if img_vec and len(img_vec) == len(query_vec):
                        # Compute cosine similarity manually
                        # OpenSearch kNN score formula: score = (1 + cosine_similarity) / 2
                        # Compute cosine similarity manually (pure Python, no numpy)
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

        final.append((h.get("_score", 0.0) * boost, result))

    final.sort(key=lambda x: x[0], reverse=True)
    results = [x[1] for x in final[:size]]

    logger.info("Returning %d final results", len(results))

    # DEBUG: Build comprehensive diagnostic response
    response_data = {
        "ok": True,
        "results": results,
        "total": len(results),
        "must_have": list(must_tags),
        "debug_info": debug_info  # Include all diagnostic information
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
    Get a single listing by zpid (DEBUG version - same as production).

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


def lambda_handler(event, context):
    """
    Router function that dispatches to correct handler based on HTTP method and path.

    This allows a single Lambda to handle multiple endpoints:
    - POST /search → handler() for search
    - GET /listings/{zpid} → get_listing_handler() for single listing retrieval

    API Gateway uses Lambda Proxy integration, so all request details are in event.
    """
    # CORS headers for all responses
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
    }

    path = event.get('path', '')
    method = event.get('httpMethod', '')

    # If no path/method (direct Lambda invocation), assume search
    if not path and not method and 'q' in event:
        logger.info("Direct Lambda invocation - routing to search handler")
        return handler(event, context)

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
