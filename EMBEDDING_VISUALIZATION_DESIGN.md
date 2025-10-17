# Embedding Space Visualization Design

## Goal
Show a 2D scatter plot of query and result embeddings to understand:
- How close query is to each result
- Why certain properties rank higher
- Clustering of similar architectural styles
- Visual vs text embedding distances

## What You'll See

```
                    2D Embedding Space Visualization

    ⭐ Query: "modern architecture"
         │
         │ 0.85 ←─────── High similarity (close in space)
         │
         🏠 Result #1: Modern glass house


         │
         │ 0.72 ←─────── Moderate similarity
         │
         🏠 Result #2: Contemporary home


                         0.35 ←─── Low similarity (far in space)

         🏠 Result #10: Victorian home
```

---

## Architecture Overview

### Phase 1: Backend - Return Raw Embeddings
**File:** `search_detailed_scoring.py`

Add to response:
```json
{
  "results": [...],
  "debug_info": {...},
  "embeddings_data": {
    "query_vector": [0.12, -0.45, ...],  // 1024-dim
    "results": [
      {
        "zpid": "12345",
        "text_vector": [0.15, -0.42, ...],   // From vector_text field
        "image_vectors": [                    // From image_vectors field
          {"vector": [0.18, -0.40, ...], "url": "https://..."},
          {"vector": [0.19, -0.38, ...], "url": "https://..."}
        ],
        "knn_similarity": 0.85  // Cosine similarity with query
      }
    ]
  }
}
```

### Phase 2: Frontend - Dimensionality Reduction
**Library:** `umap-js` (client-side UMAP implementation)
**Alternative:** Send vectors to backend Python endpoint for UMAP (more accurate)

Reduce 1024-dim vectors → 2D coordinates:
```javascript
// Collect all vectors
let vectors = [
  query_vector,
  ...results.map(r => r.text_vector),
  ...results.flatMap(r => r.image_vectors.map(iv => iv.vector))
];

// Run UMAP projection
const umap = new UMAP({
  nNeighbors: 15,
  minDist: 0.1,
  nComponents: 2
});
const embedding2D = await umap.fitAsync(vectors);

// Now embedding2D[0] = [x, y] for query
// embedding2D[1] = [x, y] for result #1 text
// embedding2D[2] = [x, y] for result #1 image #1
// etc.
```

### Phase 3: Visualization
**Library:** `Plotly.js` or `D3.js`

Create interactive scatter plot showing:
- **Query point** (large star, gold color)
- **Text embeddings** (circles, blue)
- **Image embeddings** (circles, red)
- **Lines** connecting query to top results (with distance labels)

---

## Implementation Options

### Option A: Client-Side UMAP (Faster to implement)
**Pros:**
- No backend changes needed initially
- Interactive and instant
- Works in browser

**Cons:**
- UMAP.js slower than Python UMAP
- Limited to ~100 vectors (browser memory)
- Less accurate projection

### Option B: Backend UMAP Endpoint (Better quality)
**Pros:**
- Fast Python UMAP (scikit-learn)
- Can handle thousands of vectors
- More accurate projections
- Can cache projections

**Cons:**
- Need to add new Lambda or endpoint
- Requires Python dependencies (umap-learn)

---

## Recommended Implementation Path

### Step 1: Add Embedding Data to Response (15 min)

**Edit `search_detailed_scoring.py`:**

```python
def handler(event, context):
    # ... existing search logic ...

    # NEW: Collect embeddings for visualization
    embeddings_data = {
        "query_vector": q_vec,  # Already have this
        "results": []
    }

    for hit in hits[:size]:  # Top results only
        zpid = hit["_id"]
        source = hit["_source"]

        result_embeddings = {
            "zpid": zpid,
            "text_vector": source.get("vector_text"),  # 1024-dim
            "image_vectors": []
        }

        # Get image vectors
        if "image_vectors" in source:
            for img_vec in source["image_vectors"][:5]:  # Limit to first 5 images
                result_embeddings["image_vectors"].append({
                    "vector": img_vec.get("vector"),
                    "url": img_vec.get("image_url")
                })

        embeddings_data["results"].append(result_embeddings)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "ok": True,
            "results": results,
            "debug_info": debug_info,
            "embeddings_data": embeddings_data  # NEW!
        })
    }
```

### Step 2: Add UMAP Visualization Endpoint (30 min)

**Create new file: `visualize_embeddings.py`**

```python
"""
Lambda function to project embeddings to 2D using UMAP.
"""
import json
import numpy as np
from umap import UMAP

def handler(event, context):
    body = json.loads(event.get("body", "{}"))

    # Extract vectors from request
    vectors_data = body["vectors"]  # List of dicts with vector + metadata

    # Convert to numpy array
    vectors = np.array([v["vector"] for v in vectors_data])

    # Run UMAP projection
    reducer = UMAP(
        n_components=2,
        n_neighbors=15,
        min_dist=0.1,
        metric='cosine',  # Important! Use cosine for embeddings
        random_state=42
    )

    embedding_2d = reducer.fit_transform(vectors)

    # Attach 2D coordinates to metadata
    results = []
    for i, metadata in enumerate(vectors_data):
        results.append({
            "x": float(embedding_2d[i, 0]),
            "y": float(embedding_2d[i, 1]),
            "type": metadata["type"],  # "query", "text", "image"
            "zpid": metadata.get("zpid"),
            "label": metadata.get("label"),
            "image_url": metadata.get("image_url")
        })

    return {
        "statusCode": 200,
        "body": json.dumps({"points": results})
    }
```

### Step 3: Frontend Visualization (45 min)

**Add to `search.html`:**

```html
<!-- In <head> -->
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>

<!-- New div for embedding viz -->
<div id="embedding-visualization" style="display:none;">
    <h3>🗺️ Embedding Space Visualization</h3>
    <div id="embedding-plot" style="width: 100%; height: 600px;"></div>
</div>

<script>
async function visualizeEmbeddings(searchResponse) {
    const embData = searchResponse.embeddings_data;
    if (!embData) return;

    // Prepare vectors for UMAP endpoint
    let vectors = [];

    // Add query vector
    vectors.push({
        vector: embData.query_vector,
        type: "query",
        label: "Query: " + currentQuery
    });

    // Add result vectors
    embData.results.forEach((result, idx) => {
        // Text embedding
        if (result.text_vector) {
            vectors.push({
                vector: result.text_vector,
                type: "text",
                zpid: result.zpid,
                label: `#${idx+1} Text`
            });
        }

        // Image embeddings
        result.image_vectors.forEach((imgVec, imgIdx) => {
            vectors.push({
                vector: imgVec.vector,
                type: "image",
                zpid: result.zpid,
                label: `#${idx+1} Image ${imgIdx+1}`,
                image_url: imgVec.url
            });
        });
    });

    // Call UMAP endpoint
    const response = await fetch('https://YOUR-API/visualize-embeddings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({vectors})
    });

    const data = await response.json();

    // Create Plotly scatter plot
    const queryPoints = data.points.filter(p => p.type === 'query');
    const textPoints = data.points.filter(p => p.type === 'text');
    const imagePoints = data.points.filter(p => p.type === 'image');

    const traces = [
        {
            x: queryPoints.map(p => p.x),
            y: queryPoints.map(p => p.y),
            mode: 'markers',
            type: 'scatter',
            name: 'Query',
            marker: {
                size: 20,
                color: 'gold',
                symbol: 'star',
                line: {width: 2, color: 'orange'}
            },
            text: queryPoints.map(p => p.label),
            hoverinfo: 'text'
        },
        {
            x: textPoints.map(p => p.x),
            y: textPoints.map(p => p.y),
            mode: 'markers',
            type: 'scatter',
            name: 'Text Embeddings',
            marker: {size: 12, color: 'blue', opacity: 0.6},
            text: textPoints.map(p => p.label),
            hoverinfo: 'text'
        },
        {
            x: imagePoints.map(p => p.x),
            y: imagePoints.map(p => p.y),
            mode: 'markers',
            type: 'scatter',
            name: 'Image Embeddings',
            marker: {size: 10, color: 'red', opacity: 0.4},
            text: imagePoints.map(p => p.label),
            hoverinfo: 'text+name'
        }
    ];

    // Add lines from query to top 5 results
    const queryX = queryPoints[0].x;
    const queryY = queryPoints[0].y;

    textPoints.slice(0, 5).forEach(point => {
        traces.push({
            x: [queryX, point.x],
            y: [queryY, point.y],
            mode: 'lines',
            type: 'scatter',
            showlegend: false,
            line: {color: 'gray', width: 1, dash: 'dot'},
            hoverinfo: 'skip'
        });
    });

    const layout = {
        title: 'Embedding Space (UMAP Projection)',
        xaxis: {title: 'UMAP Dimension 1'},
        yaxis: {title: 'UMAP Dimension 2'},
        hovermode: 'closest',
        showlegend: true
    };

    Plotly.newPlot('embedding-plot', traces, layout);
    document.getElementById('embedding-visualization').style.display = 'block';
}
</script>
```

---

## What You'll Learn From This

### 1. **Visual Clustering**
Properties with similar architecture will cluster together:
- Modern homes → tight cluster in one region
- Craftsman homes → different cluster
- Victorian homes → another cluster

### 2. **Query-Result Distance**
Lines from query to results show:
- **Short line** = High similarity = Good match
- **Long line** = Low similarity = Poor match

### 3. **Text vs Image Alignment**
For each property, you'll see:
- Blue dot (text embedding)
- Red dots (image embeddings)
- If they're CLOSE → Description matches images
- If they're FAR → Mismatch (e.g., "modern" text but traditional images)

### 4. **Multimodal Alignment**
After your fix:
- Query should be CLOSER to image embeddings than before
- You'll see visual confirmation that query and images are in same space

### 5. **Ranking Quality**
Top ranked results (#1, #2, #3) should have:
- Shortest distances to query
- Tight grouping in embedding space

---

## Quick Win: Simple Distance Metrics (No UMAP needed)

Before building full visualization, you can add **distance metrics** to the UI immediately:

```javascript
// In detailed scoring display, add:
function calculateCosineSimilarity(vec1, vec2) {
    const dotProduct = vec1.reduce((sum, a, i) => sum + a * vec2[i], 0);
    const mag1 = Math.sqrt(vec1.reduce((sum, a) => sum + a * a, 0));
    const mag2 = Math.sqrt(vec2.reduce((sum, b) => sum + b * b, 0));
    return dotProduct / (mag1 * mag2);
}

// Show for each result:
const textSimilarity = calculateCosineSimilarity(
    embData.query_vector,
    result.text_vector
);

const avgImageSimilarity = result.image_vectors
    .map(iv => calculateCosineSimilarity(embData.query_vector, iv.vector))
    .reduce((sum, s) => sum + s, 0) / result.image_vectors.length;

console.log(`Result #${idx}:
  Text similarity: ${textSimilarity.toFixed(4)}
  Avg image similarity: ${avgImageSimilarity.toFixed(4)}
`);
```

---

## Expected Insights

### Before Multimodal Fix:
```
Query: "modern architecture"
Result #1 (Victorian home):
  Text similarity: 0.78 (high - has "modern" in description)
  Avg image similarity: 0.25 (low - images look Victorian)
  → Ranked high due to text, poor visual match
```

### After Multimodal Fix:
```
Query: "modern architecture"
Result #1 (Modern glass house):
  Text similarity: 0.75 (good)
  Avg image similarity: 0.82 (excellent! ← IMPROVED)
  → Ranked high due to both text AND visual match
```

---

## Implementation Priority

### Phase 1 (Immediate - 15 min):
✅ Add distance metrics to console output
- No visualization yet
- Just log cosine similarities
- Verify multimodal fix improved image similarities

### Phase 2 (30 min):
✅ Return embeddings in search response
- Add `embeddings_data` to detailed scoring
- Test that vectors are returned correctly

### Phase 3 (1 hour):
✅ Add simple 2D scatter plot WITHOUT UMAP
- Just plot first 2 dimensions of 1024-dim vectors
- Won't be accurate but shows concept
- Use Plotly.js

### Phase 4 (2 hours):
✅ Full UMAP implementation
- Backend UMAP endpoint
- Frontend integration
- Interactive hover tooltips
- Distance lines

---

## Questions?

1. **Do you want to start with Phase 1 (simple distance metrics)?**
   - Fastest way to see if multimodal fix is working
   - No visualization, just numbers

2. **Or jump to Phase 3 (simple scatter plot)?**
   - Visual but less accurate (no UMAP)
   - Good for prototyping

3. **Or go full Phase 4 (complete UMAP visualization)?**
   - Most accurate and insightful
   - Takes longer to implement

Let me know which approach you prefer and I'll implement it!
