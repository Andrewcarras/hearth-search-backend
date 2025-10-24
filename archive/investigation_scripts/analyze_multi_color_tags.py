#!/usr/bin/env python3
"""
Analyze why properties have multiple exterior color tags
"""

import json
import os
from collections import Counter

# Set environment variables for OpenSearch connection
os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings')
os.environ.setdefault('AWS_REGION', 'us-east-1')

from common import os_client, OS_INDEX

def main():
    print("=" * 80)
    print("ANALYZING MULTI-COLOR EXTERIOR TAGS")
    print("=" * 80)
    print()

    # Get the "bad" zpids with full details
    bad_zpids = [12778555, 70592220]

    for zpid in bad_zpids:
        response = os_client.search(
            index=OS_INDEX,
            body={
                "query": {"term": {"zpid": zpid}},
                "_source": True,
                "size": 1
            }
        )

        if response['hits']['total']['value'] > 0:
            source = response['hits']['hits'][0]['_source']

            print(f"zpid {zpid} - {source.get('address', {}).get('streetAddress', 'Unknown')}")
            print("-" * 80)

            # Analyze feature_tags
            feature_tags = source.get('feature_tags', [])
            print(f"\nFeature Tags ({len(feature_tags)}):")
            if feature_tags:
                print(f"  {feature_tags}")
            else:
                print(f"  (empty)")

            # Analyze image_tags
            image_tags = source.get('image_tags', [])
            print(f"\nImage Tags ({len(image_tags)}):")

            # Group image tags by category
            exterior_tags = [t for t in image_tags if 'exterior' in t.lower()]
            color_tags = [t for t in image_tags if any(c in t.lower() for c in ['white', 'red', 'blue', 'gray', 'brown', 'tan', 'beige', 'black'])]

            print(f"\n  Exterior-related ({len(exterior_tags)}):")
            for tag in sorted(exterior_tags):
                print(f"    - {tag}")

            print(f"\n  Color-related ({len(color_tags)}):")
            for tag in sorted(color_tags)[:30]:
                print(f"    - {tag}")
            if len(color_tags) > 30:
                print(f"    ... and {len(color_tags) - 30} more")

            # Check for duplicate/variant tags
            print(f"\n  Tag Analysis:")

            # Look for "primary exterior color" tags
            primary_tags = [t for t in image_tags if 'primary' in t.lower() and 'exterior' in t.lower()]
            if primary_tags:
                print(f"    Primary exterior color tags: {primary_tags}")

            # Look for "exterior:" prefix tags
            prefix_tags = [t for t in image_tags if t.startswith('exterior:')]
            if prefix_tags:
                print(f"    'exterior:' prefix tags: {prefix_tags}")

            # Count distinct exterior colors
            colors = set()
            for tag in image_tags:
                for color in ['white', 'red', 'blue', 'gray', 'grey', 'brown', 'tan', 'beige', 'black', 'green', 'yellow']:
                    if f'{color} exterior' in tag.lower() or f'{color}_exterior' in tag.lower():
                        colors.add(color)

            print(f"    Distinct exterior colors found: {sorted(colors)}")

            print("\n" + "=" * 80 + "\n")

    # Statistical analysis
    print("STATISTICAL ANALYSIS:")
    print("-" * 80)

    # Sample 100 properties and count exterior color tags
    response = os_client.search(
        index=OS_INDEX,
        body={
            "size": 100,
            "query": {"match_all": {}},
            "_source": ["zpid", "feature_tags", "image_tags"]
        }
    )

    exterior_color_counts = Counter()
    properties_with_multiple_colors = 0
    total_properties = 0

    for hit in response['hits']['hits']:
        source = hit['_source']
        all_tags = source.get('feature_tags', []) + source.get('image_tags', [])

        # Find distinct exterior colors
        colors = set()
        for tag in all_tags:
            for color in ['white', 'red', 'blue', 'gray', 'grey', 'brown', 'tan', 'beige', 'black']:
                if f'{color} exterior' in tag.lower() or f'{color}_exterior' in tag.lower():
                    colors.add(color)

        color_count = len(colors)
        exterior_color_counts[color_count] += 1

        if color_count > 1:
            properties_with_multiple_colors += 1

        total_properties += 1

    print(f"\nSample of {total_properties} properties:")
    print(f"  Properties with 0 exterior colors: {exterior_color_counts[0]}")
    print(f"  Properties with 1 exterior color: {exterior_color_counts[1]}")
    print(f"  Properties with 2 exterior colors: {exterior_color_counts[2]}")
    print(f"  Properties with 3+ exterior colors: {sum(exterior_color_counts[i] for i in range(3, 10))}")
    print(f"  Total with multiple colors: {properties_with_multiple_colors} ({properties_with_multiple_colors/total_properties*100:.1f}%)")

    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
