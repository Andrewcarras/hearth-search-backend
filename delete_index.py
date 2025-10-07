#!/usr/bin/env python3
"""
One-time script to delete the old OpenSearch index so it can be recreated with new mappings.
"""
import os
os.environ['OS_HOST'] = 'search-hearth-opensearch-ojqv6e2t2ohe5bvtmq64xdjsve.us-east-1.es.amazonaws.com'
os.environ['OS_INDEX'] = 'listings'
os.environ['AWS_REGION'] = 'us-east-1'

from common import os_client, OS_INDEX

try:
    if os_client.indices.exists(OS_INDEX):
        print(f"Deleting index '{OS_INDEX}'...")
        os_client.indices.delete(index=OS_INDEX)
        print(f"✓ Index '{OS_INDEX}' deleted successfully")
    else:
        print(f"Index '{OS_INDEX}' does not exist (already deleted or never created)")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
