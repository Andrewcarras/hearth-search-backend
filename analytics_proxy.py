"""
Analytics Proxy Lambda
Provides server-side DynamoDB access for analytics dashboard.
"""

import json
import boto3
import os
from decimal import Decimal

# Initialize DynamoDB client
dynamodb = boto3.client('dynamodb', region_name='us-east-1')
TABLE_NAME = 'SearchQueryLogs'


def decimal_to_float(obj):
    """Convert Decimal to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def dynamodb_to_python(item):
    """Convert DynamoDB format to Python types"""
    result = {}
    for key, value in item.items():
        result[key] = convert_dynamodb_value(value)
    return result


def convert_dynamodb_value(value):
    """Convert DynamoDB value to Python type"""
    if 'S' in value:
        return value['S']
    elif 'N' in value:
        num = float(value['N'])
        return int(num) if num.is_integer() else num
    elif 'BOOL' in value:
        return value['BOOL']
    elif 'NULL' in value:
        return None
    elif 'M' in value:
        return {k: convert_dynamodb_value(v) for k, v in value['M'].items()}
    elif 'L' in value:
        return [convert_dynamodb_value(item) for item in value['L']]
    elif 'SS' in value:
        return list(value['SS'])
    elif 'NS' in value:
        return [float(n) for n in value['NS']]
    return value


def handler(event, context):
    """
    Lambda handler for analytics proxy.

    Endpoints:
        GET /analytics/searches?limit=100  - Get recent searches
        GET /analytics/search/{query_id}   - Get specific search
    """
    # Only set Content-Type header (CORS handled by function URL config)
    headers = {
        'Content-Type': 'application/json'
    }

    # Handle OPTIONS preflight - function URL CORS will handle headers
    if event.get('httpMethod') == 'OPTIONS' or event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {
            'statusCode': 200,
            'body': ''
        }

    try:
        # Parse request
        http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        raw_path = event.get('rawPath') or event.get('path', '/')
        query_params = event.get('queryStringParameters') or {}

        # For function URLs, path is in rawPath
        path = raw_path

        # Route based on path
        if path == '/analytics/searches' or path == '/searches' or path == '/':
            # Get recent searches
            limit = int(query_params.get('limit', 100))

            params = {
                'TableName': TABLE_NAME,
                'Limit': min(limit, 500)  # Cap at 500
            }

            response = dynamodb.scan(**params)

            # Convert items
            items = [dynamodb_to_python(item) for item in response.get('Items', [])]

            # Sort by timestamp descending
            items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'ok': True,
                    'count': len(items),
                    'items': items
                }, default=str)
            }

        elif '/analytics/search/' in path or '/search/' in path:
            # Get specific search by query_id
            # Extract query_id from path
            query_id = path.split('/')[-1]

            if not query_id:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': 'Missing query_id'})
                }

            # Scan for the query_id (since we don't have timestamp)
            params = {
                'TableName': TABLE_NAME,
                'FilterExpression': 'query_id = :qid',
                'ExpressionAttributeValues': {
                    ':qid': {'S': query_id}
                },
                'Limit': 1
            }

            response = dynamodb.scan(**params)

            if not response.get('Items'):
                return {
                    'statusCode': 404,
                    'headers': headers,
                    'body': json.dumps({'error': 'Search not found'})
                }

            item = dynamodb_to_python(response['Items'][0])

            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'ok': True,
                    'item': item
                }, default=str)
            }

        else:
            # Unknown endpoint
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': f'Unknown endpoint: {path}'})
            }

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'error': str(e),
                'type': type(e).__name__
            })
        }
