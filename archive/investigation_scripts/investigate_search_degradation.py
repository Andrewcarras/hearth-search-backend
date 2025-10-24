#!/usr/bin/env python3
"""
Investigate Search Quality Degradation
Analyzes DynamoDB SearchQueryLogs to find when search quality degraded.
"""

import boto3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from decimal import Decimal
from collections import defaultdict

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
    """
    Fetch all searches from the last N hours.

    Args:
        hours: Number of hours to look back

    Returns:
        List of search log dictionaries
    """
    # Calculate timestamp threshold (in milliseconds)
    threshold_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

    print(f"Scanning for searches since {datetime.fromtimestamp(threshold_time / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Threshold timestamp: {threshold_time}")

    try:
        # Scan with filter for recent searches
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

            print(f"  Scanned {len(items)} items so far...")

        # Sort by timestamp ascending
        items.sort(key=lambda x: x.get('timestamp', 0))

        print(f"Found {len(items)} total searches in last {hours} hours\n")
        return items

    except Exception as e:
        print(f"Error scanning DynamoDB: {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_top_zpids(search_log: Dict, top_n: int = 5) -> List[str]:
    """Extract top N zpids from search results."""
    results = search_log.get('results', [])
    zpids = []
    for result in results[:top_n]:
        zpid = result.get('zpid', '')
        zpids.append(str(zpid))
    return zpids


def analyze_white_homes_queries(searches: List[Dict]) -> None:
    """
    Analyze searches for 'white homes' or similar queries.
    Track when zpids changed and quality metrics.
    """
    print("="*100)
    print("ANALYSIS: White Homes Queries")
    print("="*100)

    # Filter for white homes queries (case insensitive)
    white_home_searches = []
    for search in searches:
        query_text = search.get('query_text', '').lower()
        if 'white' in query_text and ('home' in query_text or 'house' in query_text):
            white_home_searches.append(search)

    if not white_home_searches:
        print("No white homes queries found in the time range.")
        return

    print(f"Found {len(white_home_searches)} white homes queries\n")

    # Group by multi_query mode
    multi_true = [s for s in white_home_searches if s.get('use_multi_query', False)]
    multi_false = [s for s in white_home_searches if not s.get('use_multi_query', False)]

    print(f"  - multi_query=true: {len(multi_true)}")
    print(f"  - multi_query=false: {len(multi_false)}\n")

    # Analyze multi_query=true searches
    if multi_true:
        print("-" * 100)
        print("MULTI_QUERY=TRUE Searches:")
        print("-" * 100)
        analyze_search_group(multi_true, "multi_query=true")

    # Analyze multi_query=false searches
    if multi_false:
        print("-" * 100)
        print("MULTI_QUERY=FALSE Searches:")
        print("-" * 100)
        analyze_search_group(multi_false, "multi_query=false")

    # Compare quality over time
    print("\n" + "="*100)
    print("QUALITY DEGRADATION ANALYSIS")
    print("="*100)

    if multi_true:
        print("\nMulti-Query=TRUE Quality Over Time:")
        analyze_quality_over_time(multi_true)

    if multi_false:
        print("\nMulti-Query=FALSE Quality Over Time:")
        analyze_quality_over_time(multi_false)


def analyze_search_group(searches: List[Dict], group_name: str) -> None:
    """Analyze a group of searches."""

    # Track zpid changes
    previous_zpids = None

    for i, search in enumerate(searches):
        timestamp = search.get('timestamp', 0)
        dt = datetime.fromtimestamp(timestamp / 1000)
        query_text = search.get('query_text', '')
        query_id = search.get('query_id', 'unknown')

        top_zpids = extract_top_zpids(search, 5)

        # Quality metrics
        quality = search.get('result_quality_metrics', {})
        avg_score = quality.get('avg_score', 0)
        perfect_matches = quality.get('perfect_matches', 0)
        avg_match_ratio = quality.get('avg_feature_match_ratio', 0)

        # Constraints
        constraints = search.get('extracted_constraints', {})
        must_have = constraints.get('must_have', [])

        print(f"\n[{i+1}] {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"    Query: \"{query_text}\"")
        print(f"    Query ID: {query_id}")
        print(f"    Top 5 zpids: {', '.join(top_zpids)}")
        print(f"    Quality: avg_score={avg_score:.6f}, perfect_matches={perfect_matches}, avg_match_ratio={avg_match_ratio:.2f}")
        print(f"    Must-have features: {must_have}")

        # Check for problematic zpids
        if '12778555' in top_zpids or '70592220' in top_zpids:
            print(f"    ⚠️  DEGRADED: Found problematic zpids (12778555=red brick, 70592220=blue brick)")
            if '12778555' in top_zpids:
                print(f"        - zpid 12778555 (red brick) at position {top_zpids.index('12778555') + 1}")
            if '70592220' in top_zpids:
                print(f"        - zpid 70592220 (blue brick) at position {top_zpids.index('70592220') + 1}")

        # Detect changes
        if previous_zpids is not None:
            if top_zpids != previous_zpids:
                print(f"    🔄 CHANGE: zpids changed from previous search")
                added = set(top_zpids) - set(previous_zpids)
                removed = set(previous_zpids) - set(top_zpids)
                if added:
                    print(f"        Added: {', '.join(added)}")
                if removed:
                    print(f"        Removed: {', '.join(removed)}")

        previous_zpids = top_zpids


def analyze_quality_over_time(searches: List[Dict]) -> None:
    """Analyze quality metrics over time to find degradation point."""

    if not searches:
        return

    print("\nTimeline of Quality Metrics:")
    print("-" * 80)

    for i, search in enumerate(searches):
        timestamp = search.get('timestamp', 0)
        dt = datetime.fromtimestamp(timestamp / 1000)

        quality = search.get('result_quality_metrics', {})
        avg_score = quality.get('avg_score', 0)
        perfect_matches = quality.get('perfect_matches', 0)
        partial_matches = quality.get('partial_matches', 0)
        no_matches = quality.get('no_matches', 0)
        avg_match_ratio = quality.get('avg_feature_match_ratio', 0)

        top_zpids = extract_top_zpids(search, 5)
        has_bad_zpids = '12778555' in top_zpids or '70592220' in top_zpids

        status = "❌ POOR" if has_bad_zpids else "✅ GOOD"

        print(f"{dt.strftime('%H:%M:%S')} | {status} | score={avg_score:.4f} | "
              f"perfect={perfect_matches} | partial={partial_matches} | none={no_matches} | "
              f"match_ratio={avg_match_ratio:.2f}")

        if i == 0:
            print(f"         | First zpids: {', '.join(top_zpids[:3])}")

        if has_bad_zpids and (i == 0 or '12778555' not in extract_top_zpids(searches[i-1], 5)):
            print(f"         | ⚠️  DEGRADATION POINT: Bad zpids first appeared here")
            print(f"         | zpids: {', '.join(top_zpids)}")


def analyze_all_queries(searches: List[Dict]) -> None:
    """Analyze all queries to see overall patterns."""
    print("\n" + "="*100)
    print("ALL QUERIES SUMMARY")
    print("="*100)

    # Group by query text
    queries_by_text = defaultdict(list)
    for search in searches:
        query_text = search.get('query_text', 'unknown')
        queries_by_text[query_text].append(search)

    print(f"\nUnique queries: {len(queries_by_text)}")
    print("\nQuery frequency:")
    for query_text, searches_list in sorted(queries_by_text.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {len(searches_list):3d}x: \"{query_text}\"")

    # Check for deployment markers or events
    print("\n" + "="*100)
    print("SEARCHING FOR DEPLOYMENT EVENTS OR PATTERNS")
    print("="*100)

    # Look for gaps in time (might indicate deployments)
    for i in range(1, len(searches)):
        prev_time = searches[i-1].get('timestamp', 0)
        curr_time = searches[i].get('timestamp', 0)
        gap_minutes = (curr_time - prev_time) / 1000 / 60

        if gap_minutes > 10:  # More than 10 minute gap
            prev_dt = datetime.fromtimestamp(prev_time / 1000)
            curr_dt = datetime.fromtimestamp(curr_time / 1000)
            print(f"\n⏰ Large time gap detected:")
            print(f"   {prev_dt.strftime('%Y-%m-%d %H:%M:%S')} -> {curr_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Gap: {gap_minutes:.1f} minutes")
            print(f"   Possible deployment or system change?")


def main():
    """Main execution."""
    print("\n" + "="*100)
    print("SEARCH QUALITY DEGRADATION INVESTIGATION")
    print("="*100)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100 + "\n")

    # Fetch searches from last 3 hours
    searches = get_searches_in_time_range(hours=3)

    if not searches:
        print("No searches found in the last 3 hours.")
        return

    # Show time range
    first_time = datetime.fromtimestamp(searches[0].get('timestamp', 0) / 1000)
    last_time = datetime.fromtimestamp(searches[-1].get('timestamp', 0) / 1000)
    print(f"Time range: {first_time.strftime('%Y-%m-%d %H:%M:%S')} to {last_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Analyze white homes queries specifically
    analyze_white_homes_queries(searches)

    # Analyze all queries for patterns
    analyze_all_queries(searches)

    print("\n" + "="*100)
    print("INVESTIGATION COMPLETE")
    print("="*100)


if __name__ == "__main__":
    main()
