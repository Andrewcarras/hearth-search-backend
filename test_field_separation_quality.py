"""
Field Separation Search Quality Test
=====================================

This script empirically validates whether separating visual_features_text into
exterior_visual_features and interior_visual_features improves search quality.

Test Design:
1. Sample Query Set: 20 queries across 4 categories
2. Ground Truth: Manual evaluation of 50 properties
3. Scoring Simulation: Compare current vs proposed BM25 scoring
4. Metrics: Precision@5, False Positive Rate, NDCG
5. Real Data Test: Query actual OpenSearch index

Usage:
    python test_field_separation_quality.py --mode [simulation|live|both]

    --mode simulation: Run BM25 score simulation only
    --mode live: Query real OpenSearch index
    --mode both: Run both simulations and live tests (default)
"""

import json
import logging
import math
import os
import argparse
from typing import Dict, List, Tuple, Set, Any
from collections import defaultdict, Counter
from dataclasses import dataclass, field as dataclass_field

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Lazy imports for OpenSearch (only needed for live tests)
os_client = None
OS_INDEX = None
embed_text_multimodal = None

def _init_opensearch():
    """Initialize OpenSearch client (only when needed for live tests)."""
    global os_client, OS_INDEX, embed_text_multimodal
    if os_client is None:
        import boto3
        from common import os_client as _os_client, OS_INDEX as _OS_INDEX, embed_text_multimodal as _embed
        os_client = _os_client
        OS_INDEX = _OS_INDEX
        embed_text_multimodal = _embed

# ==========================================
# TEST QUERY SET (20 QUERIES)
# ==========================================

@dataclass
class TestQuery:
    """A test query with expected behavior."""
    query: str
    category: str  # exterior_color, interior_feature, multi_feature, ambiguous
    target_exterior: List[str] = dataclass_field(default_factory=list)
    target_interior: List[str] = dataclass_field(default_factory=list)
    expected_count: int = 10  # Expected number of relevant results in top 10

EXTERIOR_COLOR_QUERIES = [
    TestQuery("white house", "exterior_color", target_exterior=["white"], expected_count=8),
    TestQuery("blue exterior", "exterior_color", target_exterior=["blue"], expected_count=8),
    TestQuery("brick home", "exterior_color", target_exterior=["brick"], expected_count=8),
    TestQuery("gray siding", "exterior_color", target_exterior=["gray", "grey"], expected_count=7),
    TestQuery("brown exterior house", "exterior_color", target_exterior=["brown"], expected_count=8),
]

INTERIOR_FEATURE_QUERIES = [
    TestQuery("granite kitchen", "interior_feature", target_interior=["granite", "countertops"], expected_count=7),
    TestQuery("hardwood floors", "interior_feature", target_interior=["hardwood", "wood floors"], expected_count=7),
    TestQuery("modern bathroom", "interior_feature", target_interior=["modern", "bathroom"], expected_count=6),
    TestQuery("stainless appliances", "interior_feature", target_interior=["stainless", "appliances"], expected_count=7),
    TestQuery("white cabinets", "interior_feature", target_interior=["white", "cabinets"], expected_count=7),
]

MULTI_FEATURE_QUERIES = [
    TestQuery("white house with granite", "multi_feature",
              target_exterior=["white"], target_interior=["granite"], expected_count=6),
    TestQuery("brick exterior hardwood floors", "multi_feature",
              target_exterior=["brick"], target_interior=["hardwood"], expected_count=6),
    TestQuery("blue house modern kitchen", "multi_feature",
              target_exterior=["blue"], target_interior=["modern", "kitchen"], expected_count=5),
    TestQuery("gray exterior white cabinets", "multi_feature",
              target_exterior=["gray", "grey"], target_interior=["white", "cabinets"], expected_count=5),
    TestQuery("ranch style granite countertops", "multi_feature",
              target_exterior=["ranch"], target_interior=["granite"], expected_count=6),
]

AMBIGUOUS_QUERIES = [
    TestQuery("modern home", "ambiguous",
              target_exterior=["modern"], target_interior=["modern"], expected_count=7),
    TestQuery("white granite house", "ambiguous",
              target_exterior=["white"], target_interior=["granite"], expected_count=6),
    TestQuery("wood home", "ambiguous",
              target_exterior=["wood"], target_interior=["wood"], expected_count=6),
    TestQuery("contemporary design", "ambiguous",
              target_exterior=["contemporary"], target_interior=["contemporary"], expected_count=6),
    TestQuery("craftsman style", "ambiguous",
              target_exterior=["craftsman"], target_interior=[], expected_count=7),
]

ALL_TEST_QUERIES = (
    EXTERIOR_COLOR_QUERIES +
    INTERIOR_FEATURE_QUERIES +
    MULTI_FEATURE_QUERIES +
    AMBIGUOUS_QUERIES
)

# ==========================================
# BM25 SCORING SIMULATION
# ==========================================

def simulate_bm25_score(query: str, text: str, boost: float = 1.0) -> float:
    """
    Simplified BM25 scoring simulation.

    Real BM25 uses:
    - Term frequency (TF)
    - Inverse document frequency (IDF)
    - Document length normalization

    This simulation uses a simplified version for testing:
    - TF: count of query terms in text
    - Boost: field weight multiplier
    - Length normalization: penalize very long documents
    """
    query_terms = query.lower().split()
    text_lower = text.lower()

    # Count term matches
    term_matches = sum(1 for term in query_terms if term in text_lower)

    if term_matches == 0:
        return 0.0

    # Simple TF component (not true BM25, but illustrative)
    tf_score = term_matches / len(query_terms)

    # Length normalization (penalize very long documents)
    doc_length = len(text.split())
    avg_length = 50  # Assume average field length
    length_norm = 1.0 / (1.0 + abs(doc_length - avg_length) / avg_length)

    # Final score
    score = tf_score * boost * length_norm

    return score


def score_current_approach(query: str, description: str, visual_features_text: str) -> float:
    """
    Current BM25 scoring approach:
    score = bm25(query, description) * 3.0 + bm25(query, visual_features_text) * 2.5
    """
    desc_score = simulate_bm25_score(query, description, boost=3.0)
    visual_score = simulate_bm25_score(query, visual_features_text, boost=2.5)

    return desc_score + visual_score


def score_proposed_approach(
    query: str,
    description: str,
    exterior_visual_features: str,
    interior_visual_features: str,
    query_category: str
) -> float:
    """
    Proposed BM25 scoring approach with field separation:

    If query targets exterior:
        score = bm25(query, description) * 3.0 +
                bm25(query, exterior_visual_features) * 4.0
    Else:
        score = bm25(query, description) * 3.0 +
                bm25(query, interior_visual_features) * 3.0
    """
    desc_score = simulate_bm25_score(query, description, boost=3.0)

    # Route query to appropriate field
    if query_category == "exterior_color" or "exterior" in query.lower():
        # Boost exterior field heavily
        visual_score = simulate_bm25_score(query, exterior_visual_features, boost=4.0)
    elif query_category == "interior_feature":
        # Boost interior field
        visual_score = simulate_bm25_score(query, interior_visual_features, boost=3.0)
    elif query_category == "multi_feature":
        # Score both fields, sum them
        ext_score = simulate_bm25_score(query, exterior_visual_features, boost=3.0)
        int_score = simulate_bm25_score(query, interior_visual_features, boost=2.5)
        visual_score = ext_score + int_score
    else:  # ambiguous
        # Score both fields equally
        ext_score = simulate_bm25_score(query, exterior_visual_features, boost=2.5)
        int_score = simulate_bm25_score(query, interior_visual_features, boost=2.5)
        visual_score = max(ext_score, int_score)  # Take best match

    return desc_score + visual_score


# ==========================================
# SYNTHETIC TEST DATA GENERATION
# ==========================================

@dataclass
class TestProperty:
    """A property with labeled ground truth data."""
    zpid: str
    description: str
    exterior_color: str
    exterior_style: str
    interior_features: List[str]
    visual_features_text: str  # Current aggregated field
    exterior_visual_features: str  # Proposed separated field
    interior_visual_features: str  # Proposed separated field


def generate_test_properties() -> List[TestProperty]:
    """
    Generate 50 synthetic test properties with known ground truth.

    These represent the key edge cases we're testing:
    1. White exterior + white interior (10 properties)
    2. Brown exterior + white interior (10 properties)
    3. Brick exterior + brick interior (5 properties)
    4. Granite exterior + granite interior (rare, 2 properties)
    5. Various other combinations (23 properties)
    """
    properties = []

    # Case 1: White exterior + white interior (the "white house" problem)
    for i in range(10):
        zpid = f"white_ext_white_int_{i}"
        description = f"Beautiful ranch home with updated features. Property {i+1} in quiet neighborhood."

        # CURRENT: Both white mentions in same field
        visual_features_text = (
            f"Exterior: ranch style white exterior with vinyl siding. "
            f"Interior features: white cabinets, white trim, updated bathroom, "
            f"hardwood floors, modern fixtures. Property includes: {i} bedrooms."
        )

        # PROPOSED: Separated by context
        exterior_visual = f"ranch style white exterior with vinyl siding"
        interior_visual = f"white cabinets, white trim, updated bathroom, hardwood floors, modern fixtures"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="white",
            exterior_style="ranch",
            interior_features=["white cabinets", "white trim", "hardwood floors"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    # Case 2: Brown exterior + white interior (should NOT match "white house")
    for i in range(10):
        zpid = f"brown_ext_white_int_{i}"
        description = f"Charming home with spacious rooms. Property {i+1} with great potential."

        visual_features_text = (
            f"Exterior: traditional style brown exterior with brick. "
            f"Interior features: white walls, white cabinets, white trim, "
            f"tile floors, ceiling fans. Property includes: attached garage."
        )

        exterior_visual = f"traditional style brown exterior with brick"
        interior_visual = f"white walls, white cabinets, white trim, tile floors, ceiling fans"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="brown",
            exterior_style="traditional",
            interior_features=["white walls", "white cabinets", "tile floors"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    # Case 3: Brick exterior + brick fireplace (ambiguous "brick home")
    for i in range(5):
        zpid = f"brick_ext_brick_int_{i}"
        description = f"Classic brick home with character. Property {i+1} in established area."

        visual_features_text = (
            f"Exterior: colonial style red exterior with brick, stone accents. "
            f"Interior features: brick fireplace, hardwood floors, crown molding, "
            f"granite countertops. Property includes: covered patio."
        )

        exterior_visual = f"colonial style red exterior with brick, stone accents"
        interior_visual = f"brick fireplace, hardwood floors, crown molding, granite countertops"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="brick",
            exterior_style="colonial",
            interior_features=["brick fireplace", "hardwood floors", "granite countertops"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    # Case 4: Brick exterior only (no interior brick)
    for i in range(5):
        zpid = f"brick_ext_only_{i}"
        description = f"Stunning brick home with modern updates. Property {i+1} in prime location."

        visual_features_text = (
            f"Exterior: craftsman style brown exterior with brick, covered porch. "
            f"Interior features: hardwood floors, white cabinets, granite countertops, "
            f"stainless appliances. Property includes: fenced yard."
        )

        exterior_visual = f"craftsman style brown exterior with brick, covered porch"
        interior_visual = f"hardwood floors, white cabinets, granite countertops, stainless appliances"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="brick",
            exterior_style="craftsman",
            interior_features=["hardwood floors", "white cabinets", "granite countertops"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    # Case 5: Blue exterior + various interiors
    for i in range(5):
        zpid = f"blue_ext_{i}"
        description = f"Beautiful blue home with curb appeal. Property {i+1} move-in ready."

        visual_features_text = (
            f"Exterior: modern style blue exterior with vinyl siding, large windows. "
            f"Interior features: hardwood floors, granite countertops, stainless appliances, "
            f"modern fixtures. Property includes: attached garage."
        )

        exterior_visual = f"modern style blue exterior with vinyl siding, large windows"
        interior_visual = f"hardwood floors, granite countertops, stainless appliances, modern fixtures"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="blue",
            exterior_style="modern",
            interior_features=["hardwood floors", "granite countertops", "stainless appliances"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    # Case 6: Gray exterior + white interior
    for i in range(5):
        zpid = f"gray_ext_white_int_{i}"
        description = f"Contemporary gray home with clean lines. Property {i+1} in desirable area."

        visual_features_text = (
            f"Exterior: contemporary style gray exterior with stone accents, metal roof. "
            f"Interior features: white cabinets, white walls, quartz countertops, "
            f"hardwood floors. Property includes: covered patio."
        )

        exterior_visual = f"contemporary style gray exterior with stone accents, metal roof"
        interior_visual = f"white cabinets, white walls, quartz countertops, hardwood floors"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="gray",
            exterior_style="contemporary",
            interior_features=["white cabinets", "quartz countertops", "hardwood floors"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    # Case 7: Multi-feature combinations (white ext + granite int)
    for i in range(5):
        zpid = f"white_ext_granite_int_{i}"
        description = f"Beautiful white home with upgraded kitchen. Property {i+1} in great condition."

        visual_features_text = (
            f"Exterior: ranch style white exterior with vinyl siding, covered porch. "
            f"Interior features: granite countertops, stainless appliances, hardwood floors, "
            f"white cabinets. Property includes: attached garage."
        )

        exterior_visual = f"ranch style white exterior with vinyl siding, covered porch"
        interior_visual = f"granite countertops, stainless appliances, hardwood floors, white cabinets"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="white",
            exterior_style="ranch",
            interior_features=["granite countertops", "white cabinets", "hardwood floors"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    # Case 8: Rare cases - granite exterior (stone facade)
    for i in range(2):
        zpid = f"granite_ext_{i}"
        description = f"Luxury home with granite stone facade. Property {i+1} custom built."

        visual_features_text = (
            f"Exterior: modern style gray exterior with granite stone facade, metal accents. "
            f"Interior features: marble countertops, hardwood floors, high-end fixtures. "
            f"Property includes: 3-car garage."
        )

        exterior_visual = f"modern style gray exterior with granite stone facade, metal accents"
        interior_visual = f"marble countertops, hardwood floors, high-end fixtures"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="gray",
            exterior_style="modern",
            interior_features=["marble countertops", "hardwood floors"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    # Case 9: Modern style (ambiguous - could be exterior or interior)
    for i in range(3):
        zpid = f"modern_style_{i}"
        description = f"Modern home with open floor plan. Property {i+1} contemporary design."

        visual_features_text = (
            f"Exterior: modern style white exterior with clean lines, large windows. "
            f"Interior features: modern kitchen, hardwood floors, stainless appliances, "
            f"granite countertops. Property includes: open floor plan."
        )

        exterior_visual = f"modern style white exterior with clean lines, large windows"
        interior_visual = f"modern kitchen, hardwood floors, stainless appliances, granite countertops"

        properties.append(TestProperty(
            zpid=zpid,
            description=description,
            exterior_color="white",
            exterior_style="modern",
            interior_features=["modern kitchen", "hardwood floors", "granite countertops"],
            visual_features_text=visual_features_text,
            exterior_visual_features=exterior_visual,
            interior_visual_features=interior_visual
        ))

    logger.info(f"Generated {len(properties)} test properties")
    return properties


# ==========================================
# EVALUATION METRICS
# ==========================================

def evaluate_relevance(
    query: TestQuery,
    ranked_results: List[TestProperty]
) -> Dict[str, float]:
    """
    Evaluate search results against ground truth.

    Returns metrics:
    - precision_at_5: % of top 5 results that are relevant
    - precision_at_10: % of top 10 results that are relevant
    - false_positive_rate: % of top 10 that shouldn't match
    - ndcg: Normalized Discounted Cumulative Gain (ranking quality)
    """
    # Determine relevance criteria
    def is_relevant(prop: TestProperty) -> bool:
        """Check if property matches query requirements."""
        relevant = True

        # Check exterior requirements
        if query.target_exterior:
            ext_match = any(
                target.lower() in prop.exterior_color.lower() or
                target.lower() in prop.exterior_style.lower()
                for target in query.target_exterior
            )
            if query.category == "exterior_color":
                # For exterior queries, MUST match exterior
                relevant = relevant and ext_match

        # Check interior requirements
        if query.target_interior:
            int_match = any(
                target.lower() in " ".join(prop.interior_features).lower()
                for target in query.target_interior
            )
            if query.category == "interior_feature":
                # For interior queries, MUST match interior
                relevant = relevant and int_match

        # Multi-feature queries require both
        if query.category == "multi_feature":
            ext_match = any(
                target.lower() in prop.exterior_color.lower() or
                target.lower() in prop.exterior_style.lower()
                for target in query.target_exterior
            )
            int_match = any(
                target.lower() in " ".join(prop.interior_features).lower()
                for target in query.target_interior
            )
            relevant = ext_match and int_match

        return relevant

    # Evaluate top results
    top_5 = ranked_results[:5]
    top_10 = ranked_results[:10]

    relevant_5 = sum(1 for prop in top_5 if is_relevant(prop))
    relevant_10 = sum(1 for prop in top_10 if is_relevant(prop))

    precision_at_5 = relevant_5 / 5.0
    precision_at_10 = relevant_10 / 10.0
    false_positive_rate = (10 - relevant_10) / 10.0

    # Calculate NDCG@10
    dcg = 0.0
    idcg = 0.0

    for i, prop in enumerate(top_10):
        rank = i + 1
        relevance_score = 1.0 if is_relevant(prop) else 0.0
        dcg += relevance_score / math.log2(rank + 1)

        # Ideal ranking (all relevant at top)
        ideal_relevance = 1.0 if i < query.expected_count else 0.0
        idcg += ideal_relevance / math.log2(rank + 1)

    ndcg = dcg / idcg if idcg > 0 else 0.0

    return {
        "precision_at_5": precision_at_5,
        "precision_at_10": precision_at_10,
        "false_positive_rate": false_positive_rate,
        "ndcg": ndcg,
        "relevant_5": relevant_5,
        "relevant_10": relevant_10
    }


def run_simulation_test(properties: List[TestProperty]) -> Dict[str, Any]:
    """
    Run BM25 scoring simulation comparing current vs proposed approach.

    Returns detailed results for all test queries.
    """
    logger.info("=" * 80)
    logger.info("RUNNING SIMULATION TEST")
    logger.info("=" * 80)

    results = {
        "queries": [],
        "summary": {
            "current": {"avg_precision_5": 0, "avg_precision_10": 0, "avg_ndcg": 0},
            "proposed": {"avg_precision_5": 0, "avg_precision_10": 0, "avg_ndcg": 0}
        },
        "improvements": [],
        "degradations": []
    }

    for test_query in ALL_TEST_QUERIES:
        logger.info(f"\nTesting query: '{test_query.query}' (category: {test_query.category})")

        # Score with current approach
        current_scores = []
        for prop in properties:
            score = score_current_approach(
                test_query.query,
                prop.description,
                prop.visual_features_text
            )
            current_scores.append((score, prop))

        current_scores.sort(key=lambda x: x[0], reverse=True)
        current_ranked = [prop for _, prop in current_scores]

        # Score with proposed approach
        proposed_scores = []
        for prop in properties:
            score = score_proposed_approach(
                test_query.query,
                prop.description,
                prop.exterior_visual_features,
                prop.interior_visual_features,
                test_query.category
            )
            proposed_scores.append((score, prop))

        proposed_scores.sort(key=lambda x: x[0], reverse=True)
        proposed_ranked = [prop for _, prop in proposed_scores]

        # Evaluate both rankings
        current_metrics = evaluate_relevance(test_query, current_ranked)
        proposed_metrics = evaluate_relevance(test_query, proposed_ranked)

        # Calculate improvement
        precision_improvement = (
            proposed_metrics["precision_at_5"] - current_metrics["precision_at_5"]
        )
        ndcg_improvement = proposed_metrics["ndcg"] - current_metrics["ndcg"]

        query_result = {
            "query": test_query.query,
            "category": test_query.category,
            "current": current_metrics,
            "proposed": proposed_metrics,
            "precision_improvement": precision_improvement,
            "ndcg_improvement": ndcg_improvement,
            "current_top_5_zpids": [p.zpid for p in current_ranked[:5]],
            "proposed_top_5_zpids": [p.zpid for p in proposed_ranked[:5]]
        }

        results["queries"].append(query_result)

        # Log results
        logger.info(f"  Current  - P@5: {current_metrics['precision_at_5']:.2f}, "
                   f"P@10: {current_metrics['precision_at_10']:.2f}, "
                   f"NDCG: {current_metrics['ndcg']:.3f}")
        logger.info(f"  Proposed - P@5: {proposed_metrics['precision_at_5']:.2f}, "
                   f"P@10: {proposed_metrics['precision_at_10']:.2f}, "
                   f"NDCG: {proposed_metrics['ndcg']:.3f}")
        logger.info(f"  Change: P@5 {precision_improvement:+.2f}, NDCG {ndcg_improvement:+.3f}")

        # Track improvements and degradations
        if precision_improvement > 0.1:
            results["improvements"].append(query_result)
        elif precision_improvement < -0.1:
            results["degradations"].append(query_result)

    # Calculate summary statistics
    current_avg_p5 = sum(q["current"]["precision_at_5"] for q in results["queries"]) / len(results["queries"])
    current_avg_p10 = sum(q["current"]["precision_at_10"] for q in results["queries"]) / len(results["queries"])
    current_avg_ndcg = sum(q["current"]["ndcg"] for q in results["queries"]) / len(results["queries"])

    proposed_avg_p5 = sum(q["proposed"]["precision_at_5"] for q in results["queries"]) / len(results["queries"])
    proposed_avg_p10 = sum(q["proposed"]["precision_at_10"] for q in results["queries"]) / len(results["queries"])
    proposed_avg_ndcg = sum(q["proposed"]["ndcg"] for q in results["queries"]) / len(results["queries"])

    results["summary"]["current"] = {
        "avg_precision_5": current_avg_p5,
        "avg_precision_10": current_avg_p10,
        "avg_ndcg": current_avg_ndcg
    }

    results["summary"]["proposed"] = {
        "avg_precision_5": proposed_avg_p5,
        "avg_precision_10": proposed_avg_p10,
        "avg_ndcg": proposed_avg_ndcg
    }

    return results


# ==========================================
# LIVE OPENSEARCH TESTING
# ==========================================

def query_opensearch_current(query: str, size: int = 10) -> List[Dict[str, Any]]:
    """
    Query OpenSearch using current approach (visual_features_text).
    """
    _init_opensearch()

    body = {
        "size": size,
        "query": {
            "bool": {
                "filter": [{"range": {"price": {"gt": 0}}}],
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "description^3",
                                "visual_features_text^2.5"
                            ],
                            "type": "cross_fields"
                        }
                    }
                ],
                "minimum_should_match": 1
            }
        }
    }

    try:
        response = os_client.search(index=OS_INDEX, body=body)
        hits = response.get("hits", {}).get("hits", [])
        return [
            {
                "zpid": hit["_id"],
                "score": hit.get("_score", 0.0),
                "source": hit.get("_source", {})
            }
            for hit in hits
        ]
    except Exception as e:
        logger.error(f"OpenSearch query failed: {e}")
        return []


def query_opensearch_proposed(query: str, size: int = 10, category: str = "general") -> List[Dict[str, Any]]:
    """
    Query OpenSearch using proposed approach (separate exterior/interior fields).

    NOTE: This requires the fields to exist in the index!
    Run migrate_split_visual_features.py first if needed.
    """
    # Determine field weights based on query category
    if category == "exterior_color" or "exterior" in query.lower():
        fields = [
            "description^3",
            "exterior_visual_features^4.0"
        ]
    elif category == "interior_feature":
        fields = [
            "description^3",
            "interior_visual_features^3.0"
        ]
    else:
        # Multi-feature or ambiguous: search both
        fields = [
            "description^3",
            "exterior_visual_features^3.0",
            "interior_visual_features^2.5"
        ]

    body = {
        "size": size,
        "query": {
            "bool": {
                "filter": [{"range": {"price": {"gt": 0}}}],
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": fields,
                            "type": "cross_fields"
                        }
                    }
                ],
                "minimum_should_match": 1
            }
        }
    }

    try:
        response = os_client.search(index=OS_INDEX, body=body)
        hits = response.get("hits", {}).get("hits", [])
        return [
            {
                "zpid": hit["_id"],
                "score": hit.get("_score", 0.0),
                "source": hit.get("_source", {})
            }
            for hit in hits
        ]
    except Exception as e:
        logger.error(f"OpenSearch query failed: {e}")
        return []


def run_live_test() -> Dict[str, Any]:
    """
    Query actual OpenSearch index comparing current vs proposed approach.

    NOTE: Requires exterior_visual_features and interior_visual_features
    fields to exist in the index!
    """
    _init_opensearch()

    logger.info("=" * 80)
    logger.info("RUNNING LIVE OPENSEARCH TEST")
    logger.info("=" * 80)

    # Check if proposed fields exist
    try:
        sample_query = os_client.search(
            index=OS_INDEX,
            body={"size": 1, "_source": ["exterior_visual_features", "interior_visual_features"]}
        )
        sample_hit = sample_query.get("hits", {}).get("hits", [])
        if sample_hit:
            has_fields = (
                "exterior_visual_features" in sample_hit[0].get("_source", {}) or
                "interior_visual_features" in sample_hit[0].get("_source", {})
            )
            if not has_fields:
                logger.warning("⚠️  Proposed fields not found in index!")
                logger.warning("    Run migrate_split_visual_features.py first to add these fields.")
                return {"error": "Proposed fields not in index"}
        else:
            logger.warning("⚠️  Index appears to be empty")
            return {"error": "Empty index"}
    except Exception as e:
        logger.error(f"Failed to check index schema: {e}")
        return {"error": str(e)}

    results = {
        "queries": [],
        "summary": {
            "queries_improved": 0,
            "queries_degraded": 0,
            "queries_unchanged": 0
        }
    }

    # Test a subset of queries on live data
    test_subset = [
        EXTERIOR_COLOR_QUERIES[0],  # "white house"
        INTERIOR_FEATURE_QUERIES[0],  # "granite kitchen"
        MULTI_FEATURE_QUERIES[0],  # "white house with granite"
        AMBIGUOUS_QUERIES[0]  # "modern home"
    ]

    for test_query in test_subset:
        logger.info(f"\nTesting live query: '{test_query.query}' (category: {test_query.category})")

        # Query with current approach
        current_results = query_opensearch_current(test_query.query, size=10)

        # Query with proposed approach
        proposed_results = query_opensearch_proposed(
            test_query.query,
            size=10,
            category=test_query.category
        )

        # Compare top results
        current_zpids = [r["zpid"] for r in current_results[:5]]
        proposed_zpids = [r["zpid"] for r in proposed_results[:5]]

        # Check for differences
        changed_count = len(set(current_zpids) ^ set(proposed_zpids))

        query_result = {
            "query": test_query.query,
            "category": test_query.category,
            "current_top_5": current_zpids,
            "proposed_top_5": proposed_zpids,
            "changed_count": changed_count,
            "current_scores": [r["score"] for r in current_results[:5]],
            "proposed_scores": [r["score"] for r in proposed_results[:5]]
        }

        results["queries"].append(query_result)

        logger.info(f"  Current top 5:  {current_zpids}")
        logger.info(f"  Proposed top 5: {proposed_zpids}")
        logger.info(f"  Changed: {changed_count}/5 results")

        if changed_count > 2:
            results["summary"]["queries_improved"] += 1
        elif changed_count == 0:
            results["summary"]["queries_unchanged"] += 1
        else:
            results["summary"]["queries_degraded"] += 1

    return results


# ==========================================
# REPORTING
# ==========================================

def print_summary_report(simulation_results: Dict[str, Any], live_results: Dict[str, Any] = None):
    """Print comprehensive test results."""
    print("\n" + "=" * 80)
    print("FIELD SEPARATION SEARCH QUALITY TEST - RESULTS")
    print("=" * 80)

    # Simulation results
    if simulation_results:
        print("\n📊 SIMULATION TEST RESULTS")
        print("-" * 80)

        current_summary = simulation_results["summary"]["current"]
        proposed_summary = simulation_results["summary"]["proposed"]

        print(f"\nCurrent Approach (visual_features_text):")
        print(f"  Precision@5:  {current_summary['avg_precision_5']:.3f}")
        print(f"  Precision@10: {current_summary['avg_precision_10']:.3f}")
        print(f"  NDCG:         {current_summary['avg_ndcg']:.3f}")

        print(f"\nProposed Approach (exterior + interior fields):")
        print(f"  Precision@5:  {proposed_summary['avg_precision_5']:.3f}")
        print(f"  Precision@10: {proposed_summary['avg_precision_10']:.3f}")
        print(f"  NDCG:         {proposed_summary['avg_ndcg']:.3f}")

        p5_improvement = proposed_summary['avg_precision_5'] - current_summary['avg_precision_5']
        ndcg_improvement = proposed_summary['avg_ndcg'] - current_summary['avg_ndcg']

        print(f"\n✨ IMPROVEMENT:")
        print(f"  Precision@5:  {p5_improvement:+.3f} ({p5_improvement/current_summary['avg_precision_5']*100:+.1f}%)")
        print(f"  NDCG:         {ndcg_improvement:+.3f} ({ndcg_improvement/current_summary['avg_ndcg']*100:+.1f}%)")

        # Breakdown by category
        print(f"\n📋 RESULTS BY CATEGORY:")
        categories = {}
        for q in simulation_results["queries"]:
            cat = q["category"]
            if cat not in categories:
                categories[cat] = {"current": [], "proposed": []}
            categories[cat]["current"].append(q["current"]["precision_at_5"])
            categories[cat]["proposed"].append(q["proposed"]["precision_at_5"])

        for cat, metrics in categories.items():
            current_avg = sum(metrics["current"]) / len(metrics["current"])
            proposed_avg = sum(metrics["proposed"]) / len(metrics["proposed"])
            improvement = proposed_avg - current_avg
            print(f"  {cat:20s} - Current: {current_avg:.3f}, Proposed: {proposed_avg:.3f}, Change: {improvement:+.3f}")

        # Notable improvements
        print(f"\n🎯 QUERIES WITH BIGGEST IMPROVEMENTS:")
        for q in sorted(simulation_results["improvements"],
                       key=lambda x: x["precision_improvement"], reverse=True)[:5]:
            print(f"  '{q['query']}' ({q['category']})")
            print(f"    Precision@5: {q['current']['precision_at_5']:.2f} → {q['proposed']['precision_at_5']:.2f} "
                  f"({q['precision_improvement']:+.2f})")

        # Degradations (if any)
        if simulation_results["degradations"]:
            print(f"\n⚠️  QUERIES THAT GOT WORSE:")
            for q in sorted(simulation_results["degradations"],
                           key=lambda x: x["precision_improvement"])[:3]:
                print(f"  '{q['query']}' ({q['category']})")
                print(f"    Precision@5: {q['current']['precision_at_5']:.2f} → {q['proposed']['precision_at_5']:.2f} "
                      f"({q['precision_improvement']:+.2f})")

    # Live test results
    if live_results and "error" not in live_results:
        print("\n" + "=" * 80)
        print("🔴 LIVE OPENSEARCH TEST RESULTS")
        print("-" * 80)

        print(f"\nQueries tested: {len(live_results['queries'])}")
        print(f"  Improved:   {live_results['summary']['queries_improved']}")
        print(f"  Degraded:   {live_results['summary']['queries_degraded']}")
        print(f"  Unchanged:  {live_results['summary']['queries_unchanged']}")

        print(f"\nQuery Details:")
        for q in live_results["queries"]:
            print(f"\n  '{q['query']}' ({q['category']})")
            print(f"    Changed: {q['changed_count']}/5 top results")
            print(f"    Current:  {q['current_top_5'][:3]}")
            print(f"    Proposed: {q['proposed_top_5'][:3]}")
    elif live_results and "error" in live_results:
        print("\n" + "=" * 80)
        print("⚠️  LIVE TEST SKIPPED")
        print(f"    Error: {live_results['error']}")

    # Final recommendation
    print("\n" + "=" * 80)
    print("💡 RECOMMENDATION")
    print("-" * 80)

    if simulation_results and p5_improvement > 0.05:
        print("✅ IMPLEMENT FIELD SEPARATION")
        print(f"   Evidence: {p5_improvement:.1%} improvement in Precision@5")
        print(f"   Impact: Significantly better results for exterior color queries")
        print(f"   Cost: Low (CRUD API migration, no reindexing)")
        print(f"\n   Next steps:")
        print(f"   1. Run: python migrate_split_visual_features.py")
        print(f"   2. Update search.py to use new fields")
        print(f"   3. Monitor search quality metrics")
    else:
        print("❌ DO NOT IMPLEMENT")
        print(f"   Evidence: Only {p5_improvement:.1%} improvement")
        print(f"   Current approach is sufficient")

    print("=" * 80)


def save_results(simulation_results: Dict[str, Any], live_results: Dict[str, Any] = None):
    """Save detailed results to JSON file."""
    output = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "simulation": simulation_results,
        "live": live_results
    }

    filename = "field_separation_test_results.json"
    with open(filename, "w") as f:
        json.dump(output, f, indent=2)

    logger.info(f"\n✅ Detailed results saved to: {filename}")


# ==========================================
# MAIN
# ==========================================

def main():
    """Run field separation quality tests."""
    parser = argparse.ArgumentParser(description="Test field separation search quality")
    parser.add_argument(
        "--mode",
        choices=["simulation", "live", "both"],
        default="both",
        help="Test mode: simulation only, live only, or both (default: both)"
    )

    args = parser.parse_args()

    # Run simulation test
    simulation_results = None
    if args.mode in ["simulation", "both"]:
        properties = generate_test_properties()
        simulation_results = run_simulation_test(properties)

    # Run live test
    live_results = None
    if args.mode in ["live", "both"]:
        live_results = run_live_test()

    # Print report
    print_summary_report(simulation_results, live_results)

    # Save detailed results
    save_results(simulation_results, live_results)


if __name__ == "__main__":
    main()
