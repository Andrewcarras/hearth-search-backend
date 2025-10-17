"""
Quick test to verify cache is model-aware
"""
import os
import sys

os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings-v2')

sys.path.insert(0, '/Users/andrewcarras/hearth_backend_new')

from common import embed_text, embed_text_multimodal
import math

def cosine_similarity(vec1, vec2):
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    return dot_product / (magnitude1 * magnitude2)

# Test with a unique query that shouldn't be cached
test_query = "unique test query 12345 xyz abc"

print("Testing model-aware cache...")
print(f"Query: '{test_query}'\n")

# Get embeddings from both models
print("1. Getting text-v2 embedding (first call - cache miss expected)...")
text_v2_emb = embed_text(test_query)
print(f"   ✓ Got {len(text_v2_emb)} dims\n")

print("2. Getting multimodal (image-v1) embedding (first call - cache miss expected)...")
multimodal_emb = embed_text_multimodal(test_query)
print(f"   ✓ Got {len(multimodal_emb)} dims\n")

# Calculate similarity
similarity = cosine_similarity(text_v2_emb, multimodal_emb)
print(f"3. Similarity between the two: {similarity:.4f}")

if similarity > 0.9:
    print("   ❌ FAIL: Embeddings are too similar (likely same model/cache issue)")
elif similarity < 0.1:
    print("   ✅ PASS: Embeddings are different (correct - different models)")
else:
    print("   ⚠️  WARN: Moderate similarity (unexpected)")

# Test cache retrieval
print("\n4. Testing cache retrieval...")
print("   Getting text-v2 embedding again (cache hit expected)...")
text_v2_cached = embed_text(test_query)

print("   Getting multimodal embedding again (cache hit expected)...")
multimodal_cached = embed_text_multimodal(test_query)

# Verify cached versions match
text_v2_match = text_v2_emb == text_v2_cached
multimodal_match = multimodal_emb == multimodal_cached

print(f"\n5. Cache verification:")
print(f"   Text-v2 cache match: {'✅ PASS' if text_v2_match else '❌ FAIL'}")
print(f"   Multimodal cache match: {'✅ PASS' if multimodal_match else '❌ FAIL'}")

if text_v2_match and multimodal_match and similarity < 0.1:
    print("\n✅ ALL TESTS PASSED - Cache is model-aware!")
else:
    print("\n❌ TESTS FAILED - Cache issue detected")
