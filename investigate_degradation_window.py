#!/usr/bin/env python3
"""
Investigate Search Degradation Between 03:30-05:38 UTC
Detailed investigation of the exact timeline when search results degraded.
"""

import boto3
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple
from decimal import Decimal
from collections import defaultdict

# Initialize AWS clients
dynamodb = boto3.client('dynamodb', region_name='us-east-1')
lambda_client = boto3.client('lambda', region_name='us-east-1')
cloudwatch_logs = boto3.client('logs', region_name='us-east-1')

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


def get_searches_in_window(start_utc: str, end_utc: str) -> List[Dict]:
    """
    Fetch ALL searches in the specific time window.

    Args:
        start_utc: Start time in 'YYYY-MM-DD HH:MM:SS' format (UTC)
        end_utc: End time in 'YYYY-MM-DD HH:MM:SS' format (UTC)

    Returns:
        List of search log dictionaries sorted by timestamp
    """
    # Parse timestamps
    start_dt = datetime.strptime(start_utc, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_utc, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    print(f"Querying DynamoDB SearchQueryLogs...")
    print(f"Time window: {start_utc} UTC to {end_utc} UTC")
    print(f"Timestamp range: {start_ms} to {end_ms}\n")

    try:
        items = []
        last_evaluated_key = None
        scan_count = 0

        while True:
            scan_kwargs = {
                'TableName': TABLE_NAME,
                'FilterExpression': '#ts BETWEEN :start AND :end',
                'ExpressionAttributeNames': {
                    '#ts': 'timestamp'
                },
                'ExpressionAttributeValues': {
                    ':start': {'N': str(start_ms)},
                    ':end': {'N': str(end_ms)}
                }
            }

            if last_evaluated_key:
                scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

            response = dynamodb.scan(**scan_kwargs)
            batch_items = [_dynamodb_to_python(item) for item in response['Items']]
            items.extend(batch_items)

            scan_count += 1
            print(f"Scan #{scan_count}: Found {len(batch_items)} items (Total: {len(items)})")

            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break

        # Sort by timestamp ascending
        items.sort(key=lambda x: x.get('timestamp', 0))

        print(f"\nTotal searches found: {len(items)}\n")
        return items

    except Exception as e:
        print(f"Error scanning DynamoDB: {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_zpids(search_log: Dict, top_n: int = 10) -> List[str]:
    """Extract top N zpids from search results."""
    results = search_log.get('results', [])
    return [str(r.get('zpid', '')) for r in results[:top_n]]


def analyze_white_homes_granite_wood(searches: List[Dict]) -> Dict[str, Any]:
    """
    Analyze the specific query: 'White homes with granite countertops and wood floors'
    with use_multi_query=true

    Returns detailed timeline and transition points.
    """
    print("="*120)
    print("ANALYSIS: 'White homes with granite countertops and wood floors' (multi_query=true)")
    print("="*120)

    # Filter for the specific query with multi_query=true
    target_searches = []
    for search in searches:
        query_text = search.get('query_text', '').lower()
        use_multi = search.get('use_multi_query', False)

        # Match the query (flexible matching)
        if use_multi and 'white' in query_text and 'granite' in query_text and 'wood' in query_text:
            target_searches.append(search)

    print(f"Found {len(target_searches)} matching searches\n")

    if not target_searches:
        print("No matching searches found!")
        return {}

    # Analyze minute-by-minute
    print("-" * 120)
    print(f"{'Timestamp (UTC)':<25} {'Query ID':<38} {'Top 5 ZPIDs':<50} {'Status':<15}")
    print("-" * 120)

    timeline = []
    transition_point = None
    last_status = None

    # Known bad zpids
    BAD_ZPIDS = {'12778555', '70592220'}

    for i, search in enumerate(target_searches):
        timestamp = search.get('timestamp', 0)
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        query_id = search.get('query_id', 'unknown')

        top_zpids = extract_zpids(search, 5)

        # Check if results are good or bad
        has_bad = bool(set(top_zpids) & BAD_ZPIDS)
        status = "❌ BAD" if has_bad else "✅ GOOD"

        # Detect transition
        if last_status is not None and last_status != status:
            transition_point = {
                'index': i,
                'timestamp': timestamp,
                'datetime': dt,
                'query_id': query_id,
                'from_status': last_status,
                'to_status': status,
                'zpids_before': extract_zpids(target_searches[i-1], 10) if i > 0 else [],
                'zpids_after': extract_zpids(search, 10),
            }

        zpids_str = ', '.join(top_zpids)
        print(f"{dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]:<25} {query_id:<38} {zpids_str:<50} {status:<15}")

        # Add to timeline
        timeline.append({
            'timestamp': timestamp,
            'datetime': dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'query_id': query_id,
            'status': status,
            'top_10_zpids': extract_zpids(search, 10),
            'avg_score': search.get('result_quality_metrics', {}).get('avg_score', 0),
            'perfect_matches': search.get('result_quality_metrics', {}).get('perfect_matches', 0),
        })

        last_status = status

    print("-" * 120)

    # Report transition point
    if transition_point:
        print("\n" + "="*120)
        print("🔍 TRANSITION POINT DETECTED")
        print("="*120)
        tp = transition_point
        print(f"\nExact Timestamp: {tp['datetime'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} UTC")
        print(f"Query ID: {tp['query_id']}")
        print(f"Status Change: {tp['from_status']} → {tp['to_status']}")
        print(f"\nBEFORE (Top 10 ZPIDs):")
        for idx, zpid in enumerate(tp['zpids_before'], 1):
            marker = "⚠️ " if zpid in BAD_ZPIDS else ""
            print(f"  {idx:2d}. {marker}{zpid}")
        print(f"\nAFTER (Top 10 ZPIDs):")
        for idx, zpid in enumerate(tp['zpids_after'], 1):
            marker = "⚠️ " if zpid in BAD_ZPIDS else ""
            print(f"  {idx:2d}. {marker}{zpid}")

        # What changed
        zpids_before_set = set(tp['zpids_before'])
        zpids_after_set = set(tp['zpids_after'])
        added = zpids_after_set - zpids_before_set
        removed = zpids_before_set - zpids_after_set

        print(f"\nChanges:")
        print(f"  Added ZPIDs: {', '.join(added) if added else 'None'}")
        print(f"  Removed ZPIDs: {', '.join(removed) if removed else 'None'}")
        print("="*120)

    return {
        'timeline': timeline,
        'transition_point': transition_point,
        'total_searches': len(target_searches)
    }


def check_lambda_deployments(start_utc: str, end_utc: str) -> List[Dict]:
    """
    Check for Lambda deployments/updates in the time window.
    """
    print("\n" + "="*120)
    print("CHECKING LAMBDA DEPLOYMENTS")
    print("="*120)

    start_dt = datetime.strptime(start_utc, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_utc, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)

    # Try to get Lambda function names related to search
    print("\nSearching for Lambda functions...")

    try:
        # List Lambda functions
        functions_response = lambda_client.list_functions()
        functions = functions_response.get('Functions', [])

        print(f"Found {len(functions)} Lambda functions total")

        # Filter for search-related functions
        search_functions = [f for f in functions if 'search' in f['FunctionName'].lower()]

        print(f"Found {len(search_functions)} search-related functions:")
        for func in search_functions:
            print(f"  - {func['FunctionName']}")

        # Check each function's version history
        deployments = []

        for func in search_functions:
            func_name = func['FunctionName']
            print(f"\nChecking {func_name}...")

            try:
                # List versions
                versions_response = lambda_client.list_versions_by_function(
                    FunctionName=func_name
                )

                versions = versions_response.get('Versions', [])
                print(f"  Found {len(versions)} versions")

                # Check version timestamps
                for version in versions:
                    last_modified = version.get('LastModified', '')
                    if last_modified:
                        # Parse timestamp (format: 2024-01-01T12:00:00.000+0000)
                        version_dt = datetime.strptime(last_modified, '%Y-%m-%dT%H:%M:%S.%f%z')

                        if start_dt <= version_dt <= end_dt:
                            deployments.append({
                                'function_name': func_name,
                                'version': version.get('Version'),
                                'timestamp': version_dt,
                                'code_sha256': version.get('CodeSha256'),
                                'runtime': version.get('Runtime'),
                                'last_modified': last_modified
                            })
                            print(f"  ✅ Deployment found: Version {version.get('Version')} at {version_dt}")

            except Exception as e:
                print(f"  Error checking versions: {e}")

        if deployments:
            print("\n" + "-"*120)
            print("DEPLOYMENTS IN TIME WINDOW:")
            print("-"*120)
            for dep in sorted(deployments, key=lambda x: x['timestamp']):
                print(f"\n  Function: {dep['function_name']}")
                print(f"  Version: {dep['version']}")
                print(f"  Timestamp: {dep['timestamp'].strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"  CodeSha256: {dep['code_sha256']}")
                print(f"  Runtime: {dep['runtime']}")
        else:
            print("\n  No Lambda deployments found in time window")

        return deployments

    except Exception as e:
        print(f"Error checking Lambda deployments: {e}")
        import traceback
        traceback.print_exc()
        return []


def check_cloudwatch_errors(start_utc: str, end_utc: str) -> List[Dict]:
    """
    Check CloudWatch logs for errors/warnings in the time window.
    """
    print("\n" + "="*120)
    print("CHECKING CLOUDWATCH LOGS FOR ERRORS")
    print("="*120)

    start_dt = datetime.strptime(start_utc, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_utc, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    try:
        # List log groups
        log_groups_response = cloudwatch_logs.describe_log_groups()
        log_groups = log_groups_response.get('logGroups', [])

        # Filter for search-related log groups
        search_log_groups = [lg for lg in log_groups if 'search' in lg['logGroupName'].lower() or 'lambda' in lg['logGroupName'].lower()]

        print(f"Found {len(search_log_groups)} relevant log groups:")
        for lg in search_log_groups[:10]:  # Show first 10
            print(f"  - {lg['logGroupName']}")

        errors = []

        # Search for ERROR and WARNING in logs
        for log_group in search_log_groups[:5]:  # Check first 5 to avoid rate limits
            log_group_name = log_group['logGroupName']
            print(f"\nSearching {log_group_name}...")

            try:
                # Query for errors
                response = cloudwatch_logs.filter_log_events(
                    logGroupName=log_group_name,
                    startTime=start_ms,
                    endTime=end_ms,
                    filterPattern='ERROR',
                    limit=50
                )

                events = response.get('events', [])

                for event in events:
                    errors.append({
                        'log_group': log_group_name,
                        'timestamp': datetime.fromtimestamp(event['timestamp'] / 1000, tz=timezone.utc),
                        'message': event.get('message', ''),
                        'level': 'ERROR'
                    })

                if events:
                    print(f"  Found {len(events)} ERROR events")

            except Exception as e:
                print(f"  Error querying log group: {e}")

        if errors:
            print("\n" + "-"*120)
            print("ERRORS FOUND:")
            print("-"*120)
            for error in sorted(errors, key=lambda x: x['timestamp'])[:20]:  # Show first 20
                print(f"\n  {error['timestamp'].strftime('%Y-%m-%d %H:%M:%S %Z')} | {error['level']}")
                print(f"  Log Group: {error['log_group']}")
                print(f"  Message: {error['message'][:200]}")
        else:
            print("\n  No errors found in CloudWatch logs")

        return errors

    except Exception as e:
        print(f"Error checking CloudWatch logs: {e}")
        import traceback
        traceback.print_exc()
        return []


def analyze_all_searches_summary(searches: List[Dict]) -> None:
    """
    Summary of all searches in the time window.
    """
    print("\n" + "="*120)
    print("ALL SEARCHES SUMMARY")
    print("="*120)

    # Group by query text
    queries_by_text = defaultdict(list)
    for search in searches:
        query_text = search.get('query_text', 'unknown')
        queries_by_text[query_text].append(search)

    print(f"\nTotal searches: {len(searches)}")
    print(f"Unique queries: {len(queries_by_text)}\n")

    print("Top 20 queries by frequency:")
    for query_text, searches_list in sorted(queries_by_text.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
        multi_true = sum(1 for s in searches_list if s.get('use_multi_query', False))
        multi_false = len(searches_list) - multi_true
        print(f"  {len(searches_list):3d}x: \"{query_text}\"")
        print(f"       (multi_query: {multi_true} true, {multi_false} false)")

    # Check for time gaps (potential deployments)
    print("\n" + "-"*120)
    print("CHECKING FOR TIME GAPS (possible deployments)")
    print("-"*120)

    gaps = []
    for i in range(1, len(searches)):
        prev_time = searches[i-1].get('timestamp', 0)
        curr_time = searches[i].get('timestamp', 0)
        gap_minutes = (curr_time - prev_time) / 1000 / 60

        if gap_minutes > 5:  # More than 5 minute gap
            prev_dt = datetime.fromtimestamp(prev_time / 1000, tz=timezone.utc)
            curr_dt = datetime.fromtimestamp(curr_time / 1000, tz=timezone.utc)
            gaps.append({
                'prev_time': prev_dt,
                'curr_time': curr_dt,
                'gap_minutes': gap_minutes
            })

    if gaps:
        print(f"\nFound {len(gaps)} time gaps > 5 minutes:")
        for gap in gaps:
            print(f"\n  {gap['prev_time'].strftime('%Y-%m-%d %H:%M:%S')} → {gap['curr_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Gap: {gap['gap_minutes']:.1f} minutes")
    else:
        print("\n  No significant time gaps found")


def main():
    """Main execution."""
    print("\n" + "="*120)
    print("INVESTIGATION: Search Results Degradation Between 03:30-05:38 UTC")
    print("="*120)
    print(f"Investigation started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("="*120 + "\n")

    # Define time window
    # 10:30 PM EST (03:30 UTC) to 12:38 AM EST (05:38 UTC)
    # Assuming date is 2025-10-23 based on environment
    start_utc = "2025-10-23 03:30:00"
    end_utc = "2025-10-23 05:38:00"

    # Note: Adjust dates if the degradation happened on a different date
    print(f"Target time window: {start_utc} UTC to {end_utc} UTC")
    print(f"(10:30 PM EST to 12:38 AM EST)\n")

    # 1. Fetch ALL searches in time window
    print("STEP 1: Querying DynamoDB for all searches in time window...")
    print("-" * 120)
    searches = get_searches_in_window(start_utc, end_utc)

    if not searches:
        print("\n⚠️  No searches found in this time window.")
        print("This might mean:")
        print("  1. The date is incorrect (update start_utc and end_utc)")
        print("  2. The time zone conversion is incorrect")
        print("  3. No searches occurred during this time")
        return

    # Show time range
    first_time = datetime.fromtimestamp(searches[0].get('timestamp', 0) / 1000, tz=timezone.utc)
    last_time = datetime.fromtimestamp(searches[-1].get('timestamp', 0) / 1000, tz=timezone.utc)
    print(f"\nActual time range of searches found:")
    print(f"  First: {first_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Last:  {last_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # 2. Analyze the specific white homes query
    print("\n\nSTEP 2: Analyzing 'White homes with granite countertops and wood floors' (multi_query=true)...")
    print("-" * 120)
    white_homes_analysis = analyze_white_homes_granite_wood(searches)

    # 3. Check Lambda deployments
    print("\n\nSTEP 3: Checking for Lambda deployments in time window...")
    print("-" * 120)
    deployments = check_lambda_deployments(start_utc, end_utc)

    # 4. Check CloudWatch errors
    print("\n\nSTEP 4: Checking CloudWatch logs for errors/warnings...")
    print("-" * 120)
    errors = check_cloudwatch_errors(start_utc, end_utc)

    # 5. Summary of all searches
    print("\n\nSTEP 5: Analyzing all searches for patterns...")
    print("-" * 120)
    analyze_all_searches_summary(searches)

    # 6. Final summary
    print("\n\n" + "="*120)
    print("FINAL SUMMARY")
    print("="*120)

    if white_homes_analysis.get('transition_point'):
        tp = white_homes_analysis['transition_point']
        print(f"\n✅ DEGRADATION POINT IDENTIFIED:")
        print(f"   Timestamp: {tp['datetime'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} UTC")
        print(f"   Query ID: {tp['query_id']}")
        print(f"   Status: {tp['from_status']} → {tp['to_status']}")
    else:
        print("\n⚠️  No clear transition point found for white homes query")

    if deployments:
        print(f"\n✅ Lambda deployments found: {len(deployments)}")
        for dep in deployments:
            print(f"   - {dep['function_name']} v{dep['version']} at {dep['timestamp'].strftime('%Y-%m-%d %H:%M:%S %Z')}")
    else:
        print(f"\n❌ No Lambda deployments found in time window")

    if errors:
        print(f"\n⚠️  CloudWatch errors found: {len(errors)}")
        print(f"   First error: {errors[0]['timestamp'].strftime('%Y-%m-%d %H:%M:%S %Z')}")
    else:
        print(f"\n✅ No CloudWatch errors found")

    print("\n" + "="*120)
    print("INVESTIGATION COMPLETE")
    print("="*120)

    # Save results to file
    output_file = '/Users/andrewcarras/hearth_backend_new/degradation_investigation_results.json'
    results = {
        'time_window': {
            'start_utc': start_utc,
            'end_utc': end_utc,
        },
        'total_searches': len(searches),
        'white_homes_analysis': {
            'total_searches': white_homes_analysis.get('total_searches', 0),
            'transition_point': white_homes_analysis.get('transition_point'),
            'timeline': white_homes_analysis.get('timeline', [])
        },
        'deployments': deployments,
        'errors_count': len(errors)
    }

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
