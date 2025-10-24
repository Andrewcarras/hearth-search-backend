#!/usr/bin/env python3
"""
Fast batch update for architectural styles - uses pagination instead of scrolling.

This version:
1. Uses search_after pagination instead of scroll API (much faster)
2. Processes properties in chunks of 100
3. Supports starting from a specific offset (skip already processed)
4. Updates via CRUD API (preserves embeddings)

Usage:
    python update_architecture_fast.py --start 600 --limit 700  # Process 600-700
    python update_architecture_fast.py --start 700 --limit 800  # Process 700-800
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
FETCH_SIZE = 100  # Fetch properties in chunks

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


def get_properties_paginated(start_offset=0, limit=100):
    """
    Fetch properties using pagination (search_after) instead of scroll.
    Much faster and doesn't create hanging scroll contexts.
    """
    print(f"🔍 Fetching properties {start_offset} to {start_offset + limit}...")

    properties = []
    skip_count = 0

    # Build query with pagination
    query_body = {
        "query": {"match_all": {}},
        "_source": ["zpid", "image_vectors", "architecture_style"],
        "size": FETCH_SIZE,
        "sort": [{"zpid": "asc"}]  # Sort by zpid for consistent pagination
    }

    # Fetch in chunks
    while len(properties) < limit:
        response = os_client.search(index=OS_INDEX, body=query_body)
        hits = response['hits']['hits']

        if not hits:
            break

        for hit in hits:
            # Skip until we reach start_offset
            if skip_count < start_offset:
                skip_count += 1
                continue

            # Stop if we've reached the limit
            if len(properties) >= limit:
                break

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
                    break

        # Use search_after for next page
        if hits:
            last_sort = hits[-1]['sort']
            query_body['search_after'] = last_sort
        else:
            break

        # Stop if we have enough
        if len(properties) >= limit:
            break

    print(f"✓ Found {len(properties)} properties with exterior images")
    return properties


def clear_vision_cache_for_image(image_url, dry_run=False):
    """Clear vision cache entry for specific image URL to force re-analysis."""
    if dry_run:
        return

    try:
        # Delete from DynamoDB cache
        dynamodb.delete_item(
            TableName='vision-cache',
            Key={'image_url': {'S': image_url}}
        )
    except Exception as e:
        # Ignore if not found
        pass


def analyze_with_hierarchical_prompt(image_url):
    """
    Analyze image with new hierarchical 60-style prompt.
    Returns dict with: architecture_style, architecture_style_specific, architecture_confidence
    """
    import base64
    import urllib.request

    prompt = """Analyze this property photo. Return STRICT JSON format:
{
  "architecture_style": "ranch" (Tier 1 broad style),
  "architecture_style_specific": "mid_century_ranch" (Tier 2 if very confident),
  "architecture_confidence": 0.85 (numeric 0-1)
}

TIER 1 (Broad Categories - ALWAYS provide one):
modern, contemporary, mid_century_modern, craftsman, ranch, colonial, victorian,
mediterranean, spanish_colonial_revival, tudor, farmhouse, cottage, bungalow,
cape_cod, split_level, traditional, transitional, industrial, minimalist,
prairie_style, mission_revival, pueblo_revival, log_cabin, a_frame,
scandinavian_modern, contemporary_farmhouse, arts_and_crafts, cabin, mountain_modern, other

TIER 2 (Specific Sub-Styles - Only If Very Confident >85%):
victorian_queen_anne, victorian_italianate, victorian_gothic, craftsman_bungalow, craftsman_foursquare,
colonial_revival, federal, georgian, mid_century_ranch, ranch_raised, split_level_ranch,
tuscan_villa, spanish_hacienda, french_provincial, english_tudor, modern_farmhouse,
industrial_loft, mid_century_modern, contemporary_modern, minimalist_modern, etc.

RULES:
- architecture_style is REQUIRED (Tier 1 broad category)
- architecture_style_specific is OPTIONAL (only if confidence >85%)
- If unsure about specific style, set to null
- Return ONLY valid JSON, no markdown
"""

    try:
        # Download image and convert to base64
        with urllib.request.urlopen(image_url) as response:
            img_bytes = response.read()

        b64_image = base64.b64encode(img_bytes).decode("utf-8")

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64_image
                    }
                }, {
                    "type": "text",
                    "text": prompt
                }]
            }]
        }

        response = brt.invoke_model(
            modelId='us.anthropic.claude-3-haiku-20240307-v1:0',
            body=json.dumps(body)
        )

        result = json.loads(response['body'].read())
        content = result['content'][0]['text']

        # Parse JSON response
        analysis = json.loads(content)

        return {
            'architecture_style': analysis.get('architecture_style'),
            'architecture_style_specific': analysis.get('architecture_style_specific'),
            'architecture_confidence': float(analysis.get('architecture_confidence', 0.0))
        }

    except Exception as e:
        print(f"      ⚠️  Vision analysis error: {e}")
        return None


def update_property_via_crud(zpid, updates, dry_run=False):
    """Update property via CRUD API."""
    if dry_run:
        return {'success': True}

    try:
        url = f"{CRUD_API_BASE}/listings/{zpid}"
        payload = {
            "updates": updates,
            "preserve_embeddings": True
        }

        response = requests.patch(url, json=payload, timeout=10)

        if response.status_code == 200:
            return {'success': True}
        else:
            return {'success': False, 'error': f"HTTP {response.status_code}"}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def process_property(prop_data, clear_cache=False, dry_run=False):
    """Process a single property."""
    zpid = prop_data['zpid']
    image_url = prop_data['image_url']
    current_style = prop_data.get('current_style')

    print(f"\n  🏠 {zpid}")
    print(f"      Current style: {current_style or 'None'}")

    # Clear cache if requested
    if clear_cache:
        print(f"      Clearing cache for {image_url[:70]}...")
        clear_vision_cache_for_image(image_url, dry_run=dry_run)

    # Analyze with new prompt
    analysis = analyze_with_hierarchical_prompt(image_url)

    if not analysis:
        return {'zpid': zpid, 'status': 'error', 'reason': 'analysis_failed'}

    new_style = analysis.get('architecture_style')
    new_specific = analysis.get('architecture_style_specific')
    new_conf = analysis.get('architecture_confidence', 0.0)

    print(f"      New: {new_style} | Specific: {new_specific} | Confidence: {new_conf:.2f}")

    # Update via CRUD
    updates = {
        'architecture_style': new_style,
        'architecture_style_specific': new_specific,
        'architecture_confidence': new_conf
    }

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
    parser = argparse.ArgumentParser(description='Fast architectural style update with pagination')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating')
    parser.add_argument('--start', type=int, default=0, help='Start offset (skip this many properties)')
    parser.add_argument('--limit', type=int, default=100, help='Number of properties to process')
    parser.add_argument('--clear-cache', action='store_true', help='Clear vision cache to force re-analysis')
    args = parser.parse_args()

    print("\n" + "="*80)
    print("🏛️  FAST ARCHITECTURAL STYLE UPDATE (PAGINATION)")
    print("="*80)
    print(f"\nMode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print(f"Range: Properties {args.start} to {args.start + args.limit}")
    print(f"Clear cache: {'YES' if args.clear_cache else 'NO'}")
    print(f"Method: CRUD API (preserves embeddings)\n")

    # Get properties using pagination
    properties = get_properties_paginated(start_offset=args.start, limit=args.limit)

    if not properties:
        print("❌ No properties found in this range")
        return

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
    total_batches = (len(properties) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(properties))
        batch = properties[start_idx:end_idx]

        print(f"\n{'='*80}")
        print(f"BATCH {batch_num + 1}/{total_batches}")
        print(f"{'='*80}")

        for prop in batch:
            result = process_property(prop, clear_cache=args.clear_cache, dry_run=args.dry_run)
            results.append(result)

        if batch_num < total_batches - 1:
            print(f"\n⏸️  Sleeping {SLEEP_BETWEEN_BATCHES}s...")
            time.sleep(SLEEP_BETWEEN_BATCHES)

    # Summary
    print(f"\n{'='*80}")
    print("📊 SUMMARY")
    print(f"{'='*80}\n")

    status_counts = Counter(r['status'] for r in results)
    print("Results:")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    # Style distribution
    new_styles = [r['new']['style'] for r in results if r.get('new', {}).get('style')]
    if new_styles:
        style_dist = Counter(new_styles)
        print(f"\nNew Style Distribution:")
        for style, count in style_dist.most_common(10):
            print(f"  {style}: {count}")

    # Specific styles
    specific_styles = [r['new']['specific'] for r in results if r.get('new', {}).get('specific')]
    if specific_styles:
        specific_dist = Counter(specific_styles)
        print(f"\nSpecific Styles (Tier 2):")
        for style, count in specific_dist.most_common(10):
            print(f"  {style}: {count}")

    # Save report
    if not args.dry_run:
        actual_cost = len([r for r in results if r['status'] == 'updated']) * BEDROCK_VISION_COST
        print(f"\nActual cost: ${actual_cost:.2f}")

        report_file = f"architecture_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'range': f"{args.start}-{args.start + args.limit}",
                'results': results,
                'summary': dict(status_counts),
                'cost': actual_cost
            }, f, indent=2)

        print(f"\n💾 Report saved: {report_file}")

    print("\n✅ Update complete!")


if __name__ == '__main__':
    main()
