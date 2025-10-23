#!/usr/bin/env python3
"""
Search Analysis CLI Tool
Interactive tool for analyzing search logs from DynamoDB.

Usage:
    python analyze_search.py --query-id abc-123-def
    python analyze_search.py --text "White houses with granite"
    python analyze_search.py --recent 10
    python analyze_search.py --slow --threshold 5000
    python analyze_search.py --errors
    python analyze_search.py --poor-quality
    python analyze_search.py --stats
    python analyze_search.py --compare query-id-1 query-id-2
"""

import argparse
import sys
from search_log_reader import (
    get_search_by_query_id,
    get_recent_searches,
    find_searches_by_text,
    find_slow_searches,
    find_searches_with_errors,
    find_poor_quality_searches,
    get_performance_stats,
    compare_searches,
    print_search_summary,
    analyze_timing,
    analyze_result_quality
)


def cmd_query_id(args):
    """Analyze search by query_id."""
    print(f"Fetching search with query_id: {args.query_id}")
    search = get_search_by_query_id(args.query_id)

    if not search:
        print(f"❌ Search not found: {args.query_id}")
        sys.exit(1)

    print_search_summary(search)


def cmd_text(args):
    """Find searches by query text."""
    print(f"Searching for queries matching: \"{args.text}\"")
    searches = find_searches_by_text(args.text, limit=args.limit)

    if not searches:
        print(f"❌ No searches found matching: \"{args.text}\"")
        sys.exit(1)

    print(f"\nFound {len(searches)} matching searches:\n")

    for i, search in enumerate(searches, 1):
        print(f"{i}. query_id: {search.get('query_id')}")
        print(f"   Time: {search.get('total_time_ms', 0):.2f} ms")
        print(f"   Results: {search.get('result_counts', {}).get('final_returned', 0)}")
        print(f"   Avg Score: {search.get('result_quality_metrics', {}).get('avg_score', 0):.6f}")
        print()

    # Show details of most recent one
    if args.details:
        print("\nMost recent search details:")
        print_search_summary(searches[0])


def cmd_recent(args):
    """Show recent searches."""
    print(f"Fetching {args.limit} most recent searches...")
    searches = get_recent_searches(args.limit)

    if not searches:
        print("❌ No searches found")
        sys.exit(1)

    print(f"\nRecent Searches ({len(searches)}):\n")

    for i, search in enumerate(searches, 1):
        from datetime import datetime
        timestamp = datetime.fromtimestamp(search.get('timestamp', 0) / 1000)

        print(f"{i}. \"{search.get('query_text', 'N/A')}\"")
        print(f"   ID: {search.get('query_id')}")
        print(f"   Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Duration: {search.get('total_time_ms', 0):.2f} ms")
        print(f"   Results: {search.get('result_counts', {}).get('final_returned', 0)}")
        print(f"   Avg Score: {search.get('result_quality_metrics', {}).get('avg_score', 0):.6f}")

        errors = search.get('errors', [])
        warnings = search.get('warnings', [])
        if errors:
            print(f"   ⚠️  Errors: {len(errors)}")
        if warnings:
            print(f"   ⚠️  Warnings: {len(warnings)}")

        print()

    # Show details of most recent one if requested
    if args.details and searches:
        print("\nMost recent search details:")
        print_search_summary(searches[0])


def cmd_slow(args):
    """Find slow searches."""
    print(f"Finding searches slower than {args.threshold} ms...")
    searches = find_slow_searches(args.threshold, args.limit)

    if not searches:
        print(f"❌ No searches found slower than {args.threshold} ms")
        return

    print(f"\nSlow Searches (>{args.threshold} ms):\n")

    for i, search in enumerate(searches, 1):
        print(f"{i}. \"{search.get('query_text', 'N/A')}\"")
        print(f"   ID: {search.get('query_id')}")
        print(f"   Total Time: {search.get('total_time_ms', 0):.2f} ms")

        # Show timing breakdown
        timing_analysis = analyze_timing(search)
        slowest = timing_analysis.get('slowest_component')
        if slowest:
            slowest_data = timing_analysis['breakdown'][slowest]
            print(f"   Slowest: {slowest} ({slowest_data['ms']:.2f} ms, {slowest_data['percentage']:.1f}%)")

        print()

    if args.details and searches:
        print("\nSlowest search details:")
        print_search_summary(searches[0])


def cmd_errors(args):
    """Find searches with errors."""
    print(f"Finding searches with errors...")
    searches = find_searches_with_errors(args.limit)

    if not searches:
        print("✅ No searches with errors found")
        return

    print(f"\nSearches with Errors ({len(searches)}):\n")

    for i, search in enumerate(searches, 1):
        errors = search.get('errors', [])
        print(f"{i}. \"{search.get('query_text', 'N/A')}\"")
        print(f"   ID: {search.get('query_id')}")
        print(f"   Errors: {len(errors)}")

        for err in errors:
            print(f"     - {err.get('component')}: {err.get('error_type')}")
            print(f"       {err.get('error_message')}")
            print(f"       Impact: {err.get('impact')}, Fallback: {err.get('fallback_used')}")

        print()

    if args.details and searches:
        print("\nFirst search with errors - full details:")
        print_search_summary(searches[0])


def cmd_poor_quality(args):
    """Find poor quality searches."""
    print(f"Finding searches with avg_score < {args.threshold}...")
    searches = find_poor_quality_searches(args.threshold, args.limit)

    if not searches:
        print(f"✅ No searches found with avg_score < {args.threshold}")
        return

    print(f"\nPoor Quality Searches (avg_score < {args.threshold}):\n")

    for i, search in enumerate(searches, 1):
        quality = analyze_result_quality(search)

        print(f"{i}. \"{search.get('query_text', 'N/A')}\"")
        print(f"   ID: {search.get('query_id')}")
        print(f"   Avg Score: {quality['avg_score']:.6f}")
        print(f"   Quality: {quality['quality_assessment']}")

        # Show why it's poor quality
        if quality['feature_matching']['avg_match_ratio'] == 0:
            must_have = search.get('extracted_constraints', {}).get('must_have', [])
            if must_have:
                print(f"   Issue: No feature matches (wanted: {must_have})")

        if quality['strategy_overlap']['all_three'] == 0:
            print(f"   Issue: No consensus between BM25/text/image strategies")

        print()

    if args.details and searches:
        print("\nWorst quality search - full details:")
        print_search_summary(searches[0])


def cmd_stats(args):
    """Show performance statistics."""
    print(f"Calculating performance statistics (last {args.limit} searches)...\n")
    stats = get_performance_stats(args.limit)

    if 'error' in stats:
        print(f"❌ Error: {stats['error']}")
        sys.exit(1)

    print("Performance Statistics:")
    print("="*50)
    print(f"Sample Size:   {stats['sample_size']} searches")
    print(f"Min Time:      {stats['min_ms']:.2f} ms")
    print(f"Max Time:      {stats['max_ms']:.2f} ms")
    print(f"Average:       {stats['avg_ms']:.2f} ms")
    print(f"Median:        {stats['median_ms']:.2f} ms")
    print(f"95th %ile:     {stats['p95_ms']:.2f} ms")
    print(f"99th %ile:     {stats['p99_ms']:.2f} ms")
    print("="*50)


def cmd_compare(args):
    """Compare two searches."""
    print(f"Comparing searches:")
    print(f"  1. {args.query_id1}")
    print(f"  2. {args.query_id2}\n")

    comparison = compare_searches(args.query_id1, args.query_id2)

    if 'error' in comparison:
        print(f"❌ Error: {comparison['error']}")
        sys.exit(1)

    s1 = comparison['search1']
    s2 = comparison['search2']
    diff = comparison['differences']

    print("="*80)
    print(f"{'Metric':<30} {'Search 1':<25} {'Search 2':<25}")
    print("="*80)
    print(f"{'Query Text':<30} {s1['query_text'][:22]:<25} {s2['query_text'][:22]:<25}")
    print(f"{'Total Time (ms)':<30} {s1['total_ms']:<25.2f} {s2['total_ms']:<25.2f}")
    print(f"{'Results Count':<30} {s1['results_count']:<25} {s2['results_count']:<25}")
    print(f"{'Avg Score':<30} {s1['avg_score']:<25.6f} {s2['avg_score']:<25.6f}")
    print(f"{'Errors':<30} {s1['errors']:<25} {s2['errors']:<25}")
    print(f"{'Warnings':<30} {s1['warnings']:<25} {s2['warnings']:<25}")
    print("="*80)

    print(f"\nDifferences (Search 2 - Search 1):")
    print(f"  Time Delta: {diff['time_delta_ms']:+.2f} ms")
    print(f"  Score Delta: {diff['score_delta']:+.6f}")

    if abs(diff['time_delta_ms']) > 1000:
        faster = "Search 1" if diff['time_delta_ms'] > 0 else "Search 2"
        print(f"  ⚡ {faster} is significantly faster")

    if abs(diff['score_delta']) > 0.01:
        better = "Search 2" if diff['score_delta'] > 0 else "Search 1"
        print(f"  ⭐ {better} has significantly better scores")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze search logs from DynamoDB',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze specific search by ID
  %(prog)s --query-id befe9ba5-0dbb-4d9a-b2a7-18929844a03d

  # Find searches by query text
  %(prog)s --text "White houses with granite"

  # Show 10 most recent searches
  %(prog)s --recent 10

  # Find slow searches (>5 seconds)
  %(prog)s --slow --threshold 5000

  # Find searches with errors
  %(prog)s --errors

  # Find poor quality searches
  %(prog)s --poor-quality --threshold 0.02

  # Show performance statistics
  %(prog)s --stats

  # Compare two searches
  %(prog)s --compare query-id-1 query-id-2

  # Add --details to any command to show full analysis of first result
  %(prog)s --recent 5 --details
        """
    )

    parser.add_argument('--query-id', help='Analyze search by query_id')
    parser.add_argument('--text', help='Find searches by query text')
    parser.add_argument('--recent', action='store_true', help='Show recent searches')
    parser.add_argument('--slow', action='store_true', help='Find slow searches')
    parser.add_argument('--errors', action='store_true', help='Find searches with errors')
    parser.add_argument('--poor-quality', action='store_true', help='Find poor quality searches')
    parser.add_argument('--stats', action='store_true', help='Show performance statistics')
    parser.add_argument('--compare', nargs=2, metavar=('QUERY_ID1', 'QUERY_ID2'),
                       help='Compare two searches')

    parser.add_argument('--limit', type=int, default=10, help='Maximum results (default: 10)')
    parser.add_argument('--threshold', type=float, default=5000,
                       help='Threshold for --slow (ms) or --poor-quality (score)')
    parser.add_argument('--details', action='store_true',
                       help='Show detailed analysis of first result')

    args = parser.parse_args()

    # Route to appropriate command
    if args.query_id:
        cmd_query_id(args)
    elif args.text:
        cmd_text(args)
    elif args.recent:
        cmd_recent(args)
    elif args.slow:
        cmd_slow(args)
    elif args.errors:
        cmd_errors(args)
    elif args.poor_quality:
        cmd_poor_quality(args)
    elif args.stats:
        cmd_stats(args)
    elif args.compare:
        args.query_id1, args.query_id2 = args.compare
        cmd_compare(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
