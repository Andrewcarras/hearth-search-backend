#!/usr/bin/env python3
"""
Smart batch update for architectural styles - only processes exterior images.

Strategy:
1. Only process properties that have exterior images
2. Selectively clear vision cache for exterior images to force re-analysis with new prompt
3. Use new hierarchical 60-style taxonomy with confidence scores
4. Update via CRUD API (preserve embeddings)

Usage:
    python update_architecture_smart.py --dry-run --limit 10  # Test first
    python update_architecture_smart.py                        # Full update
"""

import json
import sys
import time
import argparse
import requests
from collections import Counter
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
BATCH_SIZE = 25
SLEEP_BETWEEN_BATCHES = 3

# Cost tracking
BEDROCK_VISION_COST = 0.001125  # per image

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


def get_properties_with_exteriors():
    """
    Fetch properties that have at least one exterior image.
    Returns list of (zpid, exterior_image_url) tuples.
    """
    print("🔍 Finding properties with exterior images...")

    properties = []

    # Scroll through all properties
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

    while hits:
        for hit in hits:
            prop = hit['_source']
            zpid = prop.get('zpid')
            image_vectors = prop.get('image_vectors', [])

            # Find first exterior image
            for img in image_vectors:
                if img.get('image_type') == 'exterior':
                    properties.append({
                        'zpid': zpid,
                        'image_url': img.get('image_url'),
                        'current_style': prop.get('architecture_style')
                    })
                    break  # Only need one exterior per property

        # Get next batch
        response = os_client.scroll(scroll_id=scroll_id, scroll='5m')
        scroll_id = response['_scroll_id']
        hits = response['hits']['hits']

    print(f"✓ Found {len(properties)} properties with exterior images")
    return properties


def clear_vision_cache_for_image(image_url, dry_run=False):
    """Clear vision cache entry for specific image URL to force re-analysis."""
    if dry_run:
        return

    try:
        dynamodb.delete_item(
            TableName='hearth-vision-cache',
            Key={'image_url': {'S': image_url}}
        )
    except Exception as e:
        # Ignore if doesn't exist
        pass


def analyze_with_hierarchical_prompt(image_url):
    """
    Analyze property image with NEW hierarchical 60-style prompt.
    Returns architecture classification with confidence.
    """
    try:
        # Fetch image
        img_response = requests.get(image_url, timeout=10)
        img_response.raise_for_status()
        image_bytes = img_response.content

        # Convert to base64
        import base64
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        content_type = img_response.headers.get('content-type', 'image/jpeg')

        # NEW hierarchical prompt with 60 styles
        prompt = """Analyze this property photo. Return STRICT JSON format:
{
  "image_type": "exterior" or "interior",
  "architecture_style": "ranch" (Tier 1 broad style, or null if interior/unknown),
  "architecture_style_specific": "mid_century_ranch" (Tier 2 if very confident, else null),
  "architecture_confidence": 0.85 (numeric 0-1, only for exteriors)
}

ARCHITECTURE STYLES (60 total):

TIER 1 (Broad Categories - Use These When Unsure):
modern, contemporary, mid_century_modern, craftsman, ranch, colonial, victorian,
mediterranean, spanish_colonial_revival, tudor, farmhouse, cottage, bungalow,
cape_cod, split_level, traditional, transitional, industrial, minimalist,
prairie_style, mission_revival, pueblo_revival, log_cabin, a_frame,
scandinavian_modern, contemporary_farmhouse, arts_and_crafts

TIER 2 (Specific Sub-Styles - Only If Very Confident >85%):
victorian_queen_anne, victorian_italianate, victorian_gothic_revival,
craftsman_bungalow, craftsman_foursquare, colonial_revival, colonial_saltbox,
federal, georgian, tuscan_villa, french_provincial, french_country,
spanish_hacienda, monterey_colonial, english_cottage, french_chateau,
greek_revival, neoclassical, romanesque_revival, gothic_revival, beaux_arts,
art_deco, bauhaus, international_style, postmodern, modern_farmhouse,
rustic_modern, mid_century_ranch, mid_century_split_level

IMPORTANT:
- If interior photo: set architecture_style=null, architecture_confidence=0.0
- If exterior but unsure: use Tier 1 broad category only, leave architecture_style_specific=null
- Only use Tier 2 if you're very confident (>85%)
- Return ONLY valid JSON, no explanations"""

        # Call Claude
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": content_type,
                                "data": image_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }

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
            # Try to extract JSON
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(0))
            else:
                return None

        # Set defaults
        analysis.setdefault('architecture_style', None)
        analysis.setdefault('architecture_style_specific', None)
        analysis.setdefault('architecture_confidence', 0.0)

        return analysis

    except Exception as e:
        print(f"    ⚠️  Analysis error: {e}")
        return None


def update_property_via_crud(zpid, updates, dry_run=False):
    """Update property using CRUD API with preserve_embeddings."""
    if dry_run:
        return {'success': True, 'dry_run': True}

    try:
        url = f"{CRUD_API_BASE}/listings/{zpid}?index={OS_INDEX}"

        payload = {
            "updates": updates,
            "options": {
                "preserve_embeddings": True
            }
        }

        response = requests.patch(url, json=payload, timeout=30)
        response.raise_for_status()

        return {'success': True, 'response': response.json()}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def process_property(prop_data, clear_cache=False, dry_run=False):
    """
    Process single property:
    1. Optionally clear vision cache for exterior image
    2. Re-analyze with hierarchical prompt
    3. Update via CRUD API
    """
    zpid = prop_data['zpid']
    image_url = prop_data['image_url']
    current_style = prop_data['current_style']

    print(f"\n  🏠 {zpid}")
    print(f"      Current style: {current_style}")

    # Clear cache if requested (forces fresh analysis)
    if clear_cache:
        print(f"      Clearing cache for {image_url[:60]}...")
        clear_vision_cache_for_image(image_url, dry_run=dry_run)

    # Analyze with new hierarchical prompt
    analysis = analyze_with_hierarchical_prompt(image_url)

    if not analysis:
        print(f"      ❌ Analysis failed")
        return {'zpid': zpid, 'status': 'error', 'reason': 'analysis_failed'}

    new_style = analysis.get('architecture_style')
    new_specific = analysis.get('architecture_style_specific')
    new_conf = analysis.get('architecture_confidence', 0.0)

    print(f"      New: {new_style} | Specific: {new_specific} | Confidence: {new_conf:.2f}")

    # Update via CRUD API
    updates = {
        'architecture_style': new_style,
        'architecture_style_specific': new_specific,
        'architecture_confidence': new_conf
    }

    if dry_run:
        print(f"      [DRY RUN] Would update: {updates}")

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
    parser = argparse.ArgumentParser(description='Smart architectural style update (exterior images only)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of properties to process')
    parser.add_argument('--clear-cache', action='store_true', help='Clear vision cache to force re-analysis with new prompt')
    args = parser.parse_args()

    print("\n" + "="*80)
    print("🏛️  SMART ARCHITECTURAL STYLE UPDATE")
    print("="*80)
    print(f"\nMode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print(f"Strategy: Only process properties with EXTERIOR images")
    print(f"Clear cache: {'YES (force fresh analysis)' if args.clear_cache else 'NO (use cached if available)'}")
    print(f"Method: CRUD API (preserves embeddings)\n")

    # Get properties with exterior images
    properties = get_properties_with_exteriors()

    # Apply limit
    if args.limit:
        properties = properties[:args.limit]
        print(f"\n⚠️  Limited to first {args.limit} properties\n")

    # Estimate costs
    if args.clear_cache:
        estimated_cost = len(properties) * BEDROCK_VISION_COST
        print(f"💰 Estimated cost: ${estimated_cost:.2f} ({len(properties)} images × ${BEDROCK_VISION_COST})\n")

    if not args.dry_run:
        confirm = input(f"⚠️  This will update {len(properties)} properties. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return

    # Process in batches
    results = []
    total_cost = 0.0

    for i in range(0, len(properties), BATCH_SIZE):
        batch = properties[i:i+BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(properties) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"\n{'='*80}")
        print(f"BATCH {batch_num}/{total_batches}")
        print(f"{'='*80}")

        for prop_data in batch:
            result = process_property(prop_data, clear_cache=args.clear_cache, dry_run=args.dry_run)
            results.append(result)

            if result['status'] in ['updated', 'unchanged']:
                total_cost += BEDROCK_VISION_COST

            time.sleep(0.3)  # Rate limiting

        # Sleep between batches
        if i + BATCH_SIZE < len(properties):
            print(f"\n⏸️  Sleeping {SLEEP_BETWEEN_BATCHES}s...")
            time.sleep(SLEEP_BETWEEN_BATCHES)

    # Print summary
    print("\n\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)

    status_counts = Counter([r['status'] for r in results])
    print(f"\nResults:")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    print(f"\nActual cost: ${total_cost:.2f}")

    # Style distribution
    updated = [r for r in results if r['status'] == 'updated']
    if updated:
        print(f"\nNew Style Distribution:")
        styles = [r['new']['style'] for r in updated if r['new']['style']]
        style_counts = Counter(styles)
        for style, count in style_counts.most_common(10):
            print(f"  {style}: {count}")

        print(f"\nSpecific Styles (Tier 2):")
        specific = [r['new']['specific'] for r in updated if r['new'].get('specific')]
        if specific:
            specific_counts = Counter(specific)
            for style, count in specific_counts.most_common(5):
                print(f"  {style}: {count}")
        else:
            print(f"  (none - all broad categories)")

    # Save report
    report_file = f"architecture_smart_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
