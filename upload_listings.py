"""
upload_listings.py - Lambda function for indexing real estate listings to OpenSearch

This Lambda processes Zillow property listings and indexes them into OpenSearch
with multimodal embeddings (text + images) for semantic search.

Processing Pipeline (per listing):
1. Extract core fields (price, beds, location, geo coordinates) from Zillow JSON
2. Generate fallback description if missing (from available fields)
3. Generate text embedding from description via Bedrock Titan (1024-dim)
4. Download property photos (up to MAX_IMAGES, default unlimited)
5. Generate image embeddings via Bedrock Titan (1024-dim per image)
6. Detect visual features via Claude 3 Haiku Vision (DynamoDB cached)
   - Extracts: features, architecture style, colors, materials, room types
   - Cost: ~$0.00025/image
7. Index search-relevant fields + embeddings to OpenSearch
   - Complete original Zillow JSON is kept in source dataset (S3)
   - OpenSearch stores only search-relevant fields to avoid field mapping conflicts

Multi-Vector Support (Phase 2):
- For indexes ending in "-v2": Stores ALL image vectors separately (nested array)
- Enables max-match search: Property ranks high if ANY image matches well
- Legacy indexes: Average all image vectors into single vector

Self-Invocation Chain:
- Processes listings in batches (default: 500 per invocation)
- Automatically invokes next batch if more listings remain
- First invocation downloads from S3, passes data to subsequent invocations
- Prevents re-downloading same file 4+ times (optimization)
- Safety limits: max 50 invocations, loop detection, idempotency checking

Cost Optimizations:
- Unified DynamoDB caching (hearth-vision-cache): Stores both embeddings AND analysis atomically
- Prevents re-analyzing/embedding same images across re-indexes (90%+ cache hit rate)
- 576px image resolution for embeddings (sufficient quality, 1/4 the download size)

Invocation Formats:
    # First invocation (downloads from S3)
    {"bucket": "demo-hearth-data", "key": "slc_listings.json", "start": 0, "limit": 500}

    # Subsequent invocations (uses cached data)
    {"listings": [...], "start": 500, "limit": 500, "_invocation_count": 1}

    # Special operations
    {"operation": "delete_index"}
"""

import json
import logging
import os
import uuid
import threading
from typing import Any, Dict, List

import boto3
import requests

from common import (
    AWS_REGION, OS_INDEX, MAX_IMAGES, EMBEDDING_IMAGE_WIDTH,
    IMAGE_MODEL_ID, LLM_MODEL_ID,
    create_index_if_needed, bulk_upsert,
    embed_text_multimodal, embed_image_bytes, detect_labels_with_response,
    extract_zillow_images, vec_mean
)

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# AWS clients for S3 access, self-invocation, and job tracking
s3 = boto3.client("s3", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)
dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)

# Job tracking table for idempotency
JOB_TRACKING_TABLE = "hearth-indexing-jobs"

# BEDROCK API RATE LIMITING
# Limit concurrent Bedrock API calls to avoid throttling
# Conservative limit: 10 concurrent calls (adjusted based on actual rate limits observed)
# This prevents: 20 listings × 10 images = 200 concurrent calls → throttling
BEDROCK_SEMAPHORE = threading.Semaphore(10)


def _bedrock_with_retry(func, max_retries=5):
    """
    Execute a Bedrock API call with exponential backoff retry.

    Args:
        func: Lambda function that makes the Bedrock API call
        max_retries: Maximum number of retry attempts

    Returns:
        Result from func()

    Raises:
        Exception: If all retries exhausted
    """
    import time
    import random

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if "ThrottlingException" in str(e) or "Too many requests" in str(e):
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.debug(f"Bedrock throttled, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
            raise


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
    living_area = _num(lst.get("livingArea") or lst.get("livingAreaValue"))  # House square footage
    lot_size = _num(lst.get("lotSize") or lst.get("lotAreaValue") or lst.get("acreage") or lst.get("lotArea"))

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
        "bedrooms": float(beds) if beds is not None else None,  # Match UI field name
        "bathrooms": float(baths) if baths is not None else None,  # Match UI field name
        "livingArea": float(living_area) if living_area is not None else None,  # House square footage
        "lotSize": float(lot_size) if lot_size is not None else None,  # Lot size in sq ft
        "address": {  # Nested object for UI compatibility
            "streetAddress": addr,
            "city": city,
            "state": state,
            "zipcode": zipc
        },
        "city": city,  # Keep flat fields for search filters
        "state": state,
        "zip_code": zipc,
        "geo": geo,
    }


# ===============================================
# DOCUMENT BUILDING WITH EMBEDDINGS
# ===============================================

def _process_single_image(image_url: str, zpid: str) -> Dict[str, Any]:
    """
    Process a single image: download, embed, analyze, and cache.

    This function is designed to be called in parallel for all images in a listing.

    Args:
        image_url: URL of the image to process
        zpid: Property ID (for logging)

    Returns:
        Dictionary with:
        {
            "success": bool,
            "image_url": str,
            "embedding": List[float] or None,
            "analysis": Dict or None,
            "image_hash": str or None,
            "error": str or None
        }
    """
    from cache_utils import get_cached_image_data, cache_image_data
    import hashlib

    result = {
        "success": False,
        "image_url": image_url,
        "embedding": None,
        "analysis": None,
        "image_hash": None,
        "error": None
    }

    try:
        # Try to get embedding, analysis, and hash from cache
        cached_data = get_cached_image_data(dynamodb, image_url)
        if cached_data:
            img_vec, analysis, img_hash = cached_data
            logger.debug(f"💾 Cache hit for image: {image_url[:60]}...")
            result["embedding"] = img_vec
            result["analysis"] = analysis
            result["image_hash"] = img_hash
            result["success"] = True
            return result

        # Cache miss - need to download and process
        logger.debug(f"📥 Downloading image (cache miss): {image_url[:60]}...")
        resp = requests.get(image_url, timeout=8)
        resp.raise_for_status()
        bb = resp.content

        # Calculate hash immediately for dedup
        img_hash = hashlib.md5(bb).hexdigest()
        result["image_hash"] = img_hash

        # RATE LIMITING: Acquire semaphore before Bedrock API calls
        # This prevents too many concurrent requests and throttling
        with BEDROCK_SEMAPHORE:
            # Generate embedding with retry logic
            img_vec = _bedrock_with_retry(lambda: embed_image_bytes(bb))
            result["embedding"] = img_vec

            # Get comprehensive analysis with retry logic
            analysis_result = _bedrock_with_retry(lambda: detect_labels_with_response(bb, image_url=image_url))
            analysis = analysis_result["analysis"]
            llm_response = analysis_result["llm_response"]
            result["analysis"] = analysis

        # Cache both embedding and analysis atomically
        cache_image_data(
            dynamodb,
            image_url=image_url,
            image_bytes=bb,
            embedding=img_vec,
            analysis=analysis,
            llm_response=llm_response,
            embedding_model=IMAGE_MODEL_ID,
            analysis_model=LLM_MODEL_ID
        )

        result["success"] = True

    except Exception as e:
        logger.warning(f"Failed to process image {image_url[:60]}: {e}")
        result["error"] = str(e)

    return result


def _build_doc(base: Dict[str, Any], image_urls: List[str]) -> Dict[str, Any]:
    """
    Build a complete OpenSearch document with text and image embeddings.

    This is the core processing function that enriches each listing with:
    1. Text embeddings (1024-dim vector) via Bedrock Titan
    2. Image embeddings (averaged from multiple photos) via Bedrock Titan
    3. Visual features and labels via Claude 3 Haiku Vision
    4. Data quality flags (has_valid_embeddings, has_description)

    The function is resilient to failures at each step, logging errors and
    continuing with fallback values to ensure indexing completes.

    Args:
        base: Normalized core fields from _extract_core_fields()
        image_urls: List of property image URLs to process

    Returns:
        Complete document ready for OpenSearch indexing with all embeddings,
        tags, and metadata
    """
    # NOTE: Text-based LLM feature extraction removed (was $60-80 per 1,588 listings)
    # All features now extracted from images via Claude Haiku Vision (~$0.40 per dataset)
    # These fields kept for backward compatibility with existing OpenSearch mappings
    llm_profile = ""  # Always empty
    feature_tags = []  # No longer populated

    # Text embeddings will be generated AFTER image processing
    # This allows us to include visual_features_text in the embedding
    vec_text = None
    text_embedding_failed = False

    # Image vectors + tags (optional + resilient)
    # Deduplicate images by computing hash to avoid processing duplicates
    image_vecs, img_tags = [], set()
    image_vector_metadata = []  # For multi-vector schema: [{url, type, vector, analysis}, ...]
    all_image_analyses = []  # Collect all analyses to generate visual_features_text
    seen_hashes = set()
    style_from_vision = None
    best_exterior_score = 0

    if image_urls:
        # Apply MAX_IMAGES limit
        urls_to_process = image_urls if MAX_IMAGES == 0 else image_urls[:MAX_IMAGES]

        # OPTIMIZATION: Process all images in parallel using ThreadPoolExecutor
        # This provides massive speedup: 10 images × 1.5s each = 15s → 1.5s total
        import concurrent.futures
        import hashlib

        zpid = base.get("zpid", "unknown")

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(urls_to_process), 20)) as executor:
            # Submit all image processing tasks
            future_to_url = {
                executor.submit(_process_single_image, url, zpid): url
                for url in urls_to_process
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()

                    if not result["success"]:
                        logger.warning(f"Failed to process image: {result['error']}")
                        continue

                    img_vec = result["embedding"]
                    analysis = result["analysis"]
                    img_hash = result["image_hash"]

                    # Validate embedding
                    if not img_vec or len(img_vec) == 0:
                        logger.warning("Empty/invalid embedding for zpid=%s, url=%s", zpid, url)
                        continue

                    # CRITICAL: Check for duplicate images BEFORE adding to vectors
                    # Use hash from cache/processing (no need to re-download!)
                    if img_hash in seen_hashes:
                        logger.debug("⏭️  Skipping duplicate image (hash=%s) for zpid=%s", img_hash[:8], zpid)
                        continue  # Skip BEFORE adding to vectors
                    seen_hashes.add(img_hash)

                    # NOW it's safe to add the embedding (after dedup check)
                    image_vecs.append(img_vec)

                    # Analysis was already obtained above (either from cache or freshly generated)
                    # Store analysis for visual_features_text generation
                    if analysis:
                        all_image_analyses.append(analysis)

                        # Extract all features from analysis
                        features = analysis.get("features", [])
                        for feature in features:
                            img_tags.add(feature)

                        # Extract materials and visual features
                        for material in analysis.get("materials", []):
                            img_tags.add(material)
                        for visual_feature in analysis.get("visual_features", []):
                            img_tags.add(visual_feature)

                        # Add exterior color to tags if present
                        if analysis.get("exterior_color"):
                            img_tags.add(f"{analysis['exterior_color']} exterior")
                            img_tags.add(f"{analysis['exterior_color']}_exterior")  # Both formats

                        # Track best exterior image for architecture style
                        image_type = analysis.get("image_type", "unknown")
                        if image_type == "exterior":
                            # Score based on having architecture style detected
                            exterior_score = 10 if analysis.get("architecture_style") else 5

                            if exterior_score > best_exterior_score:
                                best_exterior_score = exterior_score
                                style_from_vision = analysis.get("architecture_style")

                                logger.info("Best exterior for zpid=%s: style=%s, color=%s, confidence=%s, features=%d",
                                           zpid,
                                           style_from_vision,
                                           analysis.get("exterior_color"),
                                           analysis.get("confidence"),
                                           len(features))

                        logger.debug("Analyzed image for zpid=%s: type=%s, features=%d, style=%s",
                                   zpid, image_type, len(features), analysis.get("architecture_style"))

                    # Store image vector with metadata for multi-vector schema
                    if img_vec and analysis:
                        image_vector_metadata.append({
                            "image_url": url,
                            "image_type": analysis.get("image_type", "unknown"),
                            "vector": img_vec
                        })

                except Exception as e:
                    logger.warning("Image processing failed for zpid=%s, url=%s: %s", zpid, url, e)

    # Generate visual_features_text from all image analyses
    # IMPROVEMENT: Use majority voting to eliminate contradictory features
    visual_features_text = ""
    if all_image_analyses:
        from collections import Counter

        # Collect unique features from all images
        all_features = set()

        # Separate exterior and interior analyses
        exterior_analyses = []
        interior_descriptions = []

        # Collect votes for exterior attributes
        exterior_styles = []
        exterior_colors = []
        all_materials = []

        # Track feature frequencies for "Property includes" section
        all_feature_counts = Counter()

        for analysis in all_image_analyses:
            # Add all features with frequency tracking
            for feature in analysis.get("features", []):
                all_features.add(feature)
                all_feature_counts[feature] += 1
            for material in analysis.get("materials", []):
                all_features.add(material)
                all_feature_counts[material] += 1
            for visual_feature in analysis.get("visual_features", []):
                all_features.add(visual_feature)
                all_feature_counts[visual_feature] += 1

            if analysis.get("image_type") == "exterior":
                exterior_analyses.append(analysis)
                # Collect votes for consensus
                if analysis.get("architecture_style"):
                    exterior_styles.append(analysis["architecture_style"])
                if analysis.get("exterior_color"):
                    exterior_colors.append(analysis["exterior_color"])
                # Collect all materials (will pick top ones)
                all_materials.extend(analysis.get("materials", []))

            elif analysis.get("image_type") == "interior":
                # Group interior features by type
                interior_descriptions.extend(analysis.get("features", [])[:5])  # Top 5 features per room

        # Build natural language description
        description_parts = []

        # EXTERIOR: Use majority voting for style/color, top materials for accents
        if exterior_analyses:
            parts = []

            # Most common architecture style (majority vote)
            if exterior_styles:
                style_counts = Counter(exterior_styles)
                primary_style = style_counts.most_common(1)[0][0]
                parts.append(f"{primary_style} style")
                logger.debug(f"Exterior style votes: {dict(style_counts)} → chose '{primary_style}'")

            # Most common exterior color (majority vote)
            if exterior_colors:
                color_counts = Counter(exterior_colors)
                primary_color = color_counts.most_common(1)[0][0]
                parts.append(f"{primary_color} exterior")
                logger.debug(f"Exterior color votes: {dict(color_counts)} → chose '{primary_color}'")

            # Top 2-3 materials (allow accents like brick chimney, stone foundation)
            if all_materials:
                material_counts = Counter(all_materials)
                top_materials = [material for material, _ in material_counts.most_common(3)]
                if top_materials:
                    parts.append(f"with {', '.join(top_materials)}")
                    logger.debug(f"Material votes: {dict(material_counts)} → chose top 3: {top_materials}")

            if parts:
                description_parts.append(f"Exterior: {' '.join(parts)}")

        # INTERIOR: Use most common features (frequency-based)
        if interior_descriptions:
            # Count feature frequency and get top 10
            feature_counts = Counter(interior_descriptions)
            top_interior = [feature for feature, _ in feature_counts.most_common(10)]
            description_parts.append(f"Interior features: {', '.join(top_interior)}")

        # GENERAL FEATURES: Remaining features ranked by frequency
        if all_feature_counts:
            # Exclude features already mentioned in exterior/interior descriptions
            mentioned_features = set(interior_descriptions) | set(all_materials)

            # Get remaining features with their counts
            remaining_feature_counts = {f: count for f, count in all_feature_counts.items()
                                       if f not in mentioned_features}

            # Rank by frequency (most common first), take top 15
            remaining_features = [f for f, _ in sorted(remaining_feature_counts.items(),
                                                      key=lambda x: x[1], reverse=True)[:15]]

            if remaining_features:
                description_parts.append(f"Property includes: {', '.join(remaining_features)}")
                logger.debug(f"Property includes (by frequency): {remaining_features[:5]}... (showing top 5 of {len(remaining_features)})")

        visual_features_text = ". ".join(description_parts) + "." if description_parts else ""
        logger.info(f"📝 Generated visual_features_text for zpid={base.get('zpid')}: {len(visual_features_text)} chars, {len(all_features)} unique features")

    # NOW generate text embedding with both description AND visual features
    try:
        text_for_embed = base["description"].strip() if base["description"] else ""

        # Combine original description with visual features
        if visual_features_text:
            combined_text = f"{text_for_embed} {visual_features_text}".strip()
        else:
            combined_text = text_for_embed

        if combined_text:
            vec_text = embed_text_multimodal(combined_text)
            if not vec_text or len(vec_text) == 0:
                raise ValueError("Empty vector returned from embed_text")
            logger.debug(f"Embedded {len(combined_text)} chars (desc: {len(text_for_embed)}, visual: {len(visual_features_text)})")
        else:
            logger.warning("No text to embed for zpid=%s", base.get("zpid"))
            text_embedding_failed = True
    except Exception as e:
        logger.error("Text embedding FAILED for zpid=%s: %s", base.get("zpid"), e)
        text_embedding_failed = True

    # If text embedding failed, use zeros
    if vec_text is None:
        vec_text = [0.0] * int(os.getenv("TEXT_DIM", "1024"))

    vec_image = vec_mean(image_vecs, target_dim=len(vec_text)) if image_vecs else [0.0] * len(vec_text)

    # Determine if embeddings are valid (non-zero) - compute sums once for efficiency
    zpid = base.get("zpid")
    text_embed_sum = sum(abs(v) for v in vec_text) if vec_text else 0.0
    image_embed_sum = sum(abs(v) for v in vec_image) if vec_image else 0.0

    has_valid_text_embedding = not text_embedding_failed and vec_text and text_embed_sum > 0.0
    has_valid_image_embedding = len(image_vecs) > 0 and vec_image and image_embed_sum > 0.0
    has_valid_embeddings = has_valid_text_embedding or has_valid_image_embedding

    # Logging: Embedding details and validation (now using pre-computed sums)
    logger.info(f"🔍 zpid={zpid}: text_len={len(vec_text) if vec_text else 0}, "
                f"text_sum={text_embed_sum:.4f}, text_valid={has_valid_text_embedding}")
    logger.info(f"   image_count={len(image_vecs)}, image_sum={image_embed_sum:.4f}, "
                f"image_valid={has_valid_image_embedding}, overall_valid={has_valid_embeddings}")

    if not has_valid_embeddings:
        logger.warning("❌ Document zpid=%s has NO valid embeddings", zpid)

    # Architecture style comes from vision analysis only (text extraction removed)
    architecture_style = style_from_vision

    # Detect if using multi-vector schema (listings-v2)
    is_multi_vector = OS_INDEX.endswith("-v2")

    # Build document - include ALL fields from base (don't filter out None values)
    # This is important because numeric fields like price=0 should be preserved
    # Filtering happens at search time, not index time
    doc = {
        **base,  # Include all fields from base dict
        "llm_profile": llm_profile,
        "feature_tags": sorted(set(feature_tags)),
        "image_tags": sorted(img_tags),
        "images": image_urls,  # Store all image URLs for frontend display
        "has_valid_embeddings": has_valid_embeddings,
        "status": "active",
        "indexed_at": int(__import__("time").time()),
    }

    # Add visual_features_text for enhanced BM25 matching
    if visual_features_text:
        doc["visual_features_text"] = visual_features_text

    # Add architecture style if detected
    if architecture_style:
        doc["architecture_style"] = architecture_style

    # Only add vector fields if they're valid (OpenSearch cosinesimil doesn't support zero vectors)
    if has_valid_text_embedding:
        doc["vector_text"] = vec_text

    # Add image vectors based on schema version
    if is_multi_vector:
        # PHASE 2: Store all image vectors separately for max-match search
        if image_vector_metadata and len(image_vector_metadata) > 0:
            doc["image_vectors"] = image_vector_metadata
            logger.info(f"📸 zpid={zpid}: Stored {len(image_vector_metadata)} image vectors (multi-vector schema)")
    else:
        # LEGACY: Single averaged vector for backward compatibility
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
    2. Load listings from S3 (first invocation only) or use cached data from payload
    3. Process batch of listings (default 500 per invocation)
    4. For each listing:
       - Extract core fields
       - Generate embeddings
       - Process images
       - Index to OpenSearch
    5. If more listings remain and time permits, self-invoke for next batch with data

    OPTIMIZATION: The first invocation downloads from S3, then passes the full listing
    data in subsequent invocations. This prevents re-downloading the same 12MB JSON
    file multiple times (e.g., 4 downloads → 1 download for 1,588 listings).

    The function monitors Lambda execution time and stops ~6 seconds before
    timeout to allow graceful self-invocation of the next batch.

    Payload formats:
      First invocation: {"bucket": "my-bucket", "key": "listings.json", "start": 0, "limit": 500}
      Subsequent invocations: {"listings": [...], "start": 500, "limit": 500}
      Direct mode: {"listings": [...], "start": 0, "limit": 500}

    Args:
        event: Lambda event with payload (body or direct dict)
        context: Lambda context with remaining_time_in_millis()

    Returns:
        Response dict with status, processed count, and next_start if has_more
    """
    from common import os_client, OS_INDEX

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

    # SAFEGUARD 1: Invocation counter to prevent infinite loops
    invocation_count = int(payload.get("_invocation_count", 0))
    max_invocations = int(os.getenv("MAX_INVOCATIONS", "50"))

    if invocation_count >= max_invocations:
        error_msg = f"🛑 SAFETY LIMIT: Reached max invocations ({max_invocations}). Possible infinite loop detected."
        logger.error(error_msg)
        logger.error(f"   Payload: bucket={payload.get('bucket')}, key={payload.get('key')}, start={payload.get('start')}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Max invocations exceeded",
                "invocation_count": invocation_count,
                "max_allowed": max_invocations,
                "message": "Safety limit reached. Check for infinite loop or increase MAX_INVOCATIONS env var."
            })
        }

    logger.info(f"🔢 Invocation count: {invocation_count}/{max_invocations}")

    # SAFEGUARD 5: Job idempotency check (prevent duplicate concurrent runs)
    job_id = payload.get("_job_id")
    if not job_id and "bucket" in payload and "key" in payload:
        # Generate job ID from bucket/key for S3-based jobs
        import hashlib
        job_id = hashlib.md5(f"{payload['bucket']}/{payload['key']}".encode()).hexdigest()
        payload["_job_id"] = job_id

    if job_id and invocation_count == 0:  # Only check on first invocation
        try:
            response = dynamodb.get_item(
                TableName=JOB_TRACKING_TABLE,
                Key={"job_id": {"S": job_id}}
            )
            if "Item" in response:
                status = response["Item"].get("status", {}).get("S", "")
                if status == "running":
                    logger.warning(f"⚠️  Job {job_id} is already running. Skipping duplicate invocation.")
                    return {
                        "statusCode": 409,
                        "body": json.dumps({
                            "error": "Job already running",
                            "job_id": job_id,
                            "message": "This job is already in progress. Wait for it to complete."
                        })
                    }

            # Mark job as running
            import time
            dynamodb.put_item(
                TableName=JOB_TRACKING_TABLE,
                Item={
                    "job_id": {"S": job_id},
                    "status": {"S": "running"},
                    "started_at": {"N": str(int(time.time()))},
                    "bucket": {"S": payload.get("bucket", "")},
                    "key": {"S": payload.get("key", "")}
                }
            )
            logger.info(f"🔒 Job {job_id} marked as running")
        except Exception as e:
            logger.warning(f"Job tracking failed (non-fatal): {e}")

    # Handle special operations
    if payload.get("operation") == "delete_index":
        try:
            if os_client.indices.exists(index=OS_INDEX):
                logger.info(f"Deleting index {OS_INDEX}...")
                os_client.indices.delete(index=OS_INDEX)
                return {"statusCode": 200, "body": json.dumps({"message": f"Index {OS_INDEX} deleted"})}
            else:
                return {"statusCode": 404, "body": json.dumps({"message": f"Index {OS_INDEX} does not exist"})}
        except Exception as e:
            logger.exception("Failed to delete index: %s", e)
            return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

    # Source of listings
    # OPTIMIZATION: On first invocation (start=0), load from S3 and pass data forward
    # On subsequent invocations, use the listings data passed in payload
    # This prevents re-downloading the same 12MB JSON file 4 times!
    start = int(payload.get("start", 0))

    if "listings" in payload:
        # Subsequent invocation - use cached listings from payload
        all_listings = payload["listings"]
        logger.info(f"Using cached listings from payload ({len(all_listings)} total)")
    elif "bucket" in payload and "key" in payload:
        # First invocation - download from S3 once
        logger.info(f"First invocation - downloading from S3: s3://{payload['bucket']}/{payload['key']}")
        all_listings = _load_listings_from_s3(payload["bucket"], payload["key"])
        logger.info(f"Downloaded {len(all_listings)} listings from S3")
    else:
        return {"statusCode": 400, "body": json.dumps({"error": "Provide {bucket,key} or {listings: []}."})}

    total = len(all_listings)
    limit = int(payload.get("limit", 500))
    end = min(start + limit, total)

    # SAFEGUARD 2: Validate start is within bounds
    if start >= total:
        logger.warning(f"⚠️  start={start} is >= total={total}. No work to do.")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "ok": True,
                "message": "start >= total, nothing to process",
                "start": start,
                "total": total
            })
        }

    # SAFEGUARD 3: Detect if start is not progressing (stuck loop)
    if invocation_count > 0 and start == 0:
        error_msg = f"🛑 LOOP DETECTED: Invocation {invocation_count} but start=0. Should be progressing."
        logger.error(error_msg)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Infinite loop detected",
                "message": "start position not advancing across invocations"
            })
        }

    # Enhanced logging: Track zpids in this batch
    batch_zpids = [str(all_listings[i].get('zpid', 'unknown')) for i in range(start, min(end, total))]
    logger.info(f"📦 Batch {start}-{end}: Processing {len(batch_zpids)} listings")
    logger.info(f"   First 10 zpids: {batch_zpids[:10]}")
    logger.info(f"   Source: bucket={payload.get('bucket', 'N/A')}, key={payload.get('key', 'N/A')}")
    logger.info(f"   Invocation: {invocation_count}/50, Job ID: {job_id}")

    SAFETY_MS = 30000  # stop ~30s early to allow self-invoke
    processed = 0
    success_count = 0
    error_count = 0
    error_details = []
    processed_zpids = []  # Track zpids that were successfully processed
    actions: List[Dict[str, Any]] = []

    for i in range(start, end):
        if context.get_remaining_time_in_millis() < SAFETY_MS:
            logger.warning(f"⏰ Nearing timeout at listing {i}/{end}; breaking early to self-invoke")
            break
        try:
            lst = all_listings[i]
            zpid = lst.get('zpid', 'unknown')
            core = _extract_core_fields(lst)
            images = extract_zillow_images(lst, target_width=EMBEDDING_IMAGE_WIDTH)
            doc = _build_doc(core, images)

            # Prepare for bulk indexing
            # NOTE: Complete Zillow JSON is kept in source dataset (slc_listings.json in S3)
            # OpenSearch only stores search-relevant fields to keep it lean
            actions.append({"_id": core["zpid"], "_source": doc})

            if len(actions) >= 200:  # OK with backoff; lower to 150 if cluster is busy
                bulk_upsert(actions)
                actions.clear()

            processed += 1
            success_count += 1
            processed_zpids.append(str(zpid))

            # Log every 10th listing for progress tracking
            if processed % 10 == 0:
                logger.info(f"   Progress: {processed}/{len(batch_zpids)} listings processed")

        except Exception as e:
            error_count += 1
            zpid = all_listings[i].get('zpid', 'unknown')
            error_msg = f"zpid={zpid}, error={str(e)[:100]}"
            error_details.append(error_msg)
            logger.error(f"❌ Failed listing {i} (zpid={zpid}): {str(e)[:200]}")

            # Continue processing despite errors (don't break the entire batch)
            processed += 1

    if actions:
        bulk_upsert(actions)

    # Enhanced logging: Report what was actually processed
    processed_zpids = [str(all_listings[i].get('zpid', 'unknown')) for i in range(start, start + processed)]
    logger.info(f"✅ Batch complete: Processed {processed}/{len(batch_zpids)} listings")
    logger.info(f"   ✓ Successes: {success_count}")
    logger.info(f"   ✗ Errors: {error_count}")
    logger.info(f"   Processed zpids: {processed_zpids[:10]}")

    if error_count > 0:
        logger.error(f"❌ ERRORS IN BATCH: {error_count} listings failed")
        for detail in error_details[:5]:  # Log first 5 errors
            logger.error(f"   {detail}")
        if len(error_details) > 5:
            logger.error(f"   ... and {len(error_details) - 5} more errors")

    if processed < len(batch_zpids):
        skipped = len(batch_zpids) - processed
        logger.warning(f"⚠️  Skipped {skipped} listings (timeout or errors)")

    next_start = start + processed
    has_more = next_start < total

    # Self-invoke follow-up batch (async)
    if has_more:
        # Check if we've reached max invocations BEFORE attempting to self-invoke
        if invocation_count + 1 >= max_invocations:
            logger.warning(f"⏸️  Stopping at invocation {invocation_count}/{max_invocations}. More data available but max invocations reached.")
            logger.info(f"   Next batch would start at: {next_start}")
        else:
            next_payload = {
                "start": next_start,
                "limit": limit,
                "_invocation_count": invocation_count + 1,  # SAFEGUARD: Increment counter
                "listings": all_listings  # OPTIMIZATION: Always pass listings to avoid re-downloading
            }

            # Pass through job_id for tracking
            if job_id:
                next_payload["_job_id"] = job_id

            # SAFEGUARD 4: Validate next_start is actually progressing
            if next_start <= start:
                error_msg = f"🛑 SAFETY: next_start={next_start} not > start={start}. Refusing to self-invoke."
                logger.error(error_msg)
                return {
                    "statusCode": 500,
                    "body": json.dumps({
                        "error": "Loop prevention",
                        "message": "next_start must be greater than start",
                        "start": start,
                        "next_start": next_start
                    })
                }

            try:
                logger.info("Self-invoking %s start=%d limit=%d invocation=%d", context.invoked_function_arn, next_start, limit, invocation_count + 1)
                lambda_client.invoke(
                    FunctionName=context.invoked_function_arn,
                    InvocationType="Event",
                    Payload=json.dumps(next_payload).encode("utf-8"),
                )
                logger.info("✅ Self-invoked for next batch: start=%d limit=%d invocation=%d/%d", next_start, limit, invocation_count + 1, max_invocations)
            except Exception as e:
                logger.exception("Self-invoke failed: %s", e)
    else:
        # Job complete - mark as finished in DynamoDB
        if job_id:
            try:
                import time
                dynamodb.put_item(
                    TableName=JOB_TRACKING_TABLE,
                    Item={
                        "job_id": {"S": job_id},
                        "status": {"S": "completed"},
                        "completed_at": {"N": str(int(time.time()))},
                        "total_processed": {"N": str(start + processed)}
                    }
                )
                logger.info(f"✅ Job {job_id} marked as completed")
            except Exception as e:
                logger.warning(f"Job tracking update failed (non-fatal): {e}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "ok": True,
            "index": OS_INDEX,
            "batch": {"start": start, "processed": processed, "limit": limit},
            "next_start": next_start if has_more else None,
            "total": total,
            "job_id": job_id,
            "has_more": has_more,
            "zpid": processed_zpids[0] if processed_zpids else "unknown"
        })
    }
