#!/usr/bin/env python3
"""
Test Claude's architectural style classification capabilities.

Uses real property images from OpenSearch to test:
1. Can Claude distinguish between 60+ architectural styles?
2. What's the accuracy for common vs. rare styles?
3. How confident is Claude in its classifications?

Usage:
    python test_architecture_classification.py
"""

import json
import sys
import os
import time
from collections import defaultdict

import boto3
import requests
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# AWS configuration
REGION = 'us-east-1'
OS_HOST = 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com'
OS_INDEX = 'listings-v2'

# Initialize OpenSearch client
def get_opensearch_client():
    session = boto3.Session()
    credentials = session.get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        REGION,
        'es',
        session_token=credentials.token
    )

    return OpenSearch(
        hosts=[{'host': OS_HOST, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30
    )


# Test configuration with expanded styles
EXPANDED_STYLE_LIST = [
    # Tier 1: High confidence expected (30 styles)
    "modern", "contemporary", "mid_century_modern", "craftsman",
    "arts_and_crafts", "victorian", "colonial", "ranch", "cape_cod",
    "mediterranean", "spanish_colonial_revival", "tudor", "farmhouse",
    "cottage", "bungalow", "industrial", "transitional", "minimalist",
    "prairie_style", "pueblo_revival", "mission_revival", "log_cabin",
    "a_frame", "split_level", "greek_revival", "georgian", "federal",
    "art_deco", "bauhaus", "international_style",

    # Tier 2: Medium confidence expected (30 styles)
    "victorian_queen_anne", "victorian_italianate", "victorian_gothic_revival",
    "victorian_second_empire", "victorian_romanesque_revival", "victorian_shingle_style",
    "craftsman_bungalow", "craftsman_foursquare", "craftsman_prairie_style",
    "colonial_revival", "colonial_saltbox", "colonial_dutch", "colonial_spanish",
    "mid_century_ranch", "mid_century_split_level", "usonian_organic",
    "contemporary_farmhouse", "modern_farmhouse", "rustic_modern",
    "spanish_hacienda", "tuscan_villa", "french_provincial", "french_country",
    "english_cottage", "tudor_revival", "gothic_revival", "romanesque_revival",
    "neoclassical", "beaux_arts", "postmodern"
]

# Create enhanced prompt
ENHANCED_VISION_PROMPT = f"""
Analyze this residential property exterior photo and identify the architectural style.

SUPPORTED STYLES ({len(EXPANDED_STYLE_LIST)} total):
{', '.join(EXPANDED_STYLE_LIST)}

CLASSIFICATION APPROACH:
1. First identify the BROAD style family (modern, victorian, colonial, craftsman, etc.)
2. Then attempt to identify the SPECIFIC sub-style if confident
3. Consider key visual features:
   - Roof type and pitch
   - Window style and placement
   - Decorative elements
   - Material (wood, brick, stucco, stone)
   - Symmetry vs asymmetry
   - Overall proportions
   - Historical period indicators

HONESTY REQUIRED:
- If you can confidently identify a specific style → use it
- If you can only identify the general family → use that
- If uncertain between styles → return top 2 candidates
- Include confidence score (0.0 to 1.0)

Return STRICT JSON:
{{
  "architecture_style": "primary_style_name",
  "confidence": 0.85,
  "alternative_styles": ["style2", "style3"],
  "reasoning": "Brief explanation of visual features that led to classification",
  "style_family": "broad_category",
  "key_features": ["feature1", "feature2", "feature3"]
}}

Examples:
- Turret, asymmetrical, decorative trim → victorian_queen_anne
- Low-pitched roof, exposed beams, overhanging eaves → craftsman_bungalow
- Flat roof, clean lines, glass walls → modern or contemporary
- Symmetrical, columns, classical → colonial_revival or neoclassical
- Stucco walls, red tile roof, arches → spanish_colonial_revival or mediterranean
"""


def get_test_properties(limit=20):
    """
    Fetch diverse properties from OpenSearch to test on.
    Try to get variety in descriptions to hopefully get variety in styles.
    """
    print(f"Fetching {limit} test properties from OpenSearch...")

    os_client = get_opensearch_client()

    # Known ZPIDs with specific styles from documentation/examples
    # These are guaranteed to exist and have different styles
    known_test_zpids = [
        "452249143",  # Appears in test data
        "2071441242", # Appears in feedback
        "2080387168", # Appears in test data
        "12886346",   # Appears in test data
        "448479405",  # Appears in test data
        "12874030",   # Appears in test data
        "2069879792", # Appears in test data
        "12854231",   # Appears in test data
        "12757610",   # Appears in test data
        "450456191",  # Appears in test data
    ]

    properties = []

    for zpid in known_test_zpids[:limit]:
        try:
            # Get specific property by ZPID
            response = os_client.get(
                index=OS_INDEX,
                id=zpid
            )

            source = response['_source']

            # Construct Zillow image URL
            image_url = f"https://photos.zillowstatic.com/fp/{zpid}-cc_ft_1536.jpg"

            properties.append({
                'zpid': zpid,
                'image_url': image_url,
                'description': source.get('description', '')[:200],
                'address': source.get('address', {}),
                'search_query': 'known_zpid'
            })

        except Exception as e:
            print(f"  Could not fetch ZPID {zpid}: {e}")
            continue

    # If we didn't get enough from known ZPIDs, search for more
    if len(properties) < limit:
        test_queries = [
            "modern house",
            "victorian home",
            "craftsman bungalow",
            "colonial house",
            "ranch style"
        ]

        seen_zpids = set([p['zpid'] for p in properties])

        for query in test_queries:
            if len(properties) >= limit:
                break

            try:
                response = os_client.search(
                    index=OS_INDEX,
                    body={
                        "query": {
                            "match": {
                                "description": query
                            }
                        },
                        "_source": ["zpid", "description", "address"],
                        "size": 5
                    }
                )

                for hit in response['hits']['hits']:
                    if len(properties) >= limit:
                        break

                    source = hit['_source']
                    zpid = source.get('zpid')

                    if zpid in seen_zpids:
                        continue

                    seen_zpids.add(zpid)

                    # Construct Zillow image URL
                    image_url = f"https://photos.zillowstatic.com/fp/{zpid}-cc_ft_1536.jpg"

                    properties.append({
                        'zpid': zpid,
                        'image_url': image_url,
                        'description': source.get('description', '')[:200],
                        'address': source.get('address', {}),
                        'search_query': query
                    })

            except Exception as e:
                print(f"  Error searching for '{query}': {e}")
                continue

    print(f"✓ Found {len(properties)} properties to test")
    return properties


def test_classification_on_property(property_data):
    """
    Test Claude's classification on a single property.
    """
    zpid = property_data['zpid']
    image_url = property_data['image_url']

    print(f"\n{'='*80}")
    print(f"Testing ZPID: {zpid}")
    print(f"Address: {property_data['address']}")
    print(f"Image: {image_url}")
    print(f"Description snippet: {property_data['description']}")
    print(f"{'='*80}")

    try:
        # Use your existing vision analysis function with enhanced prompt
        result = analyze_property_image_with_custom_prompt(
            image_url=image_url,
            custom_prompt=ENHANCED_VISION_PROMPT
        )

        if result and 'analysis' in result:
            analysis = result['analysis']

            print(f"\n🏛️  CLASSIFICATION RESULTS:")
            print(f"  Primary Style: {analysis.get('architecture_style', 'N/A')}")
            print(f"  Style Family: {analysis.get('style_family', 'N/A')}")
            print(f"  Confidence: {analysis.get('confidence', 0.0):.2f}")

            if analysis.get('alternative_styles'):
                print(f"  Alternatives: {', '.join(analysis['alternative_styles'])}")

            if analysis.get('reasoning'):
                print(f"  Reasoning: {analysis['reasoning']}")

            if analysis.get('key_features'):
                print(f"  Key Features: {', '.join(analysis['key_features'][:5])}")

            return {
                'zpid': zpid,
                'success': True,
                'style': analysis.get('architecture_style'),
                'confidence': analysis.get('confidence', 0.0),
                'style_family': analysis.get('style_family'),
                'alternatives': analysis.get('alternative_styles', []),
                'reasoning': analysis.get('reasoning', ''),
                'key_features': analysis.get('key_features', [])
            }
        else:
            print(f"  ❌ No analysis returned")
            return {'zpid': zpid, 'success': False, 'error': 'No analysis'}

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {'zpid': zpid, 'success': False, 'error': str(e)}


def analyze_property_image_with_custom_prompt(image_url, custom_prompt):
    """
    Modified version of analyze_property_image_comprehensive that uses custom prompt.
    """
    import boto3
    import json
    import base64
    import requests

    brt = boto3.client('bedrock-runtime', region_name='us-east-1')
    LLM_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

    # Download and encode image
    try:
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        image_data = base64.b64encode(resp.content).decode('utf-8')

        # Determine media type
        content_type = resp.headers.get('content-type', 'image/jpeg')
        if 'image/' not in content_type:
            content_type = 'image/jpeg'
    except Exception as e:
        print(f"    Error downloading image: {e}")
        return None

    # Build request
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "temperature": 0.3,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": content_type,
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": custom_prompt
                    }
                ]
            }
        ]
    }

    # Call Claude
    response = brt.invoke_model(
        modelId=LLM_MODEL_ID,
        body=json.dumps(payload)
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"].strip()

    # Parse JSON response
    try:
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text.replace("```json", "").replace("```", "").strip()
        elif text.startswith("```"):
            text = text.replace("```", "").strip()

        analysis = json.loads(text)

        return {
            "analysis": analysis,
            "embedding": None,
            "cost_usd": 0.001125  # Haiku vision cost
        }
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}")
        print(f"    Raw response: {text[:200]}")
        return None


def run_classification_test(num_properties=20):
    """
    Main test function.
    """
    print("\n" + "="*80)
    print("🏛️  ARCHITECTURAL STYLE CLASSIFICATION TEST")
    print("="*80)
    print(f"\nTesting Claude 3 Haiku's ability to classify {len(EXPANDED_STYLE_LIST)} architectural styles")
    print(f"Using {num_properties} real property images from your database\n")

    # Get test properties
    properties = get_test_properties(limit=num_properties)

    if not properties:
        print("❌ No properties found to test")
        return

    # Run tests
    results = []
    for i, prop in enumerate(properties, 1):
        print(f"\n{'#'*80}")
        print(f"TEST {i}/{len(properties)}")
        print(f"{'#'*80}")

        result = test_classification_on_property(prop)
        results.append(result)

        # Rate limiting
        time.sleep(2)

    # Analyze results
    print("\n\n" + "="*80)
    print("📊 TEST RESULTS SUMMARY")
    print("="*80)

    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]

    print(f"\n✅ Successful: {len(successful)}/{len(results)} ({len(successful)/len(results)*100:.1f}%)")
    print(f"❌ Failed: {len(failed)}/{len(results)}")

    if successful:
        # Style distribution
        style_counts = defaultdict(int)
        family_counts = defaultdict(int)
        confidence_scores = []

        for r in successful:
            style = r.get('style', 'unknown')
            family = r.get('style_family', 'unknown')
            conf = r.get('confidence', 0)

            style_counts[style] += 1
            family_counts[family] += 1
            confidence_scores.append(conf)

        print(f"\n🎯 STYLE DISTRIBUTION:")
        for style, count in sorted(style_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {style}: {count}")

        print(f"\n📊 STYLE FAMILIES:")
        for family, count in sorted(family_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {family}: {count}")

        if confidence_scores:
            avg_conf = sum(confidence_scores) / len(confidence_scores)
            min_conf = min(confidence_scores)
            max_conf = max(confidence_scores)

            print(f"\n🎲 CONFIDENCE SCORES:")
            print(f"  Average: {avg_conf:.2f}")
            print(f"  Min: {min_conf:.2f}")
            print(f"  Max: {max_conf:.2f}")

            high_conf = sum(1 for c in confidence_scores if c >= 0.8)
            med_conf = sum(1 for c in confidence_scores if 0.6 <= c < 0.8)
            low_conf = sum(1 for c in confidence_scores if c < 0.6)

            print(f"  High (≥0.8): {high_conf} ({high_conf/len(confidence_scores)*100:.1f}%)")
            print(f"  Medium (0.6-0.8): {med_conf} ({med_conf/len(confidence_scores)*100:.1f}%)")
            print(f"  Low (<0.6): {low_conf} ({low_conf/len(confidence_scores)*100:.1f}%)")

    # Save detailed results
    output_file = 'architecture_classification_test_results.json'
    with open(output_file, 'w') as f:
        json.dump({
            'test_config': {
                'num_properties': len(properties),
                'num_styles': len(EXPANDED_STYLE_LIST),
                'styles_tested': EXPANDED_STYLE_LIST
            },
            'summary': {
                'total': len(results),
                'successful': len(successful),
                'failed': len(failed),
                'success_rate': len(successful)/len(results) if results else 0
            },
            'results': results
        }, f, indent=2)

    print(f"\n💾 Detailed results saved to: {output_file}")

    print("\n" + "="*80)
    print("✓ TEST COMPLETE")
    print("="*80)


if __name__ == '__main__':
    try:
        run_classification_test(num_properties=15)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
