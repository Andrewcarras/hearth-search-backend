# Vacant Lot Image Bug - Investigation Report

## Issue Summary

**ZPID:** 2055213797
**Property:** 1603 W Warnock Ave S, West Valley City, UT 84119
**Actual Type:** Empty residential lot ($169,900)
**Problem:** Indexed with 7 images showing a "modern style white exterior home" that doesn't exist

---

## Root Cause

Zillow's API returns `responsivePhotos` array containing **nearby property images** for lots/vacant land listings that have no actual photos. The `extract_zillow_images()` function in [common.py](common.py#L907-L1005) was incorrectly using these images as fallback data.

### Technical Details

**Original Listing Data:**
- `homeType`: "LOT"
- `photoCount`: 7 (misleading!)
- `carouselPhotosComposable`: null/missing (the correct photo source)
- `responsivePhotos`: Array of 7 photos from **1601 W Warnock Ave** (nearby home, zpid 452285494)

**What Happened:**
1. `extract_zillow_images()` checked `carouselPhotosComposable` → not found
2. Fell through to `responsivePhotos` fallback (lines 972-994)
3. Extracted 7 images from the array without validating they belong to the property
4. These images were from a nearby home in the `nearbyHomes` section of Zillow's response

**Evidence:**
```
nearbyHomes.[1].miniCardPhotos.[0].url:
  https://photos.zillowstatic.com/fp/955fb974e207a95274784bd354f83b16-p_c.jpg

responsivePhotos.[0].mixedSources.jpeg.[7].url:
  https://photos.zillowstatic.com/fp/955fb974e207a95274784bd354f83b16-cc_ft_1536.jpg
```

Same image hash (`955fb974e207a95274784bd354f83b16`) - proves the images came from the nearby home!

---

## Impact

### Search Results Impact
- **Query:** "modern homes"
- **Result:** Empty lot ranked as top result in Standard mode
- **Why:** BM25 matched "modern" in the incorrect `visual_features_text`
- **User Experience:** Very poor - shows empty lot when searching for homes

### Visual Features Text (Incorrect)
```
Exterior: modern style white exterior with wood siding, stucco, brick.
Property includes: front porch, mature trees, landscaped yard, white exterior,
gabled roof, attached garage, driveway, mountain view, gravel driveway, parked
vehicles, power lines, chain link fence, green trees, residential homes, paved roads.
```

**Reality:** Empty lot with 10'x20' storage shed, no home structure.

### Scoring Details (from DynamoDB cache)
Image 1 Analysis:
- Features: `['white exterior', 'wood siding', 'gabled roof', 'attached garage', 'front porch']`
- Architecture: `modern`
- Materials: `['wood siding']`

All completely incorrect for an empty lot!

---

## Fix Applied

### Code Change: [common.py:972-1002](common.py#L972-L1002)

**Before:**
```python
# Fallback 2: responsivePhotos
responsive = listing.get("responsivePhotos", [])
if responsive:
    # Extract images without validation
    for photo in responsive:
        # ... process photo
```

**After:**
```python
# Fallback 2: responsivePhotos - extract highest resolution from each unique photo
# WARNING: For lots/vacant land, responsivePhotos may contain nearby home images!
# Only use responsivePhotos if property has actual photos (photoCount > 0 and not vacant land)
responsive = listing.get("responsivePhotos", [])
home_type = listing.get("homeType", "").lower()
photo_count = listing.get("photoCount", 0)

# Skip responsivePhotos for vacant land or lots with no photos
# These often contain misleading nearby property images from Zillow's UI
is_vacant_land = home_type in ["lot", "vacantland", "land", ""] or "vacant" in home_type

if responsive and not (is_vacant_land and photo_count == 0):
    # ... process photos only if NOT vacant land with 0 photos
```

### Logic:
- Check if `homeType` indicates vacant land ("lot", "vacantland", "land", etc.)
- If vacant land AND `photoCount == 0` (or missing `carouselPhotosComposable`)
- **Skip `responsivePhotos` entirely** to avoid indexing nearby property images

---

## Remediation Steps

### 1. Delete Incorrect Listing ✅
```bash
DELETE /listings-v2/_doc/2055213797
```
**Status:** Completed - listing deleted from OpenSearch

### 2. Clear DynamoDB Cache for Incorrect Images ⚠️
The 7 incorrect image analyses are still cached:
```
hearth-vision-cache entries:
- https://photos.zillowstatic.com/fp/955fb974e207a95274784bd354f83b16-cc_ft_1536.jpg
- https://photos.zillowstatic.com/fp/369236f678f7ff06d817db10c6f9e16d-cc_ft_1536.jpg
- ... (5 more)
```

**Options:**
- Leave cached (they'll be used if actual home at 1601 W Warnock Ave is indexed later)
- Delete if you want to regenerate analysis for that home

### 3. Find Other Affected Listings
Run query to find all vacant land with images:
```python
# Search for homeType: LOT, VACANTLAND, etc. with image_vectors_count > 0
```

### 4. Re-index Entire Dataset (Recommended)
With the fix in place, re-index all SLC listings to ensure no other vacant lots have incorrect images.

---

## Why This Happened

### Zillow API Behavior
Zillow's web interface shows nearby property images for vacant lots to make listings more appealing. Their API includes these in `responsivePhotos` even though they don't belong to the actual property.

### Our Assumption
We assumed `responsivePhotos` was always property-specific, but for vacant land it's promotional nearby content.

### photoCount Field
The `photoCount: 7` field was misleading - it counted the nearby property images, not actual lot photos.

---

## Lessons Learned

### 1. Never Trust Fallback Data Without Validation
The `responsivePhotos` field should have been validated against property type before use.

### 2. Property Type Matters
Vacant land, lots, and land listings require special handling compared to homes.

### 3. Cache Can Perpetuate Errors
Once incorrect images were cached in DynamoDB, they persisted across searches until manually deleted.

### 4. Test Edge Cases
Need test cases for:
- Empty lots
- Vacant land
- Properties with no photos
- Properties with only street view images

---

## Prevention

### Code Review Checklist for Image Extraction:
- [ ] Validate property type before using fallback data
- [ ] Check `carouselPhotosComposable` exists and has items
- [ ] Don't use `responsivePhotos` for vacant land
- [ ] Verify `photoCount` matches actual property photos
- [ ] Log warnings when using fallback image sources

### Monitoring:
- Alert when vacant land has `image_vectors_count > 0`
- Flag listings where `visual_features_text` mentions structures but `homeType` is "LOT"
- Track `responsivePhotos` usage vs `carouselPhotosComposable` usage

---

## Testing

### Test Case 1: Vacant Lot (No Photos)
```python
listing = {
    "zpid": "2055213797",
    "homeType": "LOT",
    "photoCount": 7,
    "carouselPhotosComposable": None,
    "responsivePhotos": [...]  # Nearby home images
}

images = extract_zillow_images(listing)
assert len(images) == 0, "Should not extract nearby home images"
```

### Test Case 2: Vacant Land with Actual Photos
```python
listing = {
    "zpid": "123456",
    "homeType": "LOT",
    "photoCount": 3,
    "carouselPhotosComposable": [...]  # Actual lot photos
}

images = extract_zillow_images(listing)
assert len(images) == 3, "Should extract actual lot photos from carousel"
```

### Test Case 3: Regular Home
```python
listing = {
    "zpid": "789012",
    "homeType": "SINGLE_FAMILY",
    "photoCount": 20,
    "carouselPhotosComposable": [...]  # Home photos
}

images = extract_zillow_images(listing)
assert len(images) == 20, "Should extract all home photos"
```

---

## Related Files

- [common.py:907-1005](common.py#L907-L1005) - `extract_zillow_images()` function
- [upload_listings.py](upload_listings.py) - Indexing pipeline that calls image extraction
- [SCORE_BREAKDOWN_IMPROVEMENTS.md](SCORE_BREAKDOWN_IMPROVEMENTS.md) - Recent UI improvements
- [AWS_BEDROCK_COST_INVESTIGATION.md](AWS_BEDROCK_COST_INVESTIGATION.md) - Cost analysis

---

## Next Steps

1. **User Action:** Delete zpid 2055213797 from search results using UI (already deleted from OpenSearch)
2. **Deploy Fix:** Updated [common.py](common.py#L972-1002) already has the fix
3. **Find Similar Issues:** Search for other vacant land listings with images
4. **Re-index Dataset:** Run full re-index with fixed code to clean up all affected listings
5. **Add Tests:** Create unit tests for vacant land edge cases
6. **Monitor:** Set up alerts for vacant land with image vectors

---

**Status:** 🔧 Fix Applied, Awaiting Re-index
**Priority:** High (affects search quality)
**Discovered:** October 16, 2024
**Fixed:** October 16, 2024
**Deployed:** Pending full re-index
