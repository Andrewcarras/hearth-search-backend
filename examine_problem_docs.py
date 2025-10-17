#!/usr/bin/env python3
"""
Examine specific problematic documents in detail.
"""

import json
import os
import sys

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
OS_HOST = os.getenv("OS_HOST")
OS_INDEX = os.getenv("OS_INDEX", "listings-v2")

# Problematic zpids from audit
PROBLEM_ZPIDS = [
    "455935885",  # Missing price, bedrooms, images
    "456027144",  # Short description
    "12770115",   # Good example for comparison
]


def connect_opensearch():
    """Connect to OpenSearch with AWS auth."""
    host = OS_HOST.replace("https://", "").replace("http://", "")
    session = boto3.Session(region_name=AWS_REGION)
    creds = session.get_credentials().get_frozen_credentials()

    awsauth = AWS4Auth(
        creds.access_key,
        creds.secret_key,
        AWS_REGION,
        "es",
        session_token=creds.token
    )

    client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60
    )

    return client


def examine_document(client: OpenSearch, zpid: str):
    """Examine a specific document in detail."""
    print(f"\n{'='*80}")
    print(f"📄 EXAMINING ZPID: {zpid}")
    print(f"{'='*80}")

    try:
        result = client.get(index=OS_INDEX, id=zpid)
        doc = result["_source"]

        # Basic info
        print(f"\n✅ FOUND")
        print(f"   Status: {doc.get('status', 'unknown')}")
        print(f"   Has Valid Embeddings: {doc.get('has_valid_embeddings', False)}")
        print(f"   Has Description Flag: {doc.get('has_description', 'N/A')}")

        # Text content
        print(f"\n📝 TEXT CONTENT:")
        desc = doc.get("description", "")
        print(f"   Description ({len(desc)} chars): {desc[:200] if desc else '(MISSING)'}...")

        visual = doc.get("visual_features_text", "")
        print(f"   Visual Features ({len(visual)} chars): {visual[:200] if visual else '(MISSING)'}...")

        llm_profile = doc.get("llm_profile", "")
        print(f"   LLM Profile: {llm_profile[:100] if llm_profile else '(empty - expected)'}...")

        # Embeddings
        print(f"\n🔍 EMBEDDINGS:")
        text_vec = doc.get("vector_text")
        if text_vec:
            vec_sum = sum(abs(v) for v in text_vec)
            print(f"   Text Vector: {len(text_vec)} dims, sum={vec_sum:.4f}")
        else:
            print(f"   Text Vector: MISSING")

        image_vecs = doc.get("image_vectors", [])
        if image_vecs:
            print(f"   Image Vectors: {len(image_vecs)} vectors")
            for i, img_data in enumerate(image_vecs[:3]):
                vec = img_data.get("vector", [])
                img_type = img_data.get("image_type", "unknown")
                img_url = img_data.get("image_url", "")
                vec_sum = sum(abs(v) for v in vec) if vec else 0
                print(f"      [{i}] {img_type}, {len(vec)} dims, sum={vec_sum:.4f}")
                print(f"          URL: {img_url[:60]}...")
            if len(image_vecs) > 3:
                print(f"      ... and {len(image_vecs) - 3} more")
        else:
            print(f"   Image Vectors: MISSING")

        # Tags
        print(f"\n🏷️  TAGS:")
        feature_tags = doc.get("feature_tags", [])
        print(f"   Feature Tags ({len(feature_tags)}): {feature_tags[:10] if feature_tags else '(empty - expected)'}...")

        image_tags = doc.get("image_tags", [])
        print(f"   Image Tags ({len(image_tags)}): {image_tags[:20] if image_tags else '(MISSING)'}...")

        arch_style = doc.get("architecture_style")
        print(f"   Architecture Style: {arch_style or '(MISSING)'}")

        # Metadata
        print(f"\n📊 METADATA:")
        print(f"   Price: {doc.get('price', 'MISSING')}")
        print(f"   Bedrooms: {doc.get('bedrooms', 'MISSING')}")
        print(f"   Bathrooms: {doc.get('bathrooms', 'MISSING')}")
        print(f"   Living Area: {doc.get('livingArea', 'MISSING')} sqft")

        address = doc.get("address", {})
        if isinstance(address, dict):
            print(f"   Address: {address.get('streetAddress', 'MISSING')}")
            print(f"   City: {address.get('city', 'MISSING')}")
            print(f"   State: {address.get('state', 'MISSING')}")
            print(f"   Zip: {address.get('zipcode', 'MISSING')}")
        else:
            print(f"   Address: {address}")

        geo = doc.get("geo")
        print(f"   Geo: {geo if geo else 'MISSING'}")

        images = doc.get("images", [])
        print(f"   Images: {len(images)} URLs")
        if images:
            for i, url in enumerate(images[:3]):
                print(f"      [{i}] {url[:80]}...")
            if len(images) > 3:
                print(f"      ... and {len(images) - 3} more")

        # Timestamps
        print(f"\n⏰ TIMESTAMPS:")
        print(f"   Indexed At: {doc.get('indexed_at', 'N/A')}")
        print(f"   Updated At: {doc.get('updated_at', 'N/A')}")

        # Full document structure
        print(f"\n📋 DOCUMENT FIELDS:")
        all_fields = list(doc.keys())
        print(f"   Total Fields: {len(all_fields)}")
        print(f"   Fields: {', '.join(sorted(all_fields))}")

    except Exception as e:
        print(f"❌ ERROR: {e}")


def main():
    """Main execution function."""
    print("🔍 Examining Problematic Documents...")

    # Connect to OpenSearch
    client = connect_opensearch()
    print("✅ Connected to OpenSearch")

    # Examine each problem document
    for zpid in PROBLEM_ZPIDS:
        examine_document(client, zpid)

    # Get random sample of documents with missing data
    print(f"\n{'='*80}")
    print("📊 SAMPLING DOCUMENTS WITH MISSING TAGS")
    print(f"{'='*80}")

    query = {
        "size": 5,
        "query": {
            "bool": {
                "must_not": [
                    {"exists": {"field": "image_tags"}}
                ]
            }
        }
    }

    result = client.search(index=OS_INDEX, body=query)
    print(f"\nFound {result['hits']['total']['value']} documents with missing image_tags")
    print(f"Examining first 5:")

    for hit in result["hits"]["hits"]:
        zpid = hit["_source"].get("zpid", "unknown")
        images = hit["_source"].get("images", [])
        print(f"\n   zpid: {zpid}")
        print(f"   Has images field: {len(images) > 0}")
        print(f"   Image count: {len(images)}")
        if images:
            print(f"   First image: {images[0][:80]}...")


if __name__ == "__main__":
    main()
