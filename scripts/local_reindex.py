#!/usr/bin/env python3
"""
Local re-indexing script - much faster than Lambda
Utilizes all CPU cores on your M3 Pro for parallel processing
"""

import json
import sys
import os
from multiprocessing import Pool, cpu_count
from functools import partial
import boto3

# Set environment variables
os.environ["OS_HOST"] = "search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com"
os.environ["OS_INDEX"] = "listings"
os.environ["USE_REKOGNITION"] = "false"
os.environ["MAX_IMAGES"] = "3"

from common import os_client, bulk_upsert
from upload_listings import process_listing_to_document

def process_batch(listings_batch):
    """Process a batch of listings"""
    documents = []
    for listing in listings_batch:
        try:
            doc = process_listing_to_document(listing)
            if doc:
                documents.append(doc)
                print(f"✓ Processed zpid={listing.get('zpid')}")
        except Exception as e:
            print(f"✗ Failed zpid={listing.get('zpid')}: {e}")
    
    # Bulk upsert to OpenSearch
    if documents:
        bulk_upsert(documents)
        print(f"✓ Uploaded batch of {len(documents)} listings")
    
    return len(documents)

def main():
    # Download listings from S3
    print("Downloading listings from S3...")
    s3 = boto3.client('s3', region_name='us-east-1')
    obj = s3.get_object(Bucket='demo-hearth-data', Key='murray_listings.json')
    data = json.loads(obj['Body'].read())
    listings = data.get('listings', [])
    
    print(f"Found {len(listings)} listings")
    print(f"Using {cpu_count()} CPU cores for parallel processing")
    
    # Split into batches (10 listings per batch)
    batch_size = 10
    batches = [listings[i:i+batch_size] for i in range(0, len(listings), batch_size)]
    
    print(f"Processing {len(batches)} batches in parallel...")
    
    # Use half of CPU cores to avoid overload
    num_workers = max(1, cpu_count() // 2)
    
    with Pool(processes=num_workers) as pool:
        results = pool.map(process_batch, batches)
    
    total = sum(results)
    print(f"\n✅ Completed! Processed {total}/{len(listings)} listings")

if __name__ == "__main__":
    main()
