# Architecture Styles System

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [SEARCH_SYSTEM.md](SEARCH_SYSTEM.md), [DATA_SCHEMA.md](DATA_SCHEMA.md)

Complete documentation of the 2-tier hierarchical architecture style classification system.

---

## Table of Contents

1. [Overview](#overview)
2. [2-Tier Classification](#2-tier-classification)
3. [Synonym Mapping](#synonym-mapping)
4. [Style Families](#style-families)
5. [Search Integration](#search-integration)
6. [Classification Process](#classification-process)
7. [Examples](#examples)

---

## Overview

The architecture style system classifies properties into a hierarchical taxonomy with two tiers:
- **Tier 1**: 30 broad architectural categories (e.g., "modern", "craftsman", "victorian")
- **Tier 2**: 30+ specific sub-styles (e.g., "mid_century_modern", "craftsman_bungalow", "victorian_queen_anne")

**Key Features**:
- 60+ total architectural styles
- Synonym mapping for colloquial terms
- Style family hierarchies
- Fast lookup without LLM calls (90% of queries)
- Search integration with architecture_style_mappings.py

---

## 2-Tier Classification

### Tier 1: Broad Categories (30 Styles)

**Modern & Contemporary**:
- `modern`
- `contemporary`
- `minimalist`
- `industrial`
- `scandinavian_modern`
- `mountain_modern`

**Traditional American**:
- `craftsman`
- `ranch`
- `bungalow`
- `cape_cod`
- `colonial`
- `farmhouse`
- `cottage`
- `split_level`
- `prairie_style`

**Historical Styles**:
- `victorian`
- `tudor`
- `federal`
- `georgian`
- `arts_and_crafts`

**Regional Styles**:
- `mediterranean`
- `spanish_colonial_revival`
- `mission_revival`
- `pueblo_revival`

**Transitional**:
- `traditional`
- `transitional`
- `contemporary_farmhouse`

**Unique Styles**:
- `log_cabin`
- `a_frame`
- `mid_century_modern`

### Tier 2: Specific Sub-Styles (30+ Styles)

**Victorian Sub-Styles**:
- `victorian_queen_anne` (ornate, turrets, asymmetrical)
- `victorian_italianate` (tall windows, flat roofs, brackets)
- `victorian_gothic_revival` (pointed arches, steep gables)
- `victorian_second_empire` (mansard roof)
- `victorian_romanesque_revival` (round arches, stone)
- `victorian_shingle_style` (continuous shingles)

**Craftsman Sub-Styles**:
- `craftsman_bungalow` (low-pitched roof, front porch)
- `craftsman_foursquare` (square shape, four rooms per floor)

**Colonial Sub-Styles**:
- `colonial_saltbox` (asymmetrical lean-to roof)
- `colonial_dutch` (gambrel roof)
- `colonial_spanish` (stucco, tile roof)
- `colonial_revival` (symmetrical facade)

**Mid-Century Modern Sub-Styles**:
- `mid_century_ranch` (MCM + ranch characteristics)
- `mid_century_split_level` (MCM + split-level layout)

**Mediterranean Sub-Styles**:
- `tuscan_villa`
- `spanish_hacienda`
- `monterey_colonial`

**French Styles**:
- `french_provincial`
- `french_country`
- `french_chateau`

**Other Architectural Movements**:
- `art_deco`
- `bauhaus`
- `international_style`
- `postmodern`
- `neoclassical`
- `beaux_arts`

**Modern Farmhouse**:
- `modern_farmhouse`
- `rustic_modern`

---

## Synonym Mapping

**Purpose**: Map colloquial terms to supported architectural styles

**Implementation**: [architecture_style_mappings.py](../architecture_style_mappings.py)

### Famous Architects/Styles

| User Query | Mapped Styles |
|------------|---------------|
| "Eichler" | mid_century_modern |
| "Frank Lloyd Wright" | prairie_style, craftsman |
| "Usonian" | prairie_style, mid_century_modern |

### Vernacular Names

| User Query | Mapped Styles |
|------------|---------------|
| "Painted Lady" | victorian_queen_anne, victorian |
| "Brownstone" | victorian_italianate, victorian |
| "Sears Home" | craftsman_bungalow, craftsman |

### Abbreviated Names

| User Query | Mapped Styles |
|------------|---------------|
| "Mid-Century Modern" | mid_century_modern |
| "MCM" | mid_century_modern |
| "MCM Homes" | mid_century_modern |
| "Mid Century Ranch" | mid_century_ranch, ranch |

### Style Variants

| User Query | Mapped Styles |
|------------|---------------|
| "Cape" | cape_cod |
| "Adobe" | pueblo_revival, spanish_colonial_revival |
| "Hacienda" | spanish_hacienda, spanish_colonial_revival |
| "Tuscan" | tuscan_villa, mediterranean |

### Complete Synonym Dictionary

See [architecture_style_mappings.py:38-124](../architecture_style_mappings.py#L38-L124) for full list of 100+ synonyms.

---

## Style Families

**Purpose**: Group related styles for broader search

**Example**: Searching "Victorian" returns all Victorian sub-styles

### Victorian Family
```python
"victorian": [
    "victorian_queen_anne",
    "victorian_italianate",
    "victorian_gothic_revival",
    "victorian_second_empire",
    "victorian_romanesque_revival",
    "victorian_shingle_style",
    "victorian"
]
```

### Craftsman Family
```python
"craftsman": [
    "craftsman_bungalow",
    "craftsman_foursquare",
    "arts_and_crafts",
    "prairie_style",
    "craftsman"
]
```

### Mid-Century Modern Family
```python
"mid_century_modern": [
    "mid_century_modern",
    "mid_century_ranch",
    "mid_century_split_level",
    "ranch"
]
```

### Mediterranean Family
```python
"mediterranean": [
    "mediterranean",
    "spanish_colonial_revival",
    "tuscan_villa",
    "spanish_hacienda",
    "monterey_colonial"
]
```

### Modern Family
```python
"modern": [
    "modern",
    "contemporary",
    "minimalist",
    "industrial",
    "contemporary_farmhouse",
    "modern_farmhouse"
]
```

---

## Search Integration

### Mapping Function

**File**: [architecture_style_mappings.py:221-283](../architecture_style_mappings.py#L221-L283)

```python
def map_user_style_to_supported(user_input):
    """
    Fast mapping without LLM call.

    Returns:
        dict with:
        - exact_match: bool
        - styles: list of supported styles
        - confidence: 0-1
        - method: how it was mapped
    """
```

### Mapping Methods

**1. Exact Match** (confidence: 1.0)
```python
user_input = "mid_century_modern"
# → ["mid_century_modern"]
```

**2. Synonym Dictionary** (confidence: 0.9)
```python
user_input = "MCM homes"
# → ["mid_century_modern"]
```

**3. Family Expansion** (confidence: 0.85)
```python
user_input = "Victorian"
# → ["victorian_queen_anne", "victorian_italianate", ...]
```

**4. Partial Match** (confidence: 0.7)
```python
user_input = "modern"
# → ["modern", "mid_century_modern", "contemporary_modern"]
```

**5. LLM Fallback** (confidence: varies)
```python
user_input = "atomic ranch"
# → LLM classifies as mid_century_ranch
```

### Search Query Processing

**Example Query**: "mid century modern homes with pool"

**Step 1**: Extract architecture terms
```python
architecture_terms = ["mid century modern"]
```

**Step 2**: Map to supported styles
```python
mapped = map_user_style_to_supported("mid century modern")
# Returns: {
#   "styles": ["mid_century_modern"],
#   "confidence": 0.9,
#   "method": "synonym_dictionary"
# }
```

**Step 3**: Search for properties
```python
# OpenSearch query
{
  "bool": {
    "should": [
      {"term": {"architecture_style": "mid_century_modern"}},
      {"term": {"architecture_substyle": "mid_century_modern"}}
    ]
  }
}
```

---

## Classification Process

### During Data Ingestion

**File**: [upload_listings.py](../upload_listings.py)

**Process**:
1. Extract property images
2. Send images to Claude Vision API
3. Claude analyzes architectural features
4. Returns Tier 1 + Tier 2 classification

**Example Claude Prompt**:
```python
prompt = """
Analyze this property image and classify its architectural style.

Return JSON with:
- tier1_style: broad category (e.g., "modern", "craftsman", "victorian")
- tier2_style: specific sub-style (e.g., "mid_century_modern", "craftsman_bungalow")
- confidence: 0-1
- reasoning: why you chose these styles

Supported Tier 1 styles: {list of 30 styles}
Supported Tier 2 styles: {list of 30+ styles}
"""
```

**Claude Response**:
```json
{
  "tier1_style": "mid_century_modern",
  "tier2_style": "mid_century_ranch",
  "confidence": 0.92,
  "reasoning": "Low-pitched roof, horizontal emphasis, large windows, post-and-beam construction typical of mid-century modern ranch homes"
}
```

**Stored in OpenSearch**:
```json
{
  "zpid": "123456",
  "architecture_style": "mid_century_modern",
  "architecture_substyle": "mid_century_ranch",
  ...
}
```

### Batch Updates

**Script**: [update_architecture_fast.py](../update_architecture_fast.py)

**Purpose**: Update architecture styles for existing properties

**Process**:
1. Fetch properties without architecture_style
2. For each property, call Claude Vision API
3. Get Tier 1 + Tier 2 classification
4. Update via CRUD API with preserve_embeddings=true

**Usage**:
```bash
python3 update_architecture_fast.py
```

**Progress**: 2,800+ properties updated as of 2025-10-23

---

## Examples

### Example 1: Mid-Century Modern Search

**User Query**: "mid century modern homes"

**Mapping**:
```python
map_user_style_to_supported("mid century modern homes")
# Returns:
{
  "exact_match": False,
  "styles": ["mid_century_modern"],
  "confidence": 0.9,
  "method": "synonym_dictionary",
  "reasoning": "'mid century modern homes' mapped to ['mid_century_modern']"
}
```

**Search Results**:
- Properties with `architecture_style: "mid_century_modern"`
- Properties with `architecture_substyle: "mid_century_modern"`
- Properties with `architecture_substyle: "mid_century_ranch"`
- Properties with `architecture_substyle: "mid_century_split_level"`

### Example 2: Victorian Search

**User Query**: "Victorian homes"

**Mapping**:
```python
map_user_style_to_supported("Victorian")
# Returns:
{
  "exact_match": False,
  "styles": [
    "victorian_queen_anne",
    "victorian_italianate",
    "victorian_gothic_revival",
    "victorian_second_empire",
    "victorian_romanesque_revival",
    "victorian_shingle_style",
    "victorian"
  ],
  "confidence": 0.85,
  "method": "family_expansion"
}
```

**Search Results**: All Victorian styles included

### Example 3: Eichler Search

**User Query**: "Eichler homes"

**Mapping**:
```python
map_user_style_to_supported("Eichler")
# Returns:
{
  "exact_match": False,
  "styles": ["mid_century_modern"],
  "confidence": 0.9,
  "method": "synonym_dictionary",
  "reasoning": "'Eichler' mapped to ['mid_century_modern']"
}
```

**Search Results**: Mid-century modern properties

### Example 4: Craftsman Bungalow Search

**User Query**: "Craftsman bungalow"

**Mapping**:
```python
map_user_style_to_supported("craftsman_bungalow")
# Returns:
{
  "exact_match": True,
  "styles": ["craftsman_bungalow"],
  "confidence": 1.0,
  "method": "exact_match"
}
```

**Search Results**: Craftsman bungalow properties specifically

---

## Data Quality

### Current Coverage

As of 2025-10-24:
- **Total Properties**: 3,902
- **With Architecture Style**: ~2,800 (72%)
- **Pending Classification**: ~1,100 (28%)

### Classification Accuracy

Based on manual review:
- **Tier 1 Accuracy**: 95% (broad categories are easy)
- **Tier 2 Accuracy**: 85% (specific sub-styles are harder)

### Common Misclassifications

| Actual Style | Misclassified As | Frequency |
|--------------|------------------|-----------|
| Mid-Century Ranch | Ranch | 10% |
| Craftsman Bungalow | Craftsman | 8% |
| Victorian Queen Anne | Victorian | 12% |

**Mitigation**:
- Improved Claude Vision prompts
- Manual review of high-value properties
- User feedback system (planned)

---

## Adding New Styles

### Step 1: Add to ALL_SUPPORTED_STYLES

**File**: [architecture_style_mappings.py:12-35](../architecture_style_mappings.py#L12-L35)

```python
ALL_SUPPORTED_STYLES = {
    # ... existing styles ...
    "new_style_name",
}
```

### Step 2: Add Synonyms

**File**: [architecture_style_mappings.py:38-124](../architecture_style_mappings.py#L38-L124)

```python
STYLE_SYNONYMS = {
    # ... existing synonyms ...
    "colloquial name": ["new_style_name"],
}
```

### Step 3: Add to Style Family (if applicable)

**File**: [architecture_style_mappings.py:128-196](../architecture_style_mappings.py#L128-L196)

```python
STYLE_FAMILIES = {
    "parent_style": [
        # ... existing members ...
        "new_style_name"
    ]
}
```

### Step 4: Update Claude Vision Prompt

**File**: [upload_listings.py](../upload_listings.py)

Add new style to supported styles list in prompt.

### Step 5: Deploy

```bash
# Deploy updated mappings to Lambda
./deploy_lambda.sh

# Verify
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=new+style"
```

---

## Troubleshooting

### Search Returns No Results for Architecture Style

**Issue**: User searches "mid century modern" but gets no results

**Causes**:
1. Style not in STYLE_SYNONYMS dictionary
2. Properties not classified yet
3. Lambda using old architecture_style_mappings.py

**Fix**:
```bash
# 1. Check if style is supported
python3 architecture_style_mappings.py
# Look for your query in test output

# 2. Add synonym if missing
# Edit architecture_style_mappings.py, add to STYLE_SYNONYMS

# 3. Deploy updated mappings
./deploy_lambda.sh

# 4. Verify Lambda has new code
aws lambda get-function --function-name hearth-search-v2 | grep LastModified
```

### Properties Misclassified

**Issue**: Property classified as wrong style

**Fix**:
```bash
# Update single property via CRUD API
curl -X PATCH "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/123456?index=listings-v2" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": {
      "architecture_style": "correct_tier1_style",
      "architecture_substyle": "correct_tier2_style"
    },
    "options": {"preserve_embeddings": true}
  }'
```

### Batch Update Stalled

**Issue**: update_architecture_fast.py stopped mid-batch

**Fix**:
```bash
# Check progress
tail -f /tmp/architecture_update.log

# Resume from checkpoint
python3 update_architecture_fast.py --resume
```

---

## Performance

### Lookup Speed

- **Exact Match**: < 1ms
- **Synonym Lookup**: < 1ms
- **Family Expansion**: < 2ms
- **Partial Match**: < 5ms
- **LLM Fallback**: 200-300ms

**90% of queries** resolved without LLM call.

### Classification Speed

- **Claude Vision API**: 1-2 seconds per property
- **Batch Update**: ~50 properties/minute
- **Full Re-classification**: ~2 hours for 3,902 properties

---

## See Also

- [SEARCH_SYSTEM.md](SEARCH_SYSTEM.md) - How architecture styles integrate with search
- [DATA_SCHEMA.md](DATA_SCHEMA.md) - Schema fields for architecture styles
- [API.md](API.md) - API endpoints for updating styles
- [architecture_style_mappings.py](../architecture_style_mappings.py) - Source code
