"""
Verify that vector_text is actually being updated with new embeddings
"""
import os
import sys
import math

os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings-v2')

sys.path.insert(0, '/Users/andrewcarras/hearth_backend_new')

from common import os_client, embed_text_multimodal

def cosine_similarity(vec1, vec2):
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    return dot_product / (magnitude1 * magnitude2)

# Check a recently updated listing
zpid = "2113037205"

print("Verifying vector_text was actually updated...")
print("=" * 80)

# Get the stored vector
result = os_client.get(index="listings-v2", id=zpid, _source=["zpid", "description", "visual_features_text", "vector_text", "updated_at"])

if result.get("found"):
    source = result["_source"]
    stored_vector = source.get("vector_text", [])
    description = source.get("description", "")
    visual_text = source.get("visual_features_text", "")

    print(f"ZPID: {zpid}")
    print(f"Description length: {len(description)} chars")
    print(f"Visual features length: {len(visual_text)} chars")
    print(f"Stored vector length: {len(stored_vector)} dims")

    # Generate what the vector SHOULD be
    combined_text = f"{description.strip()} {visual_text}".strip()
    expected_vector = embed_text_multimodal(combined_text)

    print(f"\nGenerated fresh multimodal embedding: {len(expected_vector)} dims")

    # Compare
    similarity = cosine_similarity(stored_vector, expected_vector)

    print(f"\n✅ Similarity between stored and fresh: {similarity:.6f}")

    if similarity > 0.99:
        print("\n✅ PERFECT! Vector was updated with multimodal embeddings!")
        print("   (Near-perfect match means it's using the same model)")
    elif similarity > 0.9:
        print("\n✅ GOOD! Vector appears updated (high similarity)")
    else:
        print(f"\n⚠️  WARNING: Low similarity ({similarity:.6f})")
        print("   This suggests the vector may not have been updated correctly")

    # Also check a few sample values
    print(f"\nSample vector values (first 5):")
    print(f"  Stored:   {stored_vector[:5]}")
    print(f"  Expected: {expected_vector[:5]}")

else:
    print(f"Listing {zpid} not found!")
