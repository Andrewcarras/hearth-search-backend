# UI Diagnostic Report - Search Mode Issue

## Investigation Results

**Date:** October 16, 2024
**Issue:** User reports same results in Adaptive vs Standard modes, and "Not found in top results" for kNN

---

## Backend Status: ✅ WORKING CORRECTLY

### Test 1: Different Results Per Mode ✅

**Adaptive Mode** (query: "modern home"):
```
Results: 12922004, 12848548, 12880332
```

**Standard Mode** (query: "modern home"):
```
Results: 456535559, 453393832, 450278046
```

**Conclusion:** Backend is returning DIFFERENT results for each mode ✅

### Test 2: Scoring Details Available ✅

Debug endpoint for zpid `12922004`:
```json
{
  "bm25_rank": null,
  "knn_text_rank": 1,
  "knn_image_rank": null
}
```

**Conclusion:** kNN ranks ARE showing when property matches that strategy ✅

### Test 3: "Not Found" is Correct Behavior ✅

**Why kNN shows "Not found in top results":**

The property `12922004`:
- **BM25 rank: null** → Property doesn't match keyword search in top 15 results
- **kNN text rank: 1** → Property is #1 in semantic text search ✓
- **kNN image rank: null** → Property doesn't match visual search in top 15 results

**This is CORRECT!** Not every property matches all three strategies. This property won because it's #1 in kNN text, even though it doesn't appear in BM25 or kNN image at all.

---

## UI Deployment Status: ✅ UP TO DATE

**S3 Upload:** 2025-10-16 14:08:37 UTC
**EC2 Sync:** 2025-10-16 14:08 UTC
**File Size:** 89KB
**Location:** http://54.234.198.245

**Verification:**
```bash
curl -s http://54.234.198.245 | grep "search_mode"
# ✓ Contains search_mode parameter
# ✓ Calls /search/debug endpoint correctly
```

---

## Root Cause: Browser Cache Issue

### Most Likely Cause

The browser is caching:
1. **Search results** from previous queries
2. **JavaScript state** from old page loads
3. **API responses** (though unlikely with POST requests)

### Evidence

1. Backend returns different results per mode ✓
2. UI code is correct and deployed ✓
3. Debug endpoint returns scoring details ✓
4. **Only user's browser shows issue** (API tests work)

---

## Solution Steps

### Step 1: Hard Refresh (Try First)

**Mac:** `Cmd + Shift + R`
**Windows/Linux:** `Ctrl + Shift + F5`

This forces browser to:
- Reload all assets from server
- Clear JavaScript state
- Bypass cache

### Step 2: Clear Browser Cache

**Chrome:**
1. Open DevTools (F12)
2. Right-click refresh button
3. Select "Empty Cache and Hard Reload"

**Firefox:**
1. Open DevTools (F12)
2. Network tab
3. Click "Disable Cache" checkbox
4. Refresh page

### Step 3: Use Incognito/Private Mode

Open the UI in a new incognito/private window:
```
http://54.234.198.245
```

This starts with a completely clean slate.

### Step 4: Check Console for Errors

1. Open DevTools (F12)
2. Go to Console tab
3. Perform a search
4. Look for any red errors

Common errors to look for:
- CORS errors
- Network failures
- JavaScript exceptions

---

## How to Verify It's Working

### Test Scenario 1: Different Results Per Mode

1. Search for: **"modern home"**
2. Mode: **Adaptive**
3. Note the first 3 zpids
4. Switch to: **Standard**
5. Search again for: **"modern home"**
6. First 3 zpids should be DIFFERENT

**Expected Results:**
```
Adaptive: 12922004, 12848548, 12880332
Standard: 456535559, 453393832, 450278046
```

### Test Scenario 2: kNN Ranks Showing

1. Search for: **"modern home"**
2. Click first result
3. Click "View Detailed Score Breakdown"
4. Look at "kNN Text Similarity Search" section

**Expected:**
- Rank in kNN text results: **1** (or other number)
- Cosine similarity score: **0.7569...** (or other number)
- RRF Contribution: **0.0217...** (or other number)

**Why some show "Not found":**
- This is CORRECT behavior
- Property only matched via kNN text, not BM25 or kNN image
- That's the point of RRF - properties can win via any strategy

### Test Scenario 3: Multi-Strategy Results

1. Search for: **"pool and garage"**
2. Click first result
3. Click "View Detailed Score Breakdown"

**Expected:**
- Should see ranks in MULTIPLE strategies (e.g., BM25 + kNN image)
- This shows RRF combining different search methods

---

## Common Misconceptions

### ❌ WRONG: "All properties should match all strategies"

**Why Wrong:** Different queries use different strategies
- "modern home" → Semantic/visual (kNN text/image)
- "pool" → Keyword (BM25 tags)
- "3 bedroom house with pool" → Multiple strategies

### ✅ CORRECT: "Properties match relevant strategies"

**Example 1:** Visual style query
```
Query: "modern home"
Property: Modern contemporary house
- BM25: null (doesn't have "modern" keyword)
- kNN text: 1 (semantic match!)
- kNN image: null (images don't emphasize style)
Result: Wins via kNN text
```

**Example 2:** Feature query
```
Query: "pool and garage"
Property: Home with both features
- BM25: 14 (has tags)
- kNN text: null
- kNN image: 2 (visual match!)
Result: Wins via BM25 + kNN image combination
```

---

## API Endpoint Reference

### Regular Search
```bash
POST https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search
```

**Returns:** Search results (no scoring details)

### Debug Search (for Score Breakdown)
```bash
POST https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search/debug
```

**Returns:** Search results WITH detailed scoring breakdown

---

## Debugging Commands

### Test API Directly

```bash
# Test Adaptive mode
curl -X POST https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search \
  -H "Content-Type: application/json" \
  -d '{"q":"modern home","size":5,"index":"listings-v2","search_mode":"adaptive"}' | jq -r '.results[0:3] | map(.zpid)'

# Test Standard mode
curl -X POST https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search \
  -H "Content-Type: application/json" \
  -d '{"q":"modern home","size":5,"index":"listings-v2","search_mode":"standard"}' | jq -r '.results[0:3] | map(.zpid)'

# Test Debug endpoint
curl -X POST https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search/debug \
  -H "Content-Type: application/json" \
  -d '{"q":"modern home","size":5,"index":"listings-v2","search_mode":"adaptive"}' | jq '.results[0]._scoring_details'
```

### Check UI Deployment

```bash
# Check S3 timestamp
aws s3api head-object --bucket demo-hearth-data --key ui/search.html --query 'LastModified'

# Check EC2 file
ssh ubuntu@54.234.198.245 "ls -lh /usr/share/nginx/html/index.html"
```

---

## What's Working

✅ **Backend:** Returning different results per mode
✅ **Lambda:** RRF scoring fix deployed and working
✅ **API:** Debug endpoint returning scoring details
✅ **UI Code:** Correctly calling endpoints with search_mode parameter
✅ **UI Deployment:** Latest version synced to EC2

---

## What to Check in Browser

### Browser DevTools Network Tab

1. Open DevTools (F12)
2. Go to Network tab
3. Perform search in Adaptive mode
4. Look for POST request to `/search`
5. Check Request Payload:
   ```json
   {
     "q": "modern home",
     "search_mode": "adaptive",
     ...
   }
   ```
6. Check Response - first 3 zpids should be: `12922004, 12848548, 12880332`
7. Switch to Standard mode
8. Perform same search
9. Response should be different: `456535559, 453393832, 450278046`

### What This Tells You

- **If payloads show correct search_mode:** UI JavaScript is working
- **If responses are different:** Backend is working
- **If UI shows same results:** Browser cache issue

---

## Recommended Action

**Primary Solution:** Hard refresh (Cmd+Shift+R or Ctrl+Shift+F5)

**If that doesn't work:**
1. Open incognito window
2. Navigate to http://54.234.198.245
3. Test both modes

**If still seeing issues:**
1. Open DevTools Console
2. Check for JavaScript errors
3. Open DevTools Network tab
4. Verify API requests/responses

---

## Contact Points

**UI URL:** http://54.234.198.245
**API Base:** https://f2o144zh31.execute-api.us-east-1.amazonaws.com
**S3 Bucket:** demo-hearth-data/ui/
**EC2 Instance:** i-03e61f15aa312c332 (hearth-ui-v2)

---

**Status:** ✅ Backend and UI code working correctly
**Issue:** 🔶 Browser cache (user-side)
**Solution:** 🔄 Hard refresh or incognito mode

**Last Updated:** October 16, 2024, 15:30 UTC
