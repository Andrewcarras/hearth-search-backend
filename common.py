"""
common.py - Shared utilities for the Hearth Real Estate Search Engine

This module provides common functionality used by both upload_listings.py and search.py:
- AWS client setup (OpenSearch, Bedrock)
- Text and image embedding generation via Amazon Bedrock
- OpenSearch index creation and bulk operations
- LLM-based query parsing and constraint extraction
- Zillow data parsing utilities

Architecture:
- Uses Amazon OpenSearch for multimodal vector search (text + images)
- Uses Amazon Bedrock Titan models for embeddings
- Uses Claude (via Bedrock) for query parsing and vision analysis
"""

import base64
import json
import logging
import os
import time
import random
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# ===============================================
# ENVIRONMENT CONFIGURATION
# ===============================================
# Load configuration from environment variables with sensible defaults

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# OpenSearch endpoint (domain name only, no https://)
OS_HOST = os.getenv("OS_HOST")  # e.g., search-xyz.us-east-1.es.amazonaws.com
if OS_HOST and OS_HOST.startswith("https://"):
    OS_HOST = urlparse(OS_HOST).netloc  # Strip protocol if provided

OS_INDEX = os.getenv("OS_INDEX", "listings-v2")  # Index name for property listings (multi-vector schema)

# Bedrock model identifiers
TEXT_MODEL_ID = os.getenv("TEXT_EMBED_MODEL", "amazon.titan-embed-text-v2:0")  # Text embeddings
IMAGE_MODEL_ID = os.getenv("IMAGE_EMBED_MODEL", "amazon.titan-embed-image-v1")  # Image embeddings
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")  # Feature extraction

# Vector dimensions (must match model outputs)
TEXT_DIM = int(os.getenv("TEXT_DIM", "1024"))   # Titan Text v2 outputs 1024-dim vectors
IMAGE_DIM = int(os.getenv("IMAGE_DIM", "1024"))  # Titan Image outputs 1024-dim vectors

# Image processing configuration
MAX_IMAGES = int(os.getenv("MAX_IMAGES", "0"))  # Max images to process per listing (0 = unlimited)
EMBEDDING_IMAGE_WIDTH = int(os.getenv("EMBEDDING_IMAGE_WIDTH", "576"))  # Target resolution for embeddings (cost optimization)

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.getLogger().setLevel(LOG_LEVEL)
logger = logging.getLogger(__name__)

# ===============================================
# AWS CLIENT INITIALIZATION
# ===============================================

# Get AWS credentials from the Lambda execution environment
session = boto3.Session(region_name=AWS_REGION)
creds = session.get_credentials().get_frozen_credentials()

# Create AWS Signature V4 auth for OpenSearch
awsauth = AWS4Auth(
    creds.access_key, creds.secret_key, AWS_REGION,
    "es",  # Service name for OpenSearch
    session_token=creds.token
)

# Initialize OpenSearch client with retry logic for production reliability
os_client = OpenSearch(
    hosts=[{"host": OS_HOST, "port": 443}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=240,  # 240 second timeout (4 minutes) - allows slow queries on partial indexes
    max_retries=8,  # Retry failed requests up to 8 times
    retry_on_timeout=True,
    retry_on_status=(429, 502, 503, 504),  # Retry on rate limits and server errors
)

# Bedrock Runtime client for model invocations (embeddings + LLM)
brt = session.client("bedrock-runtime", config=Config(read_timeout=30, retries={"max_attempts": 2}))

# DynamoDB client for caching
dynamodb = session.client("dynamodb")

# Legacy cache table (kept for backwards compatibility during transition)
# New code should use cache_utils.py with hearth-vision-cache and hearth-text-embeddings
CACHE_TABLE = "hearth-image-cache"  # Old cache table - being phased out

# ===============================================
# EMBEDDING GENERATION FUNCTIONS
# ===============================================

def _parse_embed_response(payload: Dict[str, Any]) -> List[float]:
    """
    Parse embedding vector from various Bedrock model response formats.

    Different embedding models (Titan, Cohere, etc.) return vectors in slightly
    different JSON structures. This function handles the common formats.

    Args:
        payload: JSON response from Bedrock embedding model

    Returns:
        List of floats representing the embedding vector

    Raises:
        ValueError: If the response format is not recognized
    """
    # Titan format: {"embedding": [0.1, 0.2, ...]}
    if "embedding" in payload and isinstance(payload["embedding"], list):
        return payload["embedding"]

    # Alternative format: {"vector": [0.1, 0.2, ...]}
    if "vector" in payload and isinstance(payload["vector"], list):
        return payload["vector"]

    # Batch format: {"embeddings": [{"embedding": [0.1, ...]}, ...]}
    if "embeddings" in payload:
        e = payload["embeddings"][0]
        if isinstance(e, dict) and "embedding" in e:
            return e["embedding"]
        if isinstance(e, list):
            return e

    raise ValueError(f"Unrecognized embedding response keys: {list(payload.keys())}")


def embed_text(text: str) -> List[float]:
    """
    Generate a text embedding vector using Amazon Bedrock Titan Text Embeddings.
    Results are cached in DynamoDB to avoid re-embedding same text.

    Args:
        text: Input text to embed (listing description, search query, etc.)

    Returns:
        1024-dimensional vector representing the semantic meaning of the text
    """
    if not text:
        return [0.0] * TEXT_DIM  # Return zero vector for empty text

    # Import cache utilities
    from cache_utils import get_cached_text_embedding, cache_text_embedding

    # Check cache first (with model ID to avoid cross-model cache hits)
    cached_embedding = get_cached_text_embedding(dynamodb, text, TEXT_MODEL_ID)
    if cached_embedding:
        return cached_embedding

    # Cache miss - generate embedding
    body = json.dumps({"inputText": text})
    resp = brt.invoke_model(modelId=TEXT_MODEL_ID, body=body)
    out = json.loads(resp["body"].read().decode("utf-8"))
    vec = _parse_embed_response(out)

    # Store in cache with model ID
    cache_text_embedding(dynamodb, text, vec, TEXT_MODEL_ID)

    return vec


def embed_text_multimodal(text: str) -> List[float]:
    """
    Generate text embedding using the MULTIMODAL Titan model (amazon.titan-embed-image-v1).

    This function embeds text using the same model that embeds images, ensuring that
    query text and image embeddings exist in the SAME vector space. This enables
    proper cross-modal similarity comparison in kNN image search.

    KEY DIFFERENCE from embed_text():
    - embed_text() uses amazon.titan-embed-text-v2:0 (text-only model)
    - embed_text_multimodal() uses amazon.titan-embed-image-v1 (multimodal model, text input)

    Results are cached separately from embed_text() to avoid model confusion.

    Args:
        text: Input text to embed (search query, etc.)

    Returns:
        1024-dimensional vector in the multimodal embedding space
    """
    if not text:
        return [0.0] * IMAGE_DIM

    # Import cache utilities
    from cache_utils import get_cached_text_embedding, cache_text_embedding

    # Check cache first (with model ID to avoid cross-model cache hits)
    cached_embedding = get_cached_text_embedding(dynamodb, text, IMAGE_MODEL_ID)
    if cached_embedding:
        return cached_embedding

    # Cache miss - generate embedding using multimodal model
    body = json.dumps({"inputText": text})
    resp = brt.invoke_model(modelId=IMAGE_MODEL_ID, body=body)  # Using IMAGE model for text!
    out = json.loads(resp["body"].read().decode("utf-8"))
    vec = _parse_embed_response(out)

    # Store in cache with IMAGE_MODEL_ID to separate from text-v2 embeddings
    cache_text_embedding(dynamodb, text, vec, IMAGE_MODEL_ID)

    return vec


def embed_image_bytes(img_bytes: bytes) -> List[float]:
    """
    Generate an image embedding vector using Amazon Bedrock Titan Image Embeddings.

    Args:
        img_bytes: Raw image bytes (JPEG, PNG, etc.)

    Returns:
        1024-dimensional vector representing the visual features of the image
    """
    # Encode image to base64 (required by Titan Image Embeddings)
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    # Invoke Titan Image Embeddings model
    # Format: {"inputImage": "base64string"}
    body = json.dumps({"inputImage": b64})
    resp = brt.invoke_model(modelId=IMAGE_MODEL_ID, body=body)
    out = json.loads(resp["body"].read().decode("utf-8"))

    # Titan Image returns {"embedding": [floats], "inputImageDimensions": {...}}
    if "embedding" in out:
        return out["embedding"]
    return _parse_embed_response(out)


# NOTE: embed_image_from_url() removed - was never used in production
# Image embedding with caching is handled directly in upload_listings.py for better control
# See git history if this function is ever needed


def vec_mean(vectors: List[List[float]], target_dim: int) -> List[float]:
    """
    Compute the element-wise mean of multiple vectors.

    This is used to combine multiple image embeddings into a single vector
    representing the entire property (e.g., average of 6 room photos).

    Args:
        vectors: List of embedding vectors to average
        target_dim: Dimension of output vector (for zero vector fallback)

    Returns:
        Mean vector with same dimension as input vectors
    """
    if not vectors:
        return [0.0] * target_dim

    dim = len(vectors[0])
    sums = [0.0] * dim

    # Sum all vectors element-wise
    for v in vectors:
        for i in range(dim):
            sums[i] += v[i]

    # Divide by count to get mean
    return [s / len(vectors) for s in sums]


# NOTE: _get_cached_labels() and _cache_labels() removed
# These legacy functions are replaced by detect_labels() which caches comprehensive analysis
# See git history if restoration is needed


def detect_labels(img_bytes: bytes, image_url: str = "", max_labels: int = 100) -> Dict[str, Any]:
    """
    LEGACY: Comprehensive vision analysis using Claude 3 Haiku.

    **DEPRECATED:** New code should use detect_labels_with_response() instead,
    which returns both the analysis AND raw LLM response for better caching.

    This function is kept for backwards compatibility with existing code that
    hasn't been updated to use the new unified caching system (cache_utils.py).

    Analyzes a single property image and extracts EVERYTHING in one pass:
    - All visible features and amenities
    - Architecture style (if exterior)
    - Exterior colors and materials
    - Room type identification
    - Whether image is interior or exterior

    Cost: ~$0.00025 per image (Haiku)

    Args:
        img_bytes: Raw image bytes
        image_url: URL of the image (for logging/debugging)
        max_labels: Maximum number of features to return (default 100)

    Returns:
        Dictionary with:
        {
            "features": ["pool", "granite countertops", ...],
            "image_type": "exterior" or "interior",
            "architecture_style": "modern" or null,
            "exterior_color": "blue" or null,
            "materials": ["brick", "stone"],
            "visual_features": ["balcony", "porch"],
            "confidence": "high" or "medium" or "low"
        }
    """

    # Analyze with Claude Haiku
    try:
        b64_image = base64.b64encode(img_bytes).decode("utf-8")

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 800,  # Increased for comprehensive analysis
            "temperature": 0,   # Consistent results for caching
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": """Analyze this property photo comprehensively. Extract ALL valuable information for real estate search.

STEP 1: Determine if this is EXTERIOR or INTERIOR
- Exterior: Shows outside of building, facade, yard, architectural features
- Interior: Shows rooms, furnishings, indoor spaces

STEP 2: Extract ALL visible features (be exhaustive and specific):

IF EXTERIOR:
- Primary exterior color (white, blue, gray, beige, brown, red, tan, yellow, green, black)
- Exterior materials (brick, stone, vinyl siding, wood siding, stucco, metal siding, fiber cement)
- Architecture style (modern, contemporary, craftsman, victorian, colonial, ranch, mediterranean, tudor, cape cod, farmhouse, mid-century modern, traditional, transitional, bungalow, cottage, spanish, etc.)
- Garage details (attached garage, detached garage, 2-car garage, 3-car garage, carport, tandem garage)
- Roof type (gabled roof, hipped roof, flat roof, mansard roof, gambrel roof)
- Structural features (front porch, covered porch, balcony, deck, patio, dormers, bay windows, picture windows, columns, shutters, chimney, awning)
- Outdoor features (fenced yard, wood fence, white fence, chain link fence, mature trees, landscaped yard, driveway, walkway, garden, lawn)
- Views (mountain view, city view, water view, wooded lot, golf course view)

IF INTERIOR:
- Room type (kitchen, master bedroom, living room, dining room, bathroom, bedroom, home office, laundry room, basement, bonus room, etc.)
- Flooring (hardwood floors, tile floors, carpet, laminate, luxury vinyl plank, porcelain tile, marble floors, engineered hardwood)
- Kitchen details (granite countertops, marble countertops, quartz countertops, butcher block countertops, stainless steel appliances, white cabinets, wood cabinets, gray cabinets, kitchen island, breakfast bar, double oven, gas range, electric range, pantry, farmhouse sink, subway tile backsplash, pendant lights)
- Bathroom features (soaking tub, walk-in shower, dual sinks, double vanity, frameless glass shower, tile shower, separate tub and shower, vessel sink, rain shower head, heated floors)
- Ceilings (vaulted ceilings, cathedral ceilings, coffered ceiling, tray ceiling, exposed beams, wood beams, high ceilings, popcorn ceiling)
- Windows/Lighting (large windows, floor to ceiling windows, bay windows, lots of natural light, bright and airy, recessed lighting, pendant lights, chandelier, track lighting, skylights)
- Storage (walk-in closet, built-in shelving, linen closet, custom cabinetry, built-in storage)
- Fireplace (stone fireplace, brick fireplace, gas fireplace, wood burning fireplace, electric fireplace, modern fireplace)
- Architectural details (crown molding, wainscoting, archways, open floor plan, open concept, shiplap, exposed brick)
- Appliances (stainless steel appliances, black appliances, white appliances, built-in microwave, wine fridge, dishwasher)
- Condition/Style (updated kitchen, renovated bathroom, modern finishes, contemporary style, traditional style, farmhouse style, industrial style, move-in ready, newly renovated)

OUTDOOR AMENITIES (if visible):
- Pool (in-ground pool, above-ground pool, pool with spa, heated pool, saltwater pool, lap pool, infinity pool)
- Entertainment (outdoor kitchen, fire pit, hot tub, built-in BBQ, pizza oven, outdoor fireplace, pergola, gazebo)
- Energy features (solar panels, ceiling fans)

GUIDELINES:
- Be EXHAUSTIVE - include every visible feature, color, material, detail
- Be SPECIFIC: "3-car garage" not "garage", "vaulted ceilings" not "ceiling", "quartz countertops" not "countertops"
- Include COLORS: "white cabinets", "gray walls", "black appliances", "blue exterior"
- Note CONDITION: "updated", "renovated", "modern", "newly installed"
- Include MATERIALS: specific types like "porcelain tile", "engineered hardwood", "fiber cement siding"
- Identify STYLES: architectural and design styles
- For EXTERIORS: always identify architecture style if possible

ARCHITECTURAL STYLE CLASSIFICATION (EXTERIORS ONLY):
For exterior photos, identify the architectural style using hierarchical approach:

TIER 1 (Broad/Common - Use when confident ≥80%):
modern, contemporary, mid_century_modern, craftsman, ranch, colonial, victorian,
mediterranean, spanish_colonial_revival, tudor, farmhouse, cottage, bungalow,
cape_cod, arts_and_crafts, prairie_style, etc.

TIER 2 (Specific Sub-Styles - Only if VERY confident ≥90%):
victorian_queen_anne, craftsman_bungalow, colonial_saltbox, tuscan_villa,
french_provincial, etc.

Guidelines:
- If uncertain → use broader Tier 1 style
- If interior photo → architecture_style = null
- Include confidence score in "confidence" field

Return STRICT JSON format:
{
  "image_type": "exterior" or "interior",
  "features": ["feature1", "feature2", ...],
  "architecture_style": "craftsman" (Tier 1 broad style, or null if interior/unknown),
  "architecture_style_specific": "craftsman_bungalow" (Tier 2 if very confident, else null),
  "architecture_confidence": 0.85 (numeric 0-1, only for exteriors),
  "exterior_color": "blue" (only if exterior, else null),
  "materials": ["brick", "stone"],
  "visual_features": ["balcony", "porch", "deck"],
  "confidence": "high" or "medium" or "low"
}

IMPORTANT: Be thorough. A good analysis should have 30-50+ features for a detailed photo."""
                        }
                    ]
                }
            ]
        }

        response = brt.invoke_model(
            modelId=LLM_MODEL_ID,  # Claude 3 Haiku
            body=json.dumps(payload)
        )

        result = json.loads(response["body"].read())
        text = result["content"][0]["text"].strip()

        # Parse JSON response
        try:
            analysis = json.loads(text)

            # Ensure all required fields exist with defaults
            analysis.setdefault("features", [])
            analysis.setdefault("image_type", "unknown")
            analysis.setdefault("architecture_style", None)
            analysis.setdefault("architecture_style_specific", None)
            analysis.setdefault("architecture_confidence", 0.0)
            analysis.setdefault("exterior_color", None)
            analysis.setdefault("materials", [])
            analysis.setdefault("visual_features", [])
            analysis.setdefault("confidence", "medium")

            # Normalize all strings to lowercase
            analysis["features"] = [f.lower().strip() for f in analysis["features"] if f]
            analysis["materials"] = [m.lower().strip() for m in analysis["materials"] if m]
            analysis["visual_features"] = [v.lower().strip() for v in analysis["visual_features"] if v]
            if analysis["architecture_style"]:
                analysis["architecture_style"] = analysis["architecture_style"].lower().replace(" ", "_")
            if analysis["exterior_color"]:
                analysis["exterior_color"] = analysis["exterior_color"].lower()

            # Limit features if needed
            if len(analysis["features"]) > max_labels:
                analysis["features"] = analysis["features"][:max_labels]

            logger.debug(f"Comprehensive analysis: {len(analysis['features'])} features, type={analysis['image_type']}, style={analysis['architecture_style']}")

        except json.JSONDecodeError as e:
            # Fallback: create minimal structure
            logger.warning(f"JSON parse failed for {image_url}: {e}, falling back to basic parsing")
            analysis = {
                "features": [label.strip().lower() for label in text.split(",") if label.strip()][:max_labels],
                "image_type": "unknown",
                "architecture_style": None,
                "exterior_color": None,
                "materials": [],
                "visual_features": [],
                "confidence": "low"
            }

        # No caching here - use detect_labels_with_response() + cache_utils for caching
        return analysis

    except Exception as e:
        logger.warning(f"Comprehensive vision analysis failed for {image_url}: {e}")
        return {
            "features": [],
            "image_type": "unknown",
            "architecture_style": None,
            "exterior_color": None,
            "materials": [],
            "visual_features": [],
            "confidence": "low"
        }


def detect_labels_with_response(img_bytes: bytes, image_url: str = "", max_labels: int = 100) -> Dict[str, Any]:
    """
    Comprehensive vision analysis that returns both parsed analysis AND raw LLM response.

    This function is used by the new unified caching system (cache_utils.py) to enable:
    - Storing both the parsed analysis and raw LLM response atomically
    - Debugging failed parses by inspecting raw LLM output
    - Re-parsing without re-calling the LLM

    The actual caching to hearth-vision-cache is done by cache_utils.cache_image_data()
    in the calling code.

    Args:
        img_bytes: Raw image bytes
        image_url: URL of the image (for logging/debugging)
        max_labels: Maximum number of features to return (default 100)

    Returns:
        Dictionary with:
        {
            "analysis": {
                "features": [...],
                "image_type": "exterior" or "interior",
                "architecture_style": "modern" or null,
                "exterior_color": "blue" or null,
                "materials": [...],
                "visual_features": [...],
                "confidence": "high"/"medium"/"low"
            },
            "llm_response": "raw response text from Claude"
        }
    """
    # Always call LLM - no old cache fallback
    # Analyze with Claude Haiku
    try:
        b64_image = base64.b64encode(img_bytes).decode("utf-8")

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 800,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": """Analyze this property photo comprehensively. Extract ALL valuable information for real estate search.

STEP 1: Determine if this is EXTERIOR or INTERIOR
- Exterior: Shows outside of building, facade, yard, architectural features
- Interior: Shows rooms, furnishings, indoor spaces

STEP 2: Extract ALL visible features (be exhaustive and specific):

IF EXTERIOR:
- Primary exterior color (white, blue, gray, beige, brown, red, tan, yellow, green, black)
- Exterior materials (brick, stone, vinyl siding, wood siding, stucco, metal siding, fiber cement)
- Architecture style (modern, contemporary, craftsman, victorian, colonial, ranch, mediterranean, tudor, cape cod, farmhouse, mid-century modern, traditional, transitional, bungalow, cottage, spanish, etc.)
- Garage details (attached garage, detached garage, 2-car garage, 3-car garage, carport, tandem garage)
- Roof type (gabled roof, hipped roof, flat roof, mansard roof, gambrel roof)
- Structural features (front porch, covered porch, balcony, deck, patio, dormers, bay windows, picture windows, columns, shutters, chimney, awning)
- Outdoor features (fenced yard, wood fence, white fence, chain link fence, mature trees, landscaped yard, driveway, walkway, garden, lawn)
- Views (mountain view, city view, water view, wooded lot, golf course view)

IF INTERIOR:
- Room type (kitchen, master bedroom, living room, dining room, bathroom, bedroom, home office, laundry room, basement, bonus room, etc.)
- Flooring (hardwood floors, tile floors, carpet, laminate, luxury vinyl plank, porcelain tile, marble floors, engineered hardwood)
- Kitchen details (granite countertops, marble countertops, quartz countertops, butcher block countertops, stainless steel appliances, white cabinets, wood cabinets, gray cabinets, kitchen island, breakfast bar, double oven, gas range, electric range, pantry, farmhouse sink, subway tile backsplash, pendant lights)
- Bathroom features (soaking tub, walk-in shower, dual sinks, double vanity, frameless glass shower, tile shower, separate tub and shower, vessel sink, rain shower head, heated floors)
- Ceilings (vaulted ceilings, cathedral ceilings, coffered ceiling, tray ceiling, exposed beams, wood beams, high ceilings, popcorn ceiling)
- Windows/Lighting (large windows, floor to ceiling windows, bay windows, lots of natural light, bright and airy, recessed lighting, pendant lights, chandelier, track lighting, skylights)
- Storage (walk-in closet, built-in shelving, linen closet, custom cabinetry, built-in storage)
- Fireplace (stone fireplace, brick fireplace, gas fireplace, wood burning fireplace, electric fireplace, modern fireplace)
- Architectural details (crown molding, wainscoting, archways, open floor plan, open concept, shiplap, exposed brick)
- Appliances (stainless steel appliances, black appliances, white appliances, built-in microwave, wine fridge, dishwasher)
- Condition/Style (updated kitchen, renovated bathroom, modern finishes, contemporary style, traditional style, farmhouse style, industrial style, move-in ready, newly renovated)

OUTDOOR AMENITIES (if visible):
- Pool (in-ground pool, above-ground pool, pool with spa, heated pool, saltwater pool, lap pool, infinity pool)
- Entertainment (outdoor kitchen, fire pit, hot tub, built-in BBQ, pizza oven, outdoor fireplace, pergola, gazebo)
- Energy features (solar panels, ceiling fans)

GUIDELINES:
- Be EXHAUSTIVE - include every visible feature, color, material, detail
- Be SPECIFIC: "3-car garage" not "garage", "vaulted ceilings" not "ceiling", "quartz countertops" not "countertops"
- Include COLORS: "white cabinets", "gray walls", "black appliances", "blue exterior"
- Note CONDITION: "updated", "renovated", "modern", "newly installed"
- Include MATERIALS: specific types like "porcelain tile", "engineered hardwood", "fiber cement siding"
- Identify STYLES: architectural and design styles
- For EXTERIORS: always identify architecture style if possible

Return STRICT JSON format:
{
  "image_type": "exterior" or "interior",
  "features": ["feature1", "feature2", ...],
  "architecture_style": "modern" or null (only for exteriors),
  "exterior_color": "blue" or null (only for exteriors),
  "materials": ["brick", "stone", ...],
  "visual_features": ["balcony", "porch", ...],
  "confidence": "high" or "medium" or "low"
}"""
                        }
                    ]
                }
            ]
        }

        response = brt.invoke_model(
            modelId=LLM_MODEL_ID,
            body=json.dumps(payload)
        )

        result = json.loads(response["body"].read())
        text = result["content"][0]["text"].strip()

        # Store raw response
        llm_response = text

        # Parse JSON response
        try:
            analysis = json.loads(text)

            # Ensure all required fields exist with defaults
            analysis.setdefault("features", [])
            analysis.setdefault("image_type", "unknown")
            analysis.setdefault("architecture_style", None)
            analysis.setdefault("architecture_style_specific", None)
            analysis.setdefault("architecture_confidence", 0.0)
            analysis.setdefault("exterior_color", None)
            analysis.setdefault("materials", [])
            analysis.setdefault("visual_features", [])
            analysis.setdefault("confidence", "medium")

            # Normalize all strings to lowercase
            analysis["features"] = [f.lower().strip() for f in analysis["features"] if f]
            analysis["materials"] = [m.lower().strip() for m in analysis["materials"] if m]
            analysis["visual_features"] = [v.lower().strip() for v in analysis["visual_features"] if v]
            if analysis["architecture_style"]:
                analysis["architecture_style"] = analysis["architecture_style"].lower().replace(" ", "_")
            if analysis["exterior_color"]:
                analysis["exterior_color"] = analysis["exterior_color"].lower()

            # Limit features if needed
            if len(analysis["features"]) > max_labels:
                analysis["features"] = analysis["features"][:max_labels]

            logger.debug(f"Comprehensive analysis: {len(analysis['features'])} features, type={analysis['image_type']}, style={analysis['architecture_style']}")

        except json.JSONDecodeError as e:
            # Fallback: create minimal structure
            logger.warning(f"JSON parse failed for {image_url}: {e}, falling back to basic parsing")
            analysis = {
                "features": [label.strip().lower() for label in text.split(",") if label.strip()][:max_labels],
                "image_type": "unknown",
                "architecture_style": None,
                "exterior_color": None,
                "materials": [],
                "visual_features": [],
                "confidence": "low"
            }

        return {"analysis": analysis, "llm_response": llm_response}

    except Exception as e:
        logger.warning(f"Comprehensive vision analysis failed for {image_url}: {e}")
        return {
            "analysis": {
                "features": [],
                "image_type": "unknown",
                "architecture_style": None,
                "exterior_color": None,
                "materials": [],
                "visual_features": [],
                "confidence": "low"
            },
            "llm_response": ""
        }

# ===============================================
# OPENSEARCH INDEX MANAGEMENT
# ===============================================

def create_index_if_needed():
    """
    Create the OpenSearch index with proper mappings if it doesn't exist.

    This sets up the schema for property listings with:
    - Text fields for BM25 full-text search
    - Keyword fields for exact filtering
    - Numeric fields for range queries (price, beds, baths)
    - Geo-point for location-based search
    - kNN vector fields for semantic similarity search
    - Boolean flags for data quality tracking

    The index uses HNSW (Hierarchical Navigable Small World) algorithm for
    fast approximate nearest neighbor search on high-dimensional vectors.

    Schema Version Detection:
    - "listings" → Legacy single-vector schema (backward compatible)
    - "listings-v2" → Multi-vector schema with all image embeddings stored separately
    """
    if os_client.indices.exists(index=OS_INDEX):
        return  # Index already exists

    logger.info("Creating OpenSearch index %s", OS_INDEX)

    # Detect if this is the new multi-vector schema
    is_multi_vector = OS_INDEX.endswith("-v2")

    body = {
        "settings": {
            "index": {
                "knn": True  # Enable k-nearest neighbors search
            }
        },
        "mappings": {
            "properties": {
                # Identifiers and location
                "zpid": {"type": "keyword"},  # Zillow property ID (exact match)
                "address": {  # Nested object for UI compatibility
                    "properties": {
                        "streetAddress": {"type": "text"},
                        "city": {"type": "keyword"},
                        "state": {"type": "keyword"},
                        "zipcode": {"type": "keyword"}
                    }
                },
                "city": {"type": "keyword"},  # Exact match for filtering
                "state": {"type": "keyword"},  # Exact match for filtering
                "zip_code": {"type": "keyword"},  # Exact match

                # Numeric properties for range filtering
                "price": {"type": "long"},  # Property price in dollars
                "bedrooms": {"type": "float"},  # Number of bedrooms (was beds)
                "bathrooms": {"type": "float"},  # Number of bathrooms (was baths)
                "livingArea": {"type": "float"},  # Living area in sqft (was acreage)
                "geo": {"type": "geo_point"},  # Latitude/longitude for radius search

                # Text content for search
                "description": {"type": "text"},  # Original/fallback description
                "llm_profile": {"type": "text"},  # LLM-normalized description (deprecated, always empty)
                "visual_features_text": {"type": "text"},  # Generated from image analyses (NEW)
                "feature_tags": {"type": "keyword"},  # Extracted features (pool, garage, etc.)
                "image_tags": {"type": "keyword"},  # Vision-detected labels (kitchen, brick, etc.)
                "architecture_style": {"type": "keyword"},  # Architecture style (modern, craftsman, etc.)

                # Vector embeddings for semantic search
                "vector_text": {
                    "type": "knn_vector",
                    "dimension": TEXT_DIM,  # 1024 dimensions
                    "method": {
                        "name": "hnsw",  # Fast approximate nearest neighbor algorithm
                        "engine": "lucene",  # Lucene implementation
                        "space_type": "cosinesimil"  # Cosine similarity metric
                    }
                },

                # Data quality flags
                "has_valid_embeddings": {"type": "boolean"},  # True if vectors are non-zero
                "has_description": {"type": "boolean"}  # True if original description exists

                # NOTE: Complete Zillow listing data is stored in S3 at: s3://demo-hearth-data/listings/{zpid}.json
                # OpenSearch only stores search-relevant fields to avoid mapping conflicts
            }
        }
    }

    # Add image vector field(s) based on schema version
    if is_multi_vector:
        # PHASE 2: Multi-vector schema for listings-v2
        # Stores ALL image embeddings separately for max-match search
        body["mappings"]["properties"]["image_vectors"] = {
            "type": "nested",  # Array of image vector objects
            "properties": {
                "image_url": {"type": "keyword"},  # URL of the image
                "image_type": {"type": "keyword"},  # "exterior", "interior", "kitchen", "bathroom", etc.
                "vector": {
                    "type": "knn_vector",
                    "dimension": IMAGE_DIM,  # 1024 dimensions
                    "method": {
                        "name": "hnsw",
                        "engine": "lucene",
                        "space_type": "cosinesimil"
                    }
                }
            }
        }
        logger.info("Creating listings-v2 with MULTI-VECTOR image schema (Phase 2)")
    else:
        # LEGACY: Single averaged vector for backward compatibility
        body["mappings"]["properties"]["vector_image"] = {
            "type": "knn_vector",
            "dimension": IMAGE_DIM,  # 1024 dimensions
            "method": {
                "name": "hnsw",
                "engine": "lucene",
                "space_type": "cosinesimil"
            }
        }
        logger.info("Creating legacy index with SINGLE-VECTOR image schema")

    # Create index with error handling for race conditions in parallel processing
    try:
        os_client.indices.create(index=OS_INDEX, body=body)
        logger.info(f"✅ Successfully created index {OS_INDEX}")
    except Exception as e:
        # If index already exists (race condition), that's fine - another thread created it
        if "resource_already_exists_exception" in str(e):
            logger.info(f"Index {OS_INDEX} already exists (created by parallel thread)")
        else:
            # Re-raise any other errors
            raise


def upsert_listing(doc_id: str, body: Dict[str, Any]):
    """
    Insert or update a single listing document in OpenSearch.

    Args:
        doc_id: Unique document ID (typically zpid)
        body: Document fields to index
    """
    os_client.index(index=OS_INDEX, id=doc_id, body=body, refresh=False)

def _send_bulk(chunk_lines: List[str], attempt: int = 0, base_sleep: float = 0.5, max_sleep: float = 8.0):
    """
    Send a bulk indexing request to OpenSearch with exponential backoff retry logic.

    Args:
        chunk_lines: OpenSearch bulk API format (action line + doc line pairs)
        attempt: Current retry attempt number (for exponential backoff calculation)
        base_sleep: Base sleep time in seconds
        max_sleep: Maximum sleep time in seconds

    Returns:
        True if request succeeded, False if rate limited (caller should retry)

    Raises:
        Exception: For non-retryable errors
    """
    payload = "\n".join(chunk_lines) + "\n"
    try:
        # Changed to refresh=True to make documents immediately searchable
        response = os_client.bulk(body=payload, refresh=True, request_timeout=60)

        # Enhanced logging: Log full response structure for debugging
        logger.info(f"🔍 Bulk API response keys: {list(response.keys())}")
        logger.info(f"   errors={response.get('errors')}, took={response.get('took')}ms, items_count={len(response.get('items', []))}")

        # Check for errors in bulk response
        if response.get("errors"):
            success_count = 0
            error_count = 0
            successful_zpids = []
            failed_zpids = []
            logger.error("Bulk indexing had errors!")
            for item in response.get("items", []):
                for action, details in item.items():
                    zpid = details.get("_id")
                    if details.get("error"):
                        error_count += 1
                        failed_zpids.append(zpid)
                        logger.error("Failed to index zpid %s: %s", zpid, details.get("error"))
                    else:
                        success_count += 1
                        successful_zpids.append(zpid)
                        # Log the actual response status for successful items
                        logger.info(f"   zpid={zpid}: status={details.get('status')}, result={details.get('result')}")
            logger.info("Bulk result: %d succeeded, %d failed", success_count, error_count)
            logger.info("   Successful zpids: %s", successful_zpids[:10])
            logger.error("   Failed zpids: %s", failed_zpids[:10])
            # Still return True to continue processing (partial success)
        else:
            item_count = len(response.get("items", []))
            logger.info("Bulk indexed %d documents successfully", item_count)
            # Log first few zpids for verification with their status
            zpids_with_status = []
            for item in response.get("items", []):
                for _, details in item.items():
                    zpid = details.get("_id")
                    status = details.get("status")
                    result = details.get("result")
                    zpids_with_status.append(f"{zpid}(s={status},r={result})")
            logger.info(f"   Successfully indexed zpids: {zpids_with_status[:10]}")
        return True
    except Exception as e:
        status = getattr(e, "status_code", None)
        # Retry on rate limits and temporary server errors
        if status in (429, 502, 503, 504) or "Too Many Requests" in str(e):
            # Exponential backoff: 0.5s, 1s, 2s, 4s, 8s... + jitter
            sleep = min(base_sleep * (2 ** attempt), max_sleep) + random.uniform(0, 0.3)
            time.sleep(sleep)
            return False  # Signal caller to retry
        raise  # Non-retryable error


def bulk_upsert(actions: Iterable[Dict[str, Any]], initial_chunk: int = 100, max_retries: int = 6):
    """
    Robustly index multiple documents to OpenSearch with automatic chunking and retry logic.

    This function handles:
    - Chunking large batches to avoid OpenSearch limits
    - Exponential backoff retries for rate limits
    - Automatic splitting of chunks if repeatedly throttled
    - Error handling for individual document failures

    The algorithm:
    1. Buffer documents up to initial_chunk size (default 100)
    2. Send bulk request
    3. If rate limited, retry with exponential backoff
    4. If still failing after max_retries/2, split chunk in half and retry each half
    5. Continue until all documents indexed or unrecoverable error

    Args:
        actions: Iterator of documents to index, each with {"_id": ..., "_source": {...}}
        initial_chunk: Initial batch size (will auto-reduce if throttled)
        max_retries: Maximum retry attempts before splitting or failing
    """
    def lines_from_actions(acts: List[Dict[str, Any]]) -> List[str]:
        """Convert action dicts to OpenSearch bulk API format."""
        lines = []
        for a in acts:
            # Action line: {"index": {"_index": "listings", "_id": "12345"}}
            lines.append(json.dumps({"index": {"_index": OS_INDEX, "_id": a["_id"]}}))
            # Document line: {actual document fields}
            lines.append(json.dumps(a["_source"]))
        return lines

    buf: List[Dict[str, Any]] = []
    chunk_size = initial_chunk

    def flush(buf_local: List[Dict[str, Any]]):
        """Flush buffered documents with retry and split logic."""
        if not buf_local:
            return

        logger.info(f"Indexing batch: {len(buf_local)} documents to {OS_INDEX}")
        lines = lines_from_actions(buf_local)

        # Try to send with retries
        for attempt in range(max_retries):
            if _send_bulk(lines, attempt=attempt):
                return  # Success!

            # If repeatedly throttled at halfway point, split the batch
            if attempt == max_retries // 2 and len(buf_local) > 1:
                mid = len(buf_local) // 2
                flush(buf_local[:mid])  # Recursively flush first half
                flush(buf_local[mid:])  # Recursively flush second half
                return

        # Still failing after all retries - try splitting as last resort
        if len(buf_local) > 1:
            mid = len(buf_local) // 2
            flush(buf_local[:mid])
            flush(buf_local[mid:])
        else:
            # Single document failing repeatedly - give up
            raise RuntimeError("bulk_upsert failed after retries for a single document")

    # Main loop: buffer and flush
    for a in actions:
        buf.append(a)
        if len(buf) >= chunk_size:
            flush(buf)
            buf = []

    # Flush remaining documents
    if buf:
        flush(buf)

# ===============================================
# ZILLOW DATA PARSING & LLM FEATURE EXTRACTION
# ===============================================

def extract_zillow_images(listing: Dict[str, Any], target_width: int = 576) -> List[str]:
    """
    Extract image URLs from a Zillow listing at optimal resolution for embeddings.

    For cost optimization, extracts medium-resolution images (default 576px) which are
    sufficient for vision models while being much cheaper to process than high-res.
    The API returns complete carouselPhotosComposable so frontend can use any resolution.

    Args:
        listing: Raw Zillow listing dictionary
        target_width: Target image width in pixels (default 576px for embeddings)
                     Common values: 384, 576, 768

    Returns:
        List of unique image URLs at target resolution
    """
    urls = []

    # Primary source: carouselPhotosComposable (deduplicated images)
    carousel = listing.get("carouselPhotosComposable", [])
    if carousel:
        for photo in carousel:
            # Get optimal resolution URL from this photo for embeddings
            if isinstance(photo, dict):
                # Try to get URL from image field (usually highest res)
                url = photo.get("image") or photo.get("url")

                # Check mixedSources for target resolution (cost optimization)
                if "mixedSources" in photo:
                    ms = photo["mixedSources"]
                    # Prefer jpeg over webp for compatibility
                    jpeg_sources = ms.get("jpeg", [])
                    if jpeg_sources and isinstance(jpeg_sources, list):
                        # Find closest resolution to target (prefer exact or slightly larger)
                        best_match = None
                        min_diff = float('inf')

                        for source in jpeg_sources:
                            if isinstance(source, dict) and "width" in source and "url" in source:
                                width = source.get("width", 0)
                                # Prefer slightly larger than target over smaller
                                diff = abs(width - target_width)
                                if width >= target_width and diff < min_diff:
                                    best_match = source
                                    min_diff = diff
                                elif not best_match:  # Fallback to smaller if no larger available
                                    best_match = source
                                    min_diff = diff

                        if best_match:
                            urls.append(best_match["url"])
                            continue

                # Fallback to direct URL if no mixedSources
                if url and isinstance(url, str):
                    urls.append(url)

        if urls:
            return urls

    # Fallback 1: imgSrc (main thumbnail image)
    img_src = listing.get("imgSrc")
    if img_src and isinstance(img_src, str):
        urls.append(img_src)

    # Fallback 2: responsivePhotos - extract highest resolution from each unique photo
    # WARNING: For lots/vacant land, responsivePhotos may contain nearby home images!
    # Only use responsivePhotos if property has actual photos (photoCount > 0 and not vacant land)
    responsive = listing.get("responsivePhotos", [])
    home_type = listing.get("homeType", "").lower()
    photo_count = listing.get("photoCount", 0)

    # Skip responsivePhotos for vacant land or lots with no photos
    # These often contain misleading nearby property images from Zillow's UI
    is_vacant_land = home_type in ["lot", "vacantland", "land", ""] or "vacant" in home_type

    if responsive and not (is_vacant_land and photo_count == 0):
        seen_photos = set()  # Track photo IDs to avoid duplicates
        for photo in responsive:
            if not isinstance(photo, dict):
                continue

            # Use photo caption/subjectType as unique identifier
            photo_id = photo.get("caption") or photo.get("subjectType") or len(seen_photos)
            if photo_id in seen_photos:
                continue
            seen_photos.add(photo_id)

            # Extract highest resolution URL
            ms = photo.get("mixedSources", {})
            jpeg_sources = ms.get("jpeg", [])
            if jpeg_sources and isinstance(jpeg_sources, list):
                # Get the largest resolution
                largest = max(jpeg_sources, key=lambda x: x.get("width", 0) if isinstance(x, dict) else 0)
                if isinstance(largest, dict) and "url" in largest:
                    urls.append(largest["url"])

    # Fallback 3: Simple image arrays
    for key in ["images", "photos", "photoUrls"]:
        val = listing.get(key)
        if isinstance(val, list) and not urls:
            for it in val:
                if isinstance(it, dict) and "url" in it:
                    urls.append(it["url"])
                elif isinstance(it, str):
                    urls.append(it)

    return urls if urls else []


# NOTE: classify_architecture_style_vision() removed - replaced by unified detect_labels()
# The detect_labels() function now extracts ALL features including architecture style in one pass
# This eliminated redundant LLM calls and saved ~$0.0015 per listing
# See detect_labels() above for the unified implementation




def extract_query_constraints(query_text: str) -> Dict[str, Any]:
    """
    Parse structured constraints from natural language search query using Claude LLM.

    This extracts multiple types of constraints from queries like
    "3 bedroom modern house with pool under $500k near a school":
    - must_have: Required feature tags (e.g., ["pool", "balcony", "blue_exterior"])
    - nice_to_have: Preferred features (e.g., ["garage"])
    - hard_filters: Numeric constraints (e.g., {"beds_min": 3, "price_max": 500000})
    - architecture_style: Architecture style if mentioned (e.g., "modern", "craftsman")
    - proximity: Location-based requirements (e.g., {"poi_type": "school", "max_distance_km": 5})

    The LLM intelligently interprets natural language and converts it to
    structured filters that OpenSearch can use.

    Args:
        query_text: Natural language search query from user

    Returns:
        Dictionary with keys: must_have (list), nice_to_have (list), hard_filters (dict),
        architecture_style (str or null), proximity (dict or null)
    """
    try:
        prompt = f"""
From the user's search query, extract:

1. must_have: ONLY property features explicitly mentioned (snake_case). Examples:
   - Structural: balcony, porch, deck, patio, fence, white_fence, pool, garage
   - Exterior: white_exterior, blue_exterior, gray_exterior, brick_exterior, stone_exterior
   - Interior: kitchen_island, fireplace, open_floorplan, hardwood_floors
   - Outdoor: backyard, fenced_yard, large_yard

   IMPORTANT: If query is ONLY about location (e.g., "homes near X"), leave must_have EMPTY.
   Do NOT infer features that aren't explicitly mentioned in the query.

2. nice_to_have: Additional preferred tags (snake_case)

3. hard_filters: Numeric constraints (keys: price_min, price_max, beds_min, baths_min, acreage_min, acreage_max)

4. architecture_style: ONE style if mentioned, or null. Use hierarchical approach - prefer broad category unless user is specific:

   TIER 1 (Broad Categories - Use These When Unsure):
   modern, contemporary, mid_century_modern, craftsman, ranch, colonial, victorian,
   mediterranean, spanish_colonial_revival, tudor, farmhouse, cottage, bungalow,
   cape_cod, split_level, traditional, transitional, industrial, minimalist,
   prairie_style, mission_revival, pueblo_revival, log_cabin, a_frame,
   scandinavian_modern, contemporary_farmhouse, arts_and_crafts

   TIER 2 (Specific Sub-Styles - Only If User Explicitly Mentions):
   victorian_queen_anne, victorian_italianate, victorian_gothic_revival,
   victorian_second_empire, victorian_romanesque_revival, victorian_shingle_style,
   craftsman_bungalow, craftsman_foursquare, colonial_revival, colonial_saltbox,
   colonial_dutch, colonial_spanish, federal, georgian, tuscan_villa,
   french_provincial, french_country, spanish_hacienda, monterey_colonial,
   english_cottage, french_chateau, greek_revival, neoclassical,
   romanesque_revival, gothic_revival, beaux_arts, art_deco, bauhaus,
   international_style, postmodern, modern_farmhouse, rustic_modern,
   mid_century_ranch, mid_century_split_level

   Examples:
   - "Victorian home" → "victorian" (broad)
   - "Queen Anne Victorian" → "victorian_queen_anne" (specific)
   - "Craftsman house" → "craftsman" (broad)
   - "Craftsman bungalow" → "craftsman_bungalow" (specific)
   - "Arts and Crafts" → "arts_and_crafts" (specific style user requested!)

   If uncertain, use the broader Tier 1 style.

5. proximity: If query mentions location/POI, extract:
   {{
     "poi_type": "school" | "grocery_store" | "gym" | "fitness_center" | "park" | "hospital" | "office" | "downtown" | etc,
     "max_distance_km": number (estimate: "near"=5, "close to"=3, "within X miles"=X*1.6),
     "max_drive_time_min": number (only if explicit like "10 minute drive")
   }}
   Keywords: "near", "close to", "by", "next to", "within X miles/km of"
   If no proximity mentioned, return null.

6. query_type: Classify query to optimize search scoring. ONE of:
   - "color": Query emphasizes colors (white, gray, blue, beige, brown exterior/interior)
   - "material": Query about materials (brick, stone, wood, granite, marble, hardwood, vinyl)
   - "visual_style": Query about architecture/design style, views, or visual characteristics
   - "specific_feature": Query about specific amenities (pool, garage, fireplace, specific room types)
   - "room_type": Query about specific rooms (kitchen, bathroom, master bedroom)
   - "general": Vague or general query without specific features

Return strict JSON with keys: must_have, nice_to_have, hard_filters, architecture_style, proximity, query_type

Query: "{query_text}"
"""

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "temperature": 0,  # Deterministic parsing
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }

        # Invoke Claude via Bedrock
        resp = brt.invoke_model(modelId=LLM_MODEL_ID, body=json.dumps(body))
        raw = resp["body"].read().decode("utf-8")
        parsed = json.loads(raw)
        text = parsed["content"][0]["text"]
        j = json.loads(text)  # Parse JSON from Claude's response

        # Normalize architecture style
        arch_style = j.get("architecture_style")
        if arch_style:
            arch_style = str(arch_style).lower().replace(" ", "_")

        # Get proximity and query type
        proximity = j.get("proximity")
        query_type = j.get("query_type", "general")

        return {
            "must_have": [t.strip().lower() for t in j.get("must_have", [])],
            "nice_to_have": [t.strip().lower() for t in j.get("nice_to_have", [])],
            "hard_filters": j.get("hard_filters", {}),
            "architecture_style": arch_style,
            "proximity": proximity,
            "query_type": query_type,
        }

    except Exception as e:
        logger.warning("LLM constraint extraction failed: %s", e)
        # Fallback: simple keyword matching if LLM fails
        q = (query_text or "").lower()
        must = []
        if "pool" in q: must.append("pool")
        if "kitchen island" in q or "island" in q: must.append("kitchen_island")
        if "backyard" in q: must.append("backyard")
        if "balcony" in q: must.append("balcony")
        if "fence" in q: must.append("fence")

        # Extract architecture style from common keywords
        arch_style = None
        if "mid century modern" in q or "mid-century modern" in q:
            arch_style = "mid_century_modern"
        elif "modern" in q:
            arch_style = "modern"
        elif "craftsman" in q:
            arch_style = "craftsman"
        elif "victorian" in q:
            arch_style = "victorian"
        elif "colonial" in q:
            arch_style = "colonial"
        elif "ranch" in q:
            arch_style = "ranch"
        elif "contemporary" in q:
            arch_style = "contemporary"

        # Extract proximity from common keywords
        proximity = None
        if "near" in q or "close to" in q or "within" in q or "from" in q:
            poi_type = None
            if "school" in q:
                poi_type = "elementary_school" if "elementary" in q else "school"
            elif "grocery" in q or "supermarket" in q:
                poi_type = "grocery_store"
            elif "gym" in q or "fitness" in q:
                poi_type = "gym"
            elif "park" in q:
                poi_type = "park"
            elif "office" in q:
                poi_type = "office"

            if poi_type:
                proximity = {"poi_type": poi_type}
                # Try to extract drive time
                import re
                drive_match = re.search(r'(\d+)\s*minute', q)
                if drive_match:
                    proximity["max_drive_time_min"] = int(drive_match.group(1))

        return {
            "must_have": list(set(must)),
            "nice_to_have": [],
            "hard_filters": {},
            "architecture_style": arch_style,
            "proximity": proximity,
            "query_type": "general",  # Fallback defaults to general
        }


# NOTE: Geocoding functions removed - no longer needed!
# We now use on-demand geolocation enrichment in search.py instead of
# filtering by proximity at search time. This is 100x more cost-effective.
