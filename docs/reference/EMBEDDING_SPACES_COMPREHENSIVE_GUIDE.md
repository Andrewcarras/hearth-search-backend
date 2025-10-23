# Comprehensive Guide to Embedding Spaces, Multimodal Embeddings, and Amazon Titan Models

## Table of Contents
1. [Embedding Spaces Fundamentals](#1-embedding-spaces-fundamentals)
2. [Unified vs Multiple Embedding Spaces](#2-unified-vs-multiple-embedding-spaces)
3. [Text-Only Embedding Models](#3-text-only-embedding-models)
4. [Multimodal Embedding Models](#4-multimodal-embedding-models)
5. [Amazon Titan Embedding Models](#5-amazon-titan-embedding-models)
6. [Embedding Space Migration](#6-embedding-space-migration)
7. [Practical Recommendations](#7-practical-recommendations)

---

## 1. Embedding Spaces Fundamentals

### 1.1 Mathematical Definition

An **embedding space** is a high-dimensional vector space where each point represents a semantic concept (word, sentence, document, image, etc.) as a dense numerical vector. Mathematically, an embedding is a function that maps discrete objects into continuous vector representations:

```
f: X → R^d
```

Where:
- `X` is the set of input objects (words, sentences, images)
- `R^d` is the d-dimensional real vector space
- `d` is the embedding dimension (typically 256-1024+ dimensions)

According to the **Whitney embedding theorem**, any smooth m-dimensional manifold can be smoothly embedded in a 2m-dimensional Euclidean space. This fundamental mathematical principle underlies why high-dimensional embeddings can capture complex semantic structures.

### 1.2 High-Dimensional Vector Spaces and Manifolds

Embedding spaces operate on the principle that high-dimensional data often lies on lower-dimensional **manifolds** embedded within the ambient space. Key concepts:

- **Manifold Hypothesis**: Real-world data (text, images) exists on low-dimensional manifolds within high-dimensional embedding spaces
- **Locally Isometric**: Small neighborhoods on the manifold preserve distances and relationships
- **Non-linear Structure**: Semantic relationships are often non-linear, requiring high-dimensional spaces to capture them accurately

**Example Visualization (conceptual):**
```
High-dimensional embedding space (1024-D)
    ↓ (manifold learning projects to lower dimensions for visualization)
3D projection showing semantic clusters:

           [happy] [joyful]
              *      *
                 [cheerful]
                    *

     [sad]                    [angry]
       *                        *
    [depressed]              [furious]
       *                        *
```

### 1.3 Why Similar Concepts Are Close in Embedding Space

Embedding models are trained to minimize distance between semantically similar items and maximize distance between dissimilar items. This is achieved through:

**Cosine Similarity**: The primary metric for measuring semantic similarity
```
cosine_similarity(v1, v2) = (v1 · v2) / (||v1|| × ||v2||)
```

**Why it works:**
- **Direction over magnitude**: Cosine similarity measures the angle between vectors, focusing on semantic direction rather than vector length
- **Normalized comparison**: Values range from -1 (opposite) to 1 (identical), with 0 indicating orthogonality
- **Semantic encoding**: Words/concepts with similar meanings point in similar directions

**Example:**
- `happy` and `joyful` → cosine similarity ≈ 0.85 (vectors point in nearly same direction)
- `happy` and `sad` → cosine similarity ≈ -0.30 (vectors point in opposite directions)
- `happy` and `automobile` → cosine similarity ≈ 0.05 (vectors are nearly orthogonal)

### 1.4 Linear Algebra Properties: Vector Arithmetic

One of the most remarkable properties of embeddings is their **compositional structure**, enabling vector arithmetic to capture semantic relationships:

**Famous Example: "king - man + woman ≈ queen"**

```
embedding("king") - embedding("man") + embedding("woman") ≈ embedding("queen")
```

**Mathematical Foundation:**

This works because embeddings capture **co-occurrence patterns** through Point-wise Mutual Information (PMI):
- The co-occurrence shifted PMI must be the same for word pairs for analogies to hold exactly
- Models like Word2Vec (Skip-gram with Negative Sampling) and GloVe are specifically designed to preserve these relationships

**Other Examples:**
```
Paris - France + Italy ≈ Rome
walking - walk + swim ≈ swimming
bigger - big + small ≈ smaller
```

**Why This Works:**
1. **Distributed representations**: Semantic features are spread across many dimensions
2. **Linear subspaces**: Related concepts (gender, geography, verb tense) occupy parallel linear subspaces
3. **Training objectives**: Contrastive learning and predictive objectives preserve these relationships

**Diagram Description:**
```
2D projection of gender relationship in embedding space:

        queen ●
              ↑
              | (gender vector)
              |
   king ● ----+

        woman ●
              ↑
              | (gender vector - parallel to above)
              |
   man ● -----+

(royalty axis →)
```

The "gender vector" remains consistent whether applied to royalty or commoners, demonstrating the linear substructure.

---

## 2. Unified vs Multiple Embedding Spaces

### 2.1 What is a "Unified Embedding Space"?

A **unified embedding space** is a single vector space where different modalities (text, images, audio, video) are represented using the same coordinate system and dimensionality. In a unified space:

- Text query "golden retriever puppy" → vector in space S
- Image of golden retriever puppy → vector in same space S
- These vectors are **directly comparable** using cosine similarity

**Key Properties:**
1. **Shared dimensionality**: All modalities project to same dimension (e.g., 1024-D)
2. **Aligned semantics**: Semantically similar concepts across modalities are close together
3. **Cross-modal retrieval**: Text can find images, images can find text, images can find images

### 2.2 Why Text-Only and Image-Only Embeddings Are Incompatible

When you train separate models for text and images, they create **different, incompatible embedding spaces**:

**Text-Only Model (e.g., amazon.titan-embed-text-v2:0):**
- Trained only on text corpora
- Learns semantic relationships between words, sentences, documents
- No concept of visual features (color, shape, composition)

**Image-Only Model (e.g., ResNet, ViT without text training):**
- Trained only on image classification or object detection
- Learns visual features (edges, textures, objects)
- No concept of linguistic meaning

**The Incompatibility Problem:**

```
Text Space (1024-D)          Image Space (2048-D)
    [dog] → [0.2, 0.8, ...]      Image(dog) → [0.5, 0.1, ...]
    [cat] → [0.3, 0.7, ...]      Image(cat) → [0.9, 0.3, ...]

❌ Cannot compare these vectors!
   - Different dimensions (1024 vs 2048)
   - Different coordinate systems
   - No semantic alignment
```

Even if dimensions match, the spaces are fundamentally different:
- The basis vectors represent completely different features
- No correspondence between text dimension 0 and image dimension 0
- Random similarity scores with no semantic meaning

### 2.3 The Modality Gap Problem

Even in multimodal models like CLIP, a **modality gap** can exist:

**Definition**: Text embeddings cluster separately from image embeddings, creating distinct regions in the unified space.

**Consequences:**
- Text vectors are closer to irrelevant texts than relevant images
- Cross-modal retrieval performance degrades
- Mixed-modality search shows U-shaped performance curves

**Visualization:**
```
Embedding space with modality gap:

Text cluster              Image cluster
   [cat_text]                [cat_img]
      *                          *
   [dog_text]                [dog_img]
      *                          *

← gap →
(text and images are separated)
```

Modern multimodal models minimize this gap through:
- Contrastive learning with large batch sizes
- Temperature scaling
- Hard negative mining
- Projection layers to align modalities

### 2.4 Cross-Modal Retrieval Requirements

For cross-modal retrieval to work (text query finding images), you need:

1. **Unified embedding space**: Both modalities in same coordinate system
2. **Semantic alignment**: Similar concepts across modalities close together
3. **Consistent similarity metric**: Same distance function (cosine similarity) works across modalities

**Example: Text-to-Image Search**
```python
# With unified embedding space (WORKING):
query_text = "golden retriever puppy"
text_embedding = embed_multimodal(query_text)  # → 1024-D vector

image_embeddings = [
    embed_multimodal(image1),  # dog photo → 1024-D vector
    embed_multimodal(image2),  # cat photo → 1024-D vector
    embed_multimodal(image3),  # car photo → 1024-D vector
]

# Compute similarities (ALL in same space)
similarities = [cosine_sim(text_embedding, img_emb)
                for img_emb in image_embeddings]
# Result: [0.89, 0.23, 0.11] - dog image matches best!
```

```python
# With separate embedding spaces (BROKEN):
text_embedding = embed_text_only(query_text)  # → 1024-D in Space A
image_embedding = embed_image_only(image1)    # → 1024-D in Space B

similarity = cosine_sim(text_embedding, image_embedding)
# Result: 0.47 - meaningless number, no semantic correlation!
```

### 2.5 Examples of Embedding Space Incompatibility Issues

**Problem 1: Different Models = Different Spaces**
```
OpenAI text-embedding-ada-002 (1536-D, Space A)
   vs.
Amazon titan-embed-text-v2 (1024-D, Space B)

❌ Cannot compare embeddings across these models
✅ Must use same model for all documents and queries
```

**Problem 2: Model Versions**
```
text-embedding-ada-002 (old version)
   vs.
text-embedding-3-small (new version)

❌ Different training data and architectures
❌ Incompatible vector spaces
✅ Must re-embed all documents when upgrading
```

**Problem 3: Text vs Multimodal Models**
```
titan-embed-text-v2 (text-only model)
   vs.
titan-embed-image-v1 (multimodal model)

❌ Cannot mix: text-only embedding + multimodal embedding
✅ Use titan-embed-image-v1 for BOTH text and images
   (multimodal models can embed pure text too)
```

**Problem 4: Dimension Mismatch**
```
Query embedding: 256 dimensions
Document embeddings: 1024 dimensions

❌ Vector shapes don't match: cannot compute similarity
✅ All vectors must have same dimensionality
```

---

## 3. Text-Only Embedding Models

### 3.1 How Text-Only Models Work

Text-only embedding models (like `amazon.titan-embed-text-v2:0`) transform text into semantic vectors through multiple stages:

**Architecture Pipeline:**

```
Input Text
    ↓
[1] Tokenization
    ↓
[2] Token IDs
    ↓
[3] Token Embeddings
    ↓
[4] Positional Encoding
    ↓
[5] Transformer Encoder Layers
    ↓
[6] Pooling (mean/CLS token)
    ↓
Output: Fixed-size embedding vector (e.g., 1024-D)
```

### 3.2 Tokenization and Encoding Process

**Stage 1: Tokenization**

Raw text is split into tokens using algorithms like:
- **WordPiece**: Used by BERT
- **Byte-Pair Encoding (BPE)**: Used by GPT models
- **SentencePiece**: Language-agnostic tokenization

```python
# Example tokenization
text = "The quick brown fox jumps"
tokens = ["The", "quick", "brown", "fox", "jump", "##s"]
token_ids = [1996, 4248, 2829, 4419, 6560, 2015]
```

**Key characteristics:**
- Subword tokenization handles rare words and morphology
- Average ratio: ~4.7 characters per token (English)
- OOV (out-of-vocabulary) words split into subword units

**Stage 2: Token Embedding**

Each token ID maps to a learned embedding vector:
```python
token_embedding_matrix: [vocab_size, hidden_dim]
# e.g., [50000 tokens, 768 dimensions]

token_id = 4248  # "quick"
embedding = token_embedding_matrix[4248]  # → 768-D vector
```

**Stage 3: Positional Encoding**

Transformers have no inherent notion of position, so positional embeddings are added:
```python
final_embedding = token_embedding + positional_embedding
```

This allows the model to understand word order.

**Stage 4: Transformer Processing**

Multiple transformer encoder layers process the embeddings:
- **Self-attention**: Each token attends to all other tokens
- **Context integration**: Token representations incorporate surrounding context
- **Multi-head attention**: Captures different types of relationships simultaneously

**Stage 5: Pooling**

Convert variable-length sequence to fixed-size vector:
- **Mean pooling**: Average all token embeddings
- **CLS token**: Use special classification token embedding
- **Max pooling**: Take maximum value across each dimension

### 3.3 What Information Is Captured

Text embeddings capture multiple layers of linguistic information:

**Lexical Information:**
- Word meanings and synonyms
- Semantic similarity (cat ≈ feline)

**Syntactic Information:**
- Part-of-speech patterns
- Grammatical relationships

**Semantic Information:**
- Sentence meaning and intent
- Topic and domain
- Sentiment and tone

**Contextual Information:**
- Word sense disambiguation
- Coreference resolution
- Discourse structure

**Example:**
```
Sentence: "The bank was steep and slippery"
Embedding captures:
- "bank" = riverbank (not financial institution)
- Outdoor/nature context
- Physical description
- Potential hazard/warning tone
```

### 3.4 Typical Dimensions and Architecture

**Common Embedding Dimensions:**
- **256-D**: Faster, 97% accuracy of full size, smaller storage
- **384-D**: Balance of speed and accuracy
- **512-D**: ~99% accuracy of full size
- **768-D**: BERT-base, GPT-2 small
- **1024-D**: Common for production systems (titan-embed-text-v2 default)
- **1536-D**: OpenAI text-embedding-ada-002
- **4096-D**: Very large models (rare for embeddings)

**Architecture Characteristics:**

For `amazon.titan-embed-text-v2:0`:
- **Encoder**: Transformer-based encoder (BERT-like)
- **Layers**: 12-24 transformer blocks (estimated)
- **Hidden size**: 1024 dimensions
- **Attention heads**: 16 heads (typical)
- **Parameters**: Hundreds of millions
- **Training**: Contrastive learning on text pairs

**Trade-offs:**

| Dimension | Storage | Speed | Accuracy |
|-----------|---------|-------|----------|
| 256       | 25%     | Fast  | 97%      |
| 512       | 50%     | Medium| 99%      |
| 1024      | 100%    | Slower| 100%     |

**Storage calculation:**
```
1 million documents × 1024 dimensions × 4 bytes (float32) = 4 GB
1 million documents × 256 dimensions × 4 bytes = 1 GB

Savings with 256-D: 75% reduction in storage
```

---

## 4. Multimodal Embedding Models

### 4.1 How Multimodal Models Work

Multimodal embedding models (like `amazon.titan-embed-image-v1`) create a **unified embedding space** for multiple modalities (text and images). Unlike text-only models, they can:
- Embed images into vectors
- Embed text into vectors (in the SAME space)
- Enable cross-modal retrieval (text finding images, image finding similar images)

**Core Principle**: Map different modalities into a shared semantic space where similar concepts are close together, regardless of modality.

### 4.2 Dual Encoder Architecture

The standard architecture for multimodal embeddings uses **dual encoders**:

```
Input Text                    Input Image
    ↓                             ↓
Text Encoder              Image Encoder
(Transformer)              (ViT/ResNet)
    ↓                             ↓
Text Features             Visual Features
    ↓                             ↓
Projection Head           Projection Head
    ↓                             ↓
    └────── Shared ────────┘
         Embedding Space
         (e.g., 1024-D)
```

**Components:**

**1. Text Encoder**
- Usually a Transformer (BERT-like architecture)
- Processes tokenized text
- Outputs: text features (e.g., 512-D or 768-D)

**2. Image Encoder**
- Vision Transformer (ViT) or Convolutional Network (ResNet)
- Processes image patches or pixels
- Outputs: visual features (e.g., 512-D or 2048-D)

**3. Projection Heads**
- Linear layers that project both modalities to same dimensionality
- Critical for alignment: transforms different native dimensions to shared space
- Usually MLP: `features → ReLU → shared_dim`

**Example:**
```python
# Pseudo-code for dual encoder
def dual_encoder(text, image):
    # Text path
    text_tokens = tokenize(text)
    text_features = text_transformer(text_tokens)  # → 768-D
    text_embedding = text_projection(text_features)  # → 1024-D

    # Image path
    image_patches = patchify(image)
    visual_features = vision_transformer(image_patches)  # → 512-D
    image_embedding = image_projection(visual_features)  # → 1024-D

    # Normalize for cosine similarity
    text_embedding = normalize(text_embedding)
    image_embedding = normalize(image_embedding)

    return text_embedding, image_embedding
```

### 4.3 Contrastive Learning (CLIP-Style Training)

**Objective**: Learn to align matched image-text pairs while separating unmatched pairs.

**Training Process:**

```
Batch of N image-text pairs:
[("dog photo", dog_image),
 ("cat photo", cat_image),
 ("car photo", car_image),
 ...]

Create N×N similarity matrix:
              dog_img  cat_img  car_img
"dog photo"     0.9      0.2      0.1
"cat photo"     0.2      0.8      0.1
"car photo"     0.1      0.1      0.9

Goal: Maximize diagonal (correct pairs)
      Minimize off-diagonal (incorrect pairs)
```

**Contrastive Loss Formula:**

For a batch of N pairs, compute symmetric cross-entropy loss:

```
Text-to-Image Loss:
L_t2i = -1/N Σ log(exp(sim(t_i, v_i)/τ) / Σ_j exp(sim(t_i, v_j)/τ))

Image-to-Text Loss:
L_i2t = -1/N Σ log(exp(sim(v_i, t_i)/τ) / Σ_j exp(sim(v_i, t_j)/τ))

Total Loss:
L = (L_t2i + L_i2t) / 2
```

Where:
- `sim(t, v)` = cosine similarity between text and image embeddings
- `τ` = temperature parameter (typically 0.07)
- `i` = positive pair index
- `j` = all pairs in batch (including negatives)

**Key Insights:**

1. **Contrastive objective**: Pushes correct pairs together, incorrect pairs apart
2. **Symmetric training**: Learn text→image and image→text simultaneously
3. **Large batches**: Bigger batches = more negative examples = better learning
4. **Temperature scaling**: Controls how "hard" the discrimination is

**Why This Works:**

- **In-batch negatives**: Each batch provides N² - N negative pairs for free
- **Efficient learning**: No need for explicit negative sampling
- **Semantic alignment**: Forces model to learn shared semantic concepts
- **Cross-modal transfer**: Knowledge from text helps image understanding and vice versa

### 4.4 How Text and Images Are Projected Into SAME Space

**The Alignment Challenge:**

Text and images are fundamentally different:
- Text: discrete symbols, sequential, linguistic structure
- Images: continuous pixels, spatial, visual structure

**Solution: Learned Projection**

The projection heads are the key to creating a unified space:

```
Text Features (768-D, learned from language)
         ↓
Text Projection: Linear(768 → 1024) + ReLU + Linear(1024 → 1024)
         ↓
Shared Space (1024-D)
         ↑
Image Projection: Linear(2048 → 1024) + ReLU + Linear(1024 → 1024)
         ↑
Visual Features (2048-D, learned from images)
```

**Training Dynamics:**

Initially (random weights):
- Text embedding for "dog" → random 1024-D vector
- Image embedding for dog photo → different random 1024-D vector
- Similarity: ~0 (orthogonal)

After contrastive training:
- Text embedding for "dog" → learned 1024-D vector
- Image embedding for dog photo → similar 1024-D vector
- Similarity: ~0.85 (highly aligned)

**Shared Semantic Dimensions:**

The model learns dimensions that represent concepts across both modalities:

```
Dimension 42 (example):
- High value → "furry animals"
- Text: "dog", "cat", "rabbit" → high activation
- Images: photos of dogs, cats, rabbits → high activation

Dimension 157 (example):
- High value → "vehicles"
- Text: "car", "truck", "bus" → high activation
- Images: photos of vehicles → high activation
```

**Normalization:**

Both embeddings are L2-normalized to unit length:
```python
embedding = embedding / ||embedding||_2
```

This ensures:
- Cosine similarity is the inner product
- All vectors lie on unit hypersphere
- Magnitude doesn't affect similarity, only direction

### 4.5 Why This Enables Text-to-Image and Image-to-Image Search

**1. Text-to-Image Search**

```python
# User query
query = "golden retriever puppy playing in grass"
query_embedding = embed_text(query)  # → 1024-D vector

# Database of image embeddings
image_embeddings = [
    embed_image(photo1),  # dog in grass
    embed_image(photo2),  # cat indoors
    embed_image(photo3),  # car
]

# Compute similarities (all in same space!)
similarities = [
    cosine_sim(query_embedding, img_emb)
    for img_emb in image_embeddings
]
# [0.91, 0.23, 0.08] → photo1 is best match
```

**Why it works:**
- Query and images are in same 1024-D space
- "Golden retriever" (text concept) aligns with dog photos (visual concept)
- "Grass" (text) aligns with green outdoor scenes (visual)
- Contrastive training ensures this alignment

**2. Image-to-Image Search (Similarity Search)**

```python
# User uploads an image
query_image = load_image("my_dog.jpg")
query_embedding = embed_image(query_image)  # → 1024-D vector

# Find similar images
database_embeddings = [
    embed_image(candidate1),  # another dog
    embed_image(candidate2),  # different dog breed
    embed_image(candidate3),  # cat
]

similarities = [
    cosine_sim(query_embedding, candidate_emb)
    for candidate_emb in database_embeddings
]
# [0.88, 0.76, 0.34] → similar dogs rank highest
```

**Why it works:**
- Both query and candidates use same image encoder
- Visual features (fur, shape, color) map to same semantic space
- Similar visual concepts cluster together

**3. Multimodal Search (Text + Image Query)**

Some systems support combined queries:
```python
query_text = "outdoor scene"
query_image = load_image("sunset.jpg")

# Combine embeddings (e.g., average)
text_emb = embed_text(query_text)
image_emb = embed_image(query_image)
combined_emb = (text_emb + image_emb) / 2

# Search for images matching both criteria
```

**Advantages of Unified Space:**

1. **Zero-shot retrieval**: No fine-tuning needed for new concepts
2. **Flexible queries**: Text, image, or both
3. **Semantic understanding**: Finds conceptual matches, not just pixel/word matches
4. **Multilingual support**: If trained multilingually, works across languages

---

## 5. Amazon Titan Embedding Models

### 5.1 Amazon Titan Text Embeddings V2 (amazon.titan-embed-text-v2:0)

**Model Type**: Text-only embedding model

**Specifications:**

| Parameter | Value |
|-----------|-------|
| Model ID | `amazon.titan-embed-text-v2:0` |
| Output Dimensions | 256, 512, or 1024 (default: 1024) |
| Max Input Tokens | 8,192 tokens |
| Max Input Characters | 50,000 characters |
| Character-to-Token Ratio | ~4.7 chars/token (English) |
| Supported Languages | 100+ languages |
| Embedding Types | float, binary, or both |

**Architecture:**
- Transformer-based encoder (BERT-like)
- Optimized for text retrieval tasks
- Also supports semantic similarity and clustering

**Input Format:**
```json
{
  "inputText": "Your text here",
  "dimensions": 1024,
  "embeddingTypes": ["float"]
}
```

**Output Format:**
```json
{
  "embedding": [0.123, -0.456, 0.789, ...],
  "inputTextTokenCount": 42
}
```

**Dimension Trade-offs:**

| Dimensions | Accuracy vs 1024-D | Use Case |
|------------|-------------------|----------|
| 256 | 97% | Maximum speed, storage-constrained |
| 512 | 99% | Balanced performance |
| 1024 | 100% (baseline) | Maximum accuracy |

**Key Features:**
- **Multilingual**: Pre-trained on 100+ languages
- **Long context**: Up to 8,192 tokens (much longer than many competitors)
- **Flexible dimensions**: Choose dimension based on accuracy/speed trade-off
- **Binary embeddings**: For ultra-fast approximate search

### 5.2 Amazon Titan Multimodal Embeddings G1 (amazon.titan-embed-image-v1)

**Model Type**: Multimodal embedding model (text + image)

**Specifications:**

| Parameter | Value |
|-----------|-------|
| Model ID | `amazon.titan-embed-image-v1` |
| Output Dimensions | 256, 384, or 1024 (default: 1024) |
| Max Input Text Tokens | 128 tokens |
| Max Input Image Size | 5-25 MB (sources vary) |
| Supported Languages | English (text) |
| Supported Image Formats | JPEG, PNG |

**Architecture:**
- Dual encoder (text + vision)
- Contrastive learning (CLIP-style)
- Shared embedding space for cross-modal retrieval

**Input Format (Text):**
```json
{
  "inputText": "A golden retriever puppy",
  "embeddingConfig": {
    "outputEmbeddingLength": 1024
  }
}
```

**Input Format (Image):**
```json
{
  "inputImage": "<base64-encoded-image>",
  "embeddingConfig": {
    "outputEmbeddingLength": 1024
  }
}
```

**Input Format (Text + Image):**
```json
{
  "inputText": "outdoor scene",
  "inputImage": "<base64-encoded-image>",
  "embeddingConfig": {
    "outputEmbeddingLength": 1024
  }
}
```

**Supported Use Cases:**
- Image search by text
- Image search by image (similarity search)
- Image search by text + image (combined query)
- Recommendations and personalization
- Content moderation

### 5.3 Key Differences Between Models

| Feature | titan-embed-text-v2 | titan-embed-image-v1 |
|---------|---------------------|----------------------|
| **Modality** | Text only | Text + Image |
| **Max Text Input** | 8,192 tokens | 128 tokens |
| **Image Support** | ❌ No | ✅ Yes |
| **Languages** | 100+ | English only (text) |
| **Dimensions** | 256, 512, 1024 | 256, 384, 1024 |
| **Primary Use** | Document retrieval, RAG | Visual search, e-commerce |
| **Cross-modal** | ❌ No | ✅ Yes (text↔image) |
| **Embedding Space** | Text-only space | Unified multimodal space |

**Critical Incompatibility:**

```
❌ WRONG: Cannot mix embeddings from different models
text_emb = titan_text_v2.embed("dog")      # Space A
img_emb = titan_image_v1.embed("dog")      # Space B
similarity = cosine(text_emb, img_emb)     # MEANINGLESS!

✅ CORRECT: Use same model for all embeddings
text_emb = titan_image_v1.embed_text("dog")    # Space B
img_emb = titan_image_v1.embed_image(dog_img)  # Space B
similarity = cosine(text_emb, img_emb)         # VALID!
```

### 5.4 When to Use Each Model

**Use `amazon.titan-embed-text-v2:0` when:**

✅ You only have text data (no images)
✅ You need long context support (up to 8,192 tokens)
✅ You need multilingual support (100+ languages)
✅ You want maximum cost efficiency for text-only tasks
✅ Use cases: RAG, document search, semantic search, clustering

**Example applications:**
- Question-answering over documents
- Semantic search in knowledge bases
- Document clustering and classification
- Duplicate detection
- Recommendation systems (text-based)

**Use `amazon.titan-embed-image-v1` when:**

✅ You have images or mixed text+image data
✅ You need cross-modal search (text query finding images)
✅ You need image similarity search
✅ Visual search is a requirement
✅ Use cases: E-commerce, visual search, content moderation

**Example applications:**
- E-commerce visual search ("find products like this image")
- Text-to-image search ("show me images of golden retrievers")
- Reverse image search
- Fashion recommendation
- Content moderation (finding similar problematic images)
- Visual similarity detection

**Important Note on Text-Only Use:**

Even for pure text tasks, if you might add images later, consider using `titan-embed-image-v1` from the start:
- Can embed text (up to 128 tokens)
- Avoids costly re-embedding migration later
- Enables future image features

However, be aware of trade-offs:
- More expensive per token for text
- Limited to 128 tokens (vs 8,192 for text-v2)
- English-only for text

### 5.5 Cost Implications

**Pricing (as of 2024-2025, US regions):**

**Amazon Titan Text Embeddings V2:**
- On-Demand: $0.00002 per 1,000 tokens ($0.02 per 1M tokens)
- Batch Mode: $0.00001 per 1,000 tokens (50% discount)

**Amazon Titan Multimodal Embeddings G1:**
- On-Demand: $0.0008 per 1,000 tokens OR $0.00006 per image
- Batch Mode: $0.0004 per 1,000 tokens AND $0.00003 per image

**Cost Comparison:**

For text processing:
```
titan-embed-text-v2: $0.00002 per 1K tokens
titan-embed-image-v1: $0.0008 per 1K tokens

Ratio: 40x more expensive for text with multimodal model
```

**Example Cost Calculation:**

Scenario: Index 1 million documents, average 500 tokens each

**Using titan-embed-text-v2:**
```
Total tokens: 1,000,000 docs × 500 tokens = 500M tokens
Cost: 500M × $0.00002 / 1000 = $10.00
```

**Using titan-embed-image-v1 (text-only):**
```
Total tokens: 1,000,000 docs × 500 tokens = 500M tokens
Cost: 500M × $0.0008 / 1000 = $400.00
```

**Using titan-embed-image-v1 (with images):**
```
Assume 100,000 documents have images:
Text cost: 500M tokens × $0.0008 / 1000 = $400.00
Image cost: 100,000 images × $0.00006 = $6.00
Total: $406.00
```

**Storage Costs:**

Using smaller dimensions saves storage:
```
1M documents × 1024 dims × 4 bytes (float32) = 4 GB
1M documents × 256 dims × 4 bytes = 1 GB (75% reduction)

Vector database storage: ~$0.10-0.30 per GB/month
Savings: 3 GB × $0.20 = $0.60/month
```

**Optimization Strategies:**

1. **Choose appropriate model**: Use text-v2 for text-only to save 40x
2. **Batch processing**: 50% discount for batch mode
3. **Dimension reduction**: Use 512-D (99% accuracy) for 50% storage savings
4. **Caching**: Cache embeddings to avoid re-embedding
5. **Chunking**: Don't embed more text than necessary

**Cost vs. Capability Matrix:**

| Approach | Text Cost | Image Support | Best For |
|----------|-----------|---------------|----------|
| text-v2 only | $ (cheapest) | ❌ No | Pure text RAG |
| image-v1 text | $$$$ (40x) | ✅ Yes | Future-proof, will add images |
| text-v2 now, migrate later | $ initially, $$$ migration | ✅ Eventually | Uncertain future needs |

---

## 6. Embedding Space Migration

### 6.1 What Happens When You Switch Embedding Models

When you change embedding models, you create a **fundamental incompatibility** between old and new embeddings:

**The Problem:**

```
Before (Model A):
  documents[0] = embed_A("The quick brown fox")  → [0.2, 0.8, 0.1, ...]
  documents[1] = embed_A("A lazy dog sleeps")    → [0.3, 0.7, 0.2, ...]
  query = embed_A("dog")                         → [0.35, 0.65, 0.15, ...]

  cosine(query, documents[1]) = 0.87 (high similarity ✓)

After switching to Model B (WITHOUT re-embedding):
  documents[0] = [0.2, 0.8, 0.1, ...]  (old, from Model A)
  documents[1] = [0.3, 0.7, 0.2, ...]  (old, from Model A)
  query = embed_B("dog")               → [0.1, 0.2, 0.9, ...]  (new, Model B)

  cosine(query, documents[1]) = 0.23 (low similarity ✗)

  BROKEN: Query doesn't match relevant documents!
```

**Why Incompatibility Occurs:**

1. **Different training data**: Models learn from different corpora
2. **Different architectures**: BERT vs. GPT vs. custom architectures
3. **Different tokenizers**: Different subword splits
4. **Different dimensions**: 1024-D vs. 1536-D vs. 512-D
5. **Different optimization**: Different loss functions and training objectives
6. **Different coordinate systems**: Dimension 0 in Model A ≠ Dimension 0 in Model B

**Even Same Dimensions Don't Help:**

```
Both models output 1024-D vectors, but:

Model A dimension 42 → "animal" concept
Model B dimension 42 → "color" concept

Same dimension, totally different meanings!
```

### 6.2 Why You Must Re-Embed ALL Documents When Changing Models

**The Iron Rule of Embedding Consistency:**

> **All embeddings in a vector database MUST come from the same model.**

**Why re-embedding is non-negotiable:**

1. **Vector Space Mismatch**
   - Each model creates its own unique vector space
   - No mathematical transformation can convert between spaces
   - Similarity scores become meaningless when mixing models

2. **Dimension Mismatches**
   ```python
   # Old model: 1536 dimensions
   old_docs = [[0.1, 0.2, ..., 0.3]]  # shape: (1, 1536)

   # New model: 256 dimensions
   new_query = [0.4, 0.5, ..., 0.6]   # shape: (1, 256)

   # Error: cannot compute cosine similarity!
   # Vector shapes don't match: (1536,) vs (256,)
   ```

3. **Semantic Misalignment**
   - Even with same dimensions, semantic mappings differ
   - "Cat" in Model A: [0.1, 0.9, 0.2, ...]
   - "Cat" in Model B: [0.8, 0.3, 0.1, ...]
   - No correlation between these vectors

**Migration Process:**

```
Step 1: Choose new embedding model
  ↓
Step 2: Re-embed ALL documents using new model
  ↓
Step 3: Replace old embeddings in vector database
  ↓
Step 4: Invalidate all caches
  ↓
Step 5: Use new model for all future queries
```

**Example Migration:**

```python
# BAD: Mixing old and new embeddings
old_embeddings = [embed_old(doc) for doc in documents]  # Don't reuse!
new_query = embed_new(user_query)
results = search(new_query, old_embeddings)  # BROKEN!

# GOOD: Re-embed everything
new_embeddings = [embed_new(doc) for doc in documents]
new_query = embed_new(user_query)
results = search(new_query, new_embeddings)  # WORKS!
```

**Migration Complexity:**

For a production system with 10 million documents:
```
Documents: 10,000,000
Average tokens: 500
Total tokens: 5 billion

Time to re-embed (1000 docs/sec): ~3 hours
Cost (titan-text-v2): 5B × $0.00002/1000 = $100
Storage migration: 4 GB → new vector DB

Downtime: Can run in parallel, but need deployment strategy
```

### 6.3 Cache Invalidation Requirements

**Types of Caches Affected:**

1. **Embedding Cache**
   - Stores previously computed embeddings
   - Must be completely invalidated
   - Tagged with model version

2. **Query Cache**
   - Stores query results
   - Must be invalidated (old embeddings invalid)

3. **Similarity Cache**
   - Pre-computed similarity matrices
   - Must be recomputed with new embeddings

**Cache Invalidation Strategy:**

```python
# Version-aware caching
cache_key = f"{text}:{model_version}:{dimensions}"

# Before migration
cache["The quick brown fox:text-v2:1024"] = [0.1, 0.2, ...]

# After migration
cache["The quick brown fox:image-v1:1024"] = [0.4, 0.5, ...]

# Old cache entries automatically unused (different key)
```

**Best Practices:**

1. **Version Tagging**
   ```python
   embedding_metadata = {
       "vector": [0.1, 0.2, ...],
       "model": "amazon.titan-embed-text-v2:0",
       "dimensions": 1024,
       "created_at": "2024-11-15"
   }
   ```

2. **Cache Versioning**
   ```python
   CACHE_VERSION = "v2"  # Increment when model changes
   cache_key = f"{CACHE_VERSION}:{text}"
   ```

3. **Automatic Invalidation**
   ```python
   if embedding.model != CURRENT_MODEL:
       invalidate_cache_entry(embedding.id)
       re_embed(embedding.text)
   ```

4. **Parallel Migration**
   - Run old and new models simultaneously
   - Gradually migrate traffic
   - Validate results before full cutover

**Cache Storage Considerations:**

```
Cached embeddings: 1M documents × 1024 dims × 4 bytes = 4 GB
Cache hit rate: 80% → avoid 800K re-embeddings
Migration: Must invalidate all 4 GB

Cost of invalidation:
- Storage cleared: 4 GB freed
- Re-embedding needed: 1M docs × $0.00002/1K tokens ≈ $10
- Cache rebuild: gradual (as queries come in)
```

### 6.4 Backward Compatibility Issues

**Problem: No Backward Compatibility**

Embedding models have **zero backward compatibility**. You cannot:

❌ Use old embeddings with new model queries
❌ Use new embeddings with old model queries
❌ Mix embeddings from different model versions
❌ Downgrade models without re-embedding

**Version Upgrade Scenarios:**

**Scenario 1: Minor Version Update (Same Model Family)**
```
text-embedding-3-small (v1) → text-embedding-3-small (v1.1)

Problem: Even minor updates can change vector space
Solution: Check model provider docs - often requires re-embedding
```

**Scenario 2: Major Version Update**
```
titan-embed-text-v1 → titan-embed-text-v2

Problem: Guaranteed incompatibility
Solution: Must re-embed all documents
Benefit: Usually better performance, worth the migration
```

**Scenario 3: Model Family Switch**
```
OpenAI text-embedding-ada-002 → Amazon titan-embed-text-v2

Problem: Completely different architectures and spaces
Solution: Full re-embedding required
Note: Cannot compare performance without re-embedding
```

**Scenario 4: Adding Multimodal Support**
```
titan-embed-text-v2 → titan-embed-image-v1

Problem: Moving from text-only to multimodal space
Solution: Re-embed all text documents with multimodal model
Benefit: Can now add image embeddings in same space
```

**Migration Planning:**

```python
# Production migration strategy
class EmbeddingMigration:
    def __init__(self, old_model, new_model):
        self.old_model = old_model
        self.new_model = new_model
        self.migration_state = {}

    def migrate_batch(self, documents, batch_size=1000):
        """Migrate documents in batches"""
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]

            # Embed with new model
            new_embeddings = [
                self.new_model.embed(doc.text)
                for doc in batch
            ]

            # Update vector database
            self.vector_db.upsert(
                ids=[doc.id for doc in batch],
                embeddings=new_embeddings,
                metadata=[{
                    "model": "titan-embed-image-v1",
                    "migrated_at": datetime.now()
                } for doc in batch]
            )

            # Track progress
            self.migration_state["migrated"] += len(batch)

    def verify_migration(self):
        """Ensure all docs use new model"""
        old_model_docs = self.vector_db.query(
            filter={"model": self.old_model.name}
        )

        if old_model_docs:
            raise Exception(f"{len(old_model_docs)} docs still use old model!")
```

**Rollback Challenges:**

❌ **Cannot easily rollback** once migration is complete:
- Old embeddings are overwritten
- Vector database now contains new embeddings
- Would require re-embedding again with old model

✅ **Safe Migration Strategy**:
1. Create new vector database instance
2. Migrate to new instance (old still running)
3. Run both in parallel, compare results
4. Switch traffic to new instance
5. Keep old instance for 30 days as backup
6. Delete old instance after validation

**Testing Before Migration:**

```python
# Test with small sample before full migration
def test_new_model(sample_size=1000):
    # Get sample of documents
    sample = documents[:sample_size]

    # Embed with both models
    old_embeddings = [old_model.embed(d.text) for d in sample]
    new_embeddings = [new_model.embed(d.text) for d in sample]

    # Test retrieval quality
    for query in test_queries:
        old_results = search(old_model.embed(query), old_embeddings)
        new_results = search(new_model.embed(query), new_embeddings)

        # Compare result quality
        compare_results(old_results, new_results)

    # If quality is acceptable, proceed with full migration
```

---

## 7. Practical Recommendations

### 7.1 Choosing the Right Model

**Decision Tree:**

```
Do you have images or plan to add them?
├─ YES → Use titan-embed-image-v1
│  └─ Trade-offs: 40x more expensive for text, 128 token limit
│
└─ NO → Continue
    │
    Do you need multilingual support?
    ├─ YES → Use titan-embed-text-v2
    │
    Do you need long context (>128 tokens)?
    ├─ YES → Use titan-embed-text-v2
    │
    Is cost a major concern?
    ├─ YES → Use titan-embed-text-v2
    │
    Otherwise → Use titan-embed-text-v2
```

**Recommendation Matrix:**

| Use Case | Recommended Model | Reasoning |
|----------|------------------|-----------|
| Document Q&A (RAG) | titan-embed-text-v2 | Long context, cost-effective |
| E-commerce search | titan-embed-image-v1 | Visual search critical |
| Product recommendations (text) | titan-embed-text-v2 | Text-only, cost matters |
| Product recommendations (visual) | titan-embed-image-v1 | Visual similarity important |
| Content moderation | titan-embed-image-v1 | Images + text analysis |
| Semantic search (text) | titan-embed-text-v2 | Pure text retrieval |
| Reverse image search | titan-embed-image-v1 | Image-to-image required |
| Multilingual search | titan-embed-text-v2 | 100+ languages |

### 7.2 Avoiding Costly Migrations

**Strategy 1: Plan for the Future**

Before choosing a model, ask:
- Will we add images in next 12 months?
- Will we need visual search?
- Will we need cross-modal retrieval?

If **any** answer is "maybe yes", consider starting with `titan-embed-image-v1`:
- Avoids costly re-embedding migration
- Supports text-only initially (up to 128 tokens)
- Ready for images when needed

**Cost Comparison:**

```
Scenario: Start with text, add images after 6 months
Documents: 1M, 500 tokens average

Option A: text-v2 now, migrate later
  Initial: 500M tokens × $0.00002/1K = $10
  Migration: 500M tokens × $0.0008/1K = $400
  Total: $410

Option B: image-v1 from start
  Initial: 500M tokens × $0.0008/1K = $400
  Migration: $0 (no migration needed)
  Total: $400

But: Option B costs upfront, Option A spreads cost
And: Option A cheaper if never add images
```

**Strategy 2: Chunk Wisely**

For `titan-embed-image-v1` text embedding (128 token limit):
```python
# Split long documents into chunks
def chunk_document(text, max_tokens=100):
    """Keep under 128 token limit with safety margin"""
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk = []
    current_tokens = 0

    for sentence in sentences:
        tokens = estimate_tokens(sentence)
        if current_tokens + tokens > max_tokens:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_tokens = tokens
        else:
            current_chunk.append(sentence)
            current_tokens += tokens

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks
```

**Strategy 3: Hybrid Approach**

Use both models strategically:
```python
# Use text-v2 for long-form text search
text_embeddings = titan_text_v2.embed(long_documents)

# Use image-v1 for product catalog (text + images)
product_embeddings = titan_image_v1.embed(products)

# Separate vector databases, no mixing
text_db = VectorDB("text-search")
product_db = VectorDB("product-search")
```

**Caveat**: Cannot search across both databases with single query.

### 7.3 Dimension Selection

**Guidelines:**

| Use Case | Recommended Dimension | Reasoning |
|----------|----------------------|-----------|
| Prototyping | 256 | Fast iteration, low cost |
| Production (accuracy-critical) | 1024 | Maximum accuracy |
| Production (speed-critical) | 512 | 99% accuracy, 50% storage |
| Mobile/edge deployment | 256 | Resource-constrained |
| Large-scale (billions of vectors) | 512 | Storage savings matter |

**Accuracy vs. Efficiency:**

```python
# Benchmark different dimensions
test_results = {
    256: {"accuracy": 0.97, "speed": "150ms", "storage": "1 GB"},
    512: {"accuracy": 0.99, "speed": "180ms", "storage": "2 GB"},
    1024: {"accuracy": 1.00, "speed": "220ms", "storage": "4 GB"}
}

# For most applications, 512-D is sweet spot
recommended_dim = 512 if documents > 1_000_000 else 1024
```

### 7.4 Caching Strategies

**1. Embedding Cache**

```python
import hashlib
import json

class EmbeddingCache:
    def __init__(self, model_id, dimensions):
        self.model_id = model_id
        self.dimensions = dimensions
        self.cache = {}

    def get_cache_key(self, text):
        """Version-aware cache key"""
        content = f"{text}:{self.model_id}:{self.dimensions}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, text):
        key = self.get_cache_key(text)
        return self.cache.get(key)

    def set(self, text, embedding):
        key = self.get_cache_key(text)
        self.cache[key] = embedding

    def embed_with_cache(self, text, embed_fn):
        """Get from cache or compute"""
        cached = self.get(text)
        if cached is not None:
            return cached

        embedding = embed_fn(text)
        self.set(text, embedding)
        return embedding
```

**2. Query Result Cache**

```python
class QueryCache:
    def __init__(self, ttl_seconds=3600):
        self.cache = {}
        self.ttl = ttl_seconds

    def get(self, query, top_k, filters):
        key = self._cache_key(query, top_k, filters)
        entry = self.cache.get(key)

        if entry and time.time() - entry["timestamp"] < self.ttl:
            return entry["results"]
        return None

    def set(self, query, top_k, filters, results):
        key = self._cache_key(query, top_k, filters)
        self.cache[key] = {
            "results": results,
            "timestamp": time.time()
        }
```

**3. Redis-backed Cache**

```python
import redis
import pickle

class RedisEmbeddingCache:
    def __init__(self, model_id, dimensions):
        self.redis = redis.Redis(host='localhost', port=6379)
        self.model_id = model_id
        self.dimensions = dimensions
        self.ttl = 86400  # 24 hours

    def get(self, text):
        key = f"emb:{self.model_id}:{self.dimensions}:{text}"
        data = self.redis.get(key)
        return pickle.loads(data) if data else None

    def set(self, text, embedding):
        key = f"emb:{self.model_id}:{self.dimensions}:{text}"
        self.redis.setex(key, self.ttl, pickle.dumps(embedding))
```

### 7.5 Cost Optimization

**1. Batch Processing**

Use batch mode for 50% discount:
```python
# On-demand: $0.00002 per 1K tokens
# Batch: $0.00001 per 1K tokens

# For bulk indexing, use batch mode
documents = load_documents()  # 1M documents
batch_job = submit_batch_embedding_job(documents)
# Save: 50% on embedding costs
```

**2. Dimension Reduction**

```python
# Use 512-D instead of 1024-D
embedding_config = {
    "dimensions": 512  # 99% accuracy, 50% storage
}

# Storage savings for 10M documents:
# 1024-D: 10M × 1024 × 4 bytes = 40 GB
# 512-D:  10M × 512 × 4 bytes = 20 GB
# Savings: 20 GB × $0.20/GB/month = $4/month
```

**3. Lazy Embedding**

Only embed documents when first needed:
```python
class LazyEmbeddingStore:
    def __init__(self, embedding_fn):
        self.embedding_fn = embedding_fn
        self.embeddings = {}

    def get_embedding(self, doc_id, text):
        if doc_id not in self.embeddings:
            self.embeddings[doc_id] = self.embedding_fn(text)
        return self.embeddings[doc_id]
```

**4. Compression**

Use binary embeddings for approximate search:
```python
# Request binary embeddings (1 bit per dimension)
embedding_config = {
    "embeddingTypes": ["binary"]
}

# Storage: 1024 bits = 128 bytes (vs. 4096 bytes for float32)
# 32x storage reduction, ~10% accuracy loss
```

### 7.6 Monitoring and Validation

**1. Track Model Version**

```python
class EmbeddingService:
    def __init__(self, model_id):
        self.model_id = model_id
        self.version = self._get_model_version()

    def embed(self, text):
        embedding = self._call_api(text)
        return {
            "vector": embedding,
            "model": self.model_id,
            "version": self.version,
            "timestamp": datetime.now()
        }
```

**2. Validate Embedding Quality**

```python
def validate_embeddings():
    """Sanity checks for embedding quality"""

    # Test 1: Similar texts should have high similarity
    text1 = "The cat sat on the mat"
    text2 = "A cat is sitting on the mat"
    sim = cosine_similarity(embed(text1), embed(text2))
    assert sim > 0.8, f"Similar texts have low similarity: {sim}"

    # Test 2: Dissimilar texts should have low similarity
    text3 = "Quantum physics is fascinating"
    sim = cosine_similarity(embed(text1), embed(text3))
    assert sim < 0.5, f"Dissimilar texts have high similarity: {sim}"

    # Test 3: Same text should have similarity ~1.0
    sim = cosine_similarity(embed(text1), embed(text1))
    assert abs(sim - 1.0) < 0.01, f"Self-similarity not ~1.0: {sim}"
```

**3. Monitor Migration**

```python
def monitor_migration_progress():
    stats = {
        "total_docs": count_all_documents(),
        "migrated": count_documents_with_new_model(),
        "remaining": 0
    }
    stats["remaining"] = stats["total_docs"] - stats["migrated"]
    stats["progress"] = stats["migrated"] / stats["total_docs"]

    return stats

# Example output:
# {
#   "total_docs": 1000000,
#   "migrated": 750000,
#   "remaining": 250000,
#   "progress": 0.75
# }
```

---

## Summary

### Key Takeaways

1. **Embedding Spaces are Geometric Structures**
   - High-dimensional vector spaces capturing semantic relationships
   - Cosine similarity measures semantic closeness
   - Linear algebra properties enable vector arithmetic

2. **Unified vs. Separate Spaces**
   - Text-only and image-only models create incompatible spaces
   - Multimodal models create unified spaces for cross-modal retrieval
   - Cannot mix embeddings from different models

3. **Multimodal Models Use Dual Encoders**
   - Separate encoders for text and images
   - Projection heads align modalities to shared space
   - Contrastive learning (CLIP-style) trains alignment

4. **Amazon Titan Models**
   - `titan-embed-text-v2`: Text-only, 8K tokens, 100+ languages, $0.00002/1K tokens
   - `titan-embed-image-v1`: Multimodal, 128 text tokens + images, English, $0.0008/1K tokens
   - 40x cost difference for text processing

5. **Model Migration is Costly**
   - Must re-embed ALL documents when changing models
   - No backward compatibility between models
   - Plan carefully to avoid expensive migrations

6. **Best Practices**
   - Choose model based on future needs, not just current
   - Use version-aware caching
   - Monitor embedding quality
   - Optimize costs with batching, dimension reduction, and caching

### Quick Reference

| Question | Answer |
|----------|--------|
| Can I mix embeddings from different models? | ❌ No - incompatible spaces |
| Can I use titan-embed-image-v1 for text only? | ✅ Yes - but 128 token limit, 40x cost |
| Do I need to re-embed when upgrading models? | ✅ Yes - always required |
| Which model for pure text search? | titan-embed-text-v2 |
| Which model for visual search? | titan-embed-image-v1 |
| Best dimension for production? | 512 (99% accuracy, 50% storage) |
| Can I downgrade dimensions later? | ❌ No - requires re-embedding |
| How to avoid migration costs? | Choose right model upfront |

---

**Further Reading:**

- CLIP Paper: "Learning Transferable Visual Models From Natural Language Supervision" (Radford et al., 2021)
- ALIGN Paper: "Scaling Up Visual and Vision-Language Representation Learning With Noisy Text Supervision" (Jia et al., 2021)
- AWS Titan Documentation: https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html
- Vector Database Best Practices: https://www.pinecone.io/learn/vector-database/

---

*This guide was created as a comprehensive reference for understanding embedding spaces and Amazon Titan models. For production implementations, always consult the latest AWS documentation and test thoroughly with your specific use case.*
