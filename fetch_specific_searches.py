#!/usr/bin/env python3
"""
Fetch specific search query IDs directly
"""

import boto3
import json
from datetime import datetime
from typing import Dict, Any
from decimal import Decimal

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('SearchQueryLogs')


def _convert_decimals(obj):
    """Convert Decimal types to native Python types."""
    if isinstance(obj, list):
        return [_convert_decimals(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj


def get_recent_searches_scan(limit=100):
    """Scan table for recent searches."""
    print(f"Scanning SearchQueryLogs table for last {limit} items...")

    response = table.scan(Limit=limit)
    items = response.get('Items', [])

    # Convert Decimals
    items = [_convert_decimals(item) for item in items]

    # Sort by timestamp descending
    items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    print(f"Found {len(items)} items\n")
    return items


def analyze_searches():
    """Analyze recent searches."""
    searches = get_recent_searches_scan(200)

    # Filter for white homes queries with granite and wood
    white_homes = []
    for search in searches:
        query_text = search.get('query_text', '').lower()
        if 'white' in query_text and ('granite' in query_text or 'wood' in query_text):
            white_homes.append(search)

    print(f"Found {len(white_homes)} white homes queries with granite/wood")

    # Split by multi_query
    multi_true = [s for s in white_homes if s.get('use_multi_query', False)]
    multi_false = [s for s in white_homes if not s.get('use_multi_query', False)]

    print(f"  multi_query=true: {len(multi_true)}")
    print(f"  multi_query=false: {len(multi_false)}")

    # Analyze multi_query=true
    print("\n" + "="*100)
    print("MULTI_QUERY=TRUE SEARCHES (Recent 30)")
    print("="*100)

    for i, search in enumerate(multi_true[:30], 1):
        timestamp = search.get('timestamp', 0)
        dt = datetime.fromtimestamp(timestamp / 1000)
        query_id = search.get('query_id', 'N/A')
        query_text = search.get('query_text', '')

        results = search.get('results', [])
        zpids = [str(r.get('zpid', '')) for r in results[:5]]

        quality = search.get('result_quality_metrics', {})
        avg_score = quality.get('avg_score', 0)

        has_bad = '12778555' in zpids or '70592220' in zpids
        marker = '❌' if has_bad else '✅'

        print(f"\n{i}. {marker} {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   ID: {query_id}")
        print(f"   Query: \"{query_text}\"")
        print(f"   Top 5: {', '.join(zpids)}")
        print(f"   Avg Score: {avg_score:.6f}")

        if has_bad:
            print(f"   ⚠️  BAD ZPIDS FOUND!")

    # Analyze multi_query=false
    print("\n" + "="*100)
    print("MULTI_QUERY=FALSE SEARCHES (Recent 20)")
    print("="*100)

    for i, search in enumerate(multi_false[:20], 1):
        timestamp = search.get('timestamp', 0)
        dt = datetime.fromtimestamp(timestamp / 1000)
        query_id = search.get('query_id', 'N/A')
        query_text = search.get('query_text', '')

        results = search.get('results', [])
        zpids = [str(r.get('zpid', '')) for r in results[:5]]

        quality = search.get('result_quality_metrics', {})
        avg_score = quality.get('avg_score', 0)

        has_bad = '12778555' in zpids or '70592220' in zpids
        marker = '❌' if has_bad else '✅'

        print(f"\n{i}. {marker} {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   ID: {query_id}")
        print(f"   Query: \"{query_text}\"")
        print(f"   Top 5: {', '.join(zpids)}")
        print(f"   Avg Score: {avg_score:.6f}")

        if has_bad:
            print(f"   ⚠️  BAD ZPIDS FOUND!")


def get_search_details(query_id):
    """Get detailed search info by query_id."""
    print(f"\nFetching search: {query_id}")

    # Scan to find the item
    response = table.scan(
        FilterExpression='query_id = :qid',
        ExpressionAttributeValues={':qid': query_id}
    )

    items = response.get('Items', [])
    if not items:
        print("  Not found!")
        return None

    search = _convert_decimals(items[0])

    timestamp = search.get('timestamp', 0)
    dt = datetime.fromtimestamp(timestamp / 1000)

    print(f"\n{'='*100}")
    print(f"SEARCH DETAILS: {query_id}")
    print(f"{'='*100}")
    print(f"\nTimestamp: {dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    print(f"Query: \"{search.get('query_text', 'N/A')}\"")
    print(f"Multi-Query: {search.get('use_multi_query', False)}")

    # Quality
    quality = search.get('result_quality_metrics', {})
    print(f"\nQuality:")
    print(f"  Avg Score: {quality.get('avg_score', 0):.6f}")
    print(f"  Perfect Matches: {quality.get('perfect_matches', 0)}")

    # Results
    results = search.get('results', [])
    print(f"\nTop 10 Results:")
    for i, result in enumerate(results[:10], 1):
        zpid = result.get('zpid', 'N/A')
        score = result.get('score', 0)
        marker = '⚠️ ' if str(zpid) in ['12778555', '70592220'] else ''
        print(f"  {marker}{i}. zpid={zpid}, score={score:.6f}")

    return search


if __name__ == "__main__":
    analyze_searches()

    # Get details on key searches
    print("\n" + "="*100)
    print("DETAILED ANALYSIS OF KEY SEARCHES")
    print("="*100)

    # These IDs from the first investigation
    key_ids = [
        "e8ed400e-3d6b-43be-9495-4ae566e60b6f",  # Last good before degradation
        "28ef18aa-a927-48df-9933-31f85d772ba4",  # First degraded
        "7bfee84d-c610-427c-903d-d5195eddf317",  # First recovered
    ]

    for qid in key_ids:
        get_search_details(qid)
