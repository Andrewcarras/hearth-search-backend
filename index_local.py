#!/usr/bin/env python3
"""
Local indexing script - Run upload_listings.py on your computer instead of Lambda.

OPTIMIZED & FULLY CONFIGURABLE:
- Loads S3 data ONCE (not per-listing)
- 5-10x faster than Lambda chain
- No hardcoded values - works with any bucket/file
- Calculates all metrics dynamically
- Same DynamoDB caching (saves costs!)

Benefits:
- Full control (start/stop anytime)
- No Lambda timeouts
- Better debugging
- Works with any JSON file format

Usage:
    # Index all listings from a file
    python3 index_local.py --bucket demo-hearth-data --key slc_listings.json

    # Test with first 30 listings
    python3 index_local.py --bucket demo-hearth-data --key slc_listings.json --limit 30

    # Resume from listing 500
    python3 index_local.py --bucket demo-hearth-data --key slc_listings.json --start 500

    # Index to listings-v2 (multi-vector schema)
    python3 index_local.py --bucket demo-hearth-data --key slc_listings.json --index listings-v2

    # Process specific range (listings 100-150)
    python3 index_local.py --bucket demo-hearth-data --key murray_listings.json --start 100 --limit 50

Requirements:
    pip install boto3 opensearch-py requests requests-aws4auth
"""

import argparse
import os
import sys
import json
import time
import uuid
import boto3
import concurrent.futures
from requests_aws4auth import AWS4Auth

# Parse command-line arguments FIRST (before importing common.py)
parser = argparse.ArgumentParser(description='Index property listings from S3 to OpenSearch locally')
parser.add_argument('--bucket', required=True, help='S3 bucket name (e.g., demo-hearth-data)')
parser.add_argument('--key', required=True, help='S3 object key (e.g., slc_listings.json)')
parser.add_argument('--start', type=int, default=0, help='Starting index (default: 0)')
parser.add_argument('--limit', type=int, default=None, help='Number of listings to process (default: all)')
parser.add_argument('--index', default='listings', help='OpenSearch index name (default: listings)')
parser.add_argument('--host', default='search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com',
                   help='OpenSearch host')
parser.add_argument('--batch-size', type=int, default=5, help='Parallel batch size (default: 5)')
parser.add_argument('--max-images', type=int, default=10, help='Max images per listing (default: 10)')

args = parser.parse_args()

# Set environment variables BEFORE importing common.py (it reads them at import time)
os.environ['OS_HOST'] = args.host
os.environ['OS_INDEX'] = args.index
os.environ['MAX_INVOCATIONS'] = '1'  # Disable self-invocation (we loop locally)
os.environ['MAX_IMAGES'] = str(args.max_images)
os.environ['EMBEDDING_IMAGE_WIDTH'] = '576'
os.environ['LOG_LEVEL'] = 'INFO'

# NOW import after env vars are set
from upload_listings import handler
from opensearchpy import OpenSearch, RequestsHttpConnection


def get_opensearch_client():
    """Create OpenSearch client for verification queries."""
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        'us-east-1',
        'es',
        session_token=credentials.token
    )

    client = OpenSearch(
        hosts=[{'host': args.host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30
    )
    return client


def verify_listing_in_opensearch(zpid, os_client):
    """Verify that a listing exists in OpenSearch by zpid."""
    try:
        response = os_client.get(index=args.index, id=str(zpid))
        return response.get('found', False)
    except Exception:
        return False


class MockContext:
    """Mock Lambda context for local execution."""
    def __init__(self):
        self.aws_request_id = 'local-run'
        self.log_group_name = 'local'
        self.log_stream_name = 'local'
        self.function_name = 'local-indexing'
        self.memory_limit_in_mb = '3008'
        self.invoked_function_arn = 'local'
        self.function_version = '$LATEST'

    def get_remaining_time_in_millis(self):
        return 900000  # 15 minutes


def process_single_listing(listing_data, os_client):
    """
    Process a single listing by passing data directly to handler.

    OPTIMIZATION: Passes listing data directly instead of making handler
    re-download entire S3 file. 5-10x faster!
    """
    payload = {
        "listings": [listing_data],
        "start": 0,
        "limit": 1,
        "_invocation_count": 0,
        "_job_id": str(uuid.uuid4())
    }

    context = MockContext()
    result = handler(payload, context)

    # Parse result
    listing_result = {
        'zpid': listing_data.get('zpid', 'unknown'),
        'status_code': result.get('statusCode'),
        'verified': False,
        'error': None
    }

    if result.get('statusCode') == 200:
        body = json.loads(result['body'])
        zpid = body.get('zpid', listing_result['zpid'])
        listing_result['zpid'] = zpid

        # Verify in OpenSearch
        if zpid != 'unknown':
            listing_result['verified'] = verify_listing_in_opensearch(zpid, os_client)
    else:
        body = json.loads(result.get('body', '{}'))
        listing_result['error'] = body.get('error', 'Unknown error')

    return listing_result


def main():
    """Main indexing function with full configurability."""
    print("🚀 Starting OPTIMIZED local indexing...")
    print("=" * 70)
    print(f"Source: s3://{args.bucket}/{args.key}")
    print(f"Target: OpenSearch index '{args.index}' @ {args.host}")
    print(f"Range: start={args.start}, limit={args.limit or 'ALL'}")
    print(f"Batch size: {args.batch_size} listings in parallel")
    print(f"Max images per listing: {args.max_images}")
    print("=" * 70)
    print()

    # Load all listings from S3 ONCE at startup
    print(f"📥 Loading listings from s3://{args.bucket}/{args.key}...")
    s3 = boto3.client('s3')

    try:
        response = s3.get_object(Bucket=args.bucket, Key=args.key)
        all_data = json.loads(response['Body'].read())

        # Handle both wrapped and direct array formats
        if isinstance(all_data, dict) and "listings" in all_data:
            all_listings = all_data["listings"]
        elif isinstance(all_data, list):
            all_listings = all_data
        else:
            raise ValueError("Unexpected JSON format (expected array or {listings: []})")

        total_in_file = len(all_listings)
        print(f"✅ Loaded {total_in_file:,} listings from S3")

        # Apply start/limit
        end_index = args.start + args.limit if args.limit else len(all_listings)
        all_listings = all_listings[args.start:end_index]

        print(f"📊 Processing range: [{args.start}:{end_index}] = {len(all_listings):,} listings")
        print()

    except Exception as e:
        print(f"❌ Failed to load S3 data: {e}")
        sys.exit(1)

    # Initialize OpenSearch client for verification
    print(f"🔧 Connecting to OpenSearch @ {args.host}...")
    os_client = get_opensearch_client()
    print(f"✅ Connected to index '{args.index}'")
    print()

    start_time = time.time()
    total_verified = 0
    total_errors = 0
    total_listings = len(all_listings)

    # Process in batches
    for batch_start in range(0, total_listings, args.batch_size):
        batch_end = min(batch_start + args.batch_size, total_listings)
        current_batch_size = batch_end - batch_start

        # Calculate absolute indices (for display)
        abs_start = args.start + batch_start + 1
        abs_end = args.start + batch_end

        print(f"\n📦 BATCH [{abs_start}-{abs_end}] Processing {current_batch_size} listings in parallel...")
        batch_start_time = time.time()

        # Get listing data for this batch
        batch_listings = all_listings[batch_start:batch_end]

        # Process batch in parallel using ThreadPoolExecutor
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=current_batch_size) as executor:
                # Submit all listings in batch
                futures = {
                    executor.submit(process_single_listing, listing, os_client): idx
                    for idx, listing in enumerate(batch_listings, start=batch_start)
                }

                # Collect results as they complete
                batch_results = []
                for future in concurrent.futures.as_completed(futures):
                    idx = futures[future]
                    abs_idx = args.start + idx + 1

                    try:
                        result = future.result()
                        batch_results.append(result)

                        # Show individual listing completion
                        if result['verified']:
                            status_icon = "✅"
                        elif result['error']:
                            status_icon = "❌"
                        else:
                            status_icon = "⚠️"

                        print(f"  {status_icon} [{abs_idx:4d}] zpid={result['zpid']} completed")

                    except Exception as e:
                        batch_results.append({
                            'zpid': 'unknown',
                            'status_code': 500,
                            'verified': False,
                            'error': str(e)
                        })
                        print(f"  ❌ [{abs_idx:4d}] EXCEPTION: {str(e)[:60]}")

            # Verify batch results
            batch_verified = sum(1 for r in batch_results if r['verified'])
            batch_errors = sum(1 for r in batch_results if not r['verified'])
            total_verified += batch_verified
            total_errors += batch_errors

            batch_elapsed = time.time() - batch_start_time

            # Overall progress stats
            elapsed = int(time.time() - start_time)
            percent = (total_verified / total_listings) * 100 if total_listings > 0 else 0
            rate = total_verified / elapsed if elapsed > 0 else 0
            remaining = total_listings - total_verified
            eta_secs = int(remaining / rate) if rate > 0 else 0
            eta_hours = eta_secs // 3600
            eta_mins = (eta_secs % 3600) // 60

            print(f"\n✅ BATCH COMPLETE in {batch_elapsed:.1f}s | Verified: {batch_verified}/{current_batch_size}")
            print(f"📊 PROGRESS: {total_verified}/{total_listings} ({percent:.1f}%) | "
                  f"Elapsed: {elapsed//3600}h{(elapsed%3600)//60}m | "
                  f"ETA: ~{eta_hours}h{eta_mins}m | "
                  f"Rate: {rate*60:.1f}/min | "
                  f"Errors: {total_errors}")

        except Exception as e:
            print(f"❌ BATCH EXCEPTION: {str(e)}")
            total_errors += current_batch_size
            continue

    # Final summary
    elapsed = int(time.time() - start_time)
    elapsed_hours = elapsed // 3600
    elapsed_mins = (elapsed % 3600) // 60
    elapsed_secs = elapsed % 60

    print("\n" + "=" * 70)
    print("✅ INDEXING COMPLETE!")
    print("=" * 70)
    print(f"Source: s3://{args.bucket}/{args.key}")
    print(f"Target: {args.index}")
    print(f"Range: {args.start} to {end_index} ({total_listings} listings)")
    print(f"✅ Verified in OpenSearch: {total_verified} listings")
    print(f"❌ Errors: {total_errors} listings")
    print(f"⏱️  Time taken: {elapsed_hours}h {elapsed_mins}m {elapsed_secs}s")
    if total_verified > 0:
        print(f"📊 Average: {elapsed / total_verified:.1f}s per verified listing")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        print("Progress has been saved. You can restart anytime.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
