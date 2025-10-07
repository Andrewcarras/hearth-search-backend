#!/usr/bin/env python3
"""
Lambda function to debug the OpenSearch index.
"""

import json
from common import os_client, OS_INDEX

def handler(event, context):
    """Debug Lambda to inspect OpenSearch index."""
    results = {}

    # 1. Check if index exists
    try:
        exists = os_client.indices.exists(index=OS_INDEX)
        results['index_exists'] = exists
        if not exists:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Index does not exist', 'results': results})
            }
    except Exception as e:
        results['index_check_error'] = str(e)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to check index: {e}', 'results': results})
        }

    # 2. Get document count
    try:
        stats = os_client.indices.stats(index=OS_INDEX)
        results['total_docs'] = stats['_all']['primaries']['docs']['count']
    except Exception as e:
        results['stats_error'] = str(e)

    # 3. Get sample documents
    try:
        response = os_client.search(
            index=OS_INDEX,
            body={
                "size": 3,
                "query": {"match_all": {}}
            }
        )
        hits = response.get('hits', {}).get('hits', [])
        results['sample_count'] = len(hits)
        results['samples'] = []

        for hit in hits:
            src = hit.get('_source', {})
            vec_text = src.get('vector_text', [])
            vec_img = src.get('vector_image', [])

            sample = {
                'id': hit['_id'],
                'address': src.get('address'),
                'city': src.get('city'),
                'state': src.get('state'),
                'price': src.get('price'),
                'beds': src.get('beds'),
                'baths': src.get('baths'),
                'has_valid_embeddings': src.get('has_valid_embeddings'),
                'has_description': src.get('has_description'),
                'description_length': len(src.get('description', '')),
                'feature_tags_count': len(src.get('feature_tags', [])),
                'image_tags_count': len(src.get('image_tags', [])),
                'vector_text_dims': len(vec_text) if vec_text else 0,
                'vector_image_dims': len(vec_img) if vec_img else 0,
                'vector_text_all_zero': all(v == 0.0 for v in vec_text) if vec_text else None,
                'vector_image_all_zero': all(v == 0.0 for v in vec_img) if vec_img else None,
            }
            results['samples'].append(sample)
    except Exception as e:
        results['sample_error'] = str(e)

    # 4. Test filters
    filter_tests = {}

    # Test price > 0
    try:
        response = os_client.search(
            index=OS_INDEX,
            body={
                "size": 0,  # Just get count
                "query": {
                    "bool": {
                        "filter": [{"range": {"price": {"gt": 0}}}]
                    }
                }
            }
        )
        filter_tests['price_gt_0'] = response['hits']['total']['value']
    except Exception as e:
        filter_tests['price_gt_0_error'] = str(e)

    # Test has_valid_embeddings
    try:
        response = os_client.search(
            index=OS_INDEX,
            body={
                "size": 0,
                "query": {
                    "bool": {
                        "filter": [{"term": {"has_valid_embeddings": True}}]
                    }
                }
            }
        )
        filter_tests['has_valid_embeddings_true'] = response['hits']['total']['value']
    except Exception as e:
        filter_tests['has_valid_embeddings_error'] = str(e)

    # Test BM25 text search
    try:
        response = os_client.search(
            index=OS_INDEX,
            body={
                "size": 0,
                "query": {
                    "multi_match": {
                        "query": "house",
                        "fields": ["description", "llm_profile"]
                    }
                }
            }
        )
        filter_tests['bm25_house'] = response['hits']['total']['value']
    except Exception as e:
        filter_tests['bm25_error'] = str(e)

    results['filter_tests'] = filter_tests

    return {
        'statusCode': 200,
        'body': json.dumps(results, indent=2)
    }
