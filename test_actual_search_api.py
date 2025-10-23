#!/usr/bin/env python3
"""
Test the actual search API to see scoring for "White homes" query
"""

import json
import os
import sys

# Set environment variables for OpenSearch connection
os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings')
os.environ.setdefault('AWS_REGION', 'us-east-1')

# Import the actual search handler
from search import lambda_handler

def main():
    print("=" * 80)
    print("TESTING ACTUAL SEARCH API FOR 'White homes'")
    print("=" * 80)
    print()

    # Create a test event
    event = {
        "body": json.dumps({
            "q": "White homes",
            "size": 20,
            "include_scoring_details": True,
            "target_index": "listings"
        })
    }

    context = None

    # Call the Lambda handler
    print("Calling search API...")
    response = lambda_handler(event, context)

    # Parse response
    body = json.loads(response['body'])

    print(f"Status: {response['statusCode']}")

    if response['statusCode'] != 200:
        print(f"ERROR: {body.get('error', 'Unknown error')}")
        print(f"Details: {body}")
        return

    print(f"Results found: {len(body.get('results', []))}")
    print()

    # Analyze top 20 results
    print("TOP 20 RESULTS:")
    print("-" * 80)

    for i, result in enumerate(body.get('results', [])[:20], 1):
        zpid = result.get('zpid')
        address = result.get('address', {})
        street = address.get('streetAddress', 'Unknown')

        # Get tags
        all_tags = result.get('feature_tags', []) + result.get('image_tags', [])
        exterior_tags = [t for t in all_tags if 'exterior' in t.lower() and any(color in t.lower() for color in ['white', 'red', 'blue', 'gray', 'brown', 'tan', 'beige', 'black'])]
        white_tags = [t for t in all_tags if 'white' in t.lower()]

        # Get scoring details
        scoring = result.get('scoring_details', {})
        rrf_score = scoring.get('final_rrf_score', 0)
        tag_boost = scoring.get('tag_boost_multiplier', 1.0)
        boosted_score = scoring.get('boosted_score', 0)

        bm25_info = scoring.get('bm25', {})
        knn_text_info = scoring.get('knn_text', {})
        knn_image_info = scoring.get('knn_image', {})

        print(f"\n{i}. zpid {zpid} - {street}")
        print(f"   Final Score: {boosted_score:.4f} (RRF: {rrf_score:.4f}, Tag Boost: {tag_boost:.2f}x)")

        # Show component scores
        if bm25_info:
            print(f"   BM25: rank={bm25_info.get('rank', 'N/A')}, original_score={bm25_info.get('original_score', 0):.4f}, RRF contrib={bm25_info.get('rrf_contribution', 0):.4f}")

        if knn_text_info:
            print(f"   kNN Text: rank={knn_text_info.get('rank', 'N/A')}, original_score={knn_text_info.get('original_score', 0):.4f}, RRF contrib={knn_text_info.get('rrf_contribution', 0):.4f}")

        if knn_image_info:
            print(f"   kNN Image: rank={knn_image_info.get('rank', 'N/A')}, original_score={knn_image_info.get('original_score', 0):.4f}, RRF contrib={knn_image_info.get('rrf_contribution', 0):.4f}")

        # Show tags
        print(f"   Exterior color tags: {exterior_tags if exterior_tags else 'NONE'}")
        print(f"   White-related tags ({len(white_tags)}): {white_tags[:5]}")

        # Highlight the "bad" zpids
        if zpid in [12778555, 70592220]:
            print(f"   *** THIS IS A 'BAD' ZPID ***")

    # Show adaptive k values
    print("\n" + "=" * 80)
    print("SEARCH CONFIGURATION:")
    print("-" * 80)
    if 'scoring_details' in body.get('results', [{}])[0]:
        first_result_scoring = body['results'][0]['scoring_details']
        print(f"BM25 k: {first_result_scoring.get('bm25', {}).get('k', 'N/A')}")
        print(f"kNN Text k: {first_result_scoring.get('knn_text', {}).get('k', 'N/A')}")
        print(f"kNN Image k: {first_result_scoring.get('knn_image', {}).get('k', 'N/A')}")

    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
