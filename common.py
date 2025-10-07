"""
common.py - Shared utilities for the Hearth Real Estate Search Engine

This module provides common functionality used by both upload_listings.py and search.py:
- AWS client setup (OpenSearch, Bedrock, Rekognition)
- Text and image embedding generation via Amazon Bedrock
- OpenSearch index creation and bulk operations
- LLM-based feature extraction from property descriptions
- Zillow data parsing utilities

Architecture:
- Uses Amazon OpenSearch for multimodal vector search (text + images)
- Uses Amazon Bedrock Titan models for embeddings
- Uses Claude (via Bedrock) for intelligent feature extraction
- Uses AWS Rekognition for image label detection (optional)
"""

import base64
import json
import logging
import os
import time
import random
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

import boto3
import requests
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

OS_INDEX = os.getenv("OS_INDEX", "listings")  # Index name for property listings

# Bedrock model identifiers
TEXT_MODEL_ID = os.getenv("TEXT_EMBED_MODEL", "amazon.titan-embed-text-v2:0")  # Text embeddings
IMAGE_MODEL_ID = os.getenv("IMAGE_EMBED_MODEL", "amazon.titan-embed-image-v1")  # Image embeddings
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")  # Feature extraction

# Vector dimensions (must match model outputs)
TEXT_DIM = int(os.getenv("TEXT_DIM", "1024"))   # Titan Text v2 outputs 1024-dim vectors
IMAGE_DIM = int(os.getenv("IMAGE_DIM", "1024"))  # Titan Image outputs 1024-dim vectors

# Optional features
USE_REKOGNITION = os.getenv("USE_REKOGNITION", "false").lower() in ("1", "true", "yes")  # Enable image labeling
MAX_IMAGES = int(os.getenv("MAX_IMAGES", "6"))  # Max images to process per listing

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
    timeout=60,  # 60 second timeout for bulk operations
    max_retries=8,  # Retry failed requests up to 8 times
    retry_on_timeout=True,
    retry_on_status=(429, 502, 503, 504),  # Retry on rate limits and server errors
)

# Bedrock Runtime client for model invocations (embeddings + LLM)
brt = session.client("bedrock-runtime", config=Config(read_timeout=30, retries={"max_attempts": 2}))

# Rekognition client for image label detection (optional)
rekog = session.client("rekognition") if USE_REKOGNITION else None

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

    Args:
        text: Input text to embed (listing description, search query, etc.)

    Returns:
        1024-dimensional vector representing the semantic meaning of the text
    """
    if not text:
        return [0.0] * TEXT_DIM  # Return zero vector for empty text

    # Invoke Titan Text Embeddings model
    body = json.dumps({"inputText": text})
    resp = brt.invoke_model(modelId=TEXT_MODEL_ID, body=body)
    out = json.loads(resp["body"].read().decode("utf-8"))
    vec = _parse_embed_response(out)
    return vec


def _bytes_from_url(url: str) -> bytes:
    """
    Download image bytes from a URL.

    Args:
        url: Image URL to download

    Returns:
        Raw image bytes

    Raises:
        requests.HTTPError: If download fails
    """
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.content


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


def embed_image_from_url(url: str) -> List[float]:
    """
    Download an image from URL and generate its embedding vector.

    Args:
        url: Image URL to process

    Returns:
        1024-dimensional image embedding vector
    """
    return embed_image_bytes(_bytes_from_url(url))


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


def detect_labels(img_bytes: bytes, max_labels: int = 15) -> List[str]:
    """
    Detect objects and features in an image using AWS Rekognition.

    This extracts semantic labels like "pool", "kitchen", "brick", etc.
    from property images, which are used as searchable tags.

    Args:
        img_bytes: Raw image bytes
        max_labels: Maximum number of labels to return

    Returns:
        List of lowercase label strings (e.g., ["pool", "kitchen", "hardwood"])
        Only returns labels with >=80% confidence
    """
    if not rekog:
        return []  # Rekognition disabled

    resp = rekog.detect_labels(Image={"Bytes": img_bytes}, MaxLabels=max_labels)

    # Filter for high-confidence labels and normalize to lowercase
    labels = [
        l["Name"].lower()
        for l in resp.get("Labels", [])
        if l.get("Confidence", 0) >= 80.0
    ]
    return labels

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
    """
    if os_client.indices.exists(OS_INDEX):
        return  # Index already exists

    logger.info("Creating OpenSearch index %s", OS_INDEX)

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
                "address": {"type": "text"},  # Full-text searchable
                "city": {"type": "keyword"},  # Exact match for filtering
                "state": {"type": "keyword"},  # Exact match for filtering
                "zip_code": {"type": "keyword"},  # Exact match

                # Numeric properties for range filtering
                "price": {"type": "long"},  # Property price in dollars
                "beds": {"type": "float"},  # Number of bedrooms
                "baths": {"type": "float"},  # Number of bathrooms
                "acreage": {"type": "float"},  # Lot size in acres
                "geo": {"type": "geo_point"},  # Latitude/longitude for radius search

                # Text content for search
                "description": {"type": "text"},  # Original/fallback description
                "llm_profile": {"type": "text"},  # LLM-normalized description
                "feature_tags": {"type": "keyword"},  # Extracted features (pool, garage, etc.)
                "image_tags": {"type": "keyword"},  # Rekognition labels (kitchen, brick, etc.)

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
                "vector_image": {
                    "type": "knn_vector",
                    "dimension": IMAGE_DIM,  # 1024 dimensions
                    "method": {
                        "name": "hnsw",
                        "engine": "lucene",
                        "space_type": "cosinesimil"
                    }
                },

                # Data quality flags
                "has_valid_embeddings": {"type": "boolean"},  # True if vectors are non-zero
                "has_description": {"type": "boolean"}  # True if original description exists
            }
        }
    }
    os_client.indices.create(index=OS_INDEX, body=body)


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
        response = os_client.bulk(body=payload, refresh=False, request_timeout=60)
        # Check for errors in bulk response
        if response.get("errors"):
            logger.error("Bulk indexing had errors!")
            for item in response.get("items", []):
                for action, details in item.items():
                    if details.get("error"):
                        logger.error("Failed to index document %s: %s",
                                   details.get("_id"), details.get("error"))
            # Still return True to continue processing (partial success)
        else:
            logger.info("Bulk indexed %d documents successfully", len(response.get("items", [])))
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

def extract_zillow_images(listing: Dict[str, Any]) -> List[str]:
    """
    Extract all image URLs from a Zillow listing JSON object.

    Zillow stores images in multiple possible fields with different structures
    (responsivePhotos, images, photos, photoUrls), and this function handles
    all variations to extract unique image URLs.

    Args:
        listing: Raw Zillow listing dictionary

    Returns:
        List of unique image URLs (deduplicated)
    """
    urls = set()  # Use set to automatically deduplicate

    # Try various top-level image fields
    for key in ["responsivePhotos", "images", "photos", "photoUrls"]:
        val = listing.get(key)
        if isinstance(val, list):
            for it in val:
                if isinstance(it, dict) and "url" in it:
                    urls.add(it["url"])
                elif isinstance(it, str):
                    urls.add(it)  # Direct URL string

    # Extract from nested responsivePhotos.mixedSources structure
    for photo in listing.get("responsivePhotos", []):
        ms = photo.get("mixedSources", {})
        for arr in ms.values():  # jpeg, webp, etc.
            if isinstance(arr, list):
                for obj in arr:
                    if isinstance(obj, dict) and "url" in obj:
                        urls.add(obj["url"])

    return list(urls)


def llm_feature_profile(description: str) -> Tuple[str, List[str]]:
    """
    Use Claude LLM to extract structured property features from free-text description.

    This normalizes messy real estate descriptions into:
    - A concise, standardized summary (profile)
    - A list of snake_case feature tags (pool, granite_counters, etc.)

    The LLM uses a controlled vocabulary to ensure consistent tagging across
    all listings, making features searchable and filterable.

    Example:
        Input: "Beautiful home with swimming pool and granite countertops"
        Output: ("Modern home with pool and granite finishes", ["pool", "granite_counters"])

    Args:
        description: Raw listing description text

    Returns:
        Tuple of (profile_text, feature_tags_list)
    """
    if not description:
        return "", []

    # Prompt Claude to extract features in strict JSON format
    prompt = f"""
You are extracting property features from a real estate listing description.
Return STRICT JSON with fields: profile (string, concise normalized summary) and tags (array of short snake_case tags).
Use a controlled vocabulary when possible, e.g.:
["pool","backyard","kitchen_island","fireplace","brick","fenced_yard","garage","finished_basement","open_floorplan","granite_counters","walk_in_closet","waterfront","mountain_view","hardwood_floors","new_construction"]
Text:
\"\"\"{description.strip()[:4000]}\"\"\"
JSON only:
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "temperature": 0,  # Deterministic output
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }

    try:
        # Invoke Claude via Bedrock
        resp = brt.invoke_model(modelId=LLM_MODEL_ID, body=json.dumps(body))
        raw = resp["body"].read().decode("utf-8")
        parsed = json.loads(raw)
        content = parsed["content"][0]["text"]
        j = json.loads(content)  # Parse JSON from Claude's response

        # Extract and truncate profile
        profile = str(j.get("profile", ""))[:4000]

        # Extract and normalize tags to snake_case
        tags = [str(t) for t in j.get("tags", []) if isinstance(t, (str,))]
        norm = []
        for t in tags:
            t2 = t.strip().lower().replace(" ", "_")  # "Kitchen Island" -> "kitchen_island"
            if t2:
                norm.append(t2)

        return profile, norm

    except Exception as e:
        logger.warning("LLM profile extraction failed: %s", e)
        return "", []  # Graceful fallback


def extract_query_constraints(query_text: str) -> Dict[str, Any]:
    """
    Parse structured constraints from natural language search query using Claude LLM.

    This extracts three types of constraints from queries like
    "3 bedroom house with pool under $500k":
    - must_have: Required feature tags (e.g., ["pool"])
    - nice_to_have: Preferred features (e.g., ["garage"])
    - hard_filters: Numeric constraints (e.g., {"beds_min": 3, "price_max": 500000})

    The LLM intelligently interprets natural language and converts it to
    structured filters that OpenSearch can use.

    Args:
        query_text: Natural language search query from user

    Returns:
        Dictionary with keys: must_have (list), nice_to_have (list), hard_filters (dict)
    """
    try:
        prompt = f"""
From the user's search query, extract:
- must_have: tags (snake_case) that MUST be present (e.g., pool, kitchen_island, fenced_yard)
- nice_to_have: additional tags (snake_case)
- hard_filters: numeric constraints like price/beds/baths/acreage (use keys: price_min, price_max, beds_min, baths_min, acreage_min, acreage_max)
Return strict JSON with those keys. Query: "{query_text}"
"""

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "temperature": 0,  # Deterministic parsing
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }

        # Invoke Claude via Bedrock
        resp = brt.invoke_model(modelId=LLM_MODEL_ID, body=json.dumps(body))
        raw = resp["body"].read().decode("utf-8")
        parsed = json.loads(raw)
        text = parsed["content"][0]["text"]
        j = json.loads(text)  # Parse JSON from Claude's response

        return {
            "must_have": [t.strip().lower() for t in j.get("must_have", [])],
            "nice_to_have": [t.strip().lower() for t in j.get("nice_to_have", [])],
            "hard_filters": j.get("hard_filters", {}),
        }

    except Exception:
        # Fallback: simple keyword matching if LLM fails
        q = (query_text or "").lower()
        must = []
        if "pool" in q: must.append("pool")
        if "kitchen island" in q or "island" in q: must.append("kitchen_island")
        if "backyard" in q: must.append("backyard")
        return {"must_have": list(set(must)), "nice_to_have": [], "hard_filters": {}}
