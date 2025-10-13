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

import json
import sys
import time
from upload_listings import handler

# Set environment variables (same as Lambda)
import os
os.environ['OS_HOST'] = 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com'
os.environ['OS_INDEX'] = 'listings'
os.environ['MAX_INVOCATIONS'] = '999'  # No limit locally
os.environ['MAX_IMAGES'] = '10'
os.environ['EMBEDDING_IMAGE_WIDTH'] = '576'
os.environ['LOG_LEVEL'] = 'INFO'

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
    print("🚀 Starting local indexing...")
    print("=" * 60)
    print(f"Target: 1,588 listings from s3://demo-hearth-data/murray_listings.json")
    print(f"Caching: DynamoDB (saves Bedrock costs)")
    print(f"Progress will be shown in real-time")
    print("=" * 60)
    print()

    start_time = time.time()
    total_processed = 0
    batch_size = 50  # Process 50 at a time

    for start_pos in range(0, 1588, batch_size):
        batch_num = (start_pos // batch_size) + 1
        total_batches = (1588 + batch_size - 1) // batch_size

        print(f"\n📦 Batch {batch_num}/{total_batches} (listings {start_pos}-{start_pos + batch_size})")
        print("-" * 60)

        # Create payload
        payload = {
            "bucket": "demo-hearth-data",
            "key": "murray_listings.json",
            "start": start_pos,
            "limit": batch_size,
            "_invocation_count": 0  # Reset for each batch
        }

        # Call handler (same as Lambda)
        try:
            context = MockContext()
            result = handler(payload, context)

            if result.get('statusCode') == 200:
                body = json.loads(result['body'])
                processed = body.get('processed', 0)
                total_processed += processed

                # Progress stats
                elapsed = int(time.time() - start_time)
                percent = int((total_processed / 1588) * 100)
                rate = total_processed / elapsed if elapsed > 0 else 0
                remaining = 1588 - total_processed
                eta_secs = int(remaining / rate) if rate > 0 else 0
                eta_mins = eta_secs // 60

                print(f"✅ Processed: {processed} listings")
                print(f"📊 Total: {total_processed} / 1,588 ({percent}%)")
                print(f"⏱️  Elapsed: {elapsed // 60}m {elapsed % 60}s | ETA: ~{eta_mins}m")

            else:
                print(f"⚠️  Warning: statusCode {result.get('statusCode')}")
                body = json.loads(result.get('body', '{}'))
                if 'error' in body:
                    print(f"   Error: {body['error']}")

        except Exception as e:
            print(f"❌ Error processing batch: {e}")
            print("Continuing to next batch...")
            continue

    # Final summary
    elapsed = int(time.time() - start_time)
    print("\n" + "=" * 60)
    print("✅ INDEXING COMPLETE!")
    print("=" * 60)
    print(f"Total indexed: {total_processed} listings")
    print(f"Time taken: {elapsed // 60}m {elapsed % 60}s")
    print(f"Average: {elapsed / total_processed:.1f}s per listing")
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
