"""
Test cache behavior with real description that might already be cached
"""
import os
import sys
import math

os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings-v2')

sys.path.insert(0, '/Users/andrewcarras/hearth_backend_new')

from common import embed_text, embed_text_multimodal, os_client

def cosine_similarity(vec1, vec2):
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    return dot_product / (magnitude1 * magnitude2)

# Get a real description from the index
print("Fetching a real listing description...")
response = os_client.search(
    index="listings-v2",
    body={
        "size": 1,
        "query": {"bool": {"must": [{"exists": {"field": "description"}}]}},
        "_source": ["zpid", "description"]
    }
)

hit = response['hits']['hits'][0]
zpid = hit['_source']['zpid']
description = hit['_source']['description'][:200]  # Use first 200 chars

print(f"ZPID: {zpid}")
print(f"Description: {description}...\n")

print("=" * 80)
print("TEST 1: Get embeddings with both models")
print("=" * 80)

# This might hit old cache (text_hash without model)
print("\n1. Calling embed_text() (text-v2)...")
text_v2_emb = embed_text(description)
print(f"   ✓ Got embedding: {len(text_v2_emb)} dims")

# This should NOT hit old cache (looks for text_hash#model)
print("\n2. Calling embed_text_multimodal() (image-v1)...")
multimodal_emb = embed_text_multimodal(description)
print(f"   ✓ Got embedding: {len(multimodal_emb)} dims")

# Calculate similarity
similarity = cosine_similarity(text_v2_emb, multimodal_emb)
print(f"\n3. Similarity: {similarity:.4f}")

if similarity > 0.9:
    print("   ❌ FAIL: Too similar - likely SAME embedding (cache collision!)")
    print("\n   This means the cache is NOT properly isolated.")
    print("   Old cache entries ARE interfering with new model.")
elif similarity < 0.1:
    print("   ✅ PASS: Very different - correctly using DIFFERENT models")
    print("\n   This confirms cache isolation is working correctly.")
else:
    print(f"   ⚠️  WARN: Moderate similarity ({similarity:.4f})")

print("\n" + "=" * 80)
print("TEST 2: Verify cache retrieval consistency")
print("=" * 80)

print("\n1. Getting text-v2 embedding again...")
text_v2_cached = embed_text(description)
match1 = (text_v2_emb == text_v2_cached)
print(f"   Cache match: {'✅' if match1 else '❌'}")

print("\n2. Getting multimodal embedding again...")
multimodal_cached = embed_text_multimodal(description)
match2 = (multimodal_emb == multimodal_cached)
print(f"   Cache match: {'✅' if match2 else '❌'}")

print("\n" + "=" * 80)
print("FINAL VERDICT")
print("=" * 80)

if similarity < 0.1 and match1 and match2:
    print("\n✅ ALL TESTS PASSED!")
    print("\n   - Cache is properly model-aware")
    print("   - Old cache entries don't interfere")
    print("   - Safe to proceed with re-embedding")
else:
    print("\n❌ TESTS FAILED!")
    print("\n   DO NOT proceed with re-embedding until this is fixed.")
    if similarity > 0.9:
        print("   Problem: Cache collision - same embeddings returned for both models")
    if not match1:
        print("   Problem: text-v2 cache inconsistent")
    if not match2:
        print("   Problem: multimodal cache inconsistent")
