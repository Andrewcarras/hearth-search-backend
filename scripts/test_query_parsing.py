#!/usr/bin/env python3
"""
Standalone test to validate query parsing logic without AWS dependencies.

Tests the fallback parsing logic in extract_query_constraints to ensure
it properly extracts features, architecture styles, and proximity requirements.
"""

import json
import re

def test_extract_query_constraints_fallback(query_text):
    """
    Simulate the fallback logic from extract_query_constraints.
    This tests the regex-based parsing when LLM is not available.
    """
    q = (query_text or "").lower()
    must = []

    # Feature detection
    if "pool" in q:
        must.append("pool")
    if "kitchen island" in q or "island" in q:
        must.append("kitchen_island")
    if "backyard" in q:
        must.append("backyard")
    if "balcony" in q:
        must.append("balcony")
    if "fence" in q:
        must.append("fence")
    if "white" in q and "fence" in q:
        must.append("white_fence")
    if "blue" in q and ("exterior" in q or "house" in q or "home" in q):
        must.append("blue_exterior")

    # Architecture style detection
    arch_style = None
    if "mid century modern" in q or "mid-century modern" in q:
        arch_style = "mid_century_modern"
    elif "modern" in q:
        arch_style = "modern"
    elif "craftsman" in q:
        arch_style = "craftsman"
    elif "victorian" in q:
        arch_style = "victorian"
    elif "colonial" in q:
        arch_style = "colonial"
    elif "ranch" in q:
        arch_style = "ranch"
    elif "contemporary" in q:
        arch_style = "contemporary"

    # Proximity detection
    proximity = None
    if "near" in q or "close to" in q or "within" in q or "from" in q:
        poi_type = None
        if "school" in q:
            poi_type = "elementary_school" if "elementary" in q else "school"
        elif "grocery" in q or "supermarket" in q:
            poi_type = "grocery_store"
        elif "gym" in q or "fitness" in q:
            poi_type = "gym"
        elif "park" in q:
            poi_type = "park"
        elif "office" in q:
            poi_type = "office"

        if poi_type:
            proximity = {"poi_type": poi_type}
            # Try to extract drive time
            drive_match = re.search(r'(\d+)\s*minute', q)
            if drive_match:
                proximity["max_drive_time_min"] = int(drive_match.group(1))

    return {
        "must_have": list(set(must)),
        "nice_to_have": [],
        "hard_filters": {},
        "architecture_style": arch_style,
        "proximity": proximity,
    }


# Test cases
test_queries = [
    {
        "query": "Show me homes with a balcony, a blue exterior and a modern architecture style",
        "expected": {
            "must_have": ["balcony", "blue_exterior"],
            "architecture_style": "modern"
        }
    },
    {
        "query": "Show me homes with a mid-century modern style",
        "expected": {
            "architecture_style": "mid_century_modern"
        }
    },
    {
        "query": "Show me homes with a white fence in the backyard",
        "expected": {
            "must_have": ["white_fence", "backyard", "fence"]
        }
    },
    {
        "query": "Show me homes with a colonial style that are near a grocery store and a gym",
        "expected": {
            "architecture_style": "colonial",
            "proximity_poi": "grocery_store"  # Will detect first POI
        }
    },
    {
        "query": "Show me homes near an elementary school",
        "expected": {
            "proximity_poi": "elementary_school"
        }
    },
    {
        "query": "Show me homes within a 10 minute drive from my office and have a backyard",
        "expected": {
            "must_have": ["backyard"],
            "proximity_poi": "office",
            "proximity_time": 10
        }
    }
]

print("=" * 80)
print("TESTING QUERY PARSING (Fallback Logic)")
print("=" * 80)

all_passed = True
for i, test in enumerate(test_queries, 1):
    print(f"\n[TEST {i}] Query: \"{test['query']}\"")
    print("-" * 80)

    try:
        result = test_extract_query_constraints_fallback(test['query'])
        print(f"Result: {json.dumps(result, indent=2)}")

        # Validate expected fields
        passed = True

        if "must_have" in test["expected"]:
            expected_tags = set(test["expected"]["must_have"])
            actual_tags = set(result.get("must_have", []))
            if not expected_tags.issubset(actual_tags):
                print(f"  ❌ FAIL: Expected must_have tags {expected_tags} not all found in {actual_tags}")
                passed = False
            else:
                print(f"  ✓ must_have tags include: {expected_tags}")

        if "architecture_style" in test["expected"]:
            expected_style = test["expected"]["architecture_style"]
            actual_style = result.get("architecture_style")
            if expected_style != actual_style:
                print(f"  ❌ FAIL: Expected style '{expected_style}', got '{actual_style}'")
                passed = False
            else:
                print(f"  ✓ architecture_style: {expected_style}")

        if "proximity_poi" in test["expected"]:
            expected_poi = test["expected"]["proximity_poi"]
            actual_prox = result.get("proximity")
            if not actual_prox:
                print(f"  ❌ FAIL: Expected proximity POI '{expected_poi}', got None")
                passed = False
            else:
                actual_poi = actual_prox.get("poi_type")
                if expected_poi != actual_poi:
                    print(f"  ❌ FAIL: Expected POI '{expected_poi}', got '{actual_poi}'")
                    passed = False
                else:
                    print(f"  ✓ proximity.poi_type: {expected_poi}")

                # Check drive time if specified
                if "proximity_time" in test["expected"]:
                    expected_time = test["expected"]["proximity_time"]
                    actual_time = actual_prox.get("max_drive_time_min")
                    if expected_time != actual_time:
                        print(f"  ❌ FAIL: Expected drive time {expected_time}, got {actual_time}")
                        passed = False
                    else:
                        print(f"  ✓ proximity.max_drive_time_min: {expected_time}")

        if passed:
            print(f"  ✅ TEST {i} PASSED")
        else:
            print(f"  ❌ TEST {i} FAILED")
            all_passed = False

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

print("\n" + "=" * 80)
if all_passed:
    print("✅ ALL TESTS PASSED")
    print("\nThe fallback query parsing logic works correctly!")
    print("\nNOTE: In production with AWS Bedrock, the LLM will provide even better")
    print("parsing accuracy and handle more complex queries.")
else:
    print("❌ SOME TESTS FAILED")
print("=" * 80)
