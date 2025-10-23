#!/usr/bin/env python3
"""
Compare Multi-Query Results
Focused analysis comparing multi_query=true vs multi_query=false for white homes queries.
"""

import boto3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from decimal import Decimal

# Initialize DynamoDB client
dynamodb = boto3.client('dynamodb', region_name='us-east-1')
TABLE_NAME = 'SearchQueryLogs'


def _dynamodb_to_python(obj: Any) -> Any:
    """Convert DynamoDB types to Python types."""
    if isinstance(obj, dict):
        if 'S' in obj:
            return obj['S']
        elif 'N' in obj:
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
            return {k: _dynamodb_to_python(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_dynamodb_to_python(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj


def get_searches_in_time_range(hours: int = 3) -> List[Dict]:
    """Fetch all searches from the last N hours."""
    threshold_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

    try:
        items = []
        last_evaluated_key = None

        while True:
            scan_kwargs = {
                'TableName': TABLE_NAME,
                'FilterExpression': '#ts >= :threshold',
                'ExpressionAttributeNames': {
                    '#ts': 'timestamp'
                },
                'ExpressionAttributeValues': {
                    ':threshold': {'N': str(threshold_time)}
                }
            }

            if last_evaluated_key:
                scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

            response = dynamodb.scan(**scan_kwargs)
            items.extend([_dynamodb_to_python(item) for item in response['Items']])

            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break

        items.sort(key=lambda x: x.get('timestamp', 0))
        return items

    except Exception as e:
        print(f"Error scanning DynamoDB: {e}")
        return []


def extract_top_zpids(search_log: Dict, top_n: int = 5) -> List[str]:
    """Extract top N zpids from search results."""
    results = search_log.get('results', [])
    zpids = []
    for result in results[:top_n]:
        zpid = result.get('zpid', '')
        zpids.append(str(zpid))
    return zpids


def main():
    """Main execution."""
    print("\n" + "="*100)
    print("MULTI-QUERY COMPARISON: White Homes Queries")
    print("="*100)

    # Fetch searches
    searches = get_searches_in_time_range(hours=3)

    # Filter for white homes queries
    white_home_searches = []
    for search in searches:
        query_text = search.get('query_text', '').lower()
        if 'white' in query_text and ('home' in query_text or 'house' in query_text):
            # Normalize query for grouping
            if 'granite' in query_text and ('wood' in query_text or 'hardwood' in query_text):
                white_home_searches.append(search)

    if not white_home_searches:
        print("No white homes queries found.")
        return

    # Split by multi_query mode
    multi_true = [s for s in white_home_searches if s.get('use_multi_query', False)]
    multi_false = [s for s in white_home_searches if not s.get('use_multi_query', False)]

    print(f"\nTotal white homes queries with granite & wood: {len(white_home_searches)}")
    print(f"  - multi_query=true:  {len(multi_true)}")
    print(f"  - multi_query=false: {len(multi_false)}")

    # Analyze multi_query=true
    print("\n" + "="*100)
    print("MULTI_QUERY=TRUE Timeline")
    print("="*100)

    bad_zpids_start = None
    good_zpids_before = None

    for i, search in enumerate(multi_true):
        timestamp = search.get('timestamp', 0)
        dt = datetime.fromtimestamp(timestamp / 1000)
        top_zpids = extract_top_zpids(search, 5)
        quality = search.get('result_quality_metrics', {})

        has_bad_zpids = '12778555' in top_zpids or '70592220' in top_zpids

        if has_bad_zpids:
            if bad_zpids_start is None:
                bad_zpids_start = dt
                print(f"\n🚨 DEGRADATION STARTED: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Query ID: {search.get('query_id')}")
                print(f"   First bad zpids: {', '.join(top_zpids)}")
                print(f"   Previous good zpids: {good_zpids_before}")
        else:
            if bad_zpids_start is not None:
                print(f"\n✅ RECOVERY: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Query ID: {search.get('query_id')}")
                print(f"   Good zpids: {', '.join(top_zpids)}")
                bad_zpids_start = None
            good_zpids_before = ', '.join(top_zpids)

    # Analyze multi_query=false
    print("\n" + "="*100)
    print("MULTI_QUERY=FALSE Timeline")
    print("="*100)

    bad_zpids_start = None
    good_zpids_before = None

    for i, search in enumerate(multi_false):
        timestamp = search.get('timestamp', 0)
        dt = datetime.fromtimestamp(timestamp / 1000)
        top_zpids = extract_top_zpids(search, 5)
        quality = search.get('result_quality_metrics', {})

        has_bad_zpids = '12778555' in top_zpids or '70592220' in top_zpids

        if has_bad_zpids:
            if bad_zpids_start is None:
                bad_zpids_start = dt
                print(f"\n🚨 DEGRADATION STARTED: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Query ID: {search.get('query_id')}")
                print(f"   First bad zpids: {', '.join(top_zpids)}")
                print(f"   Previous good zpids: {good_zpids_before}")
        else:
            if bad_zpids_start is not None:
                print(f"\n✅ RECOVERY: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Query ID: {search.get('query_id')}")
                print(f"   Good zpids: {', '.join(top_zpids)}")
                bad_zpids_start = None
            good_zpids_before = ', '.join(top_zpids)

    # Side-by-side comparison
    print("\n" + "="*100)
    print("SIDE-BY-SIDE COMPARISON")
    print("="*100)
    print(f"\n{'Timestamp':<20} | {'Multi=TRUE (top 5)':<50} | {'Multi=FALSE (top 5)':<50}")
    print("-" * 125)

    # Match searches by closest timestamps
    for search_true in multi_true[:20]:  # Limit to first 20 for readability
        ts_true = search_true.get('timestamp', 0)
        dt_true = datetime.fromtimestamp(ts_true / 1000)
        zpids_true = extract_top_zpids(search_true, 5)

        # Find closest multi_false search
        closest_false = None
        min_diff = float('inf')
        for search_false in multi_false:
            ts_false = search_false.get('timestamp', 0)
            diff = abs(ts_true - ts_false)
            if diff < min_diff:
                min_diff = diff
                closest_false = search_false

        zpids_false = extract_top_zpids(closest_false, 5) if closest_false else []

        # Color code if has bad zpids
        true_str = ', '.join(zpids_true[:3]) if zpids_true else 'N/A'
        false_str = ', '.join(zpids_false[:3]) if zpids_false else 'N/A'

        true_bad = '12778555' in zpids_true or '70592220' in zpids_true
        false_bad = '12778555' in zpids_false or '70592220' in zpids_false

        marker_true = '❌' if true_bad else '✅'
        marker_false = '❌' if false_bad else '✅'

        print(f"{dt_true.strftime('%H:%M:%S'):<20} | {marker_true} {true_str:<46} | {marker_false} {false_str:<46}")

    print("\n" + "="*100)


if __name__ == "__main__":
    main()
