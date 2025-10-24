# Architecture Style Fallback System

## Overview

Our search system includes an intelligent **hierarchical fallback system** for architectural styles. When a user searches for a specific style (e.g., "Second Empire"), the system automatically includes similar styles to ensure good results even when properties haven't been classified with that exact style.

## How It Works

### 1. Style Mapping
When a user searches "second empire style homes":
- System maps query to `victorian_second_empire` via synonym dictionary
- Includes parent style `victorian` as first fallback

### 2. Automatic Fallback Expansion
The system can expand to include similar styles based on similarity scores:

```python
from architecture_style_mappings import get_expanded_style_search

# Search for Second Empire
expanded = get_expanded_style_search(['victorian_second_empire'])

# Returns:
{
    "primary": ["victorian_second_empire"],
    "fallbacks": [
        ("victorian", 0.95),           # Very similar (parent style)
        ("victorian_italianate", 0.75), # Both have ornate details
        ("victorian_queen_anne", 0.70), # Similar era
        ("victorian_gothic_revival", 0.65)
    ],
    "all_styles": [
        "victorian_second_empire",
        "victorian",
        "victorian_italianate",
        "victorian_queen_anne"
    ]
}
```

### 3. Similarity Scores

Similarity scores (0.0-1.0) indicate how closely related styles are:
- **0.95**: Almost identical (parent/child relationship)
- **0.75-0.85**: Very similar (same family, different sub-styles)
- **0.65-0.70**: Related (similar era or aesthetic)
- **< 0.65**: Loosely related

## Example Fallback Hierarchies

### Victorian Family
```
second empire → victorian (0.95) → victorian_italianate (0.75) → victorian_queen_anne (0.70)
```

### Arts & Crafts Family
```
arts_and_crafts → craftsman (0.95) → craftsman_bungalow (0.90) → bungalow (0.85) → prairie_style (0.80)
```

### Mid-Century Family
```
mid_century_modern → mid_century_ranch (0.90) → ranch (0.75) → contemporary (0.70)
```

## Why This Matters

**Problem**: When properties aren't classified with architectural styles, specific searches return poor results.

**Solution**: The fallback system ensures:
1. User searches "Second Empire"
2. System searches for: `victorian_second_empire`, `victorian`, `victorian_italianate`
3. Finds Victorian homes that are stylistically similar
4. User gets relevant results instead of no results

## Current Status

✅ **Synonym mappings include parent styles** - Already implemented in synonym dictionary
✅ **Comprehensive similarity scores** - 40+ style relationships defined
✅ **Fallback functions available** - `get_fallback_styles()`, `get_expanded_style_search()`
⏸️ **Auto-fallback in search** - Available but not yet activated in search.py

## How to Use

### Get Fallback Styles
```python
from architecture_style_mappings import get_fallback_styles

# Get fallbacks for Second Empire
fallbacks = get_fallback_styles('victorian_second_empire', min_similarity=0.70)
# Returns: [("victorian", 0.95), ("victorian_italianate", 0.75), ("victorian_queen_anne", 0.70)]
```

### Expand Style Search
```python
from architecture_style_mappings import get_expanded_style_search

# Automatically expand with fallbacks
expanded = get_expanded_style_search(['victorian_second_empire'], min_similarity=0.70)
all_styles = expanded['all_styles']  # Use this for search query
```

### Test Mappings
```bash
python3 -c "
from architecture_style_mappings import map_user_style_to_supported, get_expanded_style_search

result = map_user_style_to_supported('second empire style homes')
print('Mapped:', result['styles'])

expanded = get_expanded_style_search(result['styles'])
print('With fallbacks:', expanded['all_styles'])
"
```

## Complete Style Families

### Victorian (7 sub-styles)
- victorian (parent)
- victorian_second_empire
- victorian_queen_anne
- victorian_italianate
- victorian_gothic_revival
- victorian_romanesque_revival
- victorian_shingle_style

### Craftsman (4 sub-styles)
- craftsman (parent)
- craftsman_bungalow
- craftsman_foursquare
- arts_and_crafts
- prairie_style

### Colonial (7 sub-styles)
- colonial (parent)
- colonial_revival
- colonial_saltbox
- colonial_dutch
- colonial_spanish
- federal
- georgian
- cape_cod

### Modern (6 sub-styles)
- modern (parent)
- contemporary
- minimalist
- industrial
- contemporary_farmhouse
- modern_farmhouse

### Mediterranean/Spanish (5 sub-styles)
- mediterranean (parent)
- spanish_colonial_revival
- tuscan_villa
- spanish_hacienda
- monterey_colonial
- mission_revival
- pueblo_revival

## Benefits

1. **Better User Experience**: Users get relevant results even for specific style queries
2. **Handles Missing Data**: Works even when properties aren't classified
3. **Semantic Understanding**: System knows Second Empire is a Victorian sub-style
4. **Graceful Degradation**: Falls back from specific → general
5. **Transparent**: User sees which styles are being searched

## Future Enhancements

- [ ] Activate auto-fallback in search.py when no results found
- [ ] Add UI indicator showing "Also showing similar Victorian styles"
- [ ] Track which fallbacks produce best results
- [ ] Expand similarity scores to more style combinations
- [ ] Add user preference: "strict match only" vs "include similar styles"
