#!/usr/bin/env python3
"""
Batch update all properties with hierarchical architectural style classifications.

Uses CRUD API (PATCH /listings/{zpid}) to update architecture fields WITHOUT reindexing.

Updates these fields:
- architecture_style (Tier 1 broad category)
- architecture_style_specific (Tier 2 specific sub-style, if confident)
- architecture_confidence (numeric 0-1 confidence score)

Usage:
    python update_architecture_styles_crud.py --dry-run  # Preview changes
    python update_architecture_styles_crud.py             # Execute updates
"""

import json
import sys
import time
import argparse
import requests
from collections import defaultdict, Counter
from datetime import datetime

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# Configuration
REGION = 'us-east-1'
OS_HOST = 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com'
OS_INDEX = 'listings-v2'
CRUD_API_BASE = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod'

# Batch settings
BATCH_SIZE = 50
CONCURRENT_LIMIT = 10
SLEEP_BETWEEN_BATCHES = 5  # seconds

# Cost tracking
BEDROCK_VISION_COST = 0.001125  # per image
DYNAMODB_WRITE_COST = 0.0000008  # per write

# Initialize clients
session = boto3.Session()
credentials = session.get_credentials()
awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    REGION,
    'es',
    session_token=credentials.token
)

os_client = OpenSearch(
    hosts=[{'host': OS_HOST, 'port': 443}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=30
)

brt = boto3.client('bedrock-runtime', region_name=REGION)
dynamodb = boto3.client('dynamodb', region_name=REGION)

# Import vision analysis from common.py
from common import analyze_property_image_from_cache

def get_all_property_zpids():
    """Fetch all ZPIDs from OpenSearch"""
    print("Fetching all property ZPIDs from OpenSearch...")

    zpids = []
    response = os_client.search(
        index=OS_INDEX,
        body={
            "query": {"match_all": {}},
            "_source": ["zpid"],
            "size": 10000  # Max size, but we'll use scroll for all
        },
        scroll='2m'
    )

    scroll_id = response['_scroll_id']
    hits = response['hits']['hits']

    for hit in hits:
        zpid = hit['_source'].get('zpid')
        if zpid:
            zpids.append(zpid)

    # Scroll through remaining results
    while len(hits) > 0:
        response = os_client.scroll(scroll_id=scroll_id, scroll='2m')
        scroll_id = response['_scroll_id']
        hits = response['hits']['hits']

        for hit in hits:
            zpid = hit['_source'].get('zpid')
            if zpid:
                zpids.append(zpid)

    print(f"✓ Found {len(zpids)} properties")
    return zpids


def get_property_data(zpid):
    """Fetch property data from OpenSearch"""
    try:
        response = os_client.get(index=OS_INDEX, id=zpid)
        return response['_source']
    except Exception as e:
        print(f"  Error fetching {zpid}: {e}")
        return None


def get_exterior_image_url(property_data):
    """Get first exterior image URL from property"""
    # Try to get from vision cache first (has actual URLs)
    zpid = property_data.get('zpid')

    # Check vision cache for cached images
    try:
        response = dynamodb.scan(
            TableName='hearth-vision-cache',
            FilterExpression='contains(image_url, :zpid)',
            ExpressionAttributeValues={':zpid': {'S': str(zpid)}},
            Limit=1
        )

        if response['Items']:
            return response['Items'][0]['image_url']['S']
    except:
        pass

    # Fallback: construct URL (may not exist)
    return f"https://photos.zillowstatic.com/fp/{zpid}-cc_ft_1536.jpg"


def classify_architecture_hierarchical(image_url):
    """
    Classify architecture using hierarchical approach.

    Returns:
        dict with:
        - architecture_style: Tier 1 broad category
        - architecture_style_specific: Tier 2 specific (or None)
        - architecture_confidence: 0-1 score
    """
    try:
        # Use cached vision analysis
        result = analyze_property_image_from_cache(image_url)

        if not result or 'analysis' not in result:
            return None

        analysis = result['analysis']

        # Extract hierarchical classification
        return {
            'architecture_style': analysis.get('architecture_style'),
            'architecture_style_specific': analysis.get('architecture_style_specific'),
            'architecture_confidence': float(analysis.get('architecture_confidence', 0.0))
        }

    except Exception as e:
        print(f"    Classification error: {e}")
        return None


def update_property_via_crud(zpid, updates, dry_run=False):
    """
    Update property using CRUD API (PATCH /listings/{zpid})

    This preserves all embeddings and only updates specified fields!
    """
    if dry_run:
        print(f"    [DRY RUN] Would update {zpid}: {updates}")
        return {'success': True, 'dry_run': True}

    try:
        url = f"{CRUD_API_BASE}/listings/{zpid}?index={OS_INDEX}"

        payload = {
            "updates": updates,
            "options": {
                "preserve_embeddings": True  # Critical: don't regenerate embeddings!
            }
        }

        response = requests.patch(url, json=payload, timeout=30)
        response.raise_for_status()

        return {'success': True, 'response': response.json()}

    except Exception as e:
        print(f"    CRUD API error for {zpid}: {e}")
        return {'success': False, 'error': str(e)}


def process_property(zpid, dry_run=False):
    """
    Process single property:
    1. Get property data
    2. Get exterior image
    3. Classify architecture (hierarchical)
    4. Update via CRUD API if changed
    """
    print(f"\n  Processing {zpid}...")

    # Get property data
    property_data = get_property_data(zpid)
    if not property_data:
        return {'zpid': zpid, 'status': 'error', 'reason': 'fetch_failed'}

    # Check current architecture style
    current_style = property_data.get('architecture_style')
    current_specific = property_data.get('architecture_style_specific')
    current_conf = property_data.get('architecture_confidence', 0.0)

    print(f"    Current: style={current_style}, specific={current_specific}, conf={current_conf}")

    # Get exterior image
    image_url = get_exterior_image_url(property_data)
    if not image_url:
        return {'zpid': zpid, 'status': 'skipped', 'reason': 'no_image'}

    # Classify architecture
    classification = classify_architecture_hierarchical(image_url)
    if not classification:
        return {'zpid': zpid, 'status': 'error', 'reason': 'classification_failed'}

    new_style = classification['architecture_style']
    new_specific = classification['architecture_style_specific']
    new_conf = classification['architecture_confidence']

    print(f"    New:     style={new_style}, specific={new_specific}, conf={new_conf:.2f}")

    # Check if update needed
    if (new_style == current_style and
        new_specific == current_specific and
        abs(new_conf - current_conf) < 0.01):
        print(f"    ✓ No change needed")
        return {'zpid': zpid, 'status': 'unchanged'}

    # Update via CRUD API
    updates = {
        'architecture_style': new_style,
        'architecture_style_specific': new_specific,
        'architecture_confidence': new_conf
    }

    result = update_property_via_crud(zpid, updates, dry_run=dry_run)

    if result['success']:
        print(f"    ✓ Updated successfully")
        return {
            'zpid': zpid,
            'status': 'updated',
            'old': {'style': current_style, 'specific': current_specific, 'conf': current_conf},
            'new': {'style': new_style, 'specific': new_specific, 'conf': new_conf}
        }
    else:
        print(f"    ✗ Update failed: {result.get('error')}")
        return {'zpid': zpid, 'status': 'error', 'reason': 'update_failed'}


def main():
    parser = argparse.ArgumentParser(description='Update architectural styles via CRUD API')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of properties to process')
    parser.add_argument('--start-from', type=int, default=0, help='Start from index N')
    args = parser.parse_args()

    print("\n" + "="*80)
    print("🏛️  ARCHITECTURAL STYLE BATCH UPDATE (CRUD API)")
    print("="*80)
    print(f"\nMode: {'DRY RUN (no changes)' if args.dry_run else 'LIVE UPDATE'}")
    print(f"Method: CRUD API (PATCH /listings/{{zpid}})")
    print(f"Preserves: All embeddings and other fields\n")

    # Get all properties
    all_zpids = get_all_property_zpids()

    # Apply limits
    zpids_to_process = all_zpids[args.start_from:]
    if args.limit:
        zpids_to_process = zpids_to_process[:args.limit]

    print(f"\nProcessing {len(zpids_to_process)} properties (of {len(all_zpids)} total)")
    print(f"Starting from index: {args.start_from}\n")

    if not args.dry_run:
        confirm = input("⚠️  This will UPDATE properties. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return

    # Process in batches
    results = []
    costs = {'bedrock': 0.0, 'dynamodb': 0.0}

    for i in range(0, len(zpids_to_process), BATCH_SIZE):
        batch = zpids_to_process[i:i+BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(zpids_to_process) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"\n{'='*80}")
        print(f"BATCH {batch_num}/{total_batches} (ZPIDs {i+args.start_from} to {i+args.start_from+len(batch)})")
        print(f"{'='*80}")

        for zpid in batch:
            result = process_property(zpid, dry_run=args.dry_run)
            results.append(result)

            # Track costs
            if result['status'] in ['updated', 'unchanged']:
                costs['bedrock'] += BEDROCK_VISION_COST
                if result['status'] == 'updated':
                    costs['dynamodb'] += DYNAMODB_WRITE_COST

            time.sleep(0.5)  # Rate limiting

        # Sleep between batches
        if i + BATCH_SIZE < len(zpids_to_process):
            print(f"\n⏸️  Sleeping {SLEEP_BETWEEN_BATCHES}s before next batch...")
            time.sleep(SLEEP_BETWEEN_BATCHES)

    # Print summary
    print("\n\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)

    status_counts = Counter([r['status'] for r in results])
    print(f"\nResults:")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    print(f"\nCosts:")
    print(f"  Bedrock (vision): ${costs['bedrock']:.2f}")
    print(f"  DynamoDB (writes): ${costs['dynamodb']:.4f}")
    print(f"  Total: ${costs['bedrock'] + costs['dynamodb']:.2f}")

    # Style distribution
    updated = [r for r in results if r['status'] == 'updated']
    if updated:
        print(f"\nStyle Changes:")
        style_changes = Counter([r['new']['style'] for r in updated if r['new']['style']])
        for style, count in style_changes.most_common(10):
            print(f"  {style}: {count}")

    # Save detailed report
    report_file = f"architecture_update_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump({
            'config': {
                'dry_run': args.dry_run,
                'limit': args.limit,
                'start_from': args.start_from,
                'total_processed': len(results)
            },
            'summary': dict(status_counts),
            'costs': costs,
            'results': results
        }, f, indent=2)

    print(f"\n💾 Detailed report saved to: {report_file}")
    print("\n✓ Update complete!")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
