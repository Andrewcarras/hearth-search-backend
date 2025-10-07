#!/usr/bin/env python3
"""
Lambda function to delete and recreate the OpenSearch index with correct mapping.

This fixes the critical bug where the index was created with space_type="cosinesimil" (typo)
instead of "cosinesimilarity", which causes all documents with zero vectors to fail indexing.
"""

import json
from common import os_client, OS_INDEX, create_index_if_needed

def handler(event, context):
    """Delete and recreate the OpenSearch index."""

    results = {}

    # 1. Check if index exists
    try:
        exists = os_client.indices.exists(index=OS_INDEX)
        results['index_existed'] = exists
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to check index: {e}'})
        }

    # 2. Delete if exists
    if exists:
        try:
            response = os_client.indices.delete(index=OS_INDEX)
            results['deleted'] = True
            results['delete_response'] = response
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': f'Failed to delete index: {e}', 'results': results})
            }
    else:
        results['deleted'] = False

    # 3. Recreate with correct mapping
    try:
        create_index_if_needed()
        results['created'] = True

        # Verify the mapping
        mapping = os_client.indices.get_mapping(index=OS_INDEX)
        vector_text_mapping = mapping[OS_INDEX]['mappings']['properties']['vector_text']
        vector_image_mapping = mapping[OS_INDEX]['mappings']['properties']['vector_image']

        results['vector_text_space_type'] = vector_text_mapping['method']['space_type']
        results['vector_image_space_type'] = vector_image_mapping['method']['space_type']

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to create index: {e}', 'results': results})
        }

    return {
        'statusCode': 200,
        'body': json.dumps({
            'ok': True,
            'message': 'Index recreated successfully',
            'results': results
        }, indent=2)
    }
