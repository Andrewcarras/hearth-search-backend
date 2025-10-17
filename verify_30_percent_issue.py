#!/usr/bin/env python3
"""
Verify the 30% missing data issue and get exact counts.
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


def get_aggregation_stats(client: OpenSearch):
    """Get aggregated statistics for all documents."""
    print("📊 Running Aggregation Queries...")

    # Total documents
    total = client.count(index=OS_INDEX)["count"]
    print(f"\n✅ Total Documents: {total:,}")

    # Documents with images
    query_with_images = {
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "images"}},
                    {"script": {
                        "script": "doc['images'].size() > 0"
                    }}
                ]
            }
        }
    }

    # Simplified query - check if images field exists and has content
    query_with_images = {
        "query": {
            "exists": {"field": "image_vectors"}
        }
    }

    with_images = client.count(index=OS_INDEX, body=query_with_images)["count"]
    print(f"✅ Documents with Image Vectors: {with_images:,} ({with_images/total*100:.1f}%)")

    # Documents WITHOUT images
    without_images = total - with_images
    print(f"⚠️  Documents WITHOUT Image Vectors: {without_images:,} ({without_images/total*100:.1f}%)")

    # Documents with image_tags
    query_with_tags = {
        "query": {
            "exists": {"field": "image_tags"}
        }
    }
    with_tags = client.count(index=OS_INDEX, body=query_with_tags)["count"]
    print(f"✅ Documents with Image Tags: {with_tags:,} ({with_tags/total*100:.1f}%)")

    # Documents with visual_features_text
    query_with_visual = {
        "query": {
            "exists": {"field": "visual_features_text"}
        }
    }
    with_visual = client.count(index=OS_INDEX, body=query_with_visual)["count"]
    print(f"✅ Documents with Visual Features Text: {with_visual:,} ({with_visual/total*100:.1f}%)")

    # Documents with architecture_style
    query_with_arch = {
        "query": {
            "exists": {"field": "architecture_style"}
        }
    }
    with_arch = client.count(index=OS_INDEX, body=query_with_arch)["count"]
    print(f"✅ Documents with Architecture Style: {with_arch:,} ({with_arch/total*100:.1f}%)")

    # Documents with price
    query_with_price = {
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "price"}},
                    {"range": {"price": {"gt": 0}}}
                ]
            }
        }
    }
    with_price = client.count(index=OS_INDEX, body=query_with_price)["count"]
    print(f"✅ Documents with Price: {with_price:,} ({with_price/total*100:.1f}%)")

    # Documents with bedrooms
    query_with_beds = {
        "query": {
            "exists": {"field": "bedrooms"}
        }
    }
    with_beds = client.count(index=OS_INDEX, body=query_with_beds)["count"]
    print(f"✅ Documents with Bedrooms: {with_beds:,} ({with_beds/total*100:.1f}%)")

    # Documents with ALL key fields (fully complete)
    query_fully_complete = {
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "image_vectors"}},
                    {"exists": {"field": "image_tags"}},
                    {"exists": {"field": "visual_features_text"}},
                    {"exists": {"field": "price"}},
                    {"exists": {"field": "bedrooms"}}
                ]
            }
        }
    }
    fully_complete = client.count(index=OS_INDEX, body=query_fully_complete)["count"]
    print(f"\n✅ Fully Complete Documents: {fully_complete:,} ({fully_complete/total*100:.1f}%)")

    # Documents missing ALL image-related fields
    query_no_images = {
        "query": {
            "bool": {
                "must_not": [
                    {"exists": {"field": "image_vectors"}},
                    {"exists": {"field": "image_tags"}},
                    {"exists": {"field": "visual_features_text"}}
                ]
            }
        }
    }
    no_images = client.count(index=OS_INDEX, body=query_no_images)["count"]
    print(f"⚠️  Documents with NO Image Data: {no_images:,} ({no_images/total*100:.1f}%)")

    # Summary
    print(f"\n{'='*60}")
    print("📋 SUMMARY")
    print(f"{'='*60}")
    print(f"Total: {total:,}")
    print(f"Complete (images + tags + price): {fully_complete:,} ({fully_complete/total*100:.1f}%)")
    print(f"Incomplete (missing images): {no_images:,} ({no_images/total*100:.1f}%)")
    print(f"Partially complete: {total - fully_complete - no_images:,} ({(total - fully_complete - no_images)/total*100:.1f}%)")


def sample_incomplete_documents(client: OpenSearch):
    """Sample and examine incomplete documents."""
    print(f"\n{'='*60}")
    print("🔍 SAMPLING INCOMPLETE DOCUMENTS")
    print(f"{'='*60}")

    query = {
        "size": 10,
        "query": {
            "bool": {
                "must_not": [
                    {"exists": {"field": "image_vectors"}}
                ]
            }
        },
        "_source": ["zpid", "description", "price", "bedrooms", "city", "state", "address"]
    }

    result = client.search(index=OS_INDEX, body=query)

    print(f"\nSample of {len(result['hits']['hits'])} documents WITHOUT image vectors:")

    for i, hit in enumerate(result["hits"]["hits"], 1):
        doc = hit["_source"]
        print(f"\n{i}. zpid: {doc.get('zpid')}")
        print(f"   City: {doc.get('city')}, {doc.get('state')}")
        print(f"   Price: {doc.get('price', 'None')}")
        print(f"   Bedrooms: {doc.get('bedrooms', 'None')}")
        desc = doc.get('description', '')
        print(f"   Description: {desc[:120] if desc else '(none)'}...")


def main():
    """Main execution function."""
    print("🔍 Verifying 30% Missing Data Issue...")
    print(f"   Index: {OS_INDEX}")

    # Connect to OpenSearch
    client = connect_opensearch()
    print("✅ Connected to OpenSearch\n")

    # Get aggregation statistics
    get_aggregation_stats(client)

    # Sample incomplete documents
    sample_incomplete_documents(client)

    print(f"\n{'='*60}")
    print("✅ VERIFICATION COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
