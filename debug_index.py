#!/usr/bin/env python3
"""
Debug script to inspect the OpenSearch index and diagnose why search returns 0 results.

This script:
1. Checks if the index exists
2. Gets total document count
3. Retrieves sample documents
4. Verifies document structure and field values
"""

import json
from common import os_client, OS_INDEX

print(f"Inspecting OpenSearch index: {OS_INDEX}\n")

# 1. Check if index exists
try:
    exists = os_client.indices.exists(index=OS_INDEX)
    print(f"Index exists: {exists}")
    if not exists:
        print("ERROR: Index does not exist!")
        exit(1)
except Exception as e:
    print(f"ERROR checking index existence: {e}")
    exit(1)

# 2. Get index stats
try:
    stats = os_client.indices.stats(index=OS_INDEX)
    doc_count = stats['_all']['primaries']['docs']['count']
    print(f"Total documents in index: {doc_count}\n")
    if doc_count == 0:
        print("ERROR: Index is empty! No documents uploaded.")
        exit(1)
except Exception as e:
    print(f"ERROR getting index stats: {e}")
    exit(1)

# 3. Get sample documents (no filters)
try:
    print("Fetching 5 sample documents...\n")
    response = os_client.search(
        index=OS_INDEX,
        body={
            "size": 5,
            "query": {"match_all": {}}
        }
    )
    hits = response.get('hits', {}).get('hits', [])
    print(f"Found {len(hits)} documents\n")

    for i, hit in enumerate(hits):
        src = hit.get('_source', {})
        print(f"Document {i+1} (ID: {hit['_id']}):")
        print(f"  address: {src.get('address')}")
        print(f"  city: {src.get('city')}")
        print(f"  state: {src.get('state')}")
        print(f"  price: {src.get('price')}")
        print(f"  beds: {src.get('beds')}")
        print(f"  baths: {src.get('baths')}")
        print(f"  has_valid_embeddings: {src.get('has_valid_embeddings')}")
        print(f"  has_description: {src.get('has_description')}")
        print(f"  description length: {len(src.get('description', ''))}")
        print(f"  feature_tags count: {len(src.get('feature_tags', []))}")
        print(f"  image_tags count: {len(src.get('image_tags', []))}")

        # Check vector fields
        vec_text = src.get('vector_text')
        vec_img = src.get('vector_image')
        print(f"  vector_text: {'present' if vec_text else 'MISSING'} ({len(vec_text) if vec_text else 0} dims)")
        print(f"  vector_image: {'present' if vec_img else 'MISSING'} ({len(vec_img) if vec_img else 0} dims)")

        # Check if vectors are all zeros
        if vec_text:
            all_zero = all(v == 0.0 for v in vec_text)
            print(f"  vector_text all zeros: {all_zero}")
        if vec_img:
            all_zero = all(v == 0.0 for v in vec_img)
            print(f"  vector_image all zeros: {all_zero}")
        print()

except Exception as e:
    print(f"ERROR fetching documents: {e}")
    exit(1)

# 4. Test a simple query
print("\nTesting simple match_all query with price filter...")
try:
    response = os_client.search(
        index=OS_INDEX,
        body={
            "size": 5,
            "query": {
                "bool": {
                    "filter": [
                        {"range": {"price": {"gt": 0}}}
                    ]
                }
            }
        }
    )
    count = len(response.get('hits', {}).get('hits', []))
    print(f"Documents with price > 0: {count}")
except Exception as e:
    print(f"ERROR with price filter query: {e}")

# 5. Test has_valid_embeddings filter
print("\nTesting has_valid_embeddings filter...")
try:
    response = os_client.search(
        index=OS_INDEX,
        body={
            "size": 5,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"has_valid_embeddings": True}}
                    ]
                }
            }
        }
    )
    count = len(response.get('hits', {}).get('hits', []))
    print(f"Documents with has_valid_embeddings=true: {count}")
except Exception as e:
    print(f"ERROR with has_valid_embeddings filter: {e}")

# 6. Test BM25 text search
print("\nTesting BM25 search with query 'house'...")
try:
    response = os_client.search(
        index=OS_INDEX,
        body={
            "size": 5,
            "query": {
                "multi_match": {
                    "query": "house",
                    "fields": ["description", "llm_profile", "address"]
                }
            }
        }
    )
    count = len(response.get('hits', {}).get('hits', []))
    print(f"BM25 matches for 'house': {count}")
    if count > 0:
        print(f"Top match score: {response['hits']['hits'][0]['_score']}")
except Exception as e:
    print(f"ERROR with BM25 query: {e}")

print("\n=== Debug complete ===")
