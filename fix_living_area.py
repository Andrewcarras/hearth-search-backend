#!/usr/bin/env python3
"""
Fix livingArea field in OpenSearch by updating from source Zillow data.

The livingArea field was incorrectly populated with lot size instead of house square footage.
This script reads the correct livingArea from the source JSON files and updates via CRUD API.
"""

import json
import sys
import time
import requests
from typing import Dict, List

# CRUD API endpoint
CRUD_API = "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod"
INDEX = "listings-v2"

def load_zillow_data(filepath: str) -> Dict[str, dict]:
    """Load Zillow JSON and create zpid -> property mapping."""
    print(f"Loading {filepath}...")
    with open(filepath) as f:
        data = json.load(f)

    mapping = {}
    for prop in data:
        zpid = str(prop.get('zpid'))
        living_area = prop.get('livingArea') or prop.get('livingAreaValue')
        lot_size = prop.get('lotSize') or prop.get('lotAreaValue') or prop.get('acreage') or prop.get('lotArea')

        mapping[zpid] = {
            'livingArea': living_area,
            'lotSize': lot_size
        }

    print(f"Loaded {len(mapping):,} properties")
    return mapping


def update_property(zpid: str, living_area: float, lot_size: float) -> bool:
    """Update a single property via CRUD API."""
    url = f"{CRUD_API}/listings/{zpid}?index={INDEX}"

    payload = {
        "updates": {
            "livingArea": living_area,
            "lotSize": lot_size
        },
        "options": {
            "preserve_embeddings": True
        }
    }

    try:
        response = requests.patch(url, json=payload, timeout=30)
        if response.status_code == 200:
            return True
        else:
            print(f"  ❌ Failed to update {zpid}: {response.status_code} - {response.text[:100]}")
            return False
    except Exception as e:
        print(f"  ❌ Error updating {zpid}: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_living_area.py <zillow_json_file> [batch_size]")
        print("Example: python fix_living_area.py slc_listings.json 100")
        sys.exit(1)

    filepath = sys.argv[1]
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    # Load source data
    zillow_data = load_zillow_data(filepath)

    print(f"\nUpdating {len(zillow_data):,} properties in batches of {batch_size}...")
    print(f"Target index: {INDEX}")
    print(f"CRUD API: {CRUD_API}")
    print()

    updated = 0
    failed = 0
    skipped = 0

    for i, (zpid, data) in enumerate(zillow_data.items(), 1):
        living_area = data['livingArea']
        lot_size = data['lotSize']

        # Skip if no living area data
        if living_area is None:
            skipped += 1
            continue

        # Update property
        if update_property(zpid, living_area, lot_size):
            updated += 1
            if updated % 10 == 0:
                print(f"✓ Updated {updated:,} properties ({failed} failed, {skipped} skipped)")
        else:
            failed += 1

        # Rate limiting - be gentle on API
        if i % batch_size == 0:
            print(f"\n📊 Progress: {i:,}/{len(zillow_data):,} processed")
            print(f"   ✓ {updated:,} updated | ❌ {failed} failed | ⊘ {skipped} skipped")
            print(f"   Pausing 2 seconds...\n")
            time.sleep(2)
        else:
            time.sleep(0.1)  # 100ms between requests

    print("\n" + "="*60)
    print("FINAL RESULTS:")
    print(f"  ✓ Updated: {updated:,}")
    print(f"  ❌ Failed: {failed}")
    print(f"  ⊘ Skipped (no data): {skipped}")
    print(f"  📝 Total processed: {len(zillow_data):,}")
    print("="*60)


if __name__ == "__main__":
    main()
