#!/usr/bin/env python3
"""
Detailed Degradation Analysis
Deep dive into the exact searches before, during, and after degradation.
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


def get_search_by_query_id(query_id: str) -> Dict:
    """Fetch a specific search by query_id."""
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


def print_detailed_search(search: Dict, label: str) -> None:
    """Print detailed information about a search."""
    print("\n" + "="*100)
    print(f"{label}")
    print("="*100)

    timestamp = search.get('timestamp', 0)
    dt = datetime.fromtimestamp(timestamp / 1000)

    print(f"\nTimestamp: {dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    print(f"Query ID: {search.get('query_id')}")
    print(f"Query Text: \"{search.get('query_text')}\"")
    print(f"Multi-Query: {search.get('use_multi_query', False)}")

    # Quality metrics
    quality = search.get('result_quality_metrics', {})
    print(f"\nQuality Metrics:")
    print(f"  Avg Score: {quality.get('avg_score', 0):.6f}")
    print(f"  Perfect Matches: {quality.get('perfect_matches', 0)}")
    print(f"  Partial Matches: {quality.get('partial_matches', 0)}")
    print(f"  No Matches: {quality.get('no_matches', 0)}")
    print(f"  Avg Feature Match Ratio: {quality.get('avg_feature_match_ratio', 0):.2f}")

    # Multi-query status
    multi_status = search.get('multi_query_status', {})
    if multi_status:
        print(f"\nMulti-Query Status:")
        print(f"  Enabled: {multi_status.get('enabled', False)}")
        print(f"  Generated: {multi_status.get('generated', False)}")
        print(f"  Sub-queries: {multi_status.get('sub_query_count', 0)}")
        if multi_status.get('sub_queries'):
            print(f"  Sub-query texts:")
            for sq in multi_status.get('sub_queries', []):
                print(f"    - \"{sq.get('query_text', 'N/A')}\"")

    # Results
    results = search.get('results', [])
    print(f"\nTop 10 Results:")
    print(f"{'Rank':<6} {'ZPID':<12} {'Score':<10} {'Match Ratio':<12} {'Sources':<30}")
    print("-" * 100)

    for i, result in enumerate(results[:10], 1):
        zpid = result.get('zpid', 'N/A')
        score = result.get('score', 0)
        feature_matches = result.get('feature_matches', {})
        match_ratio = feature_matches.get('match_ratio', 0)
        matched = feature_matches.get('matched', [])

        # Determine sources
        scoring = result.get('scoring', {})
        sources = []
        if scoring.get('bm25_rank') is not None:
            sources.append(f"BM25#{scoring.get('bm25_rank')}")
        if scoring.get('knn_text_rank') is not None:
            sources.append(f"Text#{scoring.get('knn_text_rank')}")
        if scoring.get('knn_image_rank') is not None:
            sources.append(f"Img#{scoring.get('knn_image_rank')}")

        sources_str = ', '.join(sources) if sources else 'None'

        # Mark bad zpids
        marker = '⚠️ ' if zpid in ['12778555', '70592220'] else ''

        print(f"{marker}{i:<6} {zpid:<12} {score:<10.6f} {match_ratio:<12.2f} {sources_str:<30}")

    # Timing
    timing = search.get('timing', {})
    if timing:
        print(f"\nTiming:")
        total_ms = timing.get('total_ms', 0)
        print(f"  Total: {total_ms:.2f} ms")
        print(f"  Bedrock calls: {timing.get('bedrock_embedding_calls', 0)}")


def main():
    """Main execution."""
    print("\n" + "="*100)
    print("DETAILED DEGRADATION ANALYSIS")
    print("="*100)

    # Key query IDs from the investigation
    print("\nAnalyzing key searches:")

    # Last good search before degradation (multi_query=true)
    last_good_id = "e8ed400e-3d6b-43be-9495-4ae566e60b6f"  # 22:35:48
    print(f"\n1. Fetching last good search: {last_good_id}")
    last_good = get_search_by_query_id(last_good_id)
    if last_good:
        print_detailed_search(last_good, "LAST GOOD SEARCH (Before Degradation)")

    # First degraded search (multi_query=true)
    first_bad_id = "28ef18aa-a927-48df-9933-31f85d772ba4"  # 23:29:51
    print(f"\n2. Fetching first degraded search: {first_bad_id}")
    first_bad = get_search_by_query_id(first_bad_id)
    if first_bad:
        print_detailed_search(first_bad, "FIRST DEGRADED SEARCH (Bad zpids appear)")

    # First recovered search (multi_query=true)
    first_recovery_id = "7bfee84d-c610-427c-903d-d5195eddf317"  # 00:10:44
    print(f"\n3. Fetching first recovered search: {first_recovery_id}")
    first_recovery = get_search_by_query_id(first_recovery_id)
    if first_recovery:
        print_detailed_search(first_recovery, "FIRST RECOVERED SEARCH (Good zpids return)")

    # Compare multi_query=false around same time
    multi_false_id = "74fd4bd1-6b27-4acd-b9f7-d05f6c5d0cf4"  # Around 23:30
    print(f"\n4. Fetching multi_query=false for comparison: {multi_false_id}")
    multi_false = get_search_by_query_id(multi_false_id)
    if multi_false:
        print_detailed_search(multi_false, "MULTI_QUERY=FALSE (Same Time as Degradation)")

    # Timeline summary
    print("\n" + "="*100)
    print("TIMELINE SUMMARY")
    print("="*100)

    if last_good and first_bad:
        last_good_time = datetime.fromtimestamp(last_good.get('timestamp', 0) / 1000)
        first_bad_time = datetime.fromtimestamp(first_bad.get('timestamp', 0) / 1000)
        time_gap = (first_bad.get('timestamp', 0) - last_good.get('timestamp', 0)) / 1000 / 60

        print(f"\nLast Good Search:  {last_good_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"First Bad Search:  {first_bad_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Time Gap:          {time_gap:.1f} minutes")

        print(f"\nLast Good Top 5:   {', '.join([r.get('zpid', '') for r in last_good.get('results', [])[:5]])}")
        print(f"First Bad Top 5:   {', '.join([r.get('zpid', '') for r in first_bad.get('results', [])[:5]])}")

    if first_bad and first_recovery:
        first_bad_time = datetime.fromtimestamp(first_bad.get('timestamp', 0) / 1000)
        recovery_time = datetime.fromtimestamp(first_recovery.get('timestamp', 0) / 1000)
        degraded_duration = (first_recovery.get('timestamp', 0) - first_bad.get('timestamp', 0)) / 1000 / 60

        print(f"\nDegradation Duration: {degraded_duration:.1f} minutes")
        print(f"From: {first_bad_time.strftime('%H:%M:%S')}")
        print(f"To:   {recovery_time.strftime('%H:%M:%S')}")

    print("\n" + "="*100)
    print("KEY FINDINGS")
    print("="*100)

    print("\n1. DEGRADATION POINT:")
    print("   - Time: 2025-10-22 23:29:51")
    print("   - Duration: Approximately 40.9 minutes")
    print("   - Affected: multi_query=true ONLY")
    print("   - Symptoms: zpids 12778555 (red brick) and 70592220 (blue brick) appeared in top 5")

    print("\n2. RECOVERY POINT:")
    print("   - Time: 2025-10-23 00:10:44")
    print("   - Good zpids returned")
    print("   - Quality scores improved")

    print("\n3. POSSIBLE CAUSES:")
    print("   - ~54 minute gap between last good (22:35:48) and first bad (23:29:51)")
    print("   - Suggests possible deployment or system change around 22:35-23:30")
    print("   - multi_query=false was NOT affected, suggesting issue in multi-query logic")

    print("\n" + "="*100)


if __name__ == "__main__":
    main()
