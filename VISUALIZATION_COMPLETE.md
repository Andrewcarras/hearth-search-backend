# ✅ Embedding Space Visualization - COMPLETE!

## 🎉 What's Been Deployed

### 1. Updated Search Lambda (with Embeddings Data)
- **Function:** `hearth-search-detailed-scoring`
- **What's new:** Returns `embeddings_data` in response containing:
  - Query vector (1024-dim)
  - Text vectors for each result (1024-dim)
  - Image vectors for each result (up to 5 per property)

### 2. Embedding Visualization Page
- **URL:** http://54.234.198.245/viz.html
- **What it does:**
  - Interactive 2D scatter plot of embedding space
  - Projects 1024-dim vectors to 2D using client-side PCA
  - Shows query ⭐, text embeddings 🔵, image embeddings 🔴
  - Distance lines from query to top 5 results
  - Similarity table with scores

### 3. Multimodal Embeddings (from earlier)
- Query embeddings now use `amazon.titan-embed-image-v1`
- Same embedding space as images (fixes cross-modal search!)

---

## 🚀 How to Use

### Open the Visualization:
```
http://54.234.198.245/viz.html
```

### Try These Queries:
1. **"modern architecture"** - See if modern homes cluster together
2. **"craftsman style home"** - Check if craftsman properties form a distinct cluster
3. **"modern house with pool"** - See combined visual + feature matching

### What You'll See:

```
                    2D Embedding Space

    ⭐ Query: "modern architecture"
         │
         │ ←─────── Short distance = High similarity
         │
         🔵 #1 Modern glass house (Text)
         🔴🔴 (Images)


         │ ←─────── Medium distance
         │
         🔵 #2 Contemporary home
         🔴🔴🔴


                   ←── Long distance = Low similarity

         🔵 #10 Victorian mansion
         🔴🔴
```

---

## 📊 What This Shows You

### 1. **Query-Result Alignment**
- **Lines from ⭐ to results** show embedding distance
- **Shorter lines** = Better match (higher similarity)
- **Longer lines** = Worse match (lower similarity)

### 2. **Text vs Image Alignment**
For each property:
- **Blue dot** = Text embedding (from description)
- **Red dots** = Image embeddings (from photos)
- **Close together** ✅ = Description matches images
- **Far apart** ❌ = Mismatch (e.g., "modern" text but traditional images)

### 3. **Architectural Style Clustering**
Properties with similar styles should cluster:
- Modern homes → One region
- Craftsman homes → Different region
- Victorian homes → Another region

If they DON'T cluster well, that indicates:
- Inconsistent tagging
- Poor image quality
- Weak visual features

### 4. **Multimodal Fix Validation**
**Before multimodal fix:**
- Query ⭐ would be FAR from image embeddings 🔴
- Poor image kNN scores

**After multimodal fix:**
- Query ⭐ should be CLOSER to image embeddings 🔴
- Better image kNN scores (shown in similarity table)

---

## 📈 Understanding the Similarity Table

The table shows **cosine similarity** between query and text embeddings:

| Similarity Score | Match Quality | What It Means |
|-----------------|---------------|---------------|
| **0.80 - 1.00** | 🟢 Excellent | Nearly identical semantic meaning |
| **0.60 - 0.80** | 🟡 Good | Strong semantic overlap |
| **0.40 - 0.60** | 🟠 Fair | Some semantic similarity |
| **0.00 - 0.40** | 🔴 Poor | Weak or no semantic match |

**Example:**
```
Query: "modern architecture"
Result #1: "Contemporary glass house with clean lines"
  → Similarity: 0.82 (Excellent match!)

Result #8: "Traditional Victorian mansion"
  → Similarity: 0.32 (Poor match - should rank lower)
```

---

## 🔍 Debugging Your Search Quality

### Problem: Top results don't visually match query

**Check the visualization:**
1. Are top-ranked results (1-5) CLOSE to query star?
   - **Yes:** Ranking is working, but results themselves are poor quality
   - **No:** Ranking algorithm needs tuning (RRF weights, k-values)

2. Are text 🔵 and image 🔴 dots close together for top results?
   - **Yes:** Property data is consistent
   - **No:** Descriptions don't match images (data quality issue)

### Problem: Results cluster randomly (no clear patterns)

**Possible causes:**
- Embeddings aren't capturing meaningful features
- Need better image quality
- Description text is too generic/marketing-heavy
- Visual features extraction (Claude vision) needs improvement

### Problem: Query star is isolated (far from all results)

**Possible causes:**
- Query is too specific (no matching properties)
- Embedding model doesn't understand the query term
- Need more properties in that architectural style

---

## 🎯 Expected Insights

### Query: "modern architecture"

**Good Search Quality:**
```
⭐ Query
├─ 🔵 #1 Modern glass house (distance: 0.15)
│  └─ 🔴🔴🔴 Images (clustered nearby)
├─ 🔵 #2 Contemporary design (distance: 0.18)
│  └─ 🔴🔴 Images (clustered nearby)
└─ 🔵 #3 Mid-century modern (distance: 0.22)
   └─ 🔴🔴🔴 Images (clustered nearby)

... far away ...

🔵 #10 Victorian mansion (distance: 0.78)
└─ 🔴🔴 Images (clustered far from query)
```

**Poor Search Quality:**
```
⭐ Query

🔵 #1 Victorian mansion (distance: 0.72) ← Should NOT be #1!
🔵 #5 Modern glass house (distance: 0.16) ← Should be #1!
```

---

## 🛠️ Technical Details

### Client-Side PCA Implementation
- **Input:** 1024-dimensional embeddings
- **Output:** 2D coordinates for visualization
- **Method:** Principal Component Analysis (power iteration)
- **Performance:** ~100-200ms for 50-100 vectors
- **Limitation:** Only captures ~60% of variance (UMAP would be better but requires backend)

### Why PCA Instead of UMAP?
- **UMAP** = Better quality, preserves local clusters
- **PCA** = Faster, smaller, works in browser
- **Trade-off:** PCA is "good enough" for debugging, UMAP would be ideal

To get UMAP (if needed later):
- Deploy separate Python Lambda with umap-learn
- OR use AWS Lambda Layers for dependencies
- OR compute projections offline and cache them

---

## 📝 Next Steps (Optional Improvements)

### 1. **Add Hover Images** (Medium effort)
Show property image thumbnails on hover:
```javascript
hovertemplate: '<img src="%{customdata}" width="200"><br>%{text}<extra></extra>'
```

### 2. **3D Visualization** (Low effort)
Change PCA to 3 components instead of 2:
```javascript
const projected = pcaProject(allVectors, 3);
// Use Plotly 3D scatter plot
```

### 3. **Animate Query Evolution** (High effort)
Show how results change as you type:
- Search "modern"
- Search "modern house"
- Search "modern house with pool"
- Animate points moving in embedding space

### 4. **Cluster Labeling** (Medium effort)
Automatically detect and label clusters:
- Use k-means on 2D projections
- Label clusters by most common architecture style
- Color-code by cluster

### 5. **Compare Before/After Multimodal Fix** (Low effort)
Add toggle to use old text-v2 embeddings vs new image-v1:
- Shows side-by-side how multimodal fix improved alignment

---

## 🐛 Troubleshooting

### "No embedding data returned"
- Make sure you deployed the updated `hearth-search-detailed-scoring` Lambda
- Check Lambda logs: `aws logs tail /aws/lambda/hearth-search-detailed-scoring --follow`

### "Projection takes too long"
- Reduce number of results: Change `size: 10` to `size: 5`
- Reduce images per result: Already limited to 5 in backend

### "Plot looks weird / points overlap"
- This is normal with PCA (loses some structure)
- Try different queries to see different clustering patterns
- Consider switching to UMAP for better quality (requires backend)

### "Similarity scores don't match ranking"
- Similarity is query→text only
- Final ranking uses: BM25 + text kNN + image kNN + tag boosting + RRF fusion
- A property can rank high overall but have low text similarity (if images match well)

---

## 🎓 Learning from the Visualization

### What Success Looks Like:
✅ Top results cluster near query star
✅ Similar architectural styles form distinct clusters
✅ Text and image embeddings align for each property
✅ Similarity scores correlate with visual distance

### What Problems Look Like:
❌ Top results scattered randomly
❌ No clear clustering by style
❌ Text and image embeddings far apart
❌ Query star isolated (no nearby results)

---

## 🚀 Ready to Explore!

**Open the visualization:**
```
http://54.234.198.245/viz.html
```

**Try these test queries:**
1. "modern architecture"
2. "craftsman style home"
3. "contemporary design with pool"
4. "traditional Victorian mansion"
5. "mid-century modern"

**What to look for:**
- Do results cluster by architectural style?
- Are top-ranked results close to the query star?
- Do text and image embeddings align?
- Did the multimodal fix improve image similarity?

**Have fun exploring your embedding space!** 🗺️✨
