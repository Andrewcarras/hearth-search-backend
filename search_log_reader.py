#!/usr/bin/env python3
"""
Search Log Reader
Helper functions for fetching and analyzing search logs from DynamoDB.
"""

import boto3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

# Initialize DynamoDB client
dynamodb = boto3.client('dynamodb', region_name='us-east-1')
TABLE_NAME = 'SearchQueryLogs'


# ==========================================
# DynamoDB Type Conversion
# ==========================================

def _dynamodb_to_python(obj: Any) -> Any:
    """
    Convert DynamoDB types to Python types.
    """
    if isinstance(obj, dict):
        if 'S' in obj:
            return obj['S']
        elif 'N' in obj:
            # Convert to float, then to int if it's a whole number
            val = float(obj['N'])
            return int(val) if val.is_integer() else val
        elif 'BOOL' in obj:
            return obj['BOOL']
        elif 'NULL' in obj:
            return None
        elif 'M' in obj:
            return {k: _dynamodb_to_python(v) for k, v in obj['M'].items()}
        elif 'L' in obj:
            return [_dynamodb_to_python(item) for item in obj['L']]
        elif 'SS' in obj:
            return set(obj['SS'])
        elif 'NS' in obj:
            return set(float(n) for n in obj['NS'])
        else:
            # Assume it's already a regular dict
            return {k: _dynamodb_to_python(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_dynamodb_to_python(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj


# ==========================================
# Fetch Functions
# ==========================================

def get_search_by_query_id(query_id: str) -> Optional[Dict]:
    """
    Fetch a search log by query_id.

    Args:
        query_id: The query_id to fetch

    Returns:
        Dictionary with search log data, or None if not found
    """
    try:
        response = dynamodb.scan(
            TableName=TABLE_NAME,
            FilterExpression='query_id = :qid',
            ExpressionAttributeValues={
                ':qid': {'S': query_id}
            },
            Limit=1
        )

        if response['Items']:
            return _dynamodb_to_python(response['Items'][0])
        return None
    except Exception as e:
        print(f"Error fetching search: {e}")
        return None


def get_recent_searches(limit: int = 10) -> List[Dict]:
    """
    Fetch the most recent searches.

    Args:
        limit: Maximum number of searches to return

    Returns:
        List of search log dictionaries, sorted by timestamp descending
    """
    try:
        response = dynamodb.scan(
            TableName=TABLE_NAME,
            Limit=limit * 2  # Scan more to account for potential filtering
        )

        items = [_dynamodb_to_python(item) for item in response['Items']]

        # Sort by timestamp descending
        items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        return items[:limit]
    except Exception as e:
        print(f"Error fetching recent searches: {e}")
        return []


def find_searches_by_text(query_text: str, limit: int = 10) -> List[Dict]:
    """
    Find searches matching the given query text (exact match).

    Args:
        query_text: The query text to search for
        limit: Maximum number of results

    Returns:
        List of matching search logs
    """
    try:
        response = dynamodb.scan(
            TableName=TABLE_NAME,
            FilterExpression='query_text = :qt',
            ExpressionAttributeValues={
                ':qt': {'S': query_text}
            },
            Limit=limit * 2
        )

        items = [_dynamodb_to_python(item) for item in response['Items']]

        # Sort by timestamp descending
        items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        return items[:limit]
    except Exception as e:
        print(f"Error finding searches: {e}")
        return []


def find_slow_searches(threshold_ms: float = 5000, limit: int = 10) -> List[Dict]:
    """
    Find searches that took longer than threshold.

    Args:
        threshold_ms: Minimum total time in milliseconds
        limit: Maximum number of results

    Returns:
        List of slow search logs, sorted by total_time_ms descending
    """
    try:
        response = dynamodb.scan(
            TableName=TABLE_NAME,
            FilterExpression='total_time_ms > :threshold',
            ExpressionAttributeValues={
                ':threshold': {'N': str(threshold_ms)}
            }
        )

        items = [_dynamodb_to_python(item) for item in response['Items']]

        # Sort by total_time_ms descending
        items.sort(key=lambda x: x.get('total_time_ms', 0), reverse=True)

        return items[:limit]
    except Exception as e:
        print(f"Error finding slow searches: {e}")
        return []


def find_searches_with_errors(limit: int = 10) -> List[Dict]:
    """
    Find searches that had errors.

    Args:
        limit: Maximum number of results

    Returns:
        List of search logs with errors
    """
    try:
        # DynamoDB doesn't support checking array length in filter expressions easily,
        # so we scan all and filter in Python
        response = dynamodb.scan(TableName=TABLE_NAME)

        items = [_dynamodb_to_python(item) for item in response['Items']]

        # Filter for items with errors
        items_with_errors = [
            item for item in items
            if item.get('errors') and len(item['errors']) > 0
        ]

        # Sort by timestamp descending
        items_with_errors.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        return items_with_errors[:limit]
    except Exception as e:
        print(f"Error finding searches with errors: {e}")
        return []


def find_poor_quality_searches(max_avg_score: float = 0.02, limit: int = 10) -> List[Dict]:
    """
    Find searches with poor quality results (low scores).

    Args:
        max_avg_score: Maximum average score to consider "poor quality"
        limit: Maximum number of results

    Returns:
        List of poor quality search logs
    """
    try:
        response = dynamodb.scan(TableName=TABLE_NAME)

        items = [_dynamodb_to_python(item) for item in response['Items']]

        # Filter for low quality
        poor_quality = [
            item for item in items
            if item.get('result_quality_metrics', {}).get('avg_score', 1.0) <= max_avg_score
        ]

        # Sort by avg_score ascending (worst first)
        poor_quality.sort(
            key=lambda x: x.get('result_quality_metrics', {}).get('avg_score', 1.0)
        )

        return poor_quality[:limit]
    except Exception as e:
        print(f"Error finding poor quality searches: {e}")
        return []


# ==========================================
# Analysis Functions
# ==========================================

def analyze_timing(search_log: Dict) -> Dict:
    """
    Analyze timing breakdown for a search.

    Args:
        search_log: Search log dictionary

    Returns:
        Dictionary with timing analysis
    """
    timing = search_log.get('timing', {})
    total_ms = timing.get('total_ms', 0)

    if total_ms == 0:
        return {"error": "No timing data available"}

    # Calculate percentages
    breakdown = {}
    for key, value in timing.items():
        if key != 'total_ms' and key != 'bedrock_embedding_calls':
            percentage = (value / total_ms) * 100
            breakdown[key] = {
                'ms': value,
                'percentage': round(percentage, 1)
            }

    # Sort by time descending
    sorted_breakdown = dict(
        sorted(breakdown.items(), key=lambda x: x[1]['ms'], reverse=True)
    )

    return {
        'total_ms': total_ms,
        'bedrock_calls': timing.get('bedrock_embedding_calls', 0),
        'breakdown': sorted_breakdown,
        'slowest_component': list(sorted_breakdown.keys())[0] if sorted_breakdown else None
    }


def analyze_result_quality(search_log: Dict) -> Dict:
    """
    Analyze result quality metrics.

    Args:
        search_log: Search log dictionary

    Returns:
        Dictionary with quality analysis
    """
    metrics = search_log.get('result_quality_metrics', {})
    overlap = search_log.get('result_overlap', {})
    counts = search_log.get('result_counts', {})

    total_results = counts.get('final_returned', 0)

    analysis = {
        'total_results': total_results,
        'avg_score': metrics.get('avg_score', 0),
        'score_variance': metrics.get('score_variance', 0),
        'feature_matching': {
            'avg_match_ratio': metrics.get('avg_feature_match_ratio', 0),
            'perfect_matches': metrics.get('perfect_matches', 0),
            'partial_matches': metrics.get('partial_matches', 0),
            'no_matches': metrics.get('no_matches', 0)
        },
        'strategy_overlap': {
            'bm25_text': overlap.get('bm25_text_overlap', 0),
            'bm25_image': overlap.get('bm25_image_overlap', 0),
            'text_image': overlap.get('text_image_overlap', 0),
            'all_three': overlap.get('all_three_overlap', 0)
        },
        'strategy_counts': {
            'bm25': counts.get('bm25_hits', 0),
            'text_knn': counts.get('knn_text_hits', 0),
            'image_knn': counts.get('knn_image_hits', 0),
            'fused': counts.get('rrf_fused', 0)
        }
    }

    # Add quality assessment
    if metrics.get('avg_score', 0) < 0.02:
        analysis['quality_assessment'] = 'POOR - Very low scores'
    elif metrics.get('avg_feature_match_ratio', 0) == 0 and search_log.get('extracted_constraints', {}).get('must_have'):
        analysis['quality_assessment'] = 'POOR - No feature matches'
    elif overlap.get('all_three_overlap', 0) == 0:
        analysis['quality_assessment'] = 'MODERATE - No consensus between strategies'
    else:
        analysis['quality_assessment'] = 'GOOD'

    return analysis


def get_performance_stats(limit: int = 100) -> Dict:
    """
    Calculate performance statistics across recent searches.

    Args:
        limit: Number of recent searches to analyze

    Returns:
        Dictionary with performance statistics
    """
    try:
        searches = get_recent_searches(limit)

        if not searches:
            return {"error": "No searches found"}

        timings = [s.get('total_time_ms', 0) for s in searches]
        timings.sort()

        n = len(timings)

        return {
            'sample_size': n,
            'min_ms': timings[0],
            'max_ms': timings[-1],
            'avg_ms': sum(timings) / n,
            'median_ms': timings[n // 2],
            'p95_ms': timings[int(n * 0.95)] if n > 20 else timings[-1],
            'p99_ms': timings[int(n * 0.99)] if n > 100 else timings[-1]
        }
    except Exception as e:
        return {"error": str(e)}


def compare_searches(query_id1: str, query_id2: str) -> Dict:
    """
    Compare two searches side by side.

    Args:
        query_id1: First query_id
        query_id2: Second query_id

    Returns:
        Dictionary with comparison data
    """
    search1 = get_search_by_query_id(query_id1)
    search2 = get_search_by_query_id(query_id2)

    if not search1 or not search2:
        return {"error": "One or both searches not found"}

    return {
        'search1': {
            'query_id': query_id1,
            'query_text': search1.get('query_text'),
            'total_ms': search1.get('total_time_ms'),
            'results_count': search1.get('result_counts', {}).get('final_returned'),
            'avg_score': search1.get('result_quality_metrics', {}).get('avg_score'),
            'errors': len(search1.get('errors', [])),
            'warnings': len(search1.get('warnings', []))
        },
        'search2': {
            'query_id': query_id2,
            'query_text': search2.get('query_text'),
            'total_ms': search2.get('total_time_ms'),
            'results_count': search2.get('result_counts', {}).get('final_returned'),
            'avg_score': search2.get('result_quality_metrics', {}).get('avg_score'),
            'errors': len(search2.get('errors', [])),
            'warnings': len(search2.get('warnings', []))
        },
        'differences': {
            'time_delta_ms': search2.get('total_time_ms', 0) - search1.get('total_time_ms', 0),
            'score_delta': search2.get('result_quality_metrics', {}).get('avg_score', 0) -
                          search1.get('result_quality_metrics', {}).get('avg_score', 0)
        }
    }


# ==========================================
# Pretty Print Functions
# ==========================================

def print_search_summary(search_log: Dict) -> None:
    """
    Print a human-readable summary of a search log.
    """
    print("\n" + "="*80)
    print(f"SEARCH LOG: {search_log.get('query_id', 'Unknown')}")
    print("="*80)

    # Basic info
    print(f"\nQuery: \"{search_log.get('query_text', 'N/A')}\"")
    print(f"Timestamp: {datetime.fromtimestamp(search_log.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total Time: {search_log.get('total_time_ms', 0):.2f} ms")

    # Parameters
    print(f"\nParameters:")
    print(f"  Index: {search_log.get('index', 'N/A')}")
    print(f"  Size: {search_log.get('size', 'N/A')}")
    print(f"  Strategy: {search_log.get('strategy', 'N/A')}")
    print(f"  Search Mode: {search_log.get('search_mode', 'N/A')}")
    print(f"  Boost Mode: {search_log.get('boost_mode', 'N/A')}")

    # Constraints
    constraints = search_log.get('extracted_constraints', {})
    print(f"\nExtracted Constraints:")
    print(f"  Must Have Tags: {constraints.get('must_have', [])}")
    print(f"  Architecture Style: {constraints.get('architecture_style', 'None')}")
    print(f"  Query Type: {constraints.get('query_type', 'general')}")

    # Timing analysis
    timing_analysis = analyze_timing(search_log)
    print(f"\nTiming Breakdown:")
    for component, data in timing_analysis.get('breakdown', {}).items():
        print(f"  {component:30s}: {data['ms']:8.2f} ms ({data['percentage']:5.1f}%)")
    print(f"  {'Bedrock API Calls':30s}: {timing_analysis.get('bedrock_calls', 0)}")

    # Quality analysis
    quality = analyze_result_quality(search_log)
    print(f"\nResult Quality: {quality.get('quality_assessment', 'N/A')}")
    print(f"  Total Results: {quality['total_results']}")
    print(f"  Avg Score: {quality['avg_score']:.6f}")
    print(f"  Score Variance: {quality['score_variance']:.8f}")

    # Feature matching
    fm = quality['feature_matching']
    print(f"\nFeature Matching:")
    print(f"  Perfect Matches: {fm['perfect_matches']}")
    print(f"  Partial Matches: {fm['partial_matches']}")
    print(f"  No Matches: {fm['no_matches']}")
    print(f"  Avg Match Ratio: {fm['avg_match_ratio']:.2%}")

    # Strategy overlap
    print(f"\nStrategy Overlap:")
    print(f"  BM25 ∩ Text kNN: {quality['strategy_overlap']['bm25_text']}")
    print(f"  BM25 ∩ Image kNN: {quality['strategy_overlap']['bm25_image']}")
    print(f"  Text ∩ Image kNN: {quality['strategy_overlap']['text_image']}")
    print(f"  All Three: {quality['strategy_overlap']['all_three']}")

    # Errors and warnings
    errors = search_log.get('errors', [])
    warnings = search_log.get('warnings', [])

    if errors:
        print(f"\n⚠️  ERRORS ({len(errors)}):")
        for err in errors:
            print(f"  - {err.get('component')}: {err.get('error_message')}")
            print(f"    Impact: {err.get('impact')}, Fallback: {err.get('fallback_used')}")

    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)}):")
        for warn in warnings:
            print(f"  - {warn.get('component')}: {warn.get('message')}")
            print(f"    Impact: {warn.get('impact')}")

    # Top results
    results = search_log.get('results', [])
    if results:
        print(f"\nTop 5 Results:")
        for i, result in enumerate(results[:5], 1):
            prop = result.get('property', {})
            zpid = result.get('zpid', 'N/A')
            score = result.get('score', 0)
            city = prop.get('city', 'N/A') if prop.get('city') else 'N/A'
            state = prop.get('state', 'N/A') if prop.get('state') else 'N/A'
            price = prop.get('price', 0) if prop.get('price') else 0
            beds = prop.get('bedrooms', 0) if prop.get('bedrooms') else 0
            baths = prop.get('bathrooms', 0) if prop.get('bathrooms') else 0

            print(f"  {i}. zpid={zpid} | score={score:.6f}")
            print(f"     {city}, {state} | ${price:,} | {beds}bd/{baths}ba")

    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    # Example usage
    print("Search Log Reader - Example Usage\n")

    # Get recent searches
    print("Fetching 5 most recent searches...")
    recent = get_recent_searches(5)
    print(f"Found {len(recent)} searches\n")

    if recent:
        # Analyze the most recent one
        print_search_summary(recent[0])

        # Get performance stats
        print("\nPerformance Statistics (last 100 searches):")
        stats = get_performance_stats(100)
        for key, value in stats.items():
            if key != 'error':
                print(f"  {key}: {value}")
