"""
test_multimodal_comparison.py - Compare text-only vs multimodal embeddings

This script tests whether multimodal embeddings actually improve search results
by comparing:
1. Text query → Text embeddings (old text-v2 model)
2. Text query → Multimodal embeddings (new image-v1 model)
3. How well each matches against image embeddings

The goal is to verify that using multimodal embeddings for text will enable
better cross-modal search (text query finding visually similar properties).
"""

import json
import os
import sys

# Set environment variables before importing common
os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings-v2')

sys.path.insert(0, '/Users/andrewcarras/hearth_backend_new')

from common import embed_text, embed_text_multimodal, embed_image_bytes, os_client
import requests
import math


def cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    return dot_product / (magnitude1 * magnitude2)


def test_query_comparison(query: str):
    """
    Test how a text query performs with both embedding models.

    Args:
        query: Search query to test (e.g., "modern home")
    """
    print("\n" + "="*80)
    print(f"TEST QUERY: '{query}'")
    print("="*80)

    # Generate embeddings for the query using both models (bypass cache)
    print("\n1. Generating query embeddings (bypassing cache for accuracy)...")

    # Directly call Bedrock to bypass cache
    import boto3
    import json
    brt = boto3.client("bedrock-runtime", region_name="us-east-1")

    # Text-only model (text-v2)
    body = json.dumps({"inputText": query})
    resp = brt.invoke_model(modelId="amazon.titan-embed-text-v2:0", body=body)
    text_only_embedding = json.loads(resp["body"].read().decode("utf-8"))["embedding"]

    # Multimodal model (image-v1)
    body = json.dumps({"inputText": query})
    resp = brt.invoke_model(modelId="amazon.titan-embed-image-v1", body=body)
    multimodal_embedding = json.loads(resp["body"].read().decode("utf-8"))["embedding"]

    print(f"   ✓ Text-only embedding (text-v2): {len(text_only_embedding)} dims")
    print(f"   ✓ Multimodal embedding (image-v1): {len(multimodal_embedding)} dims")

    # Check similarity between the two query embeddings
    query_similarity = cosine_similarity(text_only_embedding, multimodal_embedding)
    print(f"\n2. Query embedding similarity: {query_similarity:.4f}")
    print(f"   {'⚠️  Very different!' if query_similarity < 0.8 else '✓ Similar enough'}")

    # Search for properties using multimodal embedding on image vectors
    print(f"\n3. Searching for visually similar properties (kNN image search)...")
    knn_query = {
        "size": 5,
        "query": {
            "nested": {
                "path": "image_vectors",
                "query": {
                    "knn": {
                        "image_vectors.vector": {
                            "vector": multimodal_embedding,
                            "k": 50
                        }
                    }
                },
                "score_mode": "max",
                "inner_hits": {
                    "_source": False,
                    "size": 1
                }
            }
        },
        "_source": ["zpid", "description", "images", "visual_features_text", "architecture_style"]
    }

    response = os_client.search(index="listings-v2", body=knn_query)
    hits = response.get('hits', {}).get('hits', [])

    print(f"\n   Found {len(hits)} properties:")
    print("\n   " + "-"*76)

    for i, hit in enumerate(hits, 1):
        source = hit['_source']
        score = hit['_score']
        zpid = source.get('zpid', 'unknown')
        desc = source.get('description', 'No description')[:150]
        style = source.get('architecture_style', 'unknown')
        visual = source.get('visual_features_text', '')[:100]

        print(f"\n   {i}. ZPID: {zpid} | Score: {score:.4f} | Style: {style}")
        print(f"      Description: {desc}...")
        print(f"      Visual: {visual}...")

    # Now test with a sample property's image embedding
    print(f"\n4. Testing cross-modal similarity (query text vs property images)...")

    if hits:
        # Get the first property
        first_hit = hits[0]
        zpid = first_hit['_source'].get('zpid')

        # Get the full document to access image_vectors
        full_doc = os_client.get(index="listings-v2", id=zpid)
        image_vectors = full_doc['_source'].get('image_vectors', [])

        if image_vectors and len(image_vectors) > 0:
            # Test first image vector
            first_image_vec = image_vectors[0].get('vector', [])

            if first_image_vec:
                # Compare query embeddings to image embedding
                text_only_sim = cosine_similarity(text_only_embedding, first_image_vec)
                multimodal_sim = cosine_similarity(multimodal_embedding, first_image_vec)

                print(f"\n   Comparing query '{query}' to top result's first image:")
                print(f"   - Text-only (text-v2) → image similarity: {text_only_sim:.4f}")
                print(f"   - Multimodal (image-v1) → image similarity: {multimodal_sim:.4f}")
                print(f"   - Improvement: {(multimodal_sim - text_only_sim):.4f}")

                if multimodal_sim > text_only_sim:
                    print(f"\n   ✅ MULTIMODAL IS BETTER! (+{((multimodal_sim/text_only_sim - 1)*100):.1f}%)")
                else:
                    print(f"\n   ⚠️  Text-only performed better (unexpected)")
        else:
            print(f"\n   ⚠️  No image vectors found for zpid={zpid}")

    print("\n" + "="*80 + "\n")


def test_with_sample_image():
    """
    Test by downloading a real property image and comparing embeddings.
    """
    print("\n" + "="*80)
    print("TEST: Real Image Comparison")
    print("="*80)

    # Search for a property with images
    query = {
        "size": 1,
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "images"}},
                    {"exists": {"field": "image_vectors"}}
                ]
            }
        },
        "_source": ["zpid", "images", "description", "visual_features_text"]
    }

    response = os_client.search(index="listings-v2", body=query)
    hits = response.get('hits', {}).get('hits', [])

    if not hits:
        print("No properties with images found")
        return

    source = hits[0]['_source']
    zpid = source.get('zpid')
    images = source.get('images', [])
    description = source.get('description', '')
    visual_text = source.get('visual_features_text', '')

    if not images:
        print("No images available")
        return

    image_url = images[0]
    print(f"\n1. Testing with property zpid={zpid}")
    print(f"   Image: {image_url}")
    print(f"   Description: {description[:150]}...")

    # Download and embed the image
    print(f"\n2. Downloading and embedding image...")
    try:
        img_response = requests.get(image_url, timeout=10)
        img_bytes = img_response.content
        image_embedding = embed_image_bytes(img_bytes)
        print(f"   ✓ Image embedding: {len(image_embedding)} dims")
    except Exception as e:
        print(f"   ❌ Failed to download/embed image: {e}")
        return

    # Test different text queries against this image
    test_queries = [
        "modern home",
        "traditional house",
        "brick exterior",
        "open floor plan",
        visual_text[:50] if visual_text else "home"  # Use actual visual features
    ]

    print(f"\n3. Testing various queries against this image:")
    print("\n   " + "-"*76)

    results = []
    for query in test_queries:
        text_only_emb = embed_text(query)
        multimodal_emb = embed_text_multimodal(query)

        text_only_sim = cosine_similarity(text_only_emb, image_embedding)
        multimodal_sim = cosine_similarity(multimodal_emb, image_embedding)
        improvement = multimodal_sim - text_only_sim

        results.append({
            'query': query,
            'text_only': text_only_sim,
            'multimodal': multimodal_sim,
            'improvement': improvement
        })

        print(f"\n   Query: '{query}'")
        print(f"   - Text-only sim:  {text_only_sim:.4f}")
        print(f"   - Multimodal sim: {multimodal_sim:.4f}")
        print(f"   - Improvement:    {improvement:+.4f} ({(improvement/text_only_sim*100):+.1f}%)")

    # Summary
    avg_improvement = sum(r['improvement'] for r in results) / len(results)
    better_count = sum(1 for r in results if r['improvement'] > 0)

    print("\n" + "-"*80)
    print(f"\n4. SUMMARY:")
    print(f"   - Queries tested: {len(results)}")
    print(f"   - Multimodal better: {better_count}/{len(results)}")
    print(f"   - Average improvement: {avg_improvement:+.4f}")

    if better_count >= len(results) * 0.7:
        print(f"\n   ✅ MULTIMODAL EMBEDDINGS ARE SIGNIFICANTLY BETTER!")
    elif better_count > len(results) * 0.4:
        print(f"\n   ⚠️  Mixed results - multimodal sometimes better")
    else:
        print(f"\n   ❌ WARNING: Text-only performing better (unexpected)")

    print("\n" + "="*80 + "\n")


def main():
    print("\n" + "="*80)
    print("MULTIMODAL EMBEDDING COMPARISON TEST")
    print("="*80)
    print("\nThis test verifies whether using multimodal embeddings (image-v1) for")
    print("text queries will improve cross-modal search quality.\n")

    # Test with different query types
    test_queries = [
        "modern home",
        "traditional brick house",
        "open floor plan with kitchen"
    ]

    for query in test_queries:
        test_query_comparison(query)

    # Test with real image
    test_with_sample_image()

    print("\n" + "="*80)
    print("RECOMMENDATION:")
    print("="*80)
    print("\nReview the results above. If multimodal embeddings consistently show")
    print("better similarity scores with images, then proceed with re-embedding.")
    print("\nIf text-only performs better, we should reconsider the strategy.")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
