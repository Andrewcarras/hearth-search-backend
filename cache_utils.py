"""
Unified caching utilities for image embeddings, image analysis, and text embeddings.

This module provides atomic caching operations with complete metadata tracking,
including EDT timestamps, cost tracking, and access metrics.

Tables:
- hearth-vision-cache: Image embeddings + Claude Haiku vision analysis
- hearth-text-embeddings: Text embeddings for descriptions/queries
"""

import json
import time
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# Table names
VISION_CACHE_TABLE = "hearth-vision-cache"
TEXT_CACHE_TABLE = "hearth-text-embeddings"

# Cost constants (per API call)
COST_IMAGE_EMBEDDING = 0.0008  # Titan Image Embeddings
COST_IMAGE_ANALYSIS = 0.00025  # Claude Haiku Vision
COST_TEXT_EMBEDDING = 0.0001   # Titan Text Embeddings v2


def get_edt_timestamp(unix_timestamp: Optional[int] = None) -> str:
    """
    Convert Unix timestamp to EDT timezone string.

    Args:
        unix_timestamp: Unix timestamp (seconds since epoch). If None, uses current time.

    Returns:
        Formatted string like "2025-10-14 22:30:45 EDT"
    """
    if unix_timestamp is None:
        unix_timestamp = int(time.time())

    edt = pytz.timezone('America/New_York')
    dt = datetime.fromtimestamp(unix_timestamp, edt)
    return dt.strftime('%Y-%m-%d %H:%M:%S %Z')


def calculate_image_hash(image_bytes: bytes) -> str:
    """
    Calculate SHA256 hash of image bytes for deduplication.

    Args:
        image_bytes: Raw image bytes

    Returns:
        Hash string in format "sha256:abc123..."
    """
    hash_obj = hashlib.sha256(image_bytes)
    return f"sha256:{hash_obj.hexdigest()}"


def cache_image_data(
    dynamodb_client,
    image_url: str,
    image_bytes: bytes,
    embedding: List[float],
    analysis: Dict[str, Any],
    llm_response: str,
    embedding_model: str,
    analysis_model: str
) -> None:
    """
    Atomically cache all image data with complete metadata.

    This writes both embedding and analysis in a single operation to ensure
    data consistency and completeness.

    Args:
        dynamodb_client: Boto3 DynamoDB client
        image_url: URL of the image (primary key)
        image_bytes: Raw image bytes (for hash calculation)
        embedding: 1024-dim image embedding vector
        analysis: Parsed structured analysis from Claude
        llm_response: Raw LLM response text (for debugging)
        embedding_model: Model ID used for embedding
        analysis_model: Model ID used for analysis
    """
    try:
        # Calculate hash and timestamps
        img_hash = calculate_image_hash(image_bytes)
        utc_time = int(time.time())
        edt_time = get_edt_timestamp(utc_time)

        # Calculate costs
        cost_total = COST_IMAGE_EMBEDDING + COST_IMAGE_ANALYSIS

        # Single atomic write with all data
        item = {
            # Identity
            "image_url": {"S": image_url},
            "image_hash": {"S": img_hash},

            # Embedding data
            "embedding": {"S": json.dumps(embedding)},
            "embedding_model": {"S": embedding_model},
            "embedding_cached_at": {"N": str(utc_time)},
            "embedding_cached_at_edt": {"S": edt_time},

            # Analysis data
            "analysis": {"S": json.dumps(analysis)},
            "analysis_llm_response": {"S": llm_response},
            "analysis_model": {"S": analysis_model},
            "analysis_cached_at": {"N": str(utc_time)},
            "analysis_cached_at_edt": {"S": edt_time},

            # Metadata
            "cache_version": {"N": "1"},
            "first_seen": {"N": str(utc_time)},
            "last_accessed": {"N": str(utc_time)},
            "access_count": {"N": "0"},
            "image_size_bytes": {"N": str(len(image_bytes))},

            # Cost tracking
            "cost_embedding": {"N": str(COST_IMAGE_EMBEDDING)},
            "cost_analysis": {"N": str(COST_IMAGE_ANALYSIS)},
            "cost_total": {"N": str(cost_total)},
            "cost_saved": {"N": "0.0"}
        }

        dynamodb_client.put_item(
            TableName=VISION_CACHE_TABLE,
            Item=item
        )

        logger.debug(f"💾 Cached complete image data: {image_url[:60]}...")

    except Exception as e:
        logger.warning(f"Failed to cache image data for {image_url}: {e}")


def get_cached_image_data(
    dynamodb_client,
    image_url: str
) -> Optional[Tuple[List[float], Dict[str, Any], str]]:
    """
    Retrieve cached image embedding, analysis, and hash.

    Updates access tracking metrics (last_accessed, access_count, cost_saved).

    Args:
        dynamodb_client: Boto3 DynamoDB client
        image_url: URL of the image

    Returns:
        Tuple of (embedding, analysis, image_hash) if cached, None if not found
    """
    try:
        response = dynamodb_client.get_item(
            TableName=VISION_CACHE_TABLE,
            Key={"image_url": {"S": image_url}}
        )

        if "Item" not in response:
            return None

        item = response["Item"]

        # Validate required fields
        if "embedding" not in item or "analysis" not in item:
            logger.warning(f"Incomplete cache entry for {image_url}")
            return None

        # Parse embedding, analysis, and hash
        embedding = json.loads(item["embedding"]["S"])
        analysis = json.loads(item["analysis"]["S"])
        image_hash = item.get("image_hash", {}).get("S", "")  # Get hash if available

        # Update access tracking
        try:
            utc_time = int(time.time())
            access_count = int(item.get("access_count", {}).get("N", "0")) + 1
            cost_total = float(item.get("cost_total", {}).get("N", str(COST_IMAGE_EMBEDDING + COST_IMAGE_ANALYSIS)))
            cost_saved = access_count * cost_total

            dynamodb_client.update_item(
                TableName=VISION_CACHE_TABLE,
                Key={"image_url": {"S": image_url}},
                UpdateExpression="SET last_accessed = :now, access_count = :count, cost_saved = :saved",
                ExpressionAttributeValues={
                    ":now": {"N": str(utc_time)},
                    ":count": {"N": str(access_count)},
                    ":saved": {"N": str(cost_saved)}
                }
            )

            logger.debug(f"💾 Cache hit for {image_url[:60]}... (hit #{access_count}, saved ${cost_saved:.4f})")

        except Exception as e:
            logger.debug(f"Failed to update access metrics: {e}")

        return (embedding, analysis, image_hash)

    except Exception as e:
        logger.debug(f"Cache read failed for {image_url}: {e}")
        return None


def cache_text_embedding(
    dynamodb_client,
    text: str,
    embedding: List[float],
    model: str
) -> None:
    """
    Cache text embedding with metadata.

    Args:
        dynamodb_client: Boto3 DynamoDB client
        text: Input text that was embedded
        embedding: Embedding vector
        model: Model ID used
    """
    try:
        # Calculate hash as primary key
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()

        # Create composite key: text_hash + model_id
        # This ensures different models cache separately
        cache_key = f"{text_hash}#{model}"

        # Get timestamps
        utc_time = int(time.time())
        edt_time = get_edt_timestamp(utc_time)

        # Store sample of text for debugging (first 200 chars)
        text_sample = text[:200] if len(text) > 200 else text

        item = {
            "text_hash": {"S": cache_key},  # Composite key with model
            "text_sample": {"S": text_sample},
            "embedding": {"S": json.dumps(embedding)},
            "embedding_model": {"S": model},
            "cached_at": {"N": str(utc_time)},
            "cached_at_edt": {"S": edt_time},
            "access_count": {"N": "0"},
            "cost_saved": {"N": "0.0"}
        }

        dynamodb_client.put_item(
            TableName=TEXT_CACHE_TABLE,
            Item=item
        )

        logger.debug(f"💾 Cached text embedding ({model}): {text_sample[:40]}...")

    except Exception as e:
        logger.warning(f"Failed to cache text embedding: {e}")


def get_cached_text_embedding(
    dynamodb_client,
    text: str,
    model: str = None
) -> Optional[List[float]]:
    """
    Retrieve cached text embedding.

    Updates access tracking metrics.

    Args:
        dynamodb_client: Boto3 DynamoDB client
        text: Input text to look up
        model: Model ID to look up (if None, tries without model key for backward compatibility)

    Returns:
        Embedding vector if cached, None if not found
    """
    try:
        # Calculate hash
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()

        # Create composite key if model provided
        if model:
            cache_key = f"{text_hash}#{model}"
        else:
            cache_key = text_hash

        response = dynamodb_client.get_item(
            TableName=TEXT_CACHE_TABLE,
            Key={"text_hash": {"S": cache_key}}
        )

        if "Item" not in response:
            return None

        item = response["Item"]

        if "embedding" not in item:
            return None

        embedding = json.loads(item["embedding"]["S"])

        # Update access tracking
        try:
            access_count = int(item.get("access_count", {}).get("N", "0")) + 1
            cost_saved = access_count * COST_TEXT_EMBEDDING

            dynamodb_client.update_item(
                TableName=TEXT_CACHE_TABLE,
                Key={"text_hash": {"S": text_hash}},
                UpdateExpression="SET access_count = :count, cost_saved = :saved",
                ExpressionAttributeValues={
                    ":count": {"N": str(access_count)},
                    ":saved": {"N": str(cost_saved)}
                }
            )

            logger.debug(f"💾 Text cache hit (hit #{access_count}, saved ${cost_saved:.5f})")

        except Exception as e:
            logger.debug(f"Failed to update access metrics: {e}")

        return embedding

    except Exception as e:
        logger.debug(f"Text cache read failed: {e}")
        return None
