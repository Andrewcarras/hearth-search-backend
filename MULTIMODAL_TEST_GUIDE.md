# Multimodal Embedding Test Guide

## ✅ Deployment Complete!

Your Lambda functions have been updated with the multimodal embedding fix:
- `hearth-search-v2` - Updated and Active
- `hearth-search-detailed-scoring` - Updated and Active

## What Changed?

**Before:**
- Query embeddings: `amazon.titan-embed-text-v2:0` (text-only model)
- Image embeddings: `amazon.titan-embed-image-v1` (multimodal model)
- Problem: Different embedding spaces → Poor cross-modal similarity

**After:**
- Query embeddings: `amazon.titan-embed-image-v1` (multimodal model, text input)
- Image embeddings: `amazon.titan-embed-image-v1` (multimodal model, image input)
- Solution: Same embedding space → Proper cross-modal similarity ✅

## Test Queries for UI

### 1. Visual Style Queries (Should see BIGGEST improvement)

These queries rely heavily on image kNN search:

```
modern architecture with clean lines
craftsman style home
contemporary glass house
mid-century modern design
traditional Victorian home
farmhouse style with wrap-around porch
```

**What to look for:**
- Properties that visually match the style should rank higher
- Image thumbnails should look consistent with the architectural style
- Before: Results were text-description heavy (ignored visual style)
- After: Results should actually LOOK modern/craftsman/contemporary

---

### 2. Color Queries (Should maintain current quality)

These rely on BM25 tag matching:

```
white house with blue door
gray exterior home
brick house with white trim
```

**What to look for:**
- Should work as before (no regression)
- Tag matching still dominates

---

### 3. Feature Queries (Should maintain current quality)

```
house with pool and granite countertops
3 bedroom home with 2 car garage
home with fireplace and hardwood floors
```

**What to look for:**
- Results should have the requested features
- No change expected (these use tags + BM25)

---

### 4. Combined Visual + Feature Queries (Should see MODERATE improvement)

```
modern house with pool
craftsman home with large kitchen
contemporary design with mountain views
```

**What to look for:**
- Should rank properties that have BOTH visual style AND features
- Image kNN now contributes meaningfully to ranking

---

## How to Evaluate Results

### Check Image Consistency
1. Run query: "modern architecture"
2. Look at top 10 results
3. Do the property images actually look modern?
4. Before: Mix of styles, text-description driven
5. After: Visually consistent modern homes

### Check Ranking Quality
- Run query: "craftsman style home"
- Properties with craftsman-looking exteriors should rank in top 5
- Previously, they might be buried at rank 15-20

### Monitor Search Logs
Open browser console (F12) to see search details:
- BM25 scores
- kNN text scores
- kNN image scores (should be higher now!)
- Final RRF scores

---

## Quick Visual Test

**Query:** `modern white house with pool`

**Expected Results:**
1. Properties should LOOK modern (clean lines, contemporary architecture)
2. Properties should be white (tag matching)
3. Properties should have pools visible in images

**Before Fix:**
- Might get white houses with pools but traditional/Victorian style
- Image kNN couldn't properly match "modern" visual style

**After Fix:**
- Should get modern-looking white houses with pools
- Visual style matching now works!

---

## Debugging Tips

If results look wrong:

1. **Check Lambda Logs:**
```bash
aws logs tail /aws/lambda/hearth-search-v2 --follow
```

2. **Verify embedding model:**
Look for log line showing which model is used for query embedding
Should say: `amazon.titan-embed-image-v1`

3. **Check similarity scores:**
Enable detailed scoring in UI to see kNN image scores
Higher scores = better match

---

## Expected Improvements

### Visual Queries:
- **Before:** Image kNN scores typically 0.20-0.40 (weak)
- **After:** Image kNN scores typically 0.60-0.85 (strong)
- **Impact:** Properties that LOOK right rank higher

### Color/Material Queries:
- **Before:** Works well (BM25 dominant)
- **After:** Same (no change expected)

### Feature Queries:
- **Before:** Works well (tag matching)
- **After:** Same (no change expected)

---

## Test Results Template

Document your findings:

```
Query: "modern architecture"

Top 5 Results:
1. zpid=_____ - Visual match: ✅/❌ - Has modern features: ✅/❌
2. zpid=_____ - Visual match: ✅/❌ - Has modern features: ✅/❌
3. zpid=_____ - Visual match: ✅/❌ - Has modern features: ✅/❌
4. zpid=_____ - Visual match: ✅/❌ - Has modern features: ✅/❌
5. zpid=_____ - Visual match: ✅/❌ - Has modern features: ✅/❌

Overall Quality: Better / Same / Worse
Image Consistency: High / Medium / Low
```

---

## Next Steps

If results are significantly better:
1. ✅ Keep the multimodal embedding approach
2. Consider switching text kNN to also use multimodal (future enhancement)
3. Simplify to 2-strategy search (BM25 + unified multimodal kNN)

If results are the same or worse:
1. Check logs for errors
2. Verify cache isn't serving old embeddings
3. Try clearing text embedding cache
4. May need to re-index with unified embeddings

---

## Questions to Answer

- [ ] Do "modern architecture" queries return visually modern homes?
- [ ] Do "craftsman style" queries return craftsman-looking homes?
- [ ] Are image kNN similarity scores higher than before?
- [ ] Is ranking quality noticeably better for visual queries?
- [ ] Are there any regressions in feature/color queries?

Happy testing! 🚀
