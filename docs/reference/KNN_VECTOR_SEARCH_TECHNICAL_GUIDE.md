# k-Nearest Neighbors (kNN) Vector Search in OpenSearch: A Comprehensive Technical Guide

## Table of Contents
1. [kNN Search Fundamentals](#1-knn-search-fundamentals)
2. [Vector Embeddings](#2-vector-embeddings)
3. [kNN in OpenSearch](#3-knn-in-opensearch)
4. [Multi-Vector Search](#4-multi-vector-search)
5. [Filtering with kNN](#5-filtering-with-knn)
6. [Best Practices and Performance Tuning](#6-best-practices-and-performance-tuning)

---

## 1. kNN Search Fundamentals

### 1.1 What is k-Nearest Neighbors Algorithm?

The k-Nearest Neighbors (k-NN) algorithm is a fundamental machine learning technique that finds the "k" closest data points to a given query point in a vector space. In the context of search systems, k-NN identifies the k most similar documents to a search query by comparing their vector representations.

**Core Concept:**
- Given a query vector Q and a database of document vectors D
- Calculate the distance/similarity between Q and every vector in D
- Return the k vectors with the smallest distance (or highest similarity)

**Traditional vs. Modern Search:**
- **Keyword Search**: Matches exact terms or lexical patterns (e.g., "sneakers" won't match "running shoes")
- **Semantic Search (kNN)**: Understands meaning and context, finding conceptually similar results regardless of exact word matches

### 1.2 Distance Metrics

kNN search relies on distance metrics to measure similarity between vectors. The three most common metrics are:

#### **Cosine Similarity**

Measures the cosine of the angle between two vectors, ranging from -1 to 1 (or 0 to 1 for normalized positive vectors).

```
cosine_similarity(A, B) = (A · B) / (||A|| × ||B||)
```

**Properties:**
- Focuses on direction/orientation, not magnitude
- Returns 1 for identical directions, 0 for orthogonal vectors, -1 for opposite directions
- Invariant to vector magnitude (scaling doesn't affect similarity)

**When to use:**
- Text embeddings and NLP applications
- When vector direction matters more than magnitude
- High-dimensional data where normalization is important
- Most modern embedding models (BERT, GPT, etc.)

#### **Euclidean Distance**

Calculates the straight-line distance between two points in space.

```
euclidean_distance(A, B) = √(Σ(A_i - B_i)²)
```

**Properties:**
- Sensitive to both direction and magnitude
- Measures actual spatial distance
- Affected by scale differences across dimensions

**When to use:**
- Spatial proximity matters (images, object detection)
- Vector magnitudes contain meaningful information
- Low-dimensional data
- When embeddings encode counts or measurements

#### **Dot Product**

Computes the sum of element-wise products between two vectors.

```
dot_product(A, B) = Σ(A_i × B_i)
```

**Properties:**
- Combines similarity in direction with magnitude
- Higher values indicate greater similarity
- Equivalent to cosine similarity for normalized vectors

**When to use:**
- Pre-normalized embeddings
- When both direction and magnitude are important
- Computationally efficient for certain algorithms

### 1.3 Why Cosine Similarity Dominates in Embeddings

Cosine similarity is the most commonly used metric for semantic search with embeddings for several compelling reasons:

1. **Magnitude Independence**: Most neural network embedding models are trained to encode semantic meaning in the direction of vectors, not their length. Cosine similarity correctly captures this by ignoring magnitude.

2. **Normalization Equivalence**: For normalized vectors, cosine similarity and Euclidean distance are mathematically related:
   ```
   euclidean_distance = √(2(1 - cosine_similarity))
   ```
   This means on normalized data, both metrics rank results identically.

3. **High-Dimensional Stability**: In high-dimensional spaces (768, 1024, 1536 dimensions), cosine similarity is more stable and interpretable than Euclidean distance.

4. **Model Training Alignment**: Most embedding models (OpenAI's text-embedding, sentence-transformers, BERT) are trained using cosine similarity as their optimization target. Using the same metric at inference time produces optimal results.

5. **Scale Invariance**: Documents of different lengths produce vectors of different magnitudes, but cosine similarity treats them fairly by focusing on semantic direction.

### 1.4 Semantic Search vs Keyword Search

| Aspect | Keyword Search | Semantic Search (kNN) |
|--------|---------------|----------------------|
| **Matching** | Exact lexical matches | Conceptual similarity |
| **Synonyms** | Fails (must match exact terms) | Succeeds (understands equivalence) |
| **Context** | No understanding of context | Contextually aware |
| **Misspellings** | Usually fails | Often handles well |
| **Query Understanding** | Literal interpretation | Intent recognition |
| **Example** | "buy sneakers" → only matches "sneakers" | "buy sneakers" → matches "running shoes", "athletic footwear" |

**How Semantic Search Works:**
1. Convert query text into embedding vector using neural network
2. Compare query vector against all document vectors using similarity metric
3. Return top-k most similar documents based on vector proximity
4. Documents cluster together in vector space based on semantic meaning

---

## 2. Vector Embeddings

### 2.1 What Are Embeddings?

Vector embeddings are dense numerical representations of data (text, images, audio) in a continuous vector space where semantic similarity is encoded as spatial proximity.

**Key Characteristics:**
- **Dense vectors**: All values are typically non-zero (unlike sparse representations)
- **Fixed dimensionality**: Each embedding has the same number of dimensions (e.g., 768, 1024, 1536)
- **Learned representations**: Generated by neural networks trained on large datasets
- **Semantic encoding**: Similar concepts map to nearby points in vector space

**Example:**
```
"king" → [0.23, -0.45, 0.89, ..., 0.12]  (1536 dimensions)
"queen" → [0.21, -0.43, 0.87, ..., 0.15]  (nearby in space)
"car" → [-0.67, 0.34, -0.12, ..., 0.88]  (far from king/queen)
```

### 2.2 Embedding Dimensions

Embedding dimensions represent the size of the vector used to encode information. Common dimensions include:

| Model | Dimensions | Use Case |
|-------|-----------|----------|
| sentence-transformers/all-MiniLM-L6-v2 | 384 | Lightweight, fast semantic search |
| BERT-base | 768 | General NLP tasks |
| OpenAI text-embedding-3-small | 512, 1536 | Cost-effective semantic search |
| OpenAI text-embedding-ada-002 | 1536 | High-quality general-purpose |
| OpenAI text-embedding-3-large | 256, 1024, 3072 | Maximum quality, configurable |
| Cohere embed-english-v3.0 | 1024 | Multilingual support |

**Dimension Trade-offs:**

**Higher Dimensions (1536, 3072):**
- Pros: More capacity to encode nuanced semantic information, better quality
- Cons: Higher memory usage, slower search, increased storage costs

**Lower Dimensions (256, 384, 512):**
- Pros: Faster search, lower memory footprint, reduced costs
- Cons: Potentially lower quality, less nuanced representations

**Important Note on Dimension Reduction:**
Modern models like OpenAI's text-embedding-3-* support **Matryoshka Representation Learning (MRL)**, allowing you to truncate dimensions without retraining:
- Train once at full dimensionality (e.g., 3072)
- Use any lower dimension (e.g., 1024) by truncating
- Graceful quality degradation as dimensions decrease

### 2.3 How Neural Networks Generate Embeddings

The embedding generation process involves sophisticated neural network architectures:

#### **Training Process:**

1. **Data Collection**: Gather massive text corpora (billions of words/documents)

2. **Model Architecture**: Use transformer-based neural networks (BERT, GPT, etc.) with:
   - Self-attention mechanisms to capture relationships
   - Multiple layers to learn hierarchical representations
   - Feed-forward networks for non-linear transformations

3. **Training Objectives**: Common approaches include:
   - **Contrastive Learning**: Pull similar examples closer, push dissimilar ones apart
   - **Masked Language Modeling**: Predict masked words from context
   - **Next Sentence Prediction**: Determine if sentences are related
   - **Triplet Loss**: Minimize distance between anchors and positives, maximize for negatives

4. **Optimization**: The network adjusts billions of parameters to minimize loss, learning to encode semantic meaning in vector positions

#### **Inference (Embedding Generation):**

1. Input text is tokenized into subwords
2. Tokens pass through embedding layer (converts tokens to initial vectors)
3. Transformer layers process tokens with self-attention
4. Final representation is extracted (often pooling or [CLS] token)
5. Output: Dense vector embedding representing semantic meaning

**Example with BERT:**
```
Input: "The cat sat on the mat"
↓ Tokenization
["The", "cat", "sat", "on", "the", "mat"]
↓ Embedding Layer
Initial vectors (768-dim each)
↓ 12 Transformer Layers
Contextualized representations
↓ Pooling (e.g., mean or [CLS] token)
Final embedding: [0.23, -0.45, ..., 0.12] (768 dimensions)
```

### 2.4 Why Embeddings Capture Semantic Meaning

Embeddings encode semantics through learned geometric relationships:

#### **Distributional Hypothesis:**
"Words that occur in similar contexts tend to have similar meanings." Neural networks learn this by observing word co-occurrences across billions of examples.

#### **Geometric Properties:**

1. **Similarity as Proximity**: Semantically related concepts cluster together
   ```
   "dog", "puppy", "canine" → nearby in vector space
   "car", "automobile", "vehicle" → another nearby cluster
   ```

2. **Analogical Relationships**: Vector arithmetic captures semantic relationships
   ```
   vector("king") - vector("man") + vector("woman") ≈ vector("queen")
   vector("Paris") - vector("France") + vector("Italy") ≈ vector("Rome")
   ```

3. **Contextual Sensitivity**: Modern embeddings (BERT, ELMo) generate different vectors for the same word in different contexts:
   ```
   "bank" in "river bank" → vector_1
   "bank" in "savings bank" → vector_2
   (vector_1 and vector_2 are different)
   ```

4. **Hierarchical Structure**: Embeddings capture both broad categories and fine-grained distinctions
   ```
   Broad: "animal" domain clusters separately from "vehicle" domain
   Fine: Within "animal", "cat" vs "lion" vs "tiger" have nuanced differences
   ```

### 2.5 Embedding Space Geometry

Understanding the geometric structure of embedding spaces is crucial for effective vector search:

#### **Dimensionality:**
While we live in 3D space, embeddings exist in 256-3072 dimensional spaces. This high dimensionality allows:
- Encoding complex, multi-faceted semantic information
- Representing millions of concepts without collision
- Capturing subtle nuances and relationships

#### **Distance Interpretation:**

**In embedding space, "distance" encodes semantic dissimilarity:**
- **Small distance (high similarity)**: Concepts are semantically related
  ```
  distance("physician", "doctor") = 0.05  → very similar
  ```
- **Large distance (low similarity)**: Concepts are semantically unrelated
  ```
  distance("physician", "asteroid") = 0.89  → very dissimilar
  ```

**Important Properties:**

1. **Curse of Dimensionality**: In high dimensions, most vectors are approximately equidistant from each other. This is why specialized algorithms (HNSW) are needed for efficient search.

2. **Concentration of Measure**: Most of the volume in high-dimensional space is near the surface of hyperspheres, affecting search strategies.

3. **Manifold Structure**: Although embeddings exist in high-dimensional space, meaningful variations often lie on lower-dimensional manifolds (subspaces).

#### **Visualization Challenges:**

Since we can't visualize 1536-dimensional space, dimensionality reduction techniques are used:
- **t-SNE**: Preserves local structure, creates clusters
- **UMAP**: Balances local and global structure
- **PCA**: Linear projection, preserves variance

These projections to 2D/3D help humans understand relationships but lose significant information from the full embedding space.

---

## 3. kNN in OpenSearch

### 3.1 OpenSearch kNN Plugin Architecture

OpenSearch provides native support for vector search through its kNN plugin, which integrates approximate nearest neighbor search algorithms directly into the search engine.

**Architecture Components:**

1. **Custom Codec**: OpenSearch uses a custom codec to write vector data to native library indexes, separate from the standard Lucene index.

2. **Native Library Integration**: The plugin wraps external vector search libraries (FAISS, NMSLIB, Lucene) for high-performance approximate search.

3. **Index Structure**: kNN indices combine traditional inverted indices (for filtering) with vector indices (for similarity search).

4. **Memory Management**: Vector graphs are loaded into native memory (outside JVM heap) with configurable limits via `circuit_breaker_limit`.

**Index Creation Example:**
```json
PUT /my-vector-index
{
  "settings": {
    "index": {
      "knn": true,
      "knn.algo_param.ef_search": 100
    }
  },
  "mappings": {
    "properties": {
      "my_vector": {
        "type": "knn_vector",
        "dimension": 1536,
        "method": {
          "name": "hnsw",
          "engine": "faiss",
          "space_type": "cosinesimil",
          "parameters": {
            "ef_construction": 128,
            "m": 16
          }
        }
      },
      "title": {
        "type": "text"
      }
    }
  }
}
```

### 3.2 HNSW Algorithm (Hierarchical Navigable Small World)

HNSW is the most widely used algorithm for approximate nearest neighbor search, offering excellent speed-accuracy trade-offs.

#### **Core Concepts:**

**1. Navigable Small World Graphs:**
- A graph where most nodes can be reached from any other node in a small number of hops
- Combines short-range links (local connections) and long-range links (shortcuts)
- Enables logarithmic search complexity even in high dimensions

**2. Hierarchical Layers:**
HNSW constructs a multi-layered graph structure resembling a skip list:

```
Layer 2: [●]----------------[●]  (few nodes, longest links)
           ↓                  ↓
Layer 1: [●]------[●]-------[●]-------[●]  (more nodes, medium links)
           ↓       ↓         ↓         ↓
Layer 0: [●]-[●]-[●]-[●]-[●]-[●]-[●]-[●]  (all nodes, shortest links)
```

- **Top layers**: Sparse, with long-distance connections for coarse navigation
- **Bottom layer**: Dense, with all vectors and fine-grained connections

#### **Search Process:**

1. **Entry Point**: Start at the top layer with a designated entry node
2. **Greedy Search**: At each layer, navigate to the neighbor closest to the query
3. **Layer Descent**: When no closer neighbors exist, descend to the next layer
4. **Result Collection**: At the bottom layer, perform final refinement and return top-k results

**Visual Representation:**
```
Query Vector: Q
Entry: Start at Layer 2, node A

Layer 2: A → B (B is closer to Q than A)
         ↓
Layer 1: B → C → D (D is closest to Q in this layer)
         ↓
Layer 0: D → E → F → G (explore neighborhood, return top-k)

Result: [G, F, H, E, ...] (k nearest neighbors)
```

#### **Time Complexity:**

- **Search**: O(log n) average case
- **Insertion**: O(log n) average case
- **Construction**: O(n log n) for n vectors

#### **Memory Characteristics:**

HNSW requires significant memory:
```
Memory ≈ 1.1 × (4 × dimension + 8 × M) bytes per vector
```

For 1 million vectors, 256 dimensions, M=16:
```
Memory ≈ 1.1 × (4 × 256 + 8 × 16) × 1,000,000
       ≈ 1.1 × (1024 + 128) × 1,000,000
       ≈ 1.27 GB
```

### 3.3 OpenSearch kNN Engines

OpenSearch supports three engine options for vector search:

#### **1. Faiss (Facebook AI Similarity Search)**

**Strengths:**
- Best for large-scale deployments (billions of vectors)
- Highly optimized for high-dimensional indexing
- Supports advanced techniques like IVF (Inverted File) and PQ (Product Quantization)
- GPU acceleration available

**Limitations:**
- Higher memory consumption
- More complex configuration

**When to use**: Large-scale production systems with millions to billions of vectors

**Configuration Example:**
```json
{
  "type": "knn_vector",
  "dimension": 1536,
  "method": {
    "name": "hnsw",
    "engine": "faiss",
    "space_type": "cosinesimil",
    "parameters": {
      "ef_construction": 256,
      "m": 32
    }
  }
}
```

#### **2. Lucene**

**Strengths:**
- Native integration with OpenSearch (no external libraries)
- Best latency and recall for datasets up to a few million vectors
- Most memory-efficient (smallest index size)
- Intelligent filtering with automatic strategy selection
- Supports efficient pre-filtering

**Limitations:**
- Maximum 1,024 dimensions (vs 16,000 for Faiss/NMSLIB)
- Not optimal for very high recall requirements (>0.95)
- Not ideal for billions of vectors

**When to use**: Small to medium datasets (< few million vectors), when filtering is important, memory-constrained environments

**Configuration Example:**
```json
{
  "type": "knn_vector",
  "dimension": 768,
  "method": {
    "name": "hnsw",
    "engine": "lucene",
    "space_type": "cosinesimil",
    "parameters": {
      "ef_construction": 128,
      "m": 16
    }
  }
}
```

#### **3. NMSLIB (Non-Metric Space Library)**

**Status**: DEPRECATED as of OpenSearch 3.0

**Historical Context:**
- One of the first vector search implementations in OpenSearch
- Replaced by Faiss and Lucene engines with better performance
- New index creation blocked in OpenSearch 3.0+

**Migration**: Existing NMSLIB indices should be migrated to Faiss or Lucene

#### **Engine Comparison Table:**

| Feature | Lucene | Faiss | NMSLIB (deprecated) |
|---------|--------|-------|---------------------|
| Max Dimensions | 1,024 | 16,000 | 16,000 |
| Optimal Dataset Size | < few million | Millions to billions | N/A |
| Memory Efficiency | Best | Good | Fair |
| Query Latency | Best (small datasets) | Good (large datasets) | Fair |
| Filtering | Smart filtering | Basic | Basic |
| Native to OpenSearch | Yes | No (external lib) | No (external lib) |
| Recall at High k | Moderate | Excellent | Fair |

**Recommendation:**
- **< 5 million vectors + need filtering → Lucene**
- **> 5 million vectors or need very high recall → Faiss**
- **NMSLIB → migrate to Faiss or Lucene**

### 3.4 kNN Query Syntax and Parameters

#### **Basic kNN Query:**

```json
GET /my-index/_search
{
  "size": 10,
  "query": {
    "knn": {
      "my_vector": {
        "vector": [0.23, -0.45, 0.89, ..., 0.12],
        "k": 50
      }
    }
  }
}
```

#### **Key Parameters:**

**1. k (required)**
- Number of nearest neighbors to find
- Larger k = more candidates considered, better recall, higher latency
- Typical values: 10-100
- **Important**: OpenSearch may return fewer than k results after filtering

**2. vector (required)**
- The query vector to compare against indexed vectors
- Must match the dimension of the indexed field

**3. ef_search (optional, query-time)**
Controls the size of the candidate list during graph traversal:
```json
{
  "knn": {
    "my_vector": {
      "vector": [...],
      "k": 10,
      "method_parameters": {
        "ef_search": 100
      }
    }
  }
}
```

- Higher ef_search = better recall, slower queries
- Default: often 100-512 depending on engine
- **Rule of thumb**: ef_search >= k (typically 2-10x k)
- **Lucene behavior**: Ignores ef_search, dynamically sets it to k

**4. ef_construction (index-time, set in mapping)**
Controls candidate list size during index construction:
```json
{
  "method": {
    "parameters": {
      "ef_construction": 128
    }
  }
}
```

- Higher ef_construction = better graph quality, slower indexing
- Typical values: 100-512
- **Trade-off**: Spend more time building a better index for faster, more accurate searches

**5. m (index-time parameter)**
Maximum number of bidirectional links per node in the graph:
```json
{
  "method": {
    "parameters": {
      "m": 16
    }
  }
}
```

- Higher m = better recall, more memory, slower indexing
- Typical values: 16-48
- Default: often 16
- **Memory impact**: Each link costs ~8 bytes per vector

**6. space_type (distance metric)**
Specifies the similarity/distance function:
```json
{
  "method": {
    "space_type": "cosinesimil"  // or "l2", "innerproduct"
  }
}
```

Options:
- `cosinesimil`: Cosine similarity (recommended for text embeddings)
- `l2`: Euclidean distance
- `innerproduct`: Dot product

#### **Advanced Query with Filtering:**

```json
GET /my-index/_search
{
  "size": 10,
  "query": {
    "bool": {
      "must": [
        {
          "knn": {
            "my_vector": {
              "vector": [...],
              "k": 50
            }
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        },
        {
          "range": {
            "price": {
              "lte": 1000
            }
          }
        }
      ]
    }
  }
}
```

### 3.5 Approximate vs Exact kNN Search

#### **Approximate kNN (Default)**

Uses graph-based algorithms (HNSW) for sub-linear search complexity.

**Characteristics:**
- **Speed**: Very fast, O(log n) complexity
- **Accuracy**: High recall (typically 95-99%) but not guaranteed 100%
- **Scalability**: Handles millions to billions of vectors efficiently
- **Use cases**: Production systems, large datasets, real-time applications

**Trade-offs:**
- May miss true nearest neighbors (imperfect recall)
- Tunable via parameters (ef_search, ef_construction, m)
- Memory overhead for graph structure

**Example Setup:**
```json
{
  "type": "knn_vector",
  "dimension": 768,
  "method": {
    "name": "hnsw",
    "engine": "lucene",
    "parameters": {
      "ef_construction": 128,
      "m": 16
    }
  }
}
```

#### **Exact kNN**

Computes distance to every vector in the index (brute force).

**Characteristics:**
- **Speed**: Slow, O(n) complexity (linear scan)
- **Accuracy**: Perfect recall (100%), guaranteed true k-nearest neighbors
- **Scalability**: Poor, degrades linearly with dataset size
- **Use cases**: Small datasets (< 10,000 docs), validation, benchmarking

**Implementation via Script Score:**
```json
GET /my-index/_search
{
  "query": {
    "script_score": {
      "query": {"match_all": {}},
      "script": {
        "source": "cosineSimilarity(params.query_vector, 'my_vector') + 1.0",
        "params": {
          "query_vector": [0.23, -0.45, ...]
        }
      }
    }
  }
}
```

**When to Use Each:**

| Scenario | Approximate kNN | Exact kNN |
|----------|----------------|-----------|
| < 10,000 documents | Maybe | Recommended |
| 10K - 1M documents | Recommended | Possible but slow |
| > 1M documents | Strongly recommended | Impractical |
| Real-time applications | Yes | No |
| Perfect recall required | No | Yes |
| Benchmarking/validation | As comparison | As baseline |

**Performance Example** (1M vectors, 768 dims):
- **Approximate kNN**: 5-20ms per query (95%+ recall)
- **Exact kNN**: 200-500ms per query (100% recall)

### 3.6 Performance Considerations and Index Size

#### **Memory Requirements**

**HNSW Memory Formula:**
```
Memory per vector = 1.1 × (4 × dimension + 8 × M) bytes
```

**Concrete Examples:**

| Vectors | Dimensions | M | Memory Required |
|---------|-----------|---|-----------------|
| 1M | 256 | 16 | ~1.27 GB |
| 1M | 768 | 16 | ~3.5 GB |
| 1M | 1536 | 16 | ~6.9 GB |
| 10M | 768 | 16 | ~35 GB |
| 10M | 1536 | 32 | ~81 GB |

**Important Notes:**
1. **Replicas double memory**: 1 replica = 2x memory (primary + replica)
2. **Circuit breaker**: By default, kNN uses 50% of available RAM (non-JVM heap)
3. **JVM heap**: OpenSearch uses ~50% of instance RAM for JVM (up to 32GB max)

**Example Calculation for AWS Instance:**
- Instance: r6g.xlarge (32 GB RAM)
- JVM heap: 16 GB
- Available for kNN: 16 GB × 50% = 8 GB
- Can index: ~2.3M vectors at 768 dims, M=16 (without replicas)

#### **Index Size Optimization Strategies**

**1. Dimension Reduction:**
Use models with Matryoshka Representation Learning (MRL):
```json
// Instead of 3072 dimensions
"dimension": 1024  // Truncate to 1024, saves 3x memory
```

**2. Binary/Byte Vectors:**
- **Binary vectors**: 32x memory reduction (float → binary)
- **Byte vectors**: 4x memory reduction (float32 → int8)
- Trade-off: Some quality loss

**3. Product Quantization (PQ):**
Lossy compression technique available in Faiss:
```json
{
  "method": {
    "name": "hnsw",
    "engine": "faiss",
    "parameters": {
      "encoder": {
        "name": "pq",
        "parameters": {
          "code_size": 8
        }
      }
    }
  }
}
```
- Reduces memory significantly
- Decreases recall by ~5-10%

**4. Disk-Based Search (OpenSearch 2.13+):**
Store vectors on disk instead of memory:
- Lower memory footprint
- Higher search latency (still acceptable)
- Cost-effective for large-scale deployments

#### **Indexing Performance**

**Factors Affecting Indexing Speed:**

1. **ef_construction**: Higher = slower indexing
2. **m**: Higher = slower indexing
3. **Document size**: Larger documents = slower
4. **Refresh interval**: More frequent refreshes = slower overall throughput

**Optimization for Bulk Indexing:**
```json
PUT /my-index/_settings
{
  "index": {
    "refresh_interval": "30s",  // Reduce refresh frequency
    "number_of_replicas": 0      // Add replicas after indexing
  }
}
```

**Typical Indexing Rates:**
- Small vectors (256 dims): 1000-5000 docs/sec
- Medium vectors (768 dims): 500-2000 docs/sec
- Large vectors (1536 dims): 200-1000 docs/sec

(Rates vary significantly based on hardware, configuration, document complexity)

#### **Query Performance**

**Factors Affecting Query Latency:**

1. **k**: Higher k = more candidates = slower
2. **ef_search**: Higher = better recall but slower
3. **Filters**: Restrictive filters can slow queries
4. **Dataset size**: Logarithmic degradation (HNSW scales well)
5. **Concurrent queries**: More load = higher latency per query

**Tuning for Latency vs Recall:**

| Priority | Configuration |
|----------|---------------|
| **Low Latency** | k=10, ef_search=20, m=8, ef_construction=64 |
| **Balanced** | k=20, ef_search=100, m=16, ef_construction=128 |
| **High Recall** | k=50, ef_search=512, m=32, ef_construction=256 |

**Typical Query Latencies** (Approximate kNN):
- Small index (<100K vectors): 1-5ms
- Medium index (1M vectors): 5-20ms
- Large index (10M vectors): 10-40ms
- Very large index (100M+ vectors): 20-100ms

#### **Index Size on Disk**

Besides memory, consider disk storage:

**Components:**
1. Native library index (HNSW graph)
2. Lucene segments (document storage, inverted indices)
3. Translog and other metadata

**Rough Estimate:**
```
Disk size ≈ Memory requirements + Document storage + 30% overhead
```

For 1M documents with 768-dim vectors and 5KB average document:
- HNSW memory: ~3.5 GB
- Document storage: ~5 GB
- Overhead: ~2.5 GB
- **Total disk**: ~11 GB

---

## 4. Multi-Vector Search

### 4.1 Nested Fields with Multiple Vectors

Multi-vector search enables searching over documents that contain multiple embeddings per document. Common scenarios:

**Use Cases:**
1. **E-commerce**: Products with multiple images, each with its own embedding
2. **Real estate**: Properties with multiple room photos
3. **Documents**: Long documents split into paragraph/section embeddings
4. **Multi-modal**: Items with text + image embeddings

**Index Mapping with Nested Vectors:**
```json
PUT /multi-vector-index
{
  "settings": {
    "index": {
      "knn": true
    }
  },
  "mappings": {
    "properties": {
      "product_name": {
        "type": "text"
      },
      "images": {
        "type": "nested",
        "properties": {
          "image_url": {
            "type": "keyword"
          },
          "image_vector": {
            "type": "knn_vector",
            "dimension": 512,
            "method": {
              "name": "hnsw",
              "engine": "lucene",
              "space_type": "cosinesimil"
            }
          },
          "image_description": {
            "type": "text"
          }
        }
      }
    }
  }
}
```

**Sample Document:**
```json
{
  "product_name": "Modern Living Room Set",
  "images": [
    {
      "image_url": "sofa_front.jpg",
      "image_vector": [0.12, -0.34, ...],
      "image_description": "Front view of sofa"
    },
    {
      "image_url": "sofa_side.jpg",
      "image_vector": [0.15, -0.31, ...],
      "image_description": "Side view of sofa"
    },
    {
      "image_url": "chair.jpg",
      "image_vector": [0.08, -0.29, ...],
      "image_description": "Matching armchair"
    }
  ]
}
```

### 4.2 score_mode Options

The `score_mode` parameter determines how multiple nested vector scores are aggregated to produce the parent document's final score.

#### **Available Score Modes:**

**1. max (Maximum Score)**
```json
GET /multi-vector-index/_search
{
  "query": {
    "nested": {
      "path": "images",
      "score_mode": "max",
      "query": {
        "knn": {
          "images.image_vector": {
            "vector": [0.1, -0.3, ...],
            "k": 10
          }
        }
      }
    }
  }
}
```

**Behavior**: Uses the highest similarity score among all nested vectors
- Parent score = max(score₁, score₂, ..., scoreₙ)

**2. avg (Average Score - DEFAULT)**
```json
{
  "nested": {
    "path": "images",
    "score_mode": "avg",
    "query": { ... }
  }
}
```

**Behavior**: Averages all nested vector scores
- Parent score = (score₁ + score₂ + ... + scoreₙ) / n

**3. sum (Sum of Scores)**
```json
{
  "nested": {
    "path": "images",
    "score_mode": "sum",
    "query": { ... }
  }
}
```

**Behavior**: Sums all nested vector scores
- Parent score = score₁ + score₂ + ... + scoreₙ

**4. min (Minimum Score)**
```json
{
  "nested": {
    "path": "images",
    "score_mode": "min",
    "query": { ... }
  }
}
```

**Behavior**: Uses the lowest similarity score
- Parent score = min(score₁, score₂, ..., scoreₙ)
- Rarely used in practice for vector search

#### **Important Limitation:**

> When using `avg` or `sum` score modes, OpenSearch does NOT guarantee true top-k results by those aggregations. The system first identifies top-k documents using `max` scoring, then reorders those k documents using `avg` or `sum`.

This means:
- Initial retrieval uses max score internally
- Final ranking within those k results uses specified score_mode
- True global top-k by avg/sum may be missed if not in initial max-based top-k

### 4.3 When to Use max vs sum for Multiple Vectors

#### **Use max when:**

**1. Best Match Matters**
You want to find documents where ANY one nested vector strongly matches:
```
Example: Product image search
- User queries with an image of a "red sofa"
- Product has 5 images: [sofa, chair, lamp, rug, pillow]
- Only the sofa image should match strongly
- Use max to surface this product based on best single match
```

**2. Variable Number of Vectors per Document**
When documents have different numbers of nested vectors:
```
Product A: 3 images
Product B: 10 images

With max: Both fairly compared on their best match
With sum: Product B unfairly boosted (more opportunities to accumulate score)
With avg: Better than sum, but best match might be diluted
```

**3. Sparse Relevance**
Few vectors in the document are relevant to the query:
```
Real estate property with 20 room photos
Query: "modern kitchen"
Only 2-3 kitchen photos relevant
max captures the best kitchen match
```

**4. MaxSim Aggregation (ColBERT-style)**
For token-level multi-vector search:
```
Query tokens: ["modern", "kitchen", "design"]
Document tokens: [100 token vectors]

For each query token, find max similarity with any document token
Final score = sum of these max similarities per query token
```

#### **Use sum when:**

**1. Cumulative Evidence**
Multiple matching vectors should strengthen the result:
```
Example: Document paragraph search
- Each paragraph has an embedding
- Document with multiple relevant paragraphs should rank higher
- sum accumulates evidence across paragraphs
```

**2. Fixed Number of Vectors**
All documents have the same vector count:
```
All products have exactly 5 standard view images
sum fairly aggregates across all views
```

**3. Multi-modal Fusion**
Combining different types of vectors:
```
Document with: [title_vector, abstract_vector, content_vector]
sum combines evidence from all modalities
```

#### **Use avg when:**

**1. Normalized Aggregation**
Want to aggregate while normalizing for vector count:
```
Documents with varying numbers of vectors
avg prevents bias toward documents with more vectors
```

**2. Overall Similarity**
Interested in overall document-query alignment:
```
All vectors should contribute equally
Outliers (very high or low scores) should be moderated
```

#### **Decision Matrix:**

| Scenario | Variable Vector Count | Few Relevant Vectors | Multiple Should Boost | Recommended |
|----------|----------------------|---------------------|----------------------|-------------|
| Image search | Yes | Yes | No | **max** |
| Product variants | Yes | Yes | No | **max** |
| Paragraph search | Yes | No | Yes | **sum** or **avg** |
| Multi-modal fixed | No | No | Yes | **sum** |
| Document sections | Yes | No | Yes | **avg** |

#### **Practical Example Comparison:**

**Scenario**: Search for "modern sofa" in furniture products

**Product A** (3 images):
- Image 1 (sofa): similarity = 0.95
- Image 2 (pillow): similarity = 0.30
- Image 3 (rug): similarity = 0.25

**Product B** (6 images):
- Image 1 (sofa): similarity = 0.85
- Image 2 (chair): similarity = 0.40
- Image 3 (lamp): similarity = 0.35
- Image 4 (table): similarity = 0.30
- Image 5 (pillow): similarity = 0.28
- Image 6 (rug): similarity = 0.22

**Scoring:**
```
max:  Product A = 0.95,  Product B = 0.85  → A wins (correct)
sum:  Product A = 1.50,  Product B = 2.40  → B wins (incorrect, just more images)
avg:  Product A = 0.50,  Product B = 0.40  → A wins (correct, but diluted)
```

**Conclusion**: `max` correctly identifies Product A as the best match despite having fewer images.

### 4.4 Performance Implications of Multi-Vector Search

#### **Computational Costs:**

**1. Index Size**
```
Single vector per doc: 1M docs × 768 dims = baseline
Multiple vectors (avg 5): 5M vectors × 768 dims = 5x baseline memory
```

**2. Query Latency**
Multi-vector search is computationally more expensive:
- More vectors to compare against
- Nested query overhead
- Score aggregation processing

**Typical Latency Increase:**
- Single vector: 10ms
- Multi-vector (avg 5 per doc): 15-30ms (1.5-3x slower)

**3. Filtering Complexity**
Combining nested kNN with filters is expensive:
```json
GET /multi-vector-index/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "nested": {
            "path": "images",
            "score_mode": "max",
            "query": {
              "knn": {
                "images.image_vector": {
                  "vector": [...],
                  "k": 50
                }
              }
            }
          }
        }
      ],
      "filter": [
        {"term": {"category": "furniture"}},
        {"range": {"price": {"lte": 1000}}}
      ]
    }
  }
}
```
- Filters must be evaluated for each parent document
- Nested scoring requires additional passes

#### **Optimization Strategies:**

**1. Limit Vectors per Document**
Keep the number of nested vectors reasonable:
- **Good**: 2-10 vectors per document
- **Acceptable**: 10-50 vectors per document
- **Problematic**: 100+ vectors per document

**2. Use expand_nested_docs Judiciously**
Retrieving individual nested vector scores adds overhead:
```json
{
  "nested": {
    "query": {
      "knn": {
        "images.image_vector": {
          "vector": [...],
          "k": 10,
          "expand_nested_docs": false  // Only parent scores
        }
      }
    }
  }
}
```

**3. Increase k for Better Recall**
With filtering, you may need larger k:
```json
{
  "knn": {
    "images.image_vector": {
      "vector": [...],
      "k": 100  // Higher k for nested + filtering
    }
  }
}
```

**4. Consider Alternative Architectures**

For very large multi-vector scenarios:

**Option A: Flatten Structure**
```json
// Instead of nested vectors, create separate documents
{
  "product_id": "123",
  "image_id": "img1",
  "image_vector": [...],
  "product_name": "Sofa"
}
{
  "product_id": "123",
  "image_id": "img2",
  "image_vector": [...],
  "product_name": "Sofa"
}
```
- Simpler queries
- Use collapse or aggregation to deduplicate products
- Better performance for large-scale

**Option B: Pre-aggregated Vectors**
```json
// Aggregate multiple vectors at indexing time
{
  "product_name": "Sofa",
  "combined_vector": [...]  // Average or weighted combination of image vectors
}
```
- Single vector per document
- Fast queries
- Loss of granularity (can't identify which specific image matched)

**5. Memory Provisioning**
Ensure adequate memory for multi-vector indices:
```
Required memory = num_docs × avg_vectors_per_doc × vector_memory

Example:
1M products × 5 images × 3.5 GB/1M vectors (768 dims) = 17.5 GB
```

---

## 5. Filtering with kNN

Combining vector similarity search with traditional filters (category, price, date, etc.) is crucial for real-world applications. OpenSearch offers three filtering strategies with different trade-offs.

### 5.1 Filtering Approaches

#### **1. Pre-filtering (Scoring Script Filter)**

**How it works:**
1. Apply filters first to create a subset of documents
2. Run exact kNN search on the filtered subset

**Implementation:**
```json
GET /my-index/_search
{
  "query": {
    "script_score": {
      "query": {
        "bool": {
          "filter": [
            {"term": {"category": "electronics"}},
            {"range": {"price": {"lte": 1000}}}
          ]
        }
      },
      "script": {
        "source": "cosineSimilarity(params.query_vector, 'my_vector') + 1.0",
        "params": {
          "query_vector": [0.1, -0.3, ...]
        }
      }
    }
  }
}
```

**Characteristics:**
- Uses exact kNN (brute force) on filtered subset
- Guarantees perfect recall within filtered set
- O(n) complexity where n = filtered subset size

**When to use:**
- Small filtered subsets (< 10,000 docs)
- Highly restrictive filters
- When perfect recall is required

**Limitations:**
- Does NOT scale to large filtered subsets
- High latency if filters match many documents
- No graph traversal, loses HNSW benefits

#### **2. Post-filtering**

**How it works:**
1. Run vector search first to find top-k neighbors
2. Apply filters to the results after retrieval

**Implementation:**
```json
GET /my-index/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "knn": {
            "my_vector": {
              "vector": [0.1, -0.3, ...],
              "k": 100
            }
          }
        }
      ],
      "filter": [
        {"term": {"category": "electronics"}}
      ]
    }
  }
}
```

**Characteristics:**
- Fast vector search with HNSW
- Filters applied after retrieval
- May return fewer than k results

**When to use:**
- Lenient filters (match most documents)
- When some results are acceptable even if < k
- Performance is more important than recall

**Limitations:**
- **Critical issue**: Can return significantly fewer than k results
  ```
  Request k=100, but after filtering only 15 results remain
  ```
- Poor recall for restrictive filters
- Unpredictable result counts

#### **3. Efficient Filtering (Filter-During-Search) - RECOMMENDED**

**Introduced**: OpenSearch 2.9 (Faiss), improved in 2.10-2.13

**How it works:**
OpenSearch intelligently chooses between strategies based on the filtered subset size:
- **Small filtered set**: Runs exact kNN for perfect accuracy
- **Large filtered set**: Performs approximate kNN with filter-aware graph traversal

**Implementation:**
```json
GET /my-index/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "knn": {
            "my_vector": {
              "vector": [0.1, -0.3, ...],
              "k": 50,
              "filter": {
                "bool": {
                  "must": [
                    {"term": {"category": "electronics"}},
                    {"range": {"price": {"lte": 1000}}}
                  ]
                }
              }
            }
          }
        }
      ]
    }
  }
}
```

**Characteristics:**
- Automatically selects optimal strategy
- Uses graph traversal with filter awareness
- Balances recall and latency
- Available for **Faiss** and **Lucene** engines (not NMSLIB)

**When to use:**
- **Default choice for production systems**
- Any filtered kNN search scenario
- When using Faiss or Lucene engines

**Advantages:**
- Best of both worlds (recall + performance)
- Predictable result counts
- Scales to large datasets

**Requirements:**
- OpenSearch 2.9+ for Faiss
- OpenSearch 2.13+ for Lucene IVF
- Must use Faiss or Lucene engine

### 5.2 How Filters Affect kNN Recall

Recall measures what fraction of true nearest neighbors are retrieved:
```
Recall = (Retrieved True Neighbors) / (Total True Neighbors)
```

**Example:**
- True 10 nearest neighbors: [A, B, C, D, E, F, G, H, I, J]
- System retrieves: [A, B, C, E, F, X, Y, Z, W, V]
- Retrieved true neighbors: 5 (A, B, C, E, F)
- Recall = 5/10 = 0.5 (50%)

#### **Filter Impact on Recall:**

**Post-filtering:**
```
Scenario: 1M docs, filter matches 10% (100K docs)
- kNN retrieves top-100 without filter
- If only 8 of those 100 pass the filter → return 8 results
- Recall degraded significantly
```

**Pre-filtering (Exact kNN):**
```
Same scenario:
- Filter first → 100K docs
- Exact kNN on 100K → perfect recall within filtered set
- But slow (O(100K) comparisons)
```

**Efficient Filtering:**
```
Same scenario:
- Detects 100K filtered docs
- Uses approximate kNN with filter-aware traversal
- Returns ~50-100 results with high recall (90-95%)
- Fast (O(log 100K) with graph)
```

#### **Recall vs Filter Selectivity:**

| Filter Selectivity | Matched Docs | Post-Filter Recall | Efficient Filter Recall | Pre-Filter Recall |
|-------------------|--------------|-------------------|------------------------|-------------------|
| Very Lenient | 90% | High (~90%) | High (~95%) | Perfect (100%) |
| Moderate | 50% | Moderate (~60%) | High (~90%) | Perfect (100%) |
| Restrictive | 10% | Low (~20%) | High (~85%) | Perfect (100%) |
| Very Restrictive | 1% | Very Low (~5%) | Moderate (~70%) | Perfect (100%) |

### 5.3 Best Practices for Combining Filters with kNN

#### **1. Use Efficient Filtering as Default**

**Recommended Pattern:**
```json
GET /my-index/_search
{
  "size": 20,
  "query": {
    "knn": {
      "my_vector": {
        "vector": [...],
        "k": 50,
        "filter": {
          "bool": {
            "must": [
              {"term": {"status": "active"}},
              {"term": {"category": "electronics"}}
            ],
            "filter": [
              {"range": {"price": {"gte": 100, "lte": 1000}}},
              {"term": {"in_stock": true}}
            ]
          }
        }
      }
    }
  }
}
```

**Why:**
- Optimal performance and recall trade-off
- Automatic strategy selection
- Consistent result counts

#### **2. Increase k When Using Filters**

The more restrictive the filter, the higher k should be:

**Without filters:**
```json
{"k": 10}  // Requesting 10 results
```

**With moderate filtering:**
```json
{"k": 30}  // 3x increase to account for filtering
```

**With restrictive filtering:**
```json
{"k": 100}  // 10x increase for highly selective filters
```

**Rule of Thumb:**
```
k = desired_results × (1 / estimated_filter_selectivity) × safety_factor

Example:
- Want 20 results
- Filter matches 10% of docs (selectivity = 0.1)
- Safety factor = 2
- k = 20 × (1/0.1) × 2 = 400
```

#### **3. Use Index-Level Filters for Performance**

Some filters should be applied at index organization level:

**Separate Indices by Category:**
```
Instead of: single index with "category" field
Use: /electronics-index, /clothing-index, /furniture-index

Query specific index directly:
GET /electronics-index/_search
{
  "query": {
    "knn": {
      "my_vector": {...}
    }
  }
}
```

**Benefits:**
- No filter overhead
- Better cache utilization
- Smaller indices = faster queries

#### **4. Optimize Filter Order in bool Query**

OpenSearch evaluates filters in order; put most selective first:

**Inefficient:**
```json
{
  "bool": {
    "filter": [
      {"term": {"in_stock": true}},        // Matches 80% of docs
      {"term": {"category": "vintage"}},   // Matches 2% of docs
      {"range": {"price": {"gte": 5000}}}  // Matches 5% of docs
    ]
  }
}
```

**Optimized:**
```json
{
  "bool": {
    "filter": [
      {"term": {"category": "vintage"}},   // Most selective first
      {"range": {"price": {"gte": 5000}}},
      {"term": {"in_stock": true}}
    ]
  }
}
```

#### **5. Monitor Filter Impact on Recall**

Regularly measure recall with filters enabled:

**Validation Query:**
```json
// 1. Run with efficient filtering
GET /my-index/_search
{
  "query": {
    "knn": {
      "my_vector": {
        "vector": [...],
        "k": 50,
        "filter": {...}
      }
    }
  }
}

// 2. Run with pre-filtering (ground truth)
GET /my-index/_search
{
  "query": {
    "script_score": {
      "query": {"bool": {"filter": {...}}},
      "script": {...}
    }
  }
}

// 3. Compare results, calculate recall
```

**Target Metrics:**
- Recall > 90%: Excellent
- Recall 80-90%: Good
- Recall 70-80%: Acceptable
- Recall < 70%: Investigate (increase k, adjust ef_search, review filters)

#### **6. Consider Hybrid Search for Complex Scenarios**

Combine vector search with BM25 (keyword search):

```json
GET /my-index/_search
{
  "query": {
    "bool": {
      "should": [
        {
          "knn": {
            "my_vector": {
              "vector": [...],
              "k": 50,
              "boost": 0.7
            }
          }
        },
        {
          "multi_match": {
            "query": "modern electronics",
            "fields": ["title", "description"],
            "boost": 0.3
          }
        }
      ],
      "filter": [
        {"term": {"category": "electronics"}},
        {"range": {"price": {"lte": 1000}}}
      ]
    }
  }
}
```

**Benefits:**
- Combines semantic (vector) and lexical (keyword) relevance
- More robust for queries with specific terms
- Better handling of filters

#### **7. Engine-Specific Considerations**

**Lucene:**
- Best filtering support with smart automatic strategy selection
- Recommended for filter-heavy workloads
- Limitation: Max 1,024 dimensions

**Faiss:**
- Efficient filtering available since OpenSearch 2.9
- IVF algorithm support added in 2.10
- Better for large-scale with > 1,024 dimensions

**Configuration Example (Lucene with filtering):**
```json
PUT /my-index
{
  "settings": {
    "index.knn": true
  },
  "mappings": {
    "properties": {
      "my_vector": {
        "type": "knn_vector",
        "dimension": 768,
        "method": {
          "name": "hnsw",
          "engine": "lucene",
          "space_type": "cosinesimil",
          "parameters": {
            "ef_construction": 256,
            "m": 32
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "float"
      }
    }
  }
}
```

---

## 6. Best Practices and Performance Tuning

### 6.1 Tuning for Recall vs Latency

Every kNN system must balance three competing factors:

```
           Recall (Accuracy)
                 △
                / \
               /   \
              /     \
             /       \
            /         \
           /           \
          /             \
         /               \
    Latency ◄─────────► Memory
   (Speed)              (Cost)
```

#### **Parameter Impact Matrix:**

| Parameter | Increase Effect | Recall | Latency | Memory | Indexing Time |
|-----------|----------------|--------|---------|--------|---------------|
| **k** | More candidates | ↑ | ↑ | - | - |
| **ef_search** | Larger candidate list | ↑↑ | ↑↑ | - | - |
| **ef_construction** | Better graph quality | ↑ | - | - | ↑↑ |
| **m** | More graph links | ↑ | ↑ (slight) | ↑ | ↑ |
| **dimension** | More features | ↑ (maybe) | ↑ | ↑↑ | ↑ |

#### **Tuning Recipes:**

**For Maximum Speed (Low Latency):**
```json
{
  "method": {
    "name": "hnsw",
    "engine": "lucene",
    "parameters": {
      "ef_construction": 64,
      "m": 8
    }
  }
}

// Query:
{
  "knn": {
    "my_vector": {
      "vector": [...],
      "k": 10,
      "method_parameters": {
        "ef_search": 20
      }
    }
  }
}
```
- Expected recall: 85-90%
- Expected latency: 1-5ms (small index)

**For Balanced Performance:**
```json
{
  "method": {
    "parameters": {
      "ef_construction": 128,
      "m": 16
    }
  }
}

// Query:
{
  "knn": {
    "my_vector": {
      "k": 20,
      "method_parameters": {
        "ef_search": 100
      }
    }
  }
}
```
- Expected recall: 93-97%
- Expected latency: 5-20ms

**For Maximum Recall:**
```json
{
  "method": {
    "parameters": {
      "ef_construction": 256,
      "m": 32
    }
  }
}

// Query:
{
  "knn": {
    "my_vector": {
      "k": 50,
      "method_parameters": {
        "ef_search": 512
      }
    }
  }
}
```
- Expected recall: 97-99%
- Expected latency: 20-50ms

### 6.2 Memory Optimization

**Strategy 1: Reduce Dimensions**

Use MRL-trained models:
```json
// Instead of 3072 dimensions:
"dimension": 1024

// Memory savings:
// 3072 dims: ~13 MB/1M vectors → 1024 dims: ~4.5 MB/1M vectors
// 3x reduction
```

**Strategy 2: Byte Quantization**

```json
{
  "type": "knn_vector",
  "dimension": 768,
  "data_type": "byte",  // int8 instead of float32
  "method": {...}
}
```
- 4x memory reduction
- Minimal quality loss (<2% recall degradation)

**Strategy 3: Product Quantization (PQ)**

```json
{
  "method": {
    "name": "hnsw",
    "engine": "faiss",
    "parameters": {
      "encoder": {
        "name": "pq",
        "parameters": {
          "code_size": 8,
          "m": 8
        }
      }
    }
  }
}
```
- 8-32x memory reduction
- 5-10% recall degradation

**Strategy 4: Disk-Based Search**

For very large indices where memory is constrained:
```json
{
  "method": {
    "name": "hnsw",
    "engine": "faiss",
    "parameters": {
      "disk_based": true
    }
  }
}
```
- Minimal memory footprint
- 2-3x latency increase
- Cost-effective for billion-scale

### 6.3 Index Configuration Checklist

**1. Disable Replicas During Bulk Indexing**
```json
PUT /my-index/_settings
{
  "index": {
    "number_of_replicas": 0
  }
}

// After indexing complete:
PUT /my-index/_settings
{
  "index": {
    "number_of_replicas": 1
  }
}
```

**2. Increase Refresh Interval**
```json
PUT /my-index/_settings
{
  "index": {
    "refresh_interval": "30s"  // Default: 1s
  }
}
```

**3. Configure Circuit Breaker**
```json
PUT /_cluster/settings
{
  "persistent": {
    "knn.memory.circuit_breaker.limit": "60%",
    "knn.memory.circuit_breaker.enabled": true
  }
}
```

**4. Use Appropriate Shard Count**
```json
PUT /my-index
{
  "settings": {
    "index": {
      "number_of_shards": 5,  // Rule: 10-50GB per shard
      "number_of_replicas": 1
    }
  }
}
```

**5. Enable Force Merge After Indexing**
```bash
POST /my-index/_forcemerge?max_num_segments=1
```
- Reduces segment count
- Improves query performance
- Run after bulk indexing complete

### 6.4 Monitoring and Debugging

**Key Metrics to Monitor:**

**1. kNN Graph Memory Usage**
```bash
GET /_cat/nodes?v&h=name,heap.percent,ram.percent,knn.graph_memory_usage
```

**2. Query Performance**
```bash
GET /my-index/_search
{
  "profile": true,
  "query": {
    "knn": {
      "my_vector": {
        "vector": [...],
        "k": 20
      }
    }
  }
}
```
- Analyze `profile` results for bottlenecks

**3. kNN Stats**
```bash
GET /_plugins/_knn/stats
```

Returns:
- Hit count
- Miss count
- Graph memory usage
- Cache evictions

**4. Circuit Breaker Events**
```bash
GET /_nodes/stats/breaker
```
- Monitor for circuit breaker trips
- Indicates memory pressure

### 6.5 Common Issues and Solutions

| Issue | Symptom | Solution |
|-------|---------|----------|
| **Low Recall** | Irrelevant results returned | Increase ef_search, increase k, use efficient filtering |
| **High Latency** | Slow queries | Decrease ef_search, reduce k, use Lucene engine, add shards |
| **Circuit Breaker Trips** | Index/query failures | Increase circuit_breaker_limit, reduce vector dimensions, use PQ |
| **Memory Pressure** | OOM errors, slow indexing | Reduce replica count during indexing, use byte vectors, reduce m parameter |
| **Post-Filter Returns Few Results** | < k results returned | Use efficient filtering, increase k, use less restrictive filters |
| **Slow Indexing** | Long indexing times | Reduce ef_construction, reduce replicas, increase refresh_interval |

### 6.6 Recommended Architecture Patterns

**Small Dataset (< 1M vectors):**
```
Engine: Lucene
Dimensions: 768-1024
ef_construction: 128
m: 16
Shards: 1-2
Replicas: 1
```

**Medium Dataset (1-10M vectors):**
```
Engine: Lucene or Faiss
Dimensions: 768-1024
ef_construction: 128-256
m: 16-32
Shards: 3-5
Replicas: 1
Memory: 16-64 GB
```

**Large Dataset (10-100M vectors):**
```
Engine: Faiss
Dimensions: 768-1024
ef_construction: 256
m: 32
Shards: 10-20
Replicas: 1
Memory: 128-512 GB
Consider: PQ encoding, byte vectors
```

**Very Large Dataset (100M+ vectors):**
```
Engine: Faiss with IVF
Dimensions: 512-1024
Disk-based: Consider enabling
PQ encoding: Recommended
Shards: 20-50+
Replicas: 1
Memory: 512+ GB or disk-based
```

---

## Conclusion

k-Nearest Neighbors vector search in OpenSearch represents a powerful fusion of machine learning and information retrieval. By encoding semantic meaning in dense vectors and using sophisticated graph algorithms like HNSW, modern search systems can understand intent and context in ways impossible with traditional keyword matching.

**Key Takeaways:**

1. **Embeddings** transform unstructured data (text, images) into structured numerical vectors where semantic similarity maps to geometric proximity

2. **Cosine similarity** is the preferred distance metric for most embedding models because it focuses on direction (meaning) rather than magnitude

3. **HNSW** provides logarithmic search complexity through a hierarchical graph structure, making approximate kNN practical at scale

4. **OpenSearch offers three engines**: Lucene (best for < few million vectors, excellent filtering), Faiss (best for large-scale), NMSLIB (deprecated)

5. **Multi-vector search** enables sophisticated scenarios (multiple images per product) with careful consideration of score_mode (max vs sum vs avg)

6. **Efficient filtering** is critical for production systems, combining vector similarity with business logic filters

7. **Performance tuning** requires balancing recall, latency, and memory through parameters like ef_search, ef_construction, and m

The future of search is semantic, and understanding these fundamentals enables building intelligent, context-aware search experiences that truly understand what users are looking for.

---

## References and Further Reading

**OpenSearch Documentation:**
- [Approximate k-NN Search](https://docs.opensearch.org/latest/vector-search/vector-search-techniques/approximate-knn/)
- [k-NN Vector Field Type](https://opensearch.org/docs/latest/field-types/supported-field-types/knn-vector/)
- [Filtering Data](https://docs.opensearch.org/latest/vector-search/filter-search-knn/index/)
- [Nested Field Search](https://docs.opensearch.org/latest/vector-search/specialized-operations/nested-search-knn/)

**Research Papers:**
- Malkov & Yashunin (2016). "Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs." arXiv:1603.09320

**Blog Posts and Tutorials:**
- [OpenSearch kNN Plugin Tutorial - Sease](https://sease.io/2024/01/opensearch-knn-plugin-tutorial.html)
- [Efficient Filtering in OpenSearch Vector Engine](https://opensearch.org/blog/efficient-filters-in-knn/)
- [Enhanced Multi-Vector Support](https://opensearch.org/blog/enhanced-multi-vector-support-in-opensearch-knn/)

**External Resources:**
- [HNSW Visual Guide](https://cfu288.com/blog/2024-05_visual-guide-to-hnsw/)
- [Pinecone Vector Embeddings Guide](https://www.pinecone.io/learn/vector-embeddings/)
- [Understanding Distance Metrics - Zilliz](https://zilliz.com/blog/similarity-metrics-for-vector-search)
