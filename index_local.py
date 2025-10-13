#!/usr/bin/env python3
"""
Local indexing script - Run upload_listings.py on your computer instead of Lambda.

Benefits:
- Full control (start/stop anytime)
- No timeouts
- Better debugging
- Same DynamoDB caching (saves costs!)

Usage:
    python3 index_local.py

Requirements:
    pip install boto3 opensearch-py requests requests-aws4auth
"""

# MUST set environment variables BEFORE importing (common.py needs them)
import os
os.environ['OS_HOST'] = 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com'
os.environ['OS_INDEX'] = 'listings'
os.environ['MAX_INVOCATIONS'] = '1'  # Disable self-invocation (we loop locally instead)
os.environ['MAX_IMAGES'] = '10'
os.environ['EMBEDDING_IMAGE_WIDTH'] = '576'
os.environ['LOG_LEVEL'] = 'INFO'

import json
import sys
import time
import requests
from requests_aws4auth import AWS4Auth
import boto3
from upload_listings import handler

# OpenSearch client setup for verification
def get_opensearch_client():
    """Create OpenSearch client for verification queries."""
    from opensearchpy import OpenSearch, RequestsHttpConnection

    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        'us-east-1',
        'es',
        session_token=credentials.token
    )

    os_host = os.environ['OS_HOST']
    client = OpenSearch(
        hosts=[{'host': os_host, 'port': 443}],
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
        os_index = os.environ['OS_INDEX']
        response = os_client.get(index=os_index, id=str(zpid))
        return response.get('found', False)
    except Exception as e:
        # If document not found, OpenSearch raises exception
        return False

# Mock Lambda context
class MockContext:
    def __init__(self):
        self.aws_request_id = 'local-run'
        self.log_group_name = 'local'
        self.log_stream_name = 'local'
        self.function_name = 'local-indexing'
        self.memory_limit_in_mb = '3008'
        self.invoked_function_arn = 'local'
        self.function_version = '$LATEST'

    def get_remaining_time_in_millis(self):
        return 900000  # 15 minutes (plenty of time locally)

def index_all_listings():
    """Index all 1,588 listings from S3."""
    print("🚀 Starting local indexing with OpenSearch verification...")
    print("=" * 60)
    print(f"Target: 1,588 listings from s3://demo-hearth-data/murray_listings.json")
    print(f"Caching: DynamoDB (saves Bedrock costs)")
    print(f"Verification: Each listing verified in OpenSearch")
    print(f"Progress will be shown in real-time")
    print("=" * 60)
    print()

    # Initialize OpenSearch client for verification
    print("🔧 Connecting to OpenSearch...")
    os_client = get_opensearch_client()
    print("✅ Connected to OpenSearch")
    print()

    start_time = time.time()
    total_processed = 0
    total_success = 0
    total_errors = 0
    total_verified = 0
    batch_size = 1  # Process 1 at a time for detailed logging

    import uuid
    for start_pos in range(0, 1588, batch_size):
        listing_num = start_pos + 1

        # Create payload with unique job ID (avoid DynamoDB conflicts)
        payload = {
            "bucket": "demo-hearth-data",
            "key": "murray_listings.json",
            "start": start_pos,
            "limit": batch_size,
            "_invocation_count": 0,  # Reset for each listing
            "_job_id": str(uuid.uuid4())  # Unique ID per listing to skip DynamoDB job check
        }

        # Call handler (same as Lambda)
        try:
            context = MockContext()
            result = handler(payload, context)

            if result.get('statusCode') == 200:
                body = json.loads(result['body'])
                processed = body.get('processed', 0)
                zpid = body.get('zpid', 'unknown')

                total_processed += processed

                # VERIFY: Check if listing is actually in OpenSearch
                if zpid != 'unknown':
                    in_opensearch = verify_listing_in_opensearch(zpid, os_client)
                    if in_opensearch:
                        total_success += 1
                        total_verified += 1
                        status = "✅ INDEXED"
                    else:
                        total_errors += 1
                        status = "❌ NOT IN OS"
                        print(f"⚠️  [{listing_num:4d}/1588] zpid={zpid} | {status} - Handler returned 200 but NOT found in OpenSearch!")
                        continue
                else:
                    total_errors += 1
                    status = "❌ NO ZPID"

                # Progress stats
                elapsed = int(time.time() - start_time)
                percent = (total_verified / 1588) * 100
                rate = total_verified / elapsed if elapsed > 0 else 0
                remaining = 1588 - total_verified
                eta_secs = int(remaining / rate) if rate > 0 else 0
                eta_mins = eta_secs // 60

                # Detailed per-listing progress
                print(f"{status} [{listing_num:4d}/1588] zpid={zpid} | "
                      f"{percent:5.1f}% | "
                      f"Elapsed: {elapsed//60}m{elapsed%60:02d}s | "
                      f"ETA: ~{eta_mins}m | "
                      f"Verified: {total_verified}, Errors: {total_errors}")

            else:
                total_errors += 1
                body = json.loads(result.get('body', '{}'))
                error_msg = body.get('error', 'Unknown error')
                zpid = body.get('zpid', 'unknown')

                print(f"❌ [{listing_num:4d}/1588] zpid={zpid} | "
                      f"ERROR: {error_msg[:60]}")

        except Exception as e:
            total_errors += 1
            print(f"❌ [{listing_num:4d}/1588] EXCEPTION: {str(e)[:80]}")
            continue

    # Final summary
    elapsed = int(time.time() - start_time)
    print("\n" + "=" * 60)
    print("✅ INDEXING COMPLETE!")
    print("=" * 60)
    print(f"Total processed: {total_processed} listings")
    print(f"✅ Verified in OpenSearch: {total_verified} listings")
    print(f"❌ Errors: {total_errors} listings")
    print(f"Time taken: {elapsed // 60}m {elapsed % 60}s")
    if total_verified > 0:
        print(f"Average: {elapsed / total_verified:.1f}s per verified listing")
    print()
    print("🔍 Test your search:")
    print("   curl -X POST https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{\"q\":\"granite\",\"size\":5}'")
    print()

if __name__ == '__main__':
    try:
        index_all_listings()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        print("Progress has been saved. You can restart anytime.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
