#!/usr/bin/env python3
"""
Investigate OpenSearch data for specific properties to understand:
1. When they were last indexed/updated
2. What tags they have (especially exterior color tags)
3. Why multi-color properties rank higher than pure white properties
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any

# Set environment variables for OpenSearch connection
os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings')
os.environ.setdefault('AWS_REGION', 'us-east-1')

from common import os_client, OS_INDEX, embed_text_multimodal

def get_property_by_zpid(zpid: int) -> Dict[str, Any]:
    """Get property document from OpenSearch by zpid"""
    try:
        response = os_client.search(
            index=OS_INDEX,
            body={
                "query": {
                    "term": {"zpid": zpid}
                },
                "_source": True,
                "size": 1
            }
        )

        if response['hits']['total']['value'] > 0:
            return response['hits']['hits'][0]
        return None
    except Exception as e:
        print(f"Error fetching zpid {zpid}: {e}")
        return None

def analyze_tags(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze tags in a document"""
    source = doc['_source']

    analysis = {
        'zpid': source.get('zpid'),
        'address': source.get('address'),
        'indexed_at': source.get('indexed_at'),
        'updated_at': source.get('updated_at'),
        'feature_tags': [],
        'image_tags': [],
        'exterior_color_tags': [],
        'white_related_tags': [],
        'has_white_exterior': False,
        'exterior_color_count': 0
    }

    # Analyze feature_tags
    feature_tags = source.get('feature_tags', [])
    analysis['feature_tags'] = feature_tags

    # Analyze image_tags
    image_tags = source.get('image_tags', [])
    analysis['image_tags'] = image_tags

    # Find all exterior color tags and white-related tags
    all_tags = feature_tags + image_tags
    exterior_colors = []
    white_related = []
    for tag in all_tags:
        if '_exterior' in tag:
            exterior_colors.append(tag)
            if tag == 'white_exterior':
                analysis['has_white_exterior'] = True
        if 'white' in tag.lower():
            white_related.append(tag)

    analysis['exterior_color_tags'] = list(set(exterior_colors))
    analysis['white_related_tags'] = list(set(white_related))
    analysis['exterior_color_count'] = len(analysis['exterior_color_tags'])

    return analysis

def search_white_homes(query: str = "White homes", size: int = 20) -> List[Dict[str, Any]]:
    """Search for white homes using simple text search"""

    # Execute simple BM25 text search
    response = os_client.search(
        index=OS_INDEX,
        body={
            "size": size,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "description^3",
                        "feature_tags^2",
                        "image_tags^2",
                        "address"
                    ],
                    "type": "best_fields",
                    "operator": "or"
                }
            },
            "_source": ["zpid", "address", "feature_tags", "image_tags", "indexed_at", "updated_at"]
        }
    )

    results = []
    for hit in response['hits']['hits']:
        result = {
            'zpid': hit['_source']['zpid'],
            'address': hit['_source'].get('address'),
            'score': hit['_score'],
            'feature_tags': hit['_source'].get('feature_tags', []),
            'image_tags': hit['_source'].get('image_tags', []),
            'indexed_at': hit['_source'].get('indexed_at'),
            'updated_at': hit['_source'].get('updated_at')
        }

        # Analyze exterior colors
        all_tags = result['feature_tags'] + result['image_tags']
        exterior_colors = [tag for tag in all_tags if '_exterior' in tag]
        result['exterior_colors'] = list(set(exterior_colors))
        result['has_white_exterior'] = 'white_exterior' in result['exterior_colors']

        results.append(result)

    return results

def find_pure_white_properties(size: int = 10) -> List[Dict[str, Any]]:
    """Find properties that have ONLY white_exterior tag (no other color exteriors)"""

    # Get properties with white_exterior tag
    response = os_client.search(
        index=OS_INDEX,
        body={
            "size": 100,  # Get more to filter
            "query": {
                "bool": {
                    "should": [
                        {"term": {"feature_tags": "white_exterior"}},
                        {"term": {"image_tags": "white_exterior"}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "_source": ["zpid", "address", "feature_tags", "image_tags", "indexed_at", "updated_at"]
        }
    )

    pure_white = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        all_tags = source.get('feature_tags', []) + source.get('image_tags', [])
        exterior_colors = [tag for tag in all_tags if '_exterior' in tag]

        # Only include if the ONLY exterior color is white
        if exterior_colors == ['white_exterior']:
            pure_white.append({
                'zpid': source['zpid'],
                'address': source.get('address'),
                'feature_tags': source.get('feature_tags', []),
                'image_tags': source.get('image_tags', []),
                'indexed_at': source.get('indexed_at'),
                'updated_at': source.get('updated_at'),
                'exterior_colors': exterior_colors
            })

    return pure_white[:size]

def format_timestamp(ts) -> str:
    """Format timestamp to show how long ago it was"""
    if not ts:
        return "N/A"

    try:
        # Check if it's a Unix timestamp (integer or numeric string)
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str) and ts.isdigit():
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        else:
            # Try to parse as ISO timestamp
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))

        now = datetime.now(timezone.utc)
        diff = now - dt

        hours = diff.total_seconds() / 3600
        if hours < 1:
            return f"{int(diff.total_seconds() / 60)} minutes ago ({dt.strftime('%Y-%m-%d %H:%M:%S UTC')})"
        elif hours < 24:
            return f"{int(hours)} hours ago ({dt.strftime('%Y-%m-%d %H:%M:%S UTC')})"
        else:
            return f"{int(hours / 24)} days ago ({dt.strftime('%Y-%m-%d %H:%M:%S UTC')})"
    except Exception as e:
        return f"{ts} (parse error: {e})"

def main():
    print("=" * 80)
    print("INVESTIGATING OPENSEARCH PROPERTY DATA")
    print("=" * 80)
    print()

    # Part 1: Analyze the "bad" zpids (multi-color houses ranking high)
    print("PART 1: ANALYZING 'BAD' ZPIDS (Multi-color houses ranking high)")
    print("-" * 80)

    bad_zpids = [12778555, 70592220]
    bad_analyses = []

    for zpid in bad_zpids:
        print(f"\nFetching zpid {zpid}...")
        doc = get_property_by_zpid(zpid)
        if doc:
            analysis = analyze_tags(doc)
            bad_analyses.append(analysis)

            print(f"  Address: {analysis['address']}")
            print(f"  Indexed at: {format_timestamp(analysis['indexed_at'])}")
            print(f"  Updated at: {format_timestamp(analysis['updated_at'])}")
            print(f"  Has white_exterior: {analysis['has_white_exterior']}")
            print(f"  Exterior colors ({len(analysis['exterior_color_tags'])}): {', '.join(analysis['exterior_color_tags']) if analysis['exterior_color_tags'] else 'NONE'}")
            print(f"  White-related tags ({len(analysis['white_related_tags'])}): {', '.join(analysis['white_related_tags']) if analysis['white_related_tags'] else 'NONE'}")
            print(f"  Total feature_tags: {len(analysis['feature_tags'])}")
            print(f"  Total image_tags: {len(analysis['image_tags'])}")
            print(f"  Sample feature_tags: {', '.join(analysis['feature_tags'][:5])}{'...' if len(analysis['feature_tags']) > 5 else ''}")
            print(f"  Sample image_tags: {', '.join(analysis['image_tags'][:5])}{'...' if len(analysis['image_tags']) > 5 else ''}")
        else:
            print(f"  NOT FOUND in OpenSearch")

    # Part 2: Find pure white properties
    print("\n" + "=" * 80)
    print("PART 2: FINDING PURE WHITE PROPERTIES")
    print("-" * 80)

    pure_white = find_pure_white_properties(10)
    print(f"\nFound {len(pure_white)} properties with ONLY white_exterior tag:\n")

    for prop in pure_white[:5]:
        print(f"  zpid: {prop['zpid']}")
        print(f"    Address: {prop['address']}")
        print(f"    Indexed: {format_timestamp(prop['indexed_at'])}")
        print(f"    Exterior colors: {', '.join(prop['exterior_colors'])}")
        print()

    # Part 3: Search for "White homes" and analyze results
    print("=" * 80)
    print("PART 3: SEARCHING FOR 'White homes' - TOP 20 RESULTS")
    print("-" * 80)

    search_results = search_white_homes("White homes", 20)

    print(f"\nFound {len(search_results)} results. Analyzing top 20:\n")

    for i, result in enumerate(search_results[:20], 1):
        print(f"{i}. zpid: {result['zpid']} (score: {result['score']:.4f})")
        print(f"   Address: {result['address']}")
        print(f"   Has white_exterior: {result['has_white_exterior']}")
        print(f"   Exterior colors ({len(result['exterior_colors'])}): {', '.join(result['exterior_colors'])}")
        print(f"   Indexed: {format_timestamp(result['indexed_at'])}")

        # Highlight if this is one of the "bad" zpids
        if result['zpid'] in bad_zpids:
            print(f"   *** THIS IS A 'BAD' ZPID ***")

        print()

    # Part 4: Summary comparison
    print("=" * 80)
    print("PART 4: SUMMARY COMPARISON")
    print("-" * 80)

    # Count multi-color vs pure white in top 20
    multi_color_in_top20 = sum(1 for r in search_results[:20] if len(r['exterior_colors']) > 1)
    pure_white_in_top20 = sum(1 for r in search_results[:20] if r['exterior_colors'] == ['white_exterior'])
    white_tagged_in_top20 = sum(1 for r in search_results[:20] if r['has_white_exterior'])

    print(f"\nIn top 20 results for 'White homes':")
    print(f"  - Properties with white_exterior tag: {white_tagged_in_top20}")
    print(f"  - Pure white (ONLY white_exterior): {pure_white_in_top20}")
    print(f"  - Multi-color (white + other colors): {multi_color_in_top20}")
    print(f"  - No white tag at all: {20 - white_tagged_in_top20}")

    # Show positions of bad zpids
    print(f"\nPositions of 'bad' zpids in search results:")
    for zpid in bad_zpids:
        positions = [i+1 for i, r in enumerate(search_results) if r['zpid'] == zpid]
        if positions:
            print(f"  - zpid {zpid}: position {positions[0]}")
        else:
            print(f"  - zpid {zpid}: NOT in top 20")

    # Show top pure white property position
    if pure_white:
        top_pure_zpid = pure_white[0]['zpid']
        positions = [i+1 for i, r in enumerate(search_results) if r['zpid'] == top_pure_zpid]
        if positions:
            print(f"\nFirst pure white property (zpid {top_pure_zpid}):")
            print(f"  - Position in search results: {positions[0]}")
        else:
            print(f"\nFirst pure white property (zpid {top_pure_zpid}):")
            print(f"  - NOT in top 20 search results")

    print("\n" + "=" * 80)
    print("INVESTIGATION COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
