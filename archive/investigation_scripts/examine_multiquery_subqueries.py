#!/usr/bin/env python3
"""
Examine Multi-Query Sub-Queries
Detailed analysis of what sub-queries were generated during degradation.
"""

import boto3
import json
from datetime import datetime
from typing import Dict
from decimal import Decimal

# Initialize DynamoDB resource
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


def get_search_by_id(query_id: str) -> Dict:
    """Fetch search by query_id."""
    response = table.scan(
        FilterExpression='query_id = :qid',
        ExpressionAttributeValues={':qid': query_id}
    )

    items = response.get('Items', [])
    if not items:
        return None

    return _convert_decimals(items[0])


def print_multiquery_details(search: Dict, label: str):
    """Print detailed multi-query information."""
    print("\n" + "="*100)
    print(f"{label}")
    print("="*100)

    timestamp = search.get('timestamp', 0)
    dt = datetime.fromtimestamp(timestamp / 1000)

    print(f"\nTimestamp: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Query ID: {search.get('query_id')}")
    print(f"Query Text: \"{search.get('query_text')}\"")
    print(f"Multi-Query Enabled: {search.get('use_multi_query', False)}")

    # Multi-query status
    multi_status = search.get('multi_query_status', {})
    print(f"\nMulti-Query Status:")
    print(f"  Enabled: {multi_status.get('enabled', False)}")
    print(f"  Generated: {multi_status.get('generated', False)}")
    print(f"  Sub-query Count: {multi_status.get('sub_query_count', 0)}")

    # Sub-queries
    sub_queries = multi_status.get('sub_queries', [])
    if sub_queries:
        print(f"\nSub-Queries Generated:")
        for i, sq in enumerate(sub_queries, 1):
            print(f"\n  {i}. \"{sq.get('query_text', 'N/A')}\"")
            print(f"     Type: {sq.get('type', 'N/A')}")
            print(f"     Focus: {sq.get('focus', 'N/A')}")

    # Extracted constraints
    constraints = search.get('extracted_constraints', {})
    print(f"\nExtracted Constraints:")
    print(f"  Must-have features: {constraints.get('must_have', [])}")
    print(f"  Architecture style: {constraints.get('architecture_style', 'None')}")
    print(f"  Query type: {constraints.get('query_type', 'general')}")

    # Results
    results = search.get('results', [])
    print(f"\nTop 10 Results:")
    print(f"{'Rank':<6} {'ZPID':<12} {'Score':<10} {'Sources':<40}")
    print("-" * 100)

    for i, result in enumerate(results[:10], 1):
        zpid = str(result.get('zpid', 'N/A'))
        score = result.get('score', 0)

        # Sources
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
        marker = '⚠️  ' if zpid in ['12778555', '70592220'] else ''

        print(f"{marker}{i:<6} {zpid:<12} {score:<10.6f} {sources_str:<40}")

    # Quality metrics
    quality = search.get('result_quality_metrics', {})
    print(f"\nQuality Metrics:")
    print(f"  Avg Score: {quality.get('avg_score', 0):.6f}")
    print(f"  Perfect Matches: {quality.get('perfect_matches', 0)}")
    print(f"  Partial Matches: {quality.get('partial_matches', 0)}")
    print(f"  No Matches: {quality.get('no_matches', 0)}")

    # Result overlap
    overlap = search.get('result_overlap', {})
    if overlap:
        print(f"\nResult Overlap Between Sources:")
        print(f"  BM25 ∩ Text KNN: {overlap.get('bm25_text_overlap', 0)}")
        print(f"  BM25 ∩ Image KNN: {overlap.get('bm25_image_overlap', 0)}")
        print(f"  Text ∩ Image KNN: {overlap.get('text_image_overlap', 0)}")
        print(f"  All Three: {overlap.get('all_three_overlap', 0)}")


def main():
    """Main execution."""
    print("\n" + "="*100)
    print("MULTI-QUERY SUB-QUERY ANALYSIS")
    print("="*100)

    # Analyze key searches
    searches_to_analyze = [
        ("3ce8bc95-90d0-43a6-b5e8-ccda59ffb397", "EARLY DEGRADATION (21:07:06)"),
        ("8f05713a-965c-4fc2-ac51-38575983daad", "GOOD SEARCH BEFORE MAJOR DEGRADATION (21:37:13)"),
        ("31e68fba-4297-4e0e-bab7-c1c08f1d00e5", "MAJOR DEGRADATION START (23:36:03)"),
        ("cb535cbc-dbfc-4ae8-bf2a-8cad84c9f980", "MAJOR DEGRADATION END (23:52:05)"),
        ("8d048382-b4bd-46c4-812e-67e0ec8b7449", "RECOVERED (00:14:16)"),
    ]

    for query_id, label in searches_to_analyze:
        print(f"\nFetching {query_id}...")
        search = get_search_by_id(query_id)

        if search:
            print_multiquery_details(search, label)
        else:
            print(f"  ❌ Not found!")

    # Summary comparison
    print("\n" + "="*100)
    print("COMPARATIVE ANALYSIS")
    print("="*100)

    print("\nComparing sub-queries between good and degraded searches:")
    print("(This will help identify if degraded searches had problematic sub-query generation)")

    # Fetch and compare
    good_search = get_search_by_id("8f05713a-965c-4fc2-ac51-38575983daad")
    bad_search = get_search_by_id("31e68fba-4297-4e0e-bab7-c1c08f1d00e5")

    if good_search and bad_search:
        good_sqs = good_search.get('multi_query_status', {}).get('sub_queries', [])
        bad_sqs = bad_search.get('multi_query_status', {}).get('sub_queries', [])

        print(f"\nGood Search Sub-Queries ({len(good_sqs)}):")
        for i, sq in enumerate(good_sqs, 1):
            print(f"  {i}. \"{sq.get('query_text', 'N/A')}\"")

        print(f"\nDegraded Search Sub-Queries ({len(bad_sqs)}):")
        for i, sq in enumerate(bad_sqs, 1):
            print(f"  {i}. \"{sq.get('query_text', 'N/A')}\"")

        # Check for differences
        print("\n🔍 Looking for problematic patterns in degraded sub-queries:")
        for sq in bad_sqs:
            text = sq.get('query_text', '').lower()
            if 'brick' in text and 'white' not in text:
                print(f"  ⚠️  Found sub-query mentioning 'brick' without 'white': \"{sq.get('query_text')}\"")
            if 'red' in text or 'blue' in text:
                print(f"  ⚠️  Found sub-query mentioning wrong color: \"{sq.get('query_text')}\"")


if __name__ == "__main__":
    main()
