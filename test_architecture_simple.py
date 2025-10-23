#!/usr/bin/env python3
"""
Simple test: Use cached image URLs from DynamoDB to test Claude's classification.
"""

import json
import boto3
import time

# Get sample images from vision cache
dynamodb = boto3.client('dynamodb', region_name='us-east-1')
brt = boto3.client('bedrock-runtime', region_name='us-east-1')

print("🏛️  Quick Architectural Style Classification Test\n")
print("Fetching 10 cached images from DynamoDB...")

# Scan vision cache for actual working image URLs
response = dynamodb.scan(
    TableName='hearth-vision-cache',
    Limit=10
)

test_images = []
for item in response['Items']:
    url = item.get('image_url', {}).get('S', '')
    if url:
        test_images.append(url)

print(f"✓ Found {len(test_images)} images\n")

# Test prompt
PROMPT = """Identify the architectural style of this house exterior.

Choose from these common styles:
modern, contemporary, mid_century_modern, craftsman, arts_and_crafts,
victorian, colonial, ranch, mediterranean, spanish_colonial, tudor,
farmhouse, cottage, bungalow, cape_cod, split_level, traditional

Return JSON:
{"style": "style_name", "confidence": 0.85, "reasoning": "brief explanation"}
"""

results = []

for i, url in enumerate(test_images[:10], 1):  # Test 10 images
    print(f"\n{'='*70}")
    print(f"TEST {i}/10")
    print(f"{'='*70}")
    print(f"Image: {url[:80]}...")

    try:
        import requests
        import base64

        # Download image
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        image_data = base64.b64encode(resp.content).decode('utf-8')

        # Call Claude
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0.3,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": PROMPT
                    }
                ]
            }]
        }

        response = brt.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(payload)
        )

        result = json.loads(response["body"].read())
        text = result["content"][0]["text"].strip()

        # Parse response - handle non-JSON responses
        print(f"  Raw response: {text[:200]}")

        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        try:
            analysis = json.loads(text)
        except json.JSONDecodeError:
            # Claude sometimes doesn't return JSON, extract manually
            print(f"  ⚠️  Non-JSON response, skipping")
            continue

        print(f"\n🏛️  RESULT:")
        print(f"  Style: {analysis.get('style', 'N/A')}")
        print(f"  Confidence: {analysis.get('confidence', 0):.2f}")
        print(f"  Reasoning: {analysis.get('reasoning', 'N/A')}")

        results.append({
            'image_url': url,
            'style': analysis.get('style'),
            'confidence': analysis.get('confidence'),
            'reasoning': analysis.get('reasoning')
        })

        time.sleep(2)  # Rate limit

    except Exception as e:
        print(f"  ❌ Error: {e}")
        results.append({'image_url': url, 'error': str(e)})

print(f"\n\n{'='*70}")
print("📊 SUMMARY")
print(f"{'='*70}\n")

successful = [r for r in results if 'style' in r]
print(f"✅ Successful: {len(successful)}/{len(results)}")

if successful:
    styles = {}
    confidences = []

    for r in successful:
        style = r['style']
        conf = r['confidence']
        styles[style] = styles.get(style, 0) + 1
        confidences.append(conf)

    print(f"\nStyles detected:")
    for style, count in styles.items():
        print(f"  {style}: {count}")

    avg_conf = sum(confidences) / len(confidences)
    print(f"\nAverage confidence: {avg_conf:.2f}")

print(f"\n✓ Test complete!")
print(f"Cost: ~${len(successful) * 0.001125:.4f}\n")
