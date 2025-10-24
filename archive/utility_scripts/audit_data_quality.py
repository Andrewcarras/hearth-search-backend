#!/usr/bin/env python3
"""
Data Quality Audit Script for OpenSearch listings-v2 index

This script performs a comprehensive audit of the actual data in OpenSearch:
1. Embedding Quality - Check vector dimensions, zero vectors, etc.
2. Text Field Quality - Description completeness and usefulness
3. Tag Quality - Feature and image tag population
4. Metadata Completeness - Price, bedrooms, location data, etc.
5. Index Statistics - Document counts, field distributions

Usage:
    python audit_data_quality.py

Requirements:
    - AWS credentials configured
    - Access to OpenSearch domain
    - Environment variables: OS_HOST, OS_INDEX
"""

import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
OS_HOST = os.getenv("OS_HOST")
OS_INDEX = os.getenv("OS_INDEX", "listings-v2")
SAMPLE_SIZE = 50  # Number of documents to analyze in detail


def connect_opensearch():
    """Connect to OpenSearch with AWS auth."""
    if not OS_HOST:
        print("ERROR: OS_HOST environment variable not set")
        sys.exit(1)

    # Strip protocol if present
    host = OS_HOST.replace("https://", "").replace("http://", "")

    # Get AWS credentials
    session = boto3.Session(region_name=AWS_REGION)
    creds = session.get_credentials().get_frozen_credentials()

    awsauth = AWS4Auth(
        creds.access_key,
        creds.secret_key,
        AWS_REGION,
        "es",
        session_token=creds.token
    )

    client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60
    )

    return client


def get_index_stats(client: OpenSearch) -> Dict[str, Any]:
    """Get basic index statistics."""
    stats = client.indices.stats(index=OS_INDEX)
    count_result = client.count(index=OS_INDEX)

    return {
        "total_documents": count_result["count"],
        "index_size_bytes": stats["indices"][OS_INDEX]["total"]["store"]["size_in_bytes"],
        "index_size_mb": round(stats["indices"][OS_INDEX]["total"]["store"]["size_in_bytes"] / 1024 / 1024, 2)
    }


def analyze_embeddings(client: OpenSearch, sample_size: int = 50) -> Dict[str, Any]:
    """Analyze embedding quality across sample documents."""
    print("\n🔍 Analyzing Embedding Quality...")

    # Get sample of documents with embeddings
    query = {
        "size": sample_size,
        "query": {"match_all": {}},
        "_source": ["zpid", "vector_text", "image_vectors", "has_valid_embeddings"]
    }

    result = client.search(index=OS_INDEX, body=query)
    docs = result["hits"]["hits"]

    stats = {
        "total_sampled": len(docs),
        "has_text_vector": 0,
        "has_image_vectors": 0,
        "has_valid_embeddings_flag": 0,
        "text_vector_dim": None,
        "image_vector_dim": None,
        "zero_text_vectors": [],
        "zero_image_vectors": [],
        "missing_embeddings": [],
        "image_vector_counts": []
    }

    for hit in docs:
        doc = hit["_source"]
        zpid = doc.get("zpid", "unknown")

        # Check text vector
        text_vec = doc.get("vector_text")
        if text_vec:
            stats["has_text_vector"] += 1
            if stats["text_vector_dim"] is None:
                stats["text_vector_dim"] = len(text_vec)

            # Check if zero vector
            vec_sum = sum(abs(v) for v in text_vec)
            if vec_sum == 0.0:
                stats["zero_text_vectors"].append(zpid)

        # Check image vectors (multi-vector schema)
        image_vecs = doc.get("image_vectors", [])
        if image_vecs:
            stats["has_image_vectors"] += 1
            stats["image_vector_counts"].append(len(image_vecs))

            # Check first image vector dimension
            if stats["image_vector_dim"] is None and len(image_vecs) > 0:
                first_vec = image_vecs[0].get("vector", [])
                stats["image_vector_dim"] = len(first_vec)

            # Check for zero vectors
            for i, img_data in enumerate(image_vecs):
                vec = img_data.get("vector", [])
                if vec:
                    vec_sum = sum(abs(v) for v in vec)
                    if vec_sum == 0.0:
                        stats["zero_image_vectors"].append(f"{zpid}[{i}]")

        # Check has_valid_embeddings flag
        if doc.get("has_valid_embeddings"):
            stats["has_valid_embeddings_flag"] += 1

        # Check for documents with no embeddings at all
        if not text_vec and not image_vecs:
            stats["missing_embeddings"].append(zpid)

    # Calculate percentages
    stats["pct_has_text_vector"] = round(stats["has_text_vector"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0
    stats["pct_has_image_vectors"] = round(stats["has_image_vectors"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0
    stats["pct_has_valid_embeddings"] = round(stats["has_valid_embeddings_flag"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0

    # Image vector statistics
    if stats["image_vector_counts"]:
        stats["avg_image_vectors_per_doc"] = round(sum(stats["image_vector_counts"]) / len(stats["image_vector_counts"]), 1)
        stats["min_image_vectors"] = min(stats["image_vector_counts"])
        stats["max_image_vectors"] = max(stats["image_vector_counts"])

    return stats


def analyze_text_fields(client: OpenSearch, sample_size: int = 50) -> Dict[str, Any]:
    """Analyze text field quality."""
    print("\n📝 Analyzing Text Field Quality...")

    query = {
        "size": sample_size,
        "query": {"match_all": {}},
        "_source": ["zpid", "description", "visual_features_text", "llm_profile", "has_description"]
    }

    result = client.search(index=OS_INDEX, body=query)
    docs = result["hits"]["hits"]

    stats = {
        "total_sampled": len(docs),
        "has_description": 0,
        "has_visual_features": 0,
        "has_llm_profile": 0,
        "description_lengths": [],
        "visual_features_lengths": [],
        "short_descriptions": [],  # < 50 chars
        "missing_description": [],
        "examples": []
    }

    for hit in docs:
        doc = hit["_source"]
        zpid = doc.get("zpid", "unknown")

        # Description analysis
        desc = doc.get("description", "")
        if desc and desc.strip():
            stats["has_description"] += 1
            desc_len = len(desc)
            stats["description_lengths"].append(desc_len)

            if desc_len < 50:
                stats["short_descriptions"].append({
                    "zpid": zpid,
                    "length": desc_len,
                    "text": desc[:100]
                })
        else:
            stats["missing_description"].append(zpid)

        # Visual features text
        visual = doc.get("visual_features_text", "")
        if visual and visual.strip():
            stats["has_visual_features"] += 1
            stats["visual_features_lengths"].append(len(visual))

        # LLM profile (should be empty now)
        llm = doc.get("llm_profile", "")
        if llm and llm.strip():
            stats["has_llm_profile"] += 1

        # Collect examples
        if len(stats["examples"]) < 5:
            stats["examples"].append({
                "zpid": zpid,
                "description": desc[:150] if desc else None,
                "visual_features": visual[:150] if visual else None,
                "has_description_flag": doc.get("has_description")
            })

    # Calculate statistics
    stats["pct_has_description"] = round(stats["has_description"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0
    stats["pct_has_visual_features"] = round(stats["has_visual_features"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0
    stats["pct_has_llm_profile"] = round(stats["has_llm_profile"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0

    if stats["description_lengths"]:
        stats["avg_description_length"] = round(sum(stats["description_lengths"]) / len(stats["description_lengths"]), 1)
        stats["min_description_length"] = min(stats["description_lengths"])
        stats["max_description_length"] = max(stats["description_lengths"])

    if stats["visual_features_lengths"]:
        stats["avg_visual_features_length"] = round(sum(stats["visual_features_lengths"]) / len(stats["visual_features_lengths"]), 1)

    return stats


def analyze_tags(client: OpenSearch, sample_size: int = 100) -> Dict[str, Any]:
    """Analyze tag quality and consistency."""
    print("\n🏷️  Analyzing Tag Quality...")

    query = {
        "size": sample_size,
        "query": {"match_all": {}},
        "_source": ["zpid", "feature_tags", "image_tags", "architecture_style"]
    }

    result = client.search(index=OS_INDEX, body=query)
    docs = result["hits"]["hits"]

    stats = {
        "total_sampled": len(docs),
        "has_feature_tags": 0,
        "has_image_tags": 0,
        "has_architecture_style": 0,
        "feature_tag_counts": [],
        "image_tag_counts": [],
        "all_feature_tags": Counter(),
        "all_image_tags": Counter(),
        "architecture_styles": Counter(),
        "missing_tags": [],
        "tag_examples": []
    }

    for hit in docs:
        doc = hit["_source"]
        zpid = doc.get("zpid", "unknown")

        # Feature tags (should be empty now)
        feature_tags = doc.get("feature_tags", [])
        if feature_tags:
            stats["has_feature_tags"] += 1
            stats["feature_tag_counts"].append(len(feature_tags))
            stats["all_feature_tags"].update(feature_tags)

        # Image tags (from vision analysis)
        image_tags = doc.get("image_tags", [])
        if image_tags:
            stats["has_image_tags"] += 1
            stats["image_tag_counts"].append(len(image_tags))
            stats["all_image_tags"].update(image_tags)

        # Architecture style
        arch_style = doc.get("architecture_style")
        if arch_style:
            stats["has_architecture_style"] += 1
            stats["architecture_styles"][arch_style] += 1

        # Track documents with no tags at all
        if not feature_tags and not image_tags:
            stats["missing_tags"].append(zpid)

        # Collect examples
        if len(stats["tag_examples"]) < 5 and image_tags:
            stats["tag_examples"].append({
                "zpid": zpid,
                "feature_tags": feature_tags[:5],
                "image_tags": image_tags[:10],
                "architecture_style": arch_style
            })

    # Calculate percentages
    stats["pct_has_feature_tags"] = round(stats["has_feature_tags"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0
    stats["pct_has_image_tags"] = round(stats["has_image_tags"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0
    stats["pct_has_architecture_style"] = round(stats["has_architecture_style"] / stats["total_sampled"] * 100, 1) if stats["total_sampled"] > 0 else 0

    # Tag count statistics
    if stats["feature_tag_counts"]:
        stats["avg_feature_tags"] = round(sum(stats["feature_tag_counts"]) / len(stats["feature_tag_counts"]), 1)

    if stats["image_tag_counts"]:
        stats["avg_image_tags"] = round(sum(stats["image_tag_counts"]) / len(stats["image_tag_counts"]), 1)
        stats["min_image_tags"] = min(stats["image_tag_counts"])
        stats["max_image_tags"] = max(stats["image_tag_counts"])

    # Top tags
    stats["top_image_tags"] = dict(stats["all_image_tags"].most_common(20))
    stats["top_architecture_styles"] = dict(stats["architecture_styles"].most_common(10))

    return stats


def analyze_metadata(client: OpenSearch, sample_size: int = 100) -> Dict[str, Any]:
    """Analyze metadata completeness."""
    print("\n📊 Analyzing Metadata Completeness...")

    query = {
        "size": sample_size,
        "query": {"match_all": {}},
        "_source": [
            "zpid", "price", "bedrooms", "bathrooms", "livingArea",
            "address", "city", "state", "zip_code", "geo",
            "images", "status", "indexed_at"
        ]
    }

    result = client.search(index=OS_INDEX, body=query)
    docs = result["hits"]["hits"]

    stats = {
        "total_sampled": len(docs),
        "has_price": 0,
        "has_bedrooms": 0,
        "has_bathrooms": 0,
        "has_living_area": 0,
        "has_address": 0,
        "has_city": 0,
        "has_state": 0,
        "has_zip": 0,
        "has_geo": 0,
        "has_images": 0,
        "image_counts": [],
        "status_distribution": Counter(),
        "price_ranges": defaultdict(int),
        "bedroom_counts": Counter(),
        "missing_critical_data": []
    }

    for hit in docs:
        doc = hit["_source"]
        zpid = doc.get("zpid", "unknown")

        # Price
        price = doc.get("price")
        if price is not None and price > 0:
            stats["has_price"] += 1
            # Categorize price
            if price < 200000:
                stats["price_ranges"]["< $200k"] += 1
            elif price < 400000:
                stats["price_ranges"]["$200k-$400k"] += 1
            elif price < 600000:
                stats["price_ranges"]["$400k-$600k"] += 1
            elif price < 1000000:
                stats["price_ranges"]["$600k-$1M"] += 1
            else:
                stats["price_ranges"]["> $1M"] += 1

        # Bedrooms
        beds = doc.get("bedrooms")
        if beds is not None:
            stats["has_bedrooms"] += 1
            stats["bedroom_counts"][int(beds)] += 1

        # Bathrooms
        baths = doc.get("bathrooms")
        if baths is not None:
            stats["has_bathrooms"] += 1

        # Living area
        area = doc.get("livingArea")
        if area is not None and area > 0:
            stats["has_living_area"] += 1

        # Location data
        address = doc.get("address", {})
        if isinstance(address, dict):
            if address.get("streetAddress"):
                stats["has_address"] += 1
        elif address:
            stats["has_address"] += 1

        if doc.get("city"):
            stats["has_city"] += 1

        if doc.get("state"):
            stats["has_state"] += 1

        if doc.get("zip_code"):
            stats["has_zip"] += 1

        if doc.get("geo"):
            stats["has_geo"] += 1

        # Images
        images = doc.get("images", [])
        if images:
            stats["has_images"] += 1
            stats["image_counts"].append(len(images))

        # Status
        status = doc.get("status", "unknown")
        stats["status_distribution"][status] += 1

        # Check for missing critical data
        critical_missing = []
        if not price or price <= 0:
            critical_missing.append("price")
        if beds is None:
            critical_missing.append("bedrooms")
        if not doc.get("city"):
            critical_missing.append("city")
        if not images:
            critical_missing.append("images")

        if critical_missing:
            stats["missing_critical_data"].append({
                "zpid": zpid,
                "missing": critical_missing
            })

    # Calculate percentages
    if stats["total_sampled"] > 0:
        stats["pct_has_price"] = round(stats["has_price"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_bedrooms"] = round(stats["has_bedrooms"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_bathrooms"] = round(stats["has_bathrooms"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_living_area"] = round(stats["has_living_area"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_address"] = round(stats["has_address"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_city"] = round(stats["has_city"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_state"] = round(stats["has_state"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_zip"] = round(stats["has_zip"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_geo"] = round(stats["has_geo"] / stats["total_sampled"] * 100, 1)
        stats["pct_has_images"] = round(stats["has_images"] / stats["total_sampled"] * 100, 1)

    # Image statistics
    if stats["image_counts"]:
        stats["avg_images_per_listing"] = round(sum(stats["image_counts"]) / len(stats["image_counts"]), 1)
        stats["min_images"] = min(stats["image_counts"])
        stats["max_images"] = max(stats["image_counts"])

    return stats


def calculate_search_quality_score(embedding_stats, text_stats, tag_stats, metadata_stats) -> Dict[str, Any]:
    """Calculate overall data quality and search readiness scores."""
    print("\n🎯 Calculating Search Quality Scores...")

    # Embedding quality score (0-100)
    embedding_score = (
        embedding_stats["pct_has_valid_embeddings"] * 0.5 +
        (100 - len(embedding_stats["zero_text_vectors"]) / embedding_stats["total_sampled"] * 100 * 0.3) +
        (100 - len(embedding_stats["missing_embeddings"]) / embedding_stats["total_sampled"] * 100 * 0.2)
    )

    # Text quality score (0-100)
    text_score = (
        text_stats["pct_has_description"] * 0.4 +
        text_stats["pct_has_visual_features"] * 0.6
    )

    # Tag quality score (0-100)
    tag_score = (
        tag_stats["pct_has_image_tags"] * 0.7 +
        tag_stats["pct_has_architecture_style"] * 0.3
    )

    # Metadata quality score (0-100)
    metadata_score = (
        metadata_stats["pct_has_price"] * 0.25 +
        metadata_stats["pct_has_bedrooms"] * 0.15 +
        metadata_stats["pct_has_city"] * 0.15 +
        metadata_stats["pct_has_images"] * 0.25 +
        metadata_stats["pct_has_geo"] * 0.2
    )

    # Overall quality score (weighted average)
    overall_score = (
        embedding_score * 0.35 +
        text_score * 0.25 +
        tag_score * 0.20 +
        metadata_score * 0.20
    )

    # Calculate searchability percentage
    unsearchable_count = len(embedding_stats["missing_embeddings"])
    searchable_pct = (1 - unsearchable_count / embedding_stats["total_sampled"]) * 100 if embedding_stats["total_sampled"] > 0 else 0

    return {
        "embedding_quality": round(embedding_score, 1),
        "text_quality": round(text_score, 1),
        "tag_quality": round(tag_score, 1),
        "metadata_quality": round(metadata_score, 1),
        "overall_quality": round(overall_score, 1),
        "searchable_pct": round(searchable_pct, 1),
        "quality_grade": get_grade(overall_score)
    }


def get_grade(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


def print_report(index_stats, embedding_stats, text_stats, tag_stats, metadata_stats, quality_scores):
    """Print comprehensive audit report."""
    print("\n" + "="*80)
    print("📋 DATA QUALITY AUDIT REPORT")
    print("="*80)

    print(f"\n🔢 INDEX: {OS_INDEX}")
    print(f"   Total Documents: {index_stats['total_documents']:,}")
    print(f"   Index Size: {index_stats['index_size_mb']:.2f} MB")

    print("\n" + "="*80)
    print("🎯 OVERALL QUALITY SCORES")
    print("="*80)
    print(f"   Overall Quality: {quality_scores['overall_quality']}/100 (Grade: {quality_scores['quality_grade']})")
    print(f"   Searchable Documents: {quality_scores['searchable_pct']}%")
    print(f"\n   Component Scores:")
    print(f"   - Embedding Quality: {quality_scores['embedding_quality']}/100")
    print(f"   - Text Quality: {quality_scores['text_quality']}/100")
    print(f"   - Tag Quality: {quality_scores['tag_quality']}/100")
    print(f"   - Metadata Quality: {quality_scores['metadata_quality']}/100")

    print("\n" + "="*80)
    print("🔍 1. EMBEDDING QUALITY")
    print("="*80)
    print(f"   Sample Size: {embedding_stats['total_sampled']} documents")
    print(f"   Has Text Vector: {embedding_stats['pct_has_text_vector']}%")
    print(f"   Has Image Vectors: {embedding_stats['pct_has_image_vectors']}%")
    print(f"   Has Valid Embeddings Flag: {embedding_stats['pct_has_valid_embeddings']}%")
    print(f"\n   Vector Dimensions:")
    print(f"   - Text Vector: {embedding_stats['text_vector_dim']} dims")
    print(f"   - Image Vector: {embedding_stats['image_vector_dim']} dims")
    print(f"\n   Image Vectors per Document:")
    print(f"   - Average: {embedding_stats.get('avg_image_vectors_per_doc', 0)}")
    print(f"   - Range: {embedding_stats.get('min_image_vectors', 0)}-{embedding_stats.get('max_image_vectors', 0)}")

    if embedding_stats["zero_text_vectors"]:
        print(f"\n   ⚠️  Zero Text Vectors Found: {len(embedding_stats['zero_text_vectors'])}")
        print(f"       Examples: {embedding_stats['zero_text_vectors'][:5]}")

    if embedding_stats["zero_image_vectors"]:
        print(f"\n   ⚠️  Zero Image Vectors Found: {len(embedding_stats['zero_image_vectors'])}")
        print(f"       Examples: {embedding_stats['zero_image_vectors'][:5]}")

    if embedding_stats["missing_embeddings"]:
        print(f"\n   ❌ Missing ALL Embeddings: {len(embedding_stats['missing_embeddings'])}")
        print(f"       Examples: {embedding_stats['missing_embeddings'][:10]}")

    print("\n" + "="*80)
    print("📝 2. TEXT FIELD QUALITY")
    print("="*80)
    print(f"   Sample Size: {text_stats['total_sampled']} documents")
    print(f"   Has Description: {text_stats['pct_has_description']}%")
    print(f"   Has Visual Features Text: {text_stats['pct_has_visual_features']}%")
    print(f"   Has LLM Profile (deprecated): {text_stats['pct_has_llm_profile']}%")

    if text_stats.get("avg_description_length"):
        print(f"\n   Description Length Statistics:")
        print(f"   - Average: {text_stats['avg_description_length']} chars")
        print(f"   - Range: {text_stats['min_description_length']}-{text_stats['max_description_length']} chars")

    if text_stats.get("avg_visual_features_length"):
        print(f"\n   Visual Features Text Length:")
        print(f"   - Average: {text_stats['avg_visual_features_length']} chars")

    if text_stats["short_descriptions"]:
        print(f"\n   ⚠️  Short Descriptions (< 50 chars): {len(text_stats['short_descriptions'])}")
        for ex in text_stats["short_descriptions"][:3]:
            print(f"       - {ex['zpid']}: \"{ex['text']}\"")

    if text_stats["missing_description"]:
        print(f"\n   ⚠️  Missing Description: {len(text_stats['missing_description'])}")
        print(f"       Examples: {text_stats['missing_description'][:10]}")

    print(f"\n   Sample Documents:")
    for i, ex in enumerate(text_stats["examples"][:3], 1):
        print(f"\n   Example {i} - zpid: {ex['zpid']}")
        print(f"   Description: {ex['description'] or '(missing)'}...")
        print(f"   Visual Features: {ex['visual_features'] or '(missing)'}...")

    print("\n" + "="*80)
    print("🏷️  3. TAG QUALITY")
    print("="*80)
    print(f"   Sample Size: {tag_stats['total_sampled']} documents")
    print(f"   Has Feature Tags (deprecated): {tag_stats['pct_has_feature_tags']}%")
    print(f"   Has Image Tags: {tag_stats['pct_has_image_tags']}%")
    print(f"   Has Architecture Style: {tag_stats['pct_has_architecture_style']}%")

    if tag_stats.get("avg_image_tags"):
        print(f"\n   Image Tags per Document:")
        print(f"   - Average: {tag_stats['avg_image_tags']}")
        print(f"   - Range: {tag_stats['min_image_tags']}-{tag_stats['max_image_tags']}")

    if tag_stats["missing_tags"]:
        print(f"\n   ⚠️  Missing ALL Tags: {len(tag_stats['missing_tags'])}")
        print(f"       Examples: {tag_stats['missing_tags'][:10]}")

    print(f"\n   Top 20 Image Tags:")
    for tag, count in list(tag_stats["top_image_tags"].items())[:20]:
        print(f"   - {tag}: {count}")

    print(f"\n   Architecture Style Distribution:")
    for style, count in list(tag_stats["top_architecture_styles"].items())[:10]:
        print(f"   - {style}: {count}")

    print(f"\n   Sample Documents with Tags:")
    for i, ex in enumerate(tag_stats["tag_examples"][:3], 1):
        print(f"\n   Example {i} - zpid: {ex['zpid']}")
        print(f"   Image Tags ({len(ex['image_tags'])}): {ex['image_tags']}")
        print(f"   Architecture: {ex['architecture_style']}")

    print("\n" + "="*80)
    print("📊 4. METADATA COMPLETENESS")
    print("="*80)
    print(f"   Sample Size: {metadata_stats['total_sampled']} documents")
    print(f"\n   Field Completeness:")
    print(f"   - Price: {metadata_stats['pct_has_price']}%")
    print(f"   - Bedrooms: {metadata_stats['pct_has_bedrooms']}%")
    print(f"   - Bathrooms: {metadata_stats['pct_has_bathrooms']}%")
    print(f"   - Living Area: {metadata_stats['pct_has_living_area']}%")
    print(f"   - Address: {metadata_stats['pct_has_address']}%")
    print(f"   - City: {metadata_stats['pct_has_city']}%")
    print(f"   - State: {metadata_stats['pct_has_state']}%")
    print(f"   - Zip Code: {metadata_stats['pct_has_zip']}%")
    print(f"   - Geo Coordinates: {metadata_stats['pct_has_geo']}%")
    print(f"   - Images: {metadata_stats['pct_has_images']}%")

    if metadata_stats.get("avg_images_per_listing"):
        print(f"\n   Images per Listing:")
        print(f"   - Average: {metadata_stats['avg_images_per_listing']}")
        print(f"   - Range: {metadata_stats['min_images']}-{metadata_stats['max_images']}")

    print(f"\n   Status Distribution:")
    for status, count in metadata_stats["status_distribution"].items():
        pct = round(count / metadata_stats['total_sampled'] * 100, 1)
        print(f"   - {status}: {count} ({pct}%)")

    print(f"\n   Price Distribution:")
    for range_name, count in sorted(metadata_stats["price_ranges"].items()):
        pct = round(count / metadata_stats['has_price'] * 100, 1) if metadata_stats['has_price'] > 0 else 0
        print(f"   - {range_name}: {count} ({pct}%)")

    print(f"\n   Bedroom Distribution:")
    for beds, count in sorted(metadata_stats["bedroom_counts"].items()):
        pct = round(count / metadata_stats['total_sampled'] * 100, 1)
        print(f"   - {beds} beds: {count} ({pct}%)")

    if metadata_stats["missing_critical_data"]:
        print(f"\n   ⚠️  Documents Missing Critical Data: {len(metadata_stats['missing_critical_data'])}")
        for ex in metadata_stats["missing_critical_data"][:10]:
            print(f"       - {ex['zpid']}: missing {', '.join(ex['missing'])}")

    print("\n" + "="*80)
    print("💡 RECOMMENDATIONS")
    print("="*80)

    recommendations = []

    # Embedding recommendations
    if quality_scores['embedding_quality'] < 90:
        if embedding_stats["missing_embeddings"]:
            recommendations.append(f"⚠️  {len(embedding_stats['missing_embeddings'])} documents have NO embeddings - these are unsearchable!")
        if embedding_stats["zero_text_vectors"]:
            recommendations.append(f"⚠️  {len(embedding_stats['zero_text_vectors'])} documents have zero text vectors - need re-embedding")

    # Text recommendations
    if quality_scores['text_quality'] < 80:
        if text_stats['pct_has_visual_features'] < 70:
            recommendations.append(f"⚠️  Only {text_stats['pct_has_visual_features']}% have visual_features_text - impairs search quality")
        if text_stats['pct_has_description'] < 90:
            recommendations.append(f"⚠️  {100 - text_stats['pct_has_description']}% missing descriptions - generate fallback descriptions")

    # Tag recommendations
    if quality_scores['tag_quality'] < 80:
        if tag_stats['pct_has_image_tags'] < 80:
            recommendations.append(f"⚠️  Only {tag_stats['pct_has_image_tags']}% have image tags - re-run vision analysis")
        if tag_stats['pct_has_architecture_style'] < 50:
            recommendations.append(f"⚠️  Only {tag_stats['pct_has_architecture_style']}% have architecture style - may need better exterior images")

    # Metadata recommendations
    if quality_scores['metadata_quality'] < 90:
        if metadata_stats['pct_has_price'] < 95:
            recommendations.append(f"⚠️  {100 - metadata_stats['pct_has_price']}% missing price - these won't appear in price-filtered searches")
        if metadata_stats['pct_has_geo'] < 95:
            recommendations.append(f"⚠️  {100 - metadata_stats['pct_has_geo']}% missing geo coordinates - can't use location search")

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")
    else:
        print("✅ Data quality is excellent! No critical issues found.")

    print("\n" + "="*80)
    print("✅ AUDIT COMPLETE")
    print("="*80)


def main():
    """Main execution function."""
    print("🔍 Starting OpenSearch Data Quality Audit...")
    print(f"   Index: {OS_INDEX}")
    print(f"   Host: {OS_HOST}")
    print(f"   Sample Size: {SAMPLE_SIZE}")

    # Connect to OpenSearch
    client = connect_opensearch()
    print("✅ Connected to OpenSearch")

    # Run audits
    index_stats = get_index_stats(client)
    embedding_stats = analyze_embeddings(client, sample_size=SAMPLE_SIZE)
    text_stats = analyze_text_fields(client, sample_size=SAMPLE_SIZE)
    tag_stats = analyze_tags(client, sample_size=100)
    metadata_stats = analyze_metadata(client, sample_size=100)
    quality_scores = calculate_search_quality_score(embedding_stats, text_stats, tag_stats, metadata_stats)

    # Print report
    print_report(index_stats, embedding_stats, text_stats, tag_stats, metadata_stats, quality_scores)

    # Save to JSON file
    report_data = {
        "index": OS_INDEX,
        "audit_date": "2025-10-17",
        "index_stats": index_stats,
        "embedding_stats": {k: v for k, v in embedding_stats.items() if not isinstance(v, list) or len(v) < 20},
        "text_stats": {k: v for k, v in text_stats.items() if not isinstance(v, list) or len(v) < 20},
        "tag_stats": {k: v for k, v in tag_stats.items() if k in ["total_sampled", "pct_has_image_tags", "pct_has_architecture_style", "avg_image_tags", "top_image_tags", "top_architecture_styles"]},
        "metadata_stats": {k: v for k, v in metadata_stats.items() if not isinstance(v, list) or len(v) < 20},
        "quality_scores": quality_scores
    }

    output_file = f"data_quality_audit_{OS_INDEX}.json"
    with open(output_file, "w") as f:
        json.dump(report_data, f, indent=2)

    print(f"\n💾 Audit data saved to: {output_file}")


if __name__ == "__main__":
    main()
