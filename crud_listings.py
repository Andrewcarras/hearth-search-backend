"""
crud_listings.py - CRUD API for property listings

Provides Lambda handlers for manual listing management:

UPDATE (PATCH /listings/{zpid}):
- Modify any fields in existing listings
- Supports custom fields (dynamic schema)
- Optional field removal
- Preserves embeddings by default

CREATE (POST /listings):
- Add new listings with auto-generated zpid
- Optional image processing (embeddings + vision analysis)
- Quick-add mode (skip expensive processing)
- Supports both single-vector and multi-vector schemas

DELETE (DELETE /listings/{zpid}):
- Soft delete: Marks as deleted, keeps in index (default)
- Hard delete: Permanently removes from index
- Configurable via ?soft=true/false

These endpoints support the admin panel UI and future user-facing listing management.
All operations support index switching via ?index=listings-v2 query parameter.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import boto3

from common import (
    os_client, OS_INDEX, AWS_REGION,
    IMAGE_MODEL_ID, LLM_MODEL_ID,
    embed_text_multimodal, embed_image_bytes, detect_labels_with_response,
    vec_mean
)

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# AWS clients
s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)

# CORS headers for API Gateway
cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS"
}


# ===============================================
# UPDATE LISTING
# ===============================================

def update_listing_handler(event, context):
    """
    Update an existing listing.

    PATCH /listings/{zpid}
    Body: {
        "updates": {
            "price": 450000,
            "status": "sold",
            "custom_field": "any_value"
        },
        "options": {
            "preserve_embeddings": true,
            "remove_fields": ["field_to_delete"]
        }
    }

    Updates can include ANY field - completely flexible.
    New fields are automatically added to OpenSearch mapping.
    """
    logger.info("update_listing_handler invoked")

    # Extract zpid from path
    zpid = event.get("pathParameters", {}).get("zpid")
    if not zpid:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "Missing zpid in path"})
        }

    # Extract index from query parameters
    query_params = event.get("queryStringParameters") or {}
    target_index = query_params.get("index", OS_INDEX)

    # Parse request body
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", {})
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "Invalid JSON in request body"})
        }

    updates = body.get("updates", {})
    options = body.get("options", {})

    if not updates:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "No updates provided"})
        }

    logger.info(f"Updating zpid={zpid} with {len(updates)} fields in index={target_index}")

    try:
        # Fetch existing document
        response = os_client.get(index=target_index, id=str(zpid))

        if not response.get("found"):
            return {
                "statusCode": 404,
                "headers": cors_headers,
                "body": json.dumps({"error": f"Listing {zpid} not found"})
            }

        doc = response["_source"]

        # Apply updates
        for key, value in updates.items():
            doc[key] = value

        # Remove fields if requested
        remove_fields = options.get("remove_fields", [])
        for field in remove_fields:
            if field in doc:
                del doc[field]

        # Update timestamp
        doc["updated_at"] = int(time.time())

        # If preserve_embeddings=false, we'd regenerate here
        # For now, always preserve (regeneration is expensive)
        preserve_embeddings = options.get("preserve_embeddings", True)
        if not preserve_embeddings:
            logger.warning("Embedding regeneration not yet implemented")

        # Update in OpenSearch
        os_client.index(index=target_index, id=str(zpid), body=doc)

        logger.info(f"Successfully updated zpid={zpid}")

        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps({
                "ok": True,
                "zpid": zpid,
                "updated_fields": list(updates.keys()),
                "removed_fields": remove_fields
            })
        }

    except Exception as e:
        logger.error(f"Error updating listing {zpid}: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": str(e)})
        }


# ===============================================
# CREATE LISTING
# ===============================================

def add_listing_handler(event, context):
    """
    Add a new listing to the index.

    POST /listings
    Body: {
        "listing": {
            "zpid": "optional_custom_id",
            "price": 500000,
            "beds": 3,
            "address": "123 Main St",
            "images": ["url1", "url2"],
            ...any other fields...
        },
        "options": {
            "process_images": true,
            "generate_embeddings": true,
            "source": "user"
        }
    }

    If zpid not provided, generates UUID.
    Can process images for full analysis or quick-add without processing.
    """
    logger.info("add_listing_handler invoked")

    # Extract index from query parameters
    query_params = event.get("queryStringParameters") or {}
    target_index = query_params.get("index", OS_INDEX)

    # Parse request body
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", {})
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "Invalid JSON in request body"})
        }

    listing_data = body.get("listing", {})
    options = body.get("options", {})

    if not listing_data:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "No listing data provided"})
        }

    # Generate zpid if not provided
    zpid = listing_data.get("zpid")
    if not zpid:
        import uuid
        zpid = f"custom_{uuid.uuid4().hex[:12]}"
        listing_data["zpid"] = zpid

    logger.info(f"Adding new listing zpid={zpid} to index={target_index}")

    # Check if zpid already exists
    try:
        existing = os_client.get(index=target_index, id=str(zpid))
        if existing.get("found"):
            return {
                "statusCode": 409,
                "headers": cors_headers,
                "body": json.dumps({"error": f"Listing {zpid} already exists"})
            }
    except:
        pass  # Listing doesn't exist, continue

    # Build document
    doc = {
        **listing_data,
        "source": options.get("source", "user"),
        "created_at": int(time.time()),
        "indexed_at": int(time.time()),
        "status": listing_data.get("status", "active"),
        "searchable": True
    }

    process_images = options.get("process_images", False)
    generate_embeddings = options.get("generate_embeddings", True)

    processing_cost = 0.0

    try:
        # Generate text embedding if description provided
        if generate_embeddings and doc.get("description"):
            try:
                vec_text = embed_text_multimodal(doc["description"])
                if vec_text:
                    doc["vector_text"] = vec_text
                    processing_cost += 0.0001
            except Exception as e:
                logger.warning(f"Text embedding failed: {e}")

        # Process images if requested
        if process_images and doc.get("images"):
            try:
                image_urls = doc["images"]
                if not isinstance(image_urls, list):
                    image_urls = [image_urls]

                image_vecs = []
                image_vector_metadata = []  # For multi-vector schema
                img_tags = set()

                # Process up to 10 images (configurable limit to avoid timeout)
                for url in image_urls[:10]:
                    try:
                        # Import cache utilities
                        from cache_utils import get_cached_image_data, cache_image_data
                        import requests

                        img_vec = None
                        analysis = None
                        img_bytes = None

                        # Try to get from unified cache first
                        cached_data = get_cached_image_data(dynamodb, url)
                        if cached_data:
                            img_vec, analysis = cached_data
                            logger.debug(f"💾 Cache hit for image: {url[:60]}...")
                        else:
                            # Cache miss - download and process
                            logger.debug(f"📥 Downloading image (cache miss): {url[:60]}...")
                            resp = requests.get(url, timeout=8)
                            resp.raise_for_status()
                            img_bytes = resp.content

                            # Generate embedding
                            img_vec = embed_image_bytes(img_bytes)
                            processing_cost += 0.0008

                            # Run vision analysis with raw LLM response
                            analysis_result = detect_labels_with_response(img_bytes, image_url=url)
                            analysis = analysis_result["analysis"]
                            llm_response = analysis_result["llm_response"]
                            processing_cost += 0.00025

                            # Cache atomically in new unified cache
                            cache_image_data(
                                dynamodb,
                                image_url=url,
                                image_bytes=img_bytes,
                                embedding=img_vec,
                                analysis=analysis,
                                llm_response=llm_response,
                                embedding_model=IMAGE_MODEL_ID,
                                analysis_model=LLM_MODEL_ID
                            )

                        # Process analysis results
                        if img_vec:
                            image_vecs.append(img_vec)

                        if analysis:
                            for feature in analysis.get("features", []):
                                img_tags.add(feature)
                            for material in analysis.get("materials", []):
                                img_tags.add(material)
                            for visual_feature in analysis.get("visual_features", []):
                                img_tags.add(visual_feature)

                            # Store metadata for multi-vector schema
                            image_vector_metadata.append({
                                "image_url": url,
                                "image_type": analysis.get("image_type", "unknown"),
                                "vector": img_vec
                            })

                    except Exception as e:
                        logger.warning(f"Failed to process image {url}: {e}")

                # Detect schema and store vectors appropriately
                is_multi_vector = target_index.endswith("-v2")

                if is_multi_vector:
                    # Multi-vector schema: store all image vectors separately
                    if image_vector_metadata:
                        doc["image_vectors"] = image_vector_metadata
                        logger.info(f"Stored {len(image_vector_metadata)} image vectors (multi-vector schema)")
                else:
                    # Legacy schema: average image vectors
                    if image_vecs and vec_text:
                        vec_image = vec_mean(image_vecs, target_dim=len(vec_text))
                        doc["vector_image"] = vec_image

                # Add image tags
                if img_tags:
                    doc["image_tags"] = sorted(img_tags)

            except Exception as e:
                logger.warning(f"Image processing failed: {e}")

        # Index to OpenSearch
        os_client.index(index=target_index, id=str(zpid), body=doc)

        logger.info(f"Successfully added listing zpid={zpid}, cost=${processing_cost:.4f}")

        return {
            "statusCode": 201,
            "headers": cors_headers,
            "body": json.dumps({
                "ok": True,
                "zpid": zpid,
                "indexed": True,
                "processing_cost": processing_cost,
                "images_processed": len(image_vecs) if process_images else 0
            })
        }

    except Exception as e:
        logger.error(f"Error adding listing {zpid}: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": str(e)})
        }


# ===============================================
# DELETE LISTING
# ===============================================

def delete_listing_handler(event, context):
    """
    Delete a listing from the index.

    DELETE /listings/{zpid}?soft=true

    soft=true (default): Marks as deleted, keeps in index
    soft=false: Permanently removes from index
    """
    logger.info("delete_listing_handler invoked")

    # Extract zpid from path
    zpid = event.get("pathParameters", {}).get("zpid")
    if not zpid:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "Missing zpid in path"})
        }

    # Check query parameters
    query_params = event.get("queryStringParameters") or {}
    soft_delete = query_params.get("soft", "true").lower() == "true"
    target_index = query_params.get("index", OS_INDEX)

    logger.info(f"Deleting zpid={zpid}, soft={soft_delete}, index={target_index}")

    try:
        # Check if exists
        response = os_client.get(index=target_index, id=str(zpid))

        if not response.get("found"):
            return {
                "statusCode": 404,
                "headers": cors_headers,
                "body": json.dumps({"error": f"Listing {zpid} not found"})
            }

        if soft_delete:
            # Soft delete: mark as deleted, unsearchable
            doc = response["_source"]
            doc["status"] = "deleted"
            doc["searchable"] = False
            doc["deleted_at"] = int(time.time())

            os_client.index(index=target_index, id=str(zpid), body=doc)

            logger.info(f"Soft deleted zpid={zpid}")

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps({
                    "ok": True,
                    "zpid": zpid,
                    "deleted": True,
                    "soft_delete": True
                })
            }
        else:
            # Hard delete: remove from index
            os_client.delete(index=target_index, id=str(zpid))

            logger.info(f"Hard deleted zpid={zpid}")

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps({
                    "ok": True,
                    "zpid": zpid,
                    "deleted": True,
                    "soft_delete": False
                })
            }

    except Exception as e:
        logger.error(f"Error deleting listing {zpid}: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": str(e)})
        }
