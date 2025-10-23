"""
Architectural Style Mapping System

Provides:
1. Synonym dictionary for common architectural terms
2. Style family hierarchies
3. Fast lookup without LLM calls (90% of queries)
4. Intelligent fallback strategies
"""

# Complete list of supported styles (60 total)
ALL_SUPPORTED_STYLES = {
    # Tier 1: Broad categories (30 styles)
    "modern", "contemporary", "mid_century_modern", "craftsman", "ranch",
    "colonial", "victorian", "mediterranean", "spanish_colonial_revival",
    "tudor", "farmhouse", "cottage", "bungalow", "cape_cod", "split_level",
    "traditional", "transitional", "industrial", "minimalist", "prairie_style",
    "mission_revival", "pueblo_revival", "log_cabin", "a_frame",
    "scandinavian_modern", "contemporary_farmhouse", "arts_and_crafts",
    "tudor_revival", "colonial_revival", "greek_revival",

    # Tier 2: Specific sub-styles (30 styles)
    "victorian_queen_anne", "victorian_italianate", "victorian_gothic_revival",
    "victorian_second_empire", "victorian_romanesque_revival",
    "victorian_shingle_style", "craftsman_bungalow", "craftsman_foursquare",
    "colonial_saltbox", "colonial_dutch", "colonial_spanish", "federal",
    "georgian", "tuscan_villa", "french_provincial", "french_country",
    "spanish_hacienda", "monterey_colonial", "english_cottage", "french_chateau",
    "neoclassical", "romanesque_revival", "gothic_revival", "beaux_arts",
    "art_deco", "bauhaus", "international_style", "postmodern",
    "modern_farmhouse", "rustic_modern"
}

# Synonym dictionary: colloquial name → our supported style(s)
STYLE_SYNONYMS = {
    # Sears & Kit Homes
    "sears home": ["craftsman_bungalow", "craftsman"],
    "sears catalog home": ["craftsman_bungalow", "craftsman"],
    "sears kit house": ["craftsman_bungalow", "craftsman"],
    "kit house": ["craftsman_bungalow", "craftsman"],
    "mail order home": ["craftsman_bungalow", "craftsman"],

    # Famous Architects/Styles
    "eichler": ["mid_century_modern"],
    "eichler home": ["mid_century_modern"],
    "frank lloyd wright": ["prairie_style", "craftsman"],
    "prairie school": ["prairie_style"],
    "wright style": ["prairie_style"],
    "usonian": ["prairie_style", "mid_century_modern"],

    # Vernacular Names
    "brownstone": ["victorian_italianate", "victorian"],
    "row house": ["victorian_italianate", "colonial"],
    "painted lady": ["victorian_queen_anne", "victorian"],
    "gingerbread house": ["victorian_queen_anne", "victorian"],
    "shotgun house": ["traditional", "cottage"],
    "charleston single": ["colonial", "colonial_revival"],
    "dogtrot": ["farmhouse", "colonial"],

    # Abbreviated/Casual Names
    "mid century": ["mid_century_modern"],
    "mcm": ["mid_century_modern"],
    "mid mod": ["mid_century_modern"],
    "craftsman style": ["craftsman"],
    "arts and crafts": ["arts_and_crafts", "craftsman"],
    "queen anne": ["victorian_queen_anne", "victorian"],

    # Style Variants
    "cape": ["cape_cod"],
    "gambrel": ["colonial_dutch", "colonial"],
    "saltbox": ["colonial_saltbox", "colonial"],
    "adobe": ["pueblo_revival", "spanish_colonial_revival"],
    "pueblo style": ["pueblo_revival"],
    "hacienda": ["spanish_hacienda", "spanish_colonial_revival"],
    "mission style": ["mission_revival"],
    "spanish style": ["spanish_colonial_revival", "mediterranean"],
    "med style": ["mediterranean"],
    "tuscan": ["tuscan_villa", "mediterranean"],

    # Modern Variants
    "modern style": ["modern", "contemporary"],
    "contemporary style": ["contemporary", "modern"],
    "minimalist style": ["minimalist", "modern"],
    "industrial style": ["industrial", "modern"],
    "farmhouse style": ["farmhouse", "contemporary_farmhouse"],
    "modern farmhouse": ["modern_farmhouse", "contemporary_farmhouse"],
    "barn house": ["modern_farmhouse", "rustic_modern"],

    # Traditional Variants
    "colonial style": ["colonial", "colonial_revival"],
    "victorian style": ["victorian"],
    "tudor style": ["tudor", "tudor_revival"],

    # Log & Timber
    "log home": ["log_cabin"],
    "timber frame": ["log_cabin", "craftsman"],
    "a frame": ["a_frame"],

    # Luxury/Upscale Descriptors
    "luxury modern": ["modern", "contemporary"],
    "custom contemporary": ["contemporary"],
    "architect designed": ["contemporary", "modern"],
    "mcmansion": ["traditional", "colonial_revival"],
    "mansion": ["colonial_revival", "neoclassical"],

    # Regional
    "california ranch": ["ranch"],
    "california bungalow": ["craftsman_bungalow", "bungalow"],
    "new england": ["cape_cod", "colonial"],
    "southern colonial": ["colonial", "colonial_revival"],
    "southwestern": ["pueblo_revival", "spanish_colonial_revival"],
}

# Style families: parent → children
# Used for expanding "Victorian" to all Victorian sub-styles
STYLE_FAMILIES = {
    "victorian": [
        "victorian_queen_anne",
        "victorian_italianate",
        "victorian_gothic_revival",
        "victorian_second_empire",
        "victorian_romanesque_revival",
        "victorian_shingle_style",
        "victorian"  # Include parent
    ],

    "craftsman": [
        "craftsman_bungalow",
        "craftsman_foursquare",
        "arts_and_crafts",
        "prairie_style",
        "craftsman"  # Include parent
    ],

    "colonial": [
        "colonial_revival",
        "colonial_saltbox",
        "colonial_dutch",
        "colonial_spanish",
        "federal",
        "georgian",
        "cape_cod",
        "colonial"  # Include parent
    ],

    "mid_century_modern": [
        "mid_century_modern",
        "mid_century_ranch",
        "mid_century_split_level",
        "ranch"  # Often overlaps
    ],

    "mediterranean": [
        "mediterranean",
        "spanish_colonial_revival",
        "tuscan_villa",
        "spanish_hacienda",
        "monterey_colonial"
    ],

    "modern": [
        "modern",
        "contemporary",
        "minimalist",
        "industrial",
        "contemporary_farmhouse",
        "modern_farmhouse"
    ],

    "farmhouse": [
        "farmhouse",
        "contemporary_farmhouse",
        "modern_farmhouse",
        "rustic_modern"
    ],

    "spanish": [
        "spanish_colonial_revival",
        "mission_revival",
        "pueblo_revival",
        "spanish_hacienda",
        "monterey_colonial"
    ]
}

# Style similarity scores (for ranking)
# Used when user searches for unmapped style
STYLE_SIMILARITY = {
    "arts_and_crafts": {
        "craftsman": 0.95,
        "craftsman_bungalow": 0.90,
        "bungalow": 0.85,
        "prairie_style": 0.80
    },
    "mid_century_modern": {
        "ranch": 0.75,
        "contemporary": 0.70,
        "modern": 0.65
    },
    "victorian_queen_anne": {
        "victorian": 0.95,
        "victorian_italianate": 0.70,
        "victorian_gothic_revival": 0.65
    }
    # Add more as needed
}


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
    user_lower = user_input.lower().strip()

    # 1. Exact match
    if user_lower in ALL_SUPPORTED_STYLES:
        return {
            "exact_match": True,
            "styles": [user_lower],
            "confidence": 1.0,
            "method": "exact_match",
            "reasoning": f"Direct match for '{user_lower}'"
        }

    # 2. Synonym lookup
    if user_lower in STYLE_SYNONYMS:
        return {
            "exact_match": False,
            "styles": STYLE_SYNONYMS[user_lower],
            "confidence": 0.9,
            "method": "synonym_dictionary",
            "reasoning": f"'{user_input}' mapped to {STYLE_SYNONYMS[user_lower]}"
        }

    # 3. Family expansion
    if user_lower in STYLE_FAMILIES:
        return {
            "exact_match": False,
            "styles": STYLE_FAMILIES[user_lower],
            "confidence": 0.85,
            "method": "family_expansion",
            "reasoning": f"Expanded '{user_lower}' to include all {user_lower} styles"
        }

    # 4. Fuzzy/partial match
    # Check if user input is substring of any supported style
    partial_matches = [s for s in ALL_SUPPORTED_STYLES if user_lower in s or s in user_lower]
    if partial_matches:
        return {
            "exact_match": False,
            "styles": partial_matches[:3],  # Top 3
            "confidence": 0.7,
            "method": "partial_match",
            "reasoning": f"Partial match for '{user_input}'"
        }

    # 5. No match - needs LLM or semantic fallback
    return {
        "exact_match": False,
        "styles": [],
        "confidence": 0.0,
        "method": "needs_llm_mapping",
        "reasoning": f"No direct mapping found for '{user_input}'"
    }


def get_style_family(style):
    """Get the broad family for a specific style"""
    for family, members in STYLE_FAMILIES.items():
        if style in members:
            return family
    return style  # Return itself if no family found


def get_user_friendly_message(user_query, mapped_styles):
    """
    Generate user-friendly message about style mapping.

    Returns string to display in UI.
    """
    if not mapped_styles:
        return None

    if len(mapped_styles) == 1:
        return f"Showing {mapped_styles[0].replace('_', ' ').title()} homes"

    # Multiple styles
    style_names = [s.replace('_', ' ').title() for s in mapped_styles[:3]]

    if len(style_names) == 2:
        return f"Showing {style_names[0]} and {style_names[1]} homes"
    else:
        return f"Showing {', '.join(style_names[:-1])}, and {style_names[-1]} homes"


# Example usage
if __name__ == '__main__':
    # Test cases
    test_queries = [
        "Sears Catalog Home",
        "Arts and Crafts",
        "Victorian",
        "Eichler",
        "Modern Farmhouse",
        "Painted Lady",
        "Prairie School",
        "Unknown Style",  # Should fail
    ]

    print("🏛️  Style Mapping Test\n")

    for query in test_queries:
        result = map_user_style_to_supported(query)

        print(f"Query: '{query}'")
        print(f"  Method: {result['method']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Styles: {result['styles']}")
        print(f"  Message: {get_user_friendly_message(query, result['styles'])}")
        print()
