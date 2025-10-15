# Visual Features Text Quality Analysis

**Date:** 2025-01-14
**Issue:** Contradictory features in visual_features_text
**Example:** "Exterior: contemporary style white exterior, modern style brick exterior, craftsman style white exterior, ranch style brown exterior"

---

## Root Cause Analysis

### Problem

A single property is showing **multiple contradictory** architecture styles, colors, and materials:
- 4 different architecture styles: contemporary, modern, craftsman, ranch
- 3 different colors: white, brown, brick
- Mixed materials: brick, plus implied painted exteriors

This is impossible for a single property and creates noise in search results.

### Why This Happens

#### Current Process Flow:

```python
# upload_listings.py lines 407-421
for analysis in all_image_analyses:  # ← Loops through ALL images
    if analysis.get("image_type") == "exterior":
        parts = []
        if analysis.get("architecture_style"):
            parts.append(f"{analysis['architecture_style']} style")
        if analysis.get("exterior_color"):
            parts.append(f"{analysis['exterior_color']} exterior")
        if parts:
            exterior_descriptions.append(" ".join(parts))

# Later...
if exterior_descriptions:
    description_parts.append(f"Exterior: {', '.join(set(exterior_descriptions))}")
```

**The Issue:**
1. Properties have **10-50 images** in the Zillow dataset
2. Claude Haiku analyzes **each image independently**
3. Different exterior photos show different angles/lighting
4. Claude may detect **slightly different** colors/styles per photo:
   - Photo 1 (front angle, sunny): "white exterior, craftsman style"
   - Photo 2 (side angle, shade): "gray exterior, craftsman style"
   - Photo 3 (different angle): "modern style, white exterior"
   - Photo 4 (street view): "ranch style, brown siding"

5. Code **concatenates ALL** exterior descriptions without reconciliation
6. Result: "Exterior: craftsman style white exterior, modern style gray exterior, ranch style brown siding"

### Real-World Example

For a property with 15 images:
- 3 exterior photos analyzed by Claude Haiku
- Photo 1: Claude sees front angle → "craftsman style, white exterior"
- Photo 2: Claude sees side with brick chimney → "modern style, brick exterior"
- Photo 3: Claude sees backyard angle → "contemporary style, white exterior"

**Current output:**
```
Exterior: craftsman style white exterior, modern style brick exterior,
contemporary style white exterior
```

**What it should be:**
```
Exterior: craftsman style, white exterior with brick accents
```

---

## Why Detection Varies Per Image

### 1. **Architecture Style Inconsistency**

Claude Haiku determines architecture style per-image based on:
- **Visible elements**: columns, roofline, window style, trim details
- **Viewing angle**: Front view shows different features than side view
- **Ambiguous styles**: Many homes blend styles (e.g., "craftsman ranch" or "contemporary traditional")

**Example:**
- Front photo shows craftsman porch → Claude: "craftsman"
- Side photo shows simple roofline → Claude: "ranch"
- Both are technically correct based on visible elements!

### 2. **Color Detection Variations**

Exterior color can appear different due to:
- **Lighting conditions**: Sunny vs shaded areas
- **Camera white balance**: Photos taken at different times
- **Material mix**: White siding + brown stone accents
- **Angle**: Different sides of house may have accent colors

**Example:**
- Main facade: White vinyl siding → Claude: "white exterior"
- Side view: Shows brown wooden deck → Claude: "brown exterior"
- Chimney close-up: Red brick → Claude: "brick exterior"

### 3. **Material Detection**

Properties often have **multiple materials**:
- Primary siding: Vinyl (white)
- Accents: Brick (red/brown)
- Foundation: Stone (gray)
- Trim: Wood (brown)

Claude sees each material in different photos and reports them individually.

---

## Impact on Search Quality

### Negative Effects:

1. **Keyword Noise**
   - Query: "white house"
   - Matches: Properties with "white exterior, brown exterior, gray exterior"
   - Result: Many false positives

2. **Semantic Confusion**
   - Text embedding captures: "white brown gray brick exterior"
   - Vector represents conflicting concepts
   - Similarity matching becomes unreliable

3. **User Confusion**
   - Score breakdown shows: "craftsman style, modern style, ranch style"
   - User thinks: "Is this a mistake? Which is it actually?"

4. **Contradictory Signals**
   - BM25 matches "modern" and "craftsman" simultaneously
   - Boosts score even when user only wants one style

### Example Search Quality Issue:

**User Query:** "modern white house"

**Current Behavior:**
```
Property A visual_features_text:
"Exterior: modern style white exterior, craftsman style brown exterior,
contemporary style white exterior"

BM25 score: HIGH (matches "modern" AND "white")
Result: Property ranks high

Actual property: Craftsman brown house (not modern, not white!)
```

The property ranks high because it **mentioned** modern and white (from misdetection), even though it's actually craftsman brown.

---

## Proposed Solutions

### Solution 1: **Use Only Best Exterior Image (Quick Fix)**

**Approach:** Select the single best exterior photo instead of merging all

```python
# Find the best exterior analysis
best_exterior = None
best_score = 0

for analysis in all_image_analyses:
    if analysis.get("image_type") == "exterior":
        # Score based on confidence and feature count
        score = 0
        if analysis.get("architecture_style"):
            score += 10
        if analysis.get("exterior_color"):
            score += 5
        if analysis.get("confidence") == "high":
            score += 5
        score += len(analysis.get("features", []))

        if score > best_score:
            best_score = score
            best_exterior = analysis

# Use only the best exterior
if best_exterior:
    parts = []
    if best_exterior.get("architecture_style"):
        parts.append(f"{best_exterior['architecture_style']} style")
    if best_exterior.get("exterior_color"):
        parts.append(f"{best_exterior['exterior_color']} exterior")
    exterior_text = " ".join(parts)
```

**Pros:**
- ✅ Simple to implement
- ✅ Eliminates contradictions
- ✅ Fast (no additional processing)

**Cons:**
- ❌ Loses information from other angles
- ❌ Might miss accent materials (brick chimney, stone foundation)

---

### Solution 2: **Majority Voting / Consensus (Recommended)**

**Approach:** Find most common style/color across all exterior photos

```python
from collections import Counter

# Collect all exterior attributes
styles = []
colors = []
materials = []

for analysis in all_image_analyses:
    if analysis.get("image_type") == "exterior":
        if analysis.get("architecture_style"):
            styles.append(analysis["architecture_style"])
        if analysis.get("exterior_color"):
            colors.append(analysis["exterior_color"])
        materials.extend(analysis.get("materials", []))

# Find consensus
primary_style = Counter(styles).most_common(1)[0][0] if styles else None
primary_color = Counter(colors).most_common(1)[0][0] if colors else None

# Get top 2-3 materials (allow accents)
material_counts = Counter(materials)
top_materials = [m for m, c in material_counts.most_common(3)]

# Build description
parts = []
if primary_style:
    parts.append(f"{primary_style} style")
if primary_color:
    parts.append(f"{primary_color} exterior")
if top_materials:
    parts.append(f"with {', '.join(top_materials)} accents")

exterior_text = " ".join(parts)
```

**Example Output:**
```
Before: "contemporary style white exterior, modern style brick exterior,
         craftsman style white exterior, ranch style brown exterior"

After:  "craftsman style white exterior with brick accents"
```

**Pros:**
- ✅ Captures true property characteristics
- ✅ Allows for accent materials
- ✅ More accurate than single image
- ✅ Handles lighting/angle variations

**Cons:**
- ❌ Slightly more complex logic
- ❌ Still relies on Claude's per-image detection

---

### Solution 3: **Multi-Image Batch Analysis (Best Quality, Expensive)**

**Approach:** Send multiple exterior images to Claude at once, ask for unified analysis

```python
# Collect all exterior images
exterior_images = [
    analysis for analysis in all_image_analyses
    if analysis.get("image_type") == "exterior"
]

# Send all to Claude with special prompt
prompt = f"""You are analyzing {len(exterior_images)} different photos of
THE SAME property exterior. Look at all photos and determine:
1. Single architecture style (most prominent)
2. Primary exterior color
3. All visible materials

Images show same property from different angles. Reconcile any differences."""

# Call Claude with multi-image input
unified_analysis = claude_analyze_multiple_images(exterior_images, prompt)
```

**Pros:**
- ✅ Highest accuracy
- ✅ Claude can reconcile differences
- ✅ Single source of truth

**Cons:**
- ❌ More expensive ($0.00025 per image → could be $0.00125 for 5 exterior photos)
- ❌ Slower (one big call vs parallel analysis)
- ❌ Requires significant code changes

---

### Solution 4: **Weighted Voting by Image Quality (Advanced)**

**Approach:** Weight votes by Claude's confidence and feature count

```python
# Weighted voting
style_votes = {}
color_votes = {}

for analysis in all_image_analyses:
    if analysis.get("image_type") == "exterior":
        # Weight by confidence
        weight = 1.0
        if analysis.get("confidence") == "high":
            weight = 2.0
        elif analysis.get("confidence") == "low":
            weight = 0.5

        # Weight by feature count (more details = better view)
        feature_count = len(analysis.get("features", []))
        if feature_count > 20:
            weight *= 1.5

        # Apply weighted vote
        style = analysis.get("architecture_style")
        if style:
            style_votes[style] = style_votes.get(style, 0) + weight

        color = analysis.get("exterior_color")
        if color:
            color_votes[color] = color_votes.get(color, 0) + weight

# Select winners
primary_style = max(style_votes, key=style_votes.get) if style_votes else None
primary_color = max(color_votes, key=color_votes.get) if color_votes else None
```

**Pros:**
- ✅ More intelligent than simple majority
- ✅ Favors high-quality detections
- ✅ Handles edge cases better

**Cons:**
- ❌ More complex
- ❌ Weights need tuning

---

## Recommended Implementation

### **Phase 1: Majority Voting (Solution 2)**

Implement consensus-based approach:
1. Collect all styles/colors from exterior images
2. Use `Counter` to find most common
3. Limit to top 1 style, 1 color, 2-3 materials
4. Generate clean description

**Expected improvement:**
- ✅ Eliminate contradictions
- ✅ Improve search precision
- ✅ Better user experience in score breakdown
- ✅ More accurate text embeddings

### **Phase 2: Consider Weighted Voting (Solution 4)**

If quality still varies:
- Add confidence-based weighting
- Prioritize images with more detected features
- Further refine accuracy

---

## Testing Strategy

### Before/After Comparison

1. **Sample 10 properties** with multiple exterior photos
2. **Generate visual_features_text** with current method
3. **Generate visual_features_text** with majority voting
4. **Compare:**
   - Number of contradictions
   - Search result quality
   - User comprehension

### Example Test Case

**Property:** Craftsman home, white siding, brick chimney

**Current output:**
```
Exterior: craftsman style white exterior, modern style brick exterior,
contemporary style white exterior
```

**Expected output (after fix):**
```
Exterior: craftsman style white exterior with brick accents
```

**Search test:**
- Query: "craftsman white house" → Should rank high ✅
- Query: "modern brick house" → Should NOT rank high ❌ (currently does)

---

## Code Change Estimate

### Lines to Modify: ~50 lines

**File:** `upload_listings.py` (lines 407-430)

**Changes:**
1. Add `Counter` import
2. Replace concatenation logic with voting logic
3. Limit to 1 style, 1 color, top 3 materials
4. Update tests

**Time estimate:** 30-45 minutes

**Risk:** Low (only affects visual_features_text generation, doesn't change embeddings or search logic)

---

## Metrics to Track

After implementation:

1. **Contradiction Rate:**
   - Before: % of properties with 2+ styles in visual_features_text
   - After: Should be 0%

2. **Search Precision:**
   - Query: "modern white house"
   - Measure: % of top 10 results actually modern + white
   - Before: ~40%?
   - After: ~80%+?

3. **Text Length:**
   - Before: Average ~600 chars (lots of redundancy)
   - After: Average ~200 chars (concise, accurate)

4. **User Feedback:**
   - Score breakdown comprehension
   - Trust in search results

---

## Conclusion

**Root Cause:** Concatenating all per-image detections without reconciliation

**Best Solution:** Majority voting (Solution 2)
- Simple to implement
- Eliminates contradictions
- Improves search quality
- No cost increase

**Impact:**
- Better search precision
- Clearer score breakdowns
- More accurate text embeddings
- Improved user trust

**Next Step:** Implement majority voting in upload_listings.py
