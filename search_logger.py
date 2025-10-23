"""
search_logger.py - Comprehensive search query logging for quality analysis

Logs every search to DynamoDB and CloudWatch with complete context including:
- Request details (query, parameters, constraints)
- Performance metrics (timing breakdown by component)
- Results quality (feature matches, scoring details)
- Errors and warnings
"""

import json
import logging
import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional
from decimal import Decimal

import boto3

logger = logging.getLogger(__name__)

# DynamoDB client
dynamodb = boto3.client("dynamodb", region_name="us-east-1")
SEARCH_LOGS_TABLE = "SearchQueryLogs"


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types from DynamoDB"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def generate_query_id() -> str:
    """Generate unique query ID"""
    return str(uuid.uuid4())


def hash_query(query_text: str) -> str:
    """Generate deterministic hash for grouping similar queries"""
    return hashlib.md5(query_text.lower().strip().encode()).hexdigest()


def log_search_query(
    query_id: str,
    query_text: str,
    payload: dict,
    constraints: dict,
    timing_data: dict,
    results: list,
    result_counts: dict,
    result_overlap: dict,
    multi_query_data: Optional[dict],
    errors: list,
    warnings: list,
    total_time_ms: float
) -> None:
    """
    Log complete search query to DynamoDB and CloudWatch.

    Args:
        query_id: Unique identifier for this search
        query_text: The search query string
        payload: Complete request payload
        constraints: Extracted query constraints
        timing_data: Performance timing breakdown
        results: Search results (top 10 with scoring details)
        result_counts: Count of results from each source
        result_overlap: Overlap statistics between sources
        multi_query_data: Multi-query status and sub-queries
        errors: List of errors encountered
        warnings: List of warnings
        total_time_ms: Total execution time
    """
    timestamp = int(time.time() * 1000)  # Milliseconds
    query_hash = hash_query(query_text)

    # Build comprehensive log entry
    log_entry = {
        # Request context
        "query_id": query_id,
        "timestamp": timestamp,
        "query_hash": query_hash,
        "query_text": query_text,
        "query_length": len(query_text),

        # Search parameters
        "size": payload.get("size", 15),
        "index": payload.get("index", "listings-v2"),
        "boost_mode": payload.get("boost_mode", "standard"),
        "search_mode": payload.get("search_mode", "adaptive"),
        "strategy": payload.get("strategy", "hybrid"),
        "use_multi_query": payload.get("use_multi_query", False),

        # Query analysis
        "extracted_constraints": constraints,
        "multi_query_status": multi_query_data or {},

        # Performance metrics
        "timing": timing_data,
        "total_time_ms": total_time_ms,

        # Result counts
        "result_counts": result_counts,
        "result_overlap": result_overlap,

        # Results with quality metrics
        "results": _build_result_summary(results, constraints.get("must_have", [])),

        # Quality metrics
        "result_quality_metrics": _calculate_quality_metrics(results, constraints.get("must_have", [])),

        # Errors and warnings
        "errors": errors,
        "warnings": warnings,

        # TTL for auto-deletion (90 days)
        "expiration_time": int(time.time()) + (90 * 24 * 3600)
    }

    # Log to CloudWatch (structured JSON)
    logger.info(
        "SEARCH_COMPLETE",
        extra={
            "query_id": query_id,
            "query_text": query_text,
            "total_time_ms": total_time_ms,
            "result_count": len(results),
            "quality_score": log_entry["result_quality_metrics"]["avg_feature_match_ratio"],
            "errors": len(errors),
            "warnings": len(warnings)
        }
    )

    # Log to DynamoDB (for querying and analysis)
    try:
        _write_to_dynamodb(log_entry)
    except Exception as e:
        logger.error(f"Failed to write search log to DynamoDB: {e}")
        # Don't fail the search if logging fails


def _build_result_summary(results: list, required_features: list) -> list:
    """Build summarized result data for logging"""
    summaries = []

    for i, result in enumerate(results[:10]):  # Log top 10
        scoring = result.get("_scoring_details", {})
        # Results can have data in _source (from OpenSearch) or at root level (from handler)
        source = result.get("_source", result)

        # Count feature matches
        image_tags = set(source.get("image_tags", []))
        feature_tags = set(source.get("feature_tags", []))
        all_tags = image_tags.union(feature_tags)

        matched_features = []
        for feature in required_features:
            # Check both underscore and space versions
            if feature in all_tags or feature.replace("_", " ") in all_tags:
                matched_features.append(feature)

        match_ratio = len(matched_features) / len(required_features) if required_features else 1.0

        summaries.append({
            "rank": i + 1,
            "zpid": str(source.get("zpid", "")),
            "score": float(result.get("score", 0)),

            # Feature matching
            "feature_matches": {
                "matched": matched_features,
                "total_required": len(required_features),
                "match_ratio": round(match_ratio, 2)
            },

            # Scoring breakdown
            "scoring": {
                "bm25_rank": scoring.get("bm25", {}).get("rank"),
                "bm25_score": scoring.get("bm25", {}).get("original_score"),
                "bm25_contribution": scoring.get("bm25", {}).get("rrf_contribution", 0),
                "knn_text_rank": scoring.get("knn_text", {}).get("rank"),
                "knn_text_contribution": scoring.get("knn_text", {}).get("rrf_contribution", 0),
                "knn_image_rank": scoring.get("knn_image", {}).get("rank"),
                "knn_image_contribution": scoring.get("knn_image", {}).get("rrf_contribution", 0),
                "rrf_total": scoring.get("rrf_total", 0),
                "tag_boost": scoring.get("tag_boosting", {}).get("boost_factor", 1.0)
            },

            # Property details
            "property": {
                "price": source.get("price"),
                "bedrooms": source.get("bedrooms"),
                "bathrooms": source.get("bathrooms"),
                "city": source.get("city"),
                "state": source.get("state"),
                "description_length": len(source.get("description", "")),
                "image_count": len(source.get("image_vectors", [])),
                "feature_tag_count": len(source.get("feature_tags", [])),
                "image_tag_count": len(source.get("image_tags", []))
            }
        })

    return summaries


def _calculate_quality_metrics(results: list, required_features: list) -> dict:
    """Calculate quality metrics for search results"""
    if not results:
        return {
            "avg_score": 0,
            "score_variance": 0,
            "avg_feature_match_ratio": 0,
            "perfect_matches": 0,
            "partial_matches": 0,
            "no_matches": 0,
            "source_distribution": {
                "bm25_only": 0,
                "knn_text_only": 0,
                "knn_image_only": 0,
                "multiple_sources": 0
            }
        }

    scores = []
    match_ratios = []
    perfect = 0
    partial = 0
    no_match = 0

    bm25_only = 0
    knn_text_only = 0
    knn_image_only = 0
    multiple = 0

    for result in results[:10]:
        score = result.get("score", 0)
        scores.append(score)

        # Calculate feature match ratio
        source = result.get("_source", {})
        image_tags = set(source.get("image_tags", []))
        feature_tags = set(source.get("feature_tags", []))
        all_tags = image_tags.union(feature_tags)

        matched = 0
        for feature in required_features:
            if feature in all_tags or feature.replace("_", " ") in all_tags:
                matched += 1

        match_ratio = matched / len(required_features) if required_features else 1.0
        match_ratios.append(match_ratio)

        if match_ratio == 1.0:
            perfect += 1
        elif match_ratio > 0:
            partial += 1
        else:
            no_match += 1

        # Source distribution
        scoring = result.get("_scoring_details", {})
        sources_present = 0
        if scoring.get("bm25", {}).get("rank") is not None:
            sources_present += 1
        if scoring.get("knn_text", {}).get("rank") is not None:
            sources_present += 1
        if scoring.get("knn_image", {}).get("rank") is not None:
            sources_present += 1

        if sources_present > 1:
            multiple += 1
        elif scoring.get("bm25", {}).get("rank") is not None:
            bm25_only += 1
        elif scoring.get("knn_text", {}).get("rank") is not None:
            knn_text_only += 1
        elif scoring.get("knn_image", {}).get("rank") is not None:
            knn_image_only += 1

    avg_score = sum(scores) / len(scores)
    score_variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
    avg_match_ratio = sum(match_ratios) / len(match_ratios) if match_ratios else 0

    return {
        "avg_score": round(avg_score, 4),
        "score_variance": round(score_variance, 6),
        "avg_feature_match_ratio": round(avg_match_ratio, 2),
        "perfect_matches": perfect,
        "partial_matches": partial,
        "no_matches": no_match,
        "source_distribution": {
            "bm25_only": bm25_only,
            "knn_text_only": knn_text_only,
            "knn_image_only": knn_image_only,
            "multiple_sources": multiple
        }
    }


def _write_to_dynamodb(log_entry: dict) -> None:
    """Write log entry to DynamoDB"""
    # Convert to DynamoDB format
    item = {}
    for key, value in log_entry.items():
        item[key] = _python_to_dynamodb(value)

    dynamodb.put_item(
        TableName=SEARCH_LOGS_TABLE,
        Item=item
    )


def _python_to_dynamodb(value):
    """Convert Python value to DynamoDB format"""
    if value is None:
        return {"NULL": True}
    elif isinstance(value, bool):
        return {"BOOL": value}
    elif isinstance(value, (int, float)):
        return {"N": str(value)}
    elif isinstance(value, str):
        return {"S": value}
    elif isinstance(value, list):
        if not value:
            return {"L": []}
        return {"L": [_python_to_dynamodb(item) for item in value]}
    elif isinstance(value, dict):
        return {"M": {k: _python_to_dynamodb(v) for k, v in value.items()}}
    else:
        return {"S": str(value)}
