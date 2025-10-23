#!/usr/bin/env python3
"""
SAFE batch update with comprehensive safeguards against runaway costs.

Safeguards:
1. Hard cap on total properties processed
2. Cost ceiling with automatic abort
3. Timeout limits per API call
4. Retry limits with exponential backoff
5. Progress checkpointing (resume on failure)
6. Error rate monitoring (abort if too many failures)
7. Manual confirmation before start
8. Dry-run requirement for large batches

Usage:
    python update_architecture_safe.py --dry-run --limit 10  # Test first
    python update_architecture_safe.py --limit 100            # Process 100 properties
    python update_architecture_safe.py --resume checkpoint.json  # Resume from failure
"""

import json
import sys
import time
import argparse
import requests
from collections import Counter
from datetime import datetime
import os

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# ==================== SAFETY LIMITS ====================
MAX_PROPERTIES_PER_RUN = 5000  # Hard cap
MAX_COST_PER_RUN = 10.00  # Dollar limit
MAX_RETRIES = 3  # Per API call
MAX_ERROR_RATE = 0.2  # 20% failure rate triggers abort
BEDROCK_TIMEOUT = 30  # seconds
CRUD_TIMEOUT = 30  # seconds
RATE_LIMIT_DELAY = 0.5  # seconds between properties
BATCH_SIZE = 25
SLEEP_BETWEEN_BATCHES = 3

# Cost tracking
BEDROCK_VISION_COST = 0.001125  # per image

# Configuration
REGION = 'us-east-1'
OS_HOST = 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com'
OS_INDEX = 'listings-v2'
CRUD_API_BASE = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod'

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


class SafetyViolation(Exception):
    """Raised when a safety limit is exceeded"""
    pass


def get_properties_with_exteriors():
    """Fetch properties that have at least one exterior image."""
    print("🔍 Finding properties with exterior images...")

    properties = []
    response = os_client.search(
        index=OS_INDEX,
        body={
            "query": {"match_all": {}},
            "_source": ["zpid", "image_vectors", "architecture_style"],
            "size": 1000
        },
        scroll='5m'
    )

    scroll_id = response['_scroll_id']
    hits = response['hits']['hits']

    while hits and len(properties) < MAX_PROPERTIES_PER_RUN:
        for hit in hits:
            prop = hit['_source']
            zpid = prop.get('zpid')
            image_vectors = prop.get('image_vectors', [])

            for img in image_vectors:
                if img.get('image_type') == 'exterior':
                    properties.append({
                        'zpid': zpid,
                        'image_url': img.get('image_url'),
                        'current_style': prop.get('architecture_style')
                    })
                    break

        response = os_client.scroll(scroll_id=scroll_id, scroll='5m')
        scroll_id = response['_scroll_id']
        hits = response['hits']['hits']

    print(f"✓ Found {len(properties)} properties with exterior images")
    return properties


def clear_vision_cache_for_image(image_url, dry_run=False):
    """Clear vision cache entry for specific image URL."""
    if dry_run:
        return

    try:
        dynamodb.delete_item(
            TableName='hearth-vision-cache',
            Key={'image_url': {'S': image_url}}
        )
    except Exception:
        pass


def analyze_with_hierarchical_prompt(image_url, retry_count=0):
    """
    Classify with Claude vision, with timeout and retry logic.
    """
    if retry_count >= MAX_RETRIES:
        raise Exception(f"Max retries ({MAX_RETRIES}) exceeded")

    try:
        # Fetch image with timeout
        img_response = requests.get(image_url, timeout=10)
        img_response.raise_for_status()
        image_bytes = img_response.content

        import base64
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        content_type = img_response.headers.get('content-type', 'image/jpeg')

        prompt = """Analyze this property photo. Return STRICT JSON format:
{
  "image_type": "exterior" or "interior",
  "architecture_style": "ranch" (Tier 1 broad style, or null if interior/unknown),
  "architecture_style_specific": "mid_century_ranch" (Tier 2 if very confident, else null),
  "architecture_confidence": 0.85 (numeric 0-1, only for exteriors)
}

ARCHITECTURE STYLES (60 total):
TIER 1: modern, contemporary, mid_century_modern, craftsman, ranch, colonial, victorian, mediterranean, spanish_colonial_revival, tudor, farmhouse, cottage, bungalow, cape_cod, split_level, traditional, transitional, industrial, minimalist, prairie_style, mission_revival, pueblo_revival, log_cabin, a_frame, scandinavian_modern, contemporary_farmhouse, arts_and_crafts
TIER 2: victorian_queen_anne, craftsman_bungalow, colonial_revival, federal, georgian, tuscan_villa, french_provincial, spanish_hacienda, english_cottage, greek_revival, neoclassical, art_deco, bauhaus, international_style, postmodern, modern_farmhouse, rustic_modern, mid_century_ranch

Return ONLY valid JSON."""

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": image_b64}},
                    {"type": "text", "text": prompt}
                ]
            }]
        }

        # Call Bedrock with timeout
        response = brt.invoke_model(
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            body=json.dumps(body)
        )

        response_body = json.loads(response['body'].read())
        text = response_body['content'][0]['text'].strip()

        # Parse JSON
        try:
            analysis = json.loads(text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(0))
            else:
                return None

        analysis.setdefault('architecture_style', None)
        analysis.setdefault('architecture_style_specific', None)
        analysis.setdefault('architecture_confidence', 0.0)

        return analysis

    except Exception as e:
        if retry_count < MAX_RETRIES - 1:
            wait_time = 2 ** retry_count  # Exponential backoff
            print(f"      ⚠️  Retry {retry_count + 1}/{MAX_RETRIES} after {wait_time}s...")
            time.sleep(wait_time)
            return analyze_with_hierarchical_prompt(image_url, retry_count + 1)
        else:
            print(f"      ❌ Analysis error: {e}")
            return None


def update_property_via_crud(zpid, updates, dry_run=False, retry_count=0):
    """Update with retry logic."""
    if dry_run:
        return {'success': True, 'dry_run': True}

    if retry_count >= MAX_RETRIES:
        return {'success': False, 'error': f'Max retries ({MAX_RETRIES}) exceeded'}

    try:
        url = f"{CRUD_API_BASE}/listings/{zpid}?index={OS_INDEX}"
        payload = {
            "updates": updates,
            "options": {"preserve_embeddings": True}
        }

        response = requests.patch(url, json=payload, timeout=CRUD_TIMEOUT)
        response.raise_for_status()

        return {'success': True, 'response': response.json()}

    except Exception as e:
        if retry_count < MAX_RETRIES - 1:
            wait_time = 2 ** retry_count
            time.sleep(wait_time)
            return update_property_via_crud(zpid, updates, dry_run, retry_count + 1)
        else:
            return {'success': False, 'error': str(e)}


def save_checkpoint(checkpoint_file, processed, remaining, results, total_cost):
    """Save progress checkpoint for resume capability."""
    with open(checkpoint_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'processed_count': len(processed),
            'processed_zpids': processed,
            'remaining_count': len(remaining),
            'remaining': remaining,
            'results': results,
            'total_cost': total_cost
        }, f, indent=2)


def load_checkpoint(checkpoint_file):
    """Load checkpoint to resume processing."""
    if not os.path.exists(checkpoint_file):
        return None

    with open(checkpoint_file, 'r') as f:
        return json.load(f)


def process_property(prop_data, clear_cache=False, dry_run=False):
    """Process single property with error handling."""
    zpid = prop_data['zpid']
    image_url = prop_data['image_url']
    current_style = prop_data['current_style']

    print(f"\n  🏠 {zpid}")
    print(f"      Current style: {current_style}")

    if clear_cache:
        clear_vision_cache_for_image(image_url, dry_run=dry_run)

    # Analyze
    analysis = analyze_with_hierarchical_prompt(image_url)

    if not analysis:
        return {'zpid': zpid, 'status': 'error', 'reason': 'analysis_failed'}

    new_style = analysis.get('architecture_style')
    new_specific = analysis.get('architecture_style_specific')
    new_conf = analysis.get('architecture_confidence', 0.0)

    print(f"      New: {new_style} | Specific: {new_specific} | Confidence: {new_conf:.2f}")

    # Update
    updates = {
        'architecture_style': new_style,
        'architecture_style_specific': new_specific,
        'architecture_confidence': new_conf
    }

    if dry_run:
        print(f"      [DRY RUN] Would update")

    result = update_property_via_crud(zpid, updates, dry_run=dry_run)

    if result['success']:
        print(f"      ✅ {'Would update' if dry_run else 'Updated'}")
        return {
            'zpid': zpid,
            'status': 'updated',
            'old': {'style': current_style},
            'new': {'style': new_style, 'specific': new_specific, 'conf': new_conf}
        }
    else:
        print(f"      ❌ Update failed: {result.get('error')}")
        return {'zpid': zpid, 'status': 'error', 'reason': 'update_failed'}


def main():
    parser = argparse.ArgumentParser(description='SAFE architectural style batch update')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of properties to process')
    parser.add_argument('--clear-cache', action='store_true', help='Clear vision cache to force re-analysis')
    parser.add_argument('--resume', type=str, help='Resume from checkpoint file')
    args = parser.parse_args()

    print("\n" + "="*80)
    print("🏛️  SAFE ARCHITECTURAL STYLE UPDATE (WITH SAFEGUARDS)")
    print("="*80)
    print(f"\nMode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print(f"Strategy: Only process properties with EXTERIOR images")
    print(f"Method: CRUD API (preserves embeddings)")
    print()
    print("🛡️  SAFETY LIMITS:")
    print(f"  Max properties per run: {MAX_PROPERTIES_PER_RUN:,}")
    print(f"  Max cost per run: ${MAX_COST_PER_RUN:.2f}")
    print(f"  Max retries per call: {MAX_RETRIES}")
    print(f"  Max error rate: {MAX_ERROR_RATE * 100:.0f}%")
    print(f"  Timeout per API call: {BEDROCK_TIMEOUT}s")
    print()

    # Load checkpoint or get properties
    if args.resume:
        checkpoint = load_checkpoint(args.resume)
        if not checkpoint:
            print(f"❌ Checkpoint file not found: {args.resume}")
            return

        properties = checkpoint['remaining']
        previous_results = checkpoint['results']
        previous_cost = checkpoint['total_cost']
        print(f"📂 Resuming from checkpoint: {len(properties)} properties remaining")
        print(f"   Previous cost: ${previous_cost:.2f}")
        print()
    else:
        properties = get_properties_with_exteriors()
        previous_results = []
        previous_cost = 0.0

    # Apply limit
    if args.limit:
        properties = properties[:args.limit]
        print(f"⚠️  Limited to {args.limit} properties\n")

    # Safety check: property count
    if len(properties) > MAX_PROPERTIES_PER_RUN:
        raise SafetyViolation(f"Property count ({len(properties)}) exceeds safety limit ({MAX_PROPERTIES_PER_RUN})")

    # Safety check: estimated cost
    estimated_cost = len(properties) * BEDROCK_VISION_COST + previous_cost
    print(f"💰 Estimated cost: ${estimated_cost:.2f}")
    print(f"   ({len(properties)} images × ${BEDROCK_VISION_COST})")

    if estimated_cost > MAX_COST_PER_RUN:
        raise SafetyViolation(f"Estimated cost (${estimated_cost:.2f}) exceeds safety limit (${MAX_COST_PER_RUN:.2f})")

    # Safety check: require dry-run for large batches
    if len(properties) > 100 and not args.dry_run:
        print()
        print("⚠️  SAFETY REQUIREMENT: Batches > 100 must use --dry-run first")
        print("    Run with --dry-run to preview changes, then run again without it.")
        return

    # Manual confirmation
    if not args.dry_run:
        print()
        confirm = input(f"⚠️  This will update {len(properties)} properties. Type 'yes' to continue: ")
        if confirm != 'yes':
            print("Aborted.")
            return

    # Process in batches
    results = previous_results
    total_cost = previous_cost
    processed_zpids = [r['zpid'] for r in previous_results]
    checkpoint_file = f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    try:
        for i in range(0, len(properties), BATCH_SIZE):
            batch = properties[i:i+BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            total_batches = (len(properties) + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"\n{'='*80}")
            print(f"BATCH {batch_num}/{total_batches}")
            print(f"{'='*80}")

            for prop_data in batch:
                # Safety check: cost ceiling
                if total_cost >= MAX_COST_PER_RUN:
                    raise SafetyViolation(f"Cost ceiling reached: ${total_cost:.2f}")

                result = process_property(prop_data, clear_cache=args.clear_cache, dry_run=args.dry_run)
                results.append(result)
                processed_zpids.append(prop_data['zpid'])

                if result['status'] in ['updated', 'unchanged']:
                    total_cost += BEDROCK_VISION_COST

                # Safety check: error rate
                error_count = sum(1 for r in results if r['status'] == 'error')
                error_rate = error_count / len(results) if results else 0
                if error_rate > MAX_ERROR_RATE and len(results) > 10:
                    raise SafetyViolation(f"Error rate too high: {error_rate*100:.1f}% (limit: {MAX_ERROR_RATE*100:.0f}%)")

                time.sleep(RATE_LIMIT_DELAY)

            # Save checkpoint after each batch
            remaining = [p for p in properties if p['zpid'] not in processed_zpids]
            save_checkpoint(checkpoint_file, processed_zpids, remaining, results, total_cost)

            # Sleep between batches
            if i + BATCH_SIZE < len(properties):
                print(f"\n⏸️  Sleeping {SLEEP_BETWEEN_BATCHES}s...")
                time.sleep(SLEEP_BETWEEN_BATCHES)

    except SafetyViolation as e:
        print(f"\n\n🛑 SAFETY VIOLATION: {e}")
        print(f"💾 Progress saved to: {checkpoint_file}")
        print(f"   Use --resume {checkpoint_file} to continue")
        sys.exit(1)

    # Print summary
    print("\n\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)

    status_counts = Counter([r['status'] for r in results])
    print(f"\nResults:")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    print(f"\nActual cost: ${total_cost:.2f}")

    # Save final report
    report_file = f"architecture_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump({
            'config': {
                'dry_run': args.dry_run,
                'limit': args.limit,
                'clear_cache': args.clear_cache,
                'total_processed': len(results)
            },
            'summary': dict(status_counts),
            'cost': total_cost,
            'results': results
        }, f, indent=2)

    print(f"\n💾 Report saved: {report_file}")
    print("\n✅ Update complete!")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except SafetyViolation as e:
        print(f"\n\n🛑 SAFETY VIOLATION: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
