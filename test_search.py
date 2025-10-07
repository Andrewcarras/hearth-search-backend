#!/usr/bin/env python3
"""
Simple script to test the hearth-search Lambda function.

Usage:
    python3 test_search.py "your search query here"
    python3 test_search.py "3 bedroom house with pool under 500k"
"""

import json
import sys
import boto3

def search(query, size=10):
    """Invoke the hearth-search Lambda and display results."""
    client = boto3.client('lambda', region_name='us-east-1')

    payload = {
        "q": query,
        "size": size
    }

    print(f"Searching for: '{query}'")
    print("-" * 60)

    response = client.invoke(
        FunctionName='hearth-search',
        Payload=json.dumps(payload)
    )

    result = json.loads(response['Payload'].read())
    body = json.loads(result['body'])

    print(f"Found {body['total']} results")
    if body.get('must_have'):
        print(f"Must-have tags: {', '.join(body['must_have'])}")
    print()

    for i, listing in enumerate(body['results'], 1):
        print(f"{i}. {listing['address']}, {listing['city']}, {listing['state']}")
        print(f"   Price: ${listing['price']:,}" if listing.get('price') else "   Price: Not listed")
        print(f"   Beds: {listing.get('beds', 'N/A')} | Baths: {listing.get('baths', 'N/A')}")
        print(f"   Score: {listing['score']:.2f} {'(boosted ✓)' if listing.get('boosted') else ''}")
        if listing.get('feature_tags'):
            print(f"   Tags: {', '.join(listing['feature_tags'][:8])}")
        print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_search.py \"your search query\"")
        print("\nExamples:")
        print('  python3 test_search.py "3 bedroom house with pool"')
        print('  python3 test_search.py "modern home with mountain views"')
        print('  python3 test_search.py "house under 500k with garage"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    search(query)
