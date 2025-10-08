"""
upload_listings.py - Lambda function for indexing real estate listings to OpenSearch

This Lambda function processes Zillow property listings and indexes them into OpenSearch
with rich multimodal embeddings for semantic search.

Processing pipeline for each listing:
1. Extract core fields (price, beds, location, etc.) from Zillow JSON
2. Generate fallback description if missing
3. Use Claude LLM to extract normalized feature tags
4. Generate text embeddings from description using Bedrock Titan
5. Download and process up to MAX_IMAGES property photos
6. Generate image embeddings using Bedrock Titan
7. Detect visual features using AWS Rekognition
8. Index document with all fields and embeddings to OpenSearch

The function supports self-invocation for processing large datasets that exceed
Lambda's execution time limit (15 minutes).

Invocation modes:
- From S3: {"bucket": "my-bucket", "key": "listings.json", "start": 0, "limit": 500}
- Direct: {"listings": [...], "start": 0, "limit": 500}
"""

import json
import logging
import os
import uuid
from typing import Any, Dict, List

import boto3
import requests

from common import (
    AWS_REGION, OS_INDEX, MAX_IMAGES,
    create_index_if_needed, bulk_upsert,
    embed_text, embed_image_bytes, detect_labels,
    extract_zillow_images, vec_mean, llm_feature_profile,
    classify_architecture_style_vision
)

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# AWS clients for S3 access and self-invocation
s3 = boto3.client("s3", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)


# ===============================================
# DATA LOADING & EXTRACTION HELPERS
# ===============================================

def _load_listings_from_s3(bucket: str, key: str) -> List[Dict[str, Any]]:
    """
    Load listings array from S3 JSON file.

    Supports two JSON formats:
    - {"listings": [...]}  (wrapped array)
    - [...]  (direct array)

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        List of listing dictionaries

    Raises:
        ValueError: If JSON structure is not recognized
    """
    obj = s3.get_object(Bucket=bucket, Key=key)
    raw = obj["Body"].read().decode("utf-8")
    data = json.loads(raw)

    if isinstance(data, dict) and "listings" in data:
        return data["listings"]  # Wrapped format
    if isinstance(data, list):
        return data  # Direct array format

    raise ValueError("Unsupported JSON shape for listings")


def _num(x):
    """
    Safely convert value to numeric type, returning None for empty/null values.

    Args:
        x: Value to convert

    Returns:
        Original value if non-empty, None otherwise
    """
    return None if x in (None, "", "null") else x

def _extract_core_fields(lst: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize core listing fields from raw Zillow JSON.

    Zillow's JSON format varies significantly across scrapes, with fields appearing
    at different nesting levels or with different names. This function handles all
    known variations and provides sensible fallbacks.

    Key features:
    - Handles nested vs flat address structures
    - Generates fallback descriptions when missing
    - Normalizes field names to consistent schema
    - Validates and converts data types

    Args:
        lst: Raw Zillow listing dictionary

    Returns:
        Dictionary with normalized fields: zpid, description, price, beds, baths,
        acreage, address, city, state, zip_code, geo, has_description
    """
    # Extract unique identifier (zpid = Zillow Property ID)
    zpid = str(lst.get("zpid") or lst.get("id") or uuid.uuid4().hex)

    # Try multiple possible description fields
    desc = lst.get("description") or lst.get("homeDescription") or lst.get("descriptionText") or ""

    # Extract price from various possible field names
    price = _num(lst.get("price") or lst.get("listPrice") or lst.get("unformattedPrice"))

    # Extract location components (try top-level first, then nested address object)
    city = lst.get("city") or lst.get("addressCity")
    state = lst.get("state") or lst.get("addressState")
    zipc = lst.get("zipcode") or lst.get("postalCode")

    # Fallback: check nested address object
    if not city or not state or not zipc:
        addr_obj = lst.get("address", {})
        if isinstance(addr_obj, dict):
            city = city or addr_obj.get("city")
            state = state or addr_obj.get("state")
            zipc = zipc or addr_obj.get("zipcode")

    # Extract street address (handle both string and nested object formats)
    addr = lst.get("address") or lst.get("streetAddress") or lst.get("homeAddress") or ""
    if isinstance(addr, dict):
        addr = addr.get("streetAddress", "")

    # Extract property characteristics
    beds  = _num(lst.get("bedrooms") or lst.get("beds"))
    baths = _num(lst.get("bathrooms") or lst.get("baths"))
    acreage = _num(lst.get("lotSize") or lst.get("acreage") or lst.get("lotArea"))

    # Extract geo coordinates for location-based search
    lat = lst.get("latitude") or (lst.get("latLong") or {}).get("latitude")
    lon = lst.get("longitude") or (lst.get("latLong") or {}).get("longitude")
    geo = {"lat": float(lat), "lon": float(lon)} if (lat and lon) else None

    # Generate fallback description if missing (critical for search quality)
    has_description = bool(desc.strip())
    if not has_description:
        # Build description from available fields
        fallback_parts = []
        if addr:
            fallback_parts.append(f"Property at {addr}")
        if city and state:
            fallback_parts.append(f"in {city}, {state}")
        if beds:
            fallback_parts.append(f"{int(beds)} bedroom")
        if baths:
            fallback_parts.append(f"{baths} bath")
        if price and price > 0:
            fallback_parts.append(f"listed at ${price:,}")

        desc = " ".join(fallback_parts) if fallback_parts else "Property listing"
        logger.info("Generated fallback description for zpid=%s: %s", zpid, desc[:100])

    return {
        "zpid": zpid,
        "description": str(desc),
        "has_description": has_description,
        "price": int(price) if price is not None else None,
        "beds": float(beds) if beds is not None else None,
        "baths": float(baths) if baths is not None else None,
        "acreage": float(acreage) if acreage is not None else None,
        "address": addr,
        "city": city,
        "state": state,
        "zip_code": zipc,
        "geo": geo,
    }


# ===============================================
# DOCUMENT BUILDING WITH EMBEDDINGS
# ===============================================

def _build_doc(base: Dict[str, Any], image_urls: List[str]) -> Dict[str, Any]:
    """
    Build a complete OpenSearch document with text and image embeddings.

    This is the core processing function that enriches each listing with:
    1. LLM-extracted features (pool, garage, etc.) via Claude
    2. Text embeddings (1024-dim vector) via Bedrock Titan
    3. Image embeddings (averaged from multiple photos) via Bedrock Titan
    4. Visual labels (kitchen, brick, etc.) via Rekognition
    5. Data quality flags (has_valid_embeddings, has_description)

    The function is resilient to failures at each step, logging errors and
    continuing with fallback values to ensure indexing completes.

    Args:
        base: Normalized core fields from _extract_core_fields()
        image_urls: List of property image URLs to process

    Returns:
        Complete document ready for OpenSearch indexing with all embeddings,
        tags, and metadata
    """
    # Step 1: Extract structured features using Claude LLM (including architecture style from text)
    llm_profile, feature_tags, style_from_text = "", [], None
    try:
        llm_profile, feature_tags, style_from_text = llm_feature_profile(base["description"])
    except Exception as e:
        logger.warning("LLM profile extraction failed for zpid=%s: %s", base.get("zpid"), e)

    # Text embeddings (resilient)
    vec_text = None
    text_embedding_failed = False
    try:
        text_for_embed = " ".join([t for t in [base["description"], llm_profile] if t]).strip()
        if text_for_embed:
            vec_text = embed_text(text_for_embed)
            if not vec_text or len(vec_text) == 0:
                raise ValueError("Empty vector returned from embed_text")
        else:
            logger.warning("No text to embed for zpid=%s", base.get("zpid"))
            text_embedding_failed = True
    except Exception as e:
        logger.error("Text embedding FAILED for zpid=%s: %s", base.get("zpid"), e)
        text_embedding_failed = True

    # If text embedding failed, use zeros
    if vec_text is None:
        vec_text = [0.0] * int(os.getenv("TEXT_DIM", "1024"))

    # Image vectors + tags (optional + resilient)
    # Deduplicate images by computing hash to avoid processing duplicates
    image_vecs, img_tags = [], set()
    seen_hashes = set()
    style_from_vision = None
    best_exterior_image = None  # Store best exterior image for architecture classification
    best_exterior_score = 0

    # Keywords that indicate exterior/facade views
    EXTERIOR_KEYWORDS = {'house', 'building', 'home', 'exterior', 'facade', 'front', 'architecture',
                         'roof', 'siding', 'porch', 'deck', 'yard', 'lawn', 'driveway', 'garage'}
    # Keywords that indicate interior/detail views (to avoid)
    INTERIOR_KEYWORDS = {'room', 'kitchen', 'bathroom', 'bedroom', 'living', 'dining', 'closet',
                         'interior', 'furniture', 'appliance', 'cabinet', 'counter'}

    if MAX_IMAGES and MAX_IMAGES > 0 and image_urls:
        count = 0
        for u in image_urls:
            if count >= MAX_IMAGES:
                break
            try:
                resp = requests.get(u, timeout=8)
                resp.raise_for_status()
                bb = resp.content

                # Skip duplicate images using content hash
                import hashlib
                img_hash = hashlib.md5(bb).hexdigest()
                if img_hash in seen_hashes:
                    logger.debug("Skipping duplicate image for zpid=%s", base.get("zpid"))
                    continue
                seen_hashes.add(img_hash)

                try:
                    img_vec = embed_image_bytes(bb)
                    if img_vec and len(img_vec) > 0:
                        image_vecs.append(img_vec)
                except Exception as e:
                    logger.warning("Image embedding failed for zpid=%s, url=%s: %s", base.get("zpid"), u, e)

                # COST OPTIMIZATION: Only use Rekognition for first image to detect exterior vs interior
                # Claude Vision will do comprehensive analysis later on the best exterior image
                # This reduces Rekognition calls from 6 per property to 1-2 per property
                if count == 0:
                    # Get labels ONLY for first image to identify if it's exterior
                    try:
                        labels = detect_labels(bb)
                        for t in labels:
                            img_tags.add(t)

                        # Score this image for architecture classification
                        # Higher score = better exterior shot
                        exterior_score = 0
                        label_set = set(l.lower() for l in labels)

                        # Add points for exterior indicators
                        exterior_score += sum(3 for kw in EXTERIOR_KEYWORDS if kw in label_set)
                        # Subtract points for interior indicators
                        exterior_score -= sum(2 for kw in INTERIOR_KEYWORDS if kw in label_set)

                        # If this is the best exterior image so far, save it
                        if exterior_score > best_exterior_score:
                            best_exterior_score = exterior_score
                            best_exterior_image = bb
                            logger.debug("Found better exterior image for zpid=%s (score: %d, labels: %s)",
                                       base.get("zpid"), exterior_score, labels[:5])

                    except Exception as e:
                        logger.warning("Image label detection failed for zpid=%s: %s", base.get("zpid"), e)
                else:
                    # For subsequent images, just use the first one as exterior candidate
                    # This saves 5 Rekognition calls per property (83% cost reduction)
                    if count == 1 and not best_exterior_image:
                        best_exterior_image = bb
                        best_exterior_score = 1

                count += 1
            except Exception as e:
                logger.warning("Image fetch failed for zpid=%s, url=%s: %s", base.get("zpid"), u, e)

    # Classify architecture style using vision LLM on best exterior image
    if best_exterior_image:
        try:
            style_data = classify_architecture_style_vision(best_exterior_image)
            style_from_vision = style_data.get("primary_style")

            # Add exterior color and materials to image tags if present
            if style_data.get("exterior_color"):
                img_tags.add(f"{style_data['exterior_color']}_exterior")
            for material in style_data.get("materials", []):
                img_tags.add(material)

            # Add visual features (balcony, porch, fence, etc.) to image tags
            for feature in style_data.get("visual_features", []):
                img_tags.add(feature)

            logger.info("Classified architecture style for zpid=%s: %s (confidence: %s, exterior_score: %d, features: %s)",
                       base.get("zpid"), style_from_vision, style_data.get("confidence"),
                       best_exterior_score, style_data.get("visual_features", [])[:5])
        except Exception as e:
            logger.warning("Vision-based style classification failed for zpid=%s: %s", base.get("zpid"), e)

    vec_image = vec_mean(image_vecs, target_dim=len(vec_text)) if image_vecs else [0.0] * len(vec_text)

    # Determine if embeddings are valid (non-zero)
    has_valid_text_embedding = not text_embedding_failed and vec_text and sum(abs(v) for v in vec_text) > 0.0
    has_valid_image_embedding = len(image_vecs) > 0 and vec_image and sum(abs(v) for v in vec_image) > 0.0
    has_valid_embeddings = has_valid_text_embedding or has_valid_image_embedding

    if not has_valid_embeddings:
        logger.warning("Document zpid=%s has NO valid embeddings (text_valid=%s, image_valid=%s)",
                      base.get("zpid"), has_valid_text_embedding, has_valid_image_embedding)

    # Determine final architecture style (vision takes priority over text)
    architecture_style = style_from_vision or style_from_text

    # Build document - only include vectors if they're valid (non-zero)
    # This prevents indexing errors with cosinesimil space_type
    doc = {
        **{k: v for k, v in base.items() if v not in (None, "")},
        "llm_profile": llm_profile,
        "feature_tags": sorted(set(feature_tags)),
        "image_tags": sorted(img_tags),
        "has_valid_embeddings": has_valid_embeddings,
        "status": "active",
        "indexed_at": int(__import__("time").time()),
    }

    # Add architecture style if detected
    if architecture_style:
        doc["architecture_style"] = architecture_style

    # Only add vector fields if they're valid (OpenSearch cosinesimil doesn't support zero vectors)
    if has_valid_text_embedding:
        doc["vector_text"] = vec_text
    if has_valid_image_embedding:
        doc["vector_image"] = vec_image

    return doc


# ===============================================
# LAMBDA HANDLER
# ===============================================

def handler(event, context):
    """
    AWS Lambda handler for indexing real estate listings to OpenSearch.

    This function processes listings in batches with automatic continuation via
    self-invocation if the dataset is too large to process in one execution.

    Processing flow:
    1. Create OpenSearch index if it doesn't exist
    2. Load listings from S3 or direct payload
    3. Process batch of listings (default 500 per invocation)
    4. For each listing:
       - Extract core fields
       - Generate embeddings
       - Process images
       - Index to OpenSearch
    5. If more listings remain and time permits, self-invoke for next batch

    The function monitors Lambda execution time and stops ~6 seconds before
    timeout to allow graceful self-invocation of the next batch.

    Payload formats:
      S3 mode: {"bucket": "my-bucket", "key": "listings.json", "start": 0, "limit": 500}
      Direct mode: {"listings": [...], "start": 0, "limit": 500}

    Args:
        event: Lambda event with payload (body or direct dict)
        context: Lambda context with remaining_time_in_millis()

    Returns:
        Response dict with status, processed count, and next_start if has_more
    """
    # Ensure index exists with correct mappings
    create_index_if_needed()

    # Parse payload
    body = event.get("body") if isinstance(event, dict) else None
    if body and isinstance(body, str):
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}
    else:
        payload = event if isinstance(event, dict) else {}

    # Source of listings
    if "bucket" in payload and "key" in payload:
        all_listings = _load_listings_from_s3(payload["bucket"], payload["key"])
    elif "listings" in payload:
        all_listings = payload["listings"]
    else:
        return {"statusCode": 400, "body": json.dumps({"error": "Provide {bucket,key} or {listings: []}."})}

    total = len(all_listings)
    start = int(payload.get("start", 0))
    limit = int(payload.get("limit", 500))
    end = min(start + limit, total)

    SAFETY_MS = 6000  # stop ~6s early to allow self-invoke
    processed = 0
    actions: List[Dict[str, Any]] = []

    for i in range(start, end):
        if context.get_remaining_time_in_millis() < SAFETY_MS:
            logger.info("Nearing timeout; breaking early at i=%d", i)
            break
        try:
            lst = all_listings[i]
            core = _extract_core_fields(lst)
            images = extract_zillow_images(lst)
            doc = _build_doc(core, images)
            actions.append({"_id": core["zpid"], "_source": doc})

            if len(actions) >= 200:  # OK with backoff; lower to 150 if cluster is busy
                bulk_upsert(actions)
                actions.clear()

            processed += 1
        except Exception as e:
            logger.exception("Failed on listing index %d: %s", i, e)

    if actions:
        bulk_upsert(actions)

    next_start = start + processed
    has_more = next_start < total

    # Self-invoke follow-up batch (async)
    if has_more:
        next_payload = {
            "start": next_start,
            "limit": limit
        }
        # Pass through bucket/key if this is an S3-based job
        if "bucket" in payload and "key" in payload:
            next_payload["bucket"] = payload["bucket"]
            next_payload["key"] = payload["key"]
        # Pass through listings array if this is a direct invocation (DON'T pass empty array)
        elif "listings" in payload:
            next_payload["listings"] = all_listings
        try:
            logger.info("Self-invoking %s start=%d limit=%d", context.invoked_function_arn, next_start, limit)
            lambda_client.invoke(
                FunctionName=context.invoked_function_arn,
                InvocationType="Event",
                Payload=json.dumps(next_payload).encode("utf-8"),
            )
            logger.info("Self-invoked for next batch: start=%d limit=%d", next_start, limit)
        except Exception as e:
            logger.exception("Self-invoke failed: %s", e)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "ok": True,
            "index": OS_INDEX,
            "batch": {"start": start, "processed": processed, "limit": limit},
            "next_start": next_start if has_more else None,
            "total": total,
            "has_more": has_more
        })
    }
