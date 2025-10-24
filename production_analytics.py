import json
import boto3
import time
import uuid
from decimal import Decimal
from datetime import datetime, timedelta

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Table references
search_logs_table = dynamodb.Table('hearth-production-search-logs')
feedback_table = dynamodb.Table('hearth-production-feedback')
sessions_table = dynamodb.Table('hearth-production-sessions')
issues_table = dynamodb.Table('hearth-production-issues')

# Constants
SESSION_TIMEOUT_MINUTES = 30

def decimal_default(obj):
    """Convert Decimal to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def convert_floats_to_decimal(obj):
    """Recursively convert floats to Decimal for DynamoDB"""
    if isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_floats_to_decimal(value) for key, value in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))
    return obj

def lambda_handler(event, context):
    """Main Lambda handler for production analytics"""

    print(f"Event: {json.dumps(event)}")

    # CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }

    # Get path and method (support both API Gateway v1 and v2)
    path = event.get('rawPath') or event.get('path', '')
    method = event.get('requestContext', {}).get('http', {}).get('method') or event.get('httpMethod', '')

    # Handle OPTIONS preflight
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'message': 'OK'})
        }

    try:
        # Route to appropriate handler
        if path == '/production/log-search' and method == 'POST':
            return log_search(event, headers)

        elif path == '/production/log-feedback' and method == 'POST':
            return log_feedback(event, headers)

        elif path == '/production/log-search-quality' and method == 'POST':
            return log_search_quality(event, headers)

        elif path == '/production/report-issue' and method == 'POST':
            return report_issue(event, headers)

        elif path == '/production/update-session' and method == 'POST':
            return update_session(event, headers)

        elif path == '/production/end-session' and method == 'POST':
            return end_session(event, headers)

        elif path == '/production/analytics/overview' and method == 'GET':
            return get_overview(event, headers)

        elif path == '/production/analytics/searches' and method == 'GET':
            return get_searches(event, headers)

        elif path == '/production/analytics/feedback' and method == 'GET':
            return get_feedback(event, headers)

        elif path == '/production/analytics/sessions' and method == 'GET':
            return get_sessions(event, headers)

        elif path.startswith('/production/analytics/session/') and method == 'GET':
            session_id = path.split('/')[-1]
            return get_session_detail(session_id, headers)

        elif path == '/production/analytics/properties/top-clicked' and method == 'GET':
            return get_top_clicked_properties(event, headers)

        elif path == '/production/analytics/properties/top-rated' and method == 'GET':
            return get_top_rated_properties(event, headers)

        elif path == '/production/analytics/issues' and method == 'GET':
            return get_issues(event, headers)

        elif path.startswith('/production/analytics/issue/') and '/status' in path and method == 'POST':
            issue_id = path.split('/')[-2]
            return update_issue_status(issue_id, event, headers)

        elif path == '/production/analytics/export/feedback' and method == 'GET':
            return export_feedback(event, headers)

        elif path == '/production/analytics/export/searches' and method == 'GET':
            return export_searches(event, headers)

        elif path == '/production/analytics/searches-over-time' and method == 'GET':
            return get_searches_over_time(event, headers)

        elif path == '/production/analytics/feedback-summary' and method == 'GET':
            return get_feedback_summary(event, headers)

        elif path == '/production/analytics/recent-activity' and method == 'GET':
            return get_recent_activity(event, headers)

        elif path == '/production/analytics/search-quality' and method == 'GET':
            return get_search_quality(event, headers)

        elif path == '/production/analytics/top-queries' and method == 'GET':
            return get_top_queries(event, headers)

        elif path == '/production/analytics/recent-searches' and method == 'GET':
            return get_recent_searches(event, headers)

        elif path == '/production/analytics/feedback-details' and method == 'GET':
            return get_feedback_details(event, headers)

        elif path == '/production/analytics/all-feedback' and method == 'GET':
            return get_all_feedback(event, headers)

        elif path == '/production/analytics/user-journey' and method == 'GET':
            return get_user_journey(event, headers)

        elif path == '/production/analytics/properties' and method == 'GET':
            return get_properties_summary(event, headers)

        elif path == '/production/analytics/property-performance' and method == 'GET':
            return get_property_performance(event, headers)

        elif path == '/production/analytics/issues-summary' and method == 'GET':
            return get_issues_summary(event, headers)

        elif path == '/production/analytics/all-issues' and method == 'GET':
            return get_all_issues(event, headers)

        elif path == '/production/analytics/export-issues' and method == 'GET':
            return export_issues(event, headers)

        else:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'Not found'})
            }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }


def log_search(event, headers):
    """Log a search with full details"""
    body = json.loads(event.get('body', '{}'))

    # Generate IDs
    query_id = str(uuid.uuid4())
    timestamp = int(time.time() * 1000)

    # Calculate TTL (90 days from now)
    ttl = int((datetime.now() + timedelta(days=90)).timestamp())

    # Extract data
    session_id = body.get('session_id')
    search_query = body.get('search_query', '')

    # Device info
    user_agent = event.get('headers', {}).get('User-Agent', '')

    # IP address from CloudFront header
    ip_address = event.get('headers', {}).get('X-Forwarded-For', '').split(',')[0].strip()
    if not ip_address:
        ip_address = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')

    # Build item
    item = {
        'query_id': query_id,
        'session_id': session_id,
        'timestamp': timestamp,
        'search_query': search_query,
        'user_agent': user_agent,
        'screen_resolution': body.get('screen_resolution', ''),
        'viewport_size': body.get('viewport_size', ''),
        'device_type': body.get('device_type', 'unknown'),
        'ip_address': ip_address,
        'geographic_location': body.get('geographic_location', ''),

        # Results data
        'total_results': body.get('total_results', 0),
        'results_zpids': body.get('results_zpids', []),
        'result_scores': body.get('result_scores', []),
        'top_5_zpids': body.get('top_5_zpids', []),

        # Backend query details
        'sub_queries': body.get('sub_queries', []),
        'llm_success': body.get('llm_success', False),
        'fallback_used': body.get('fallback_used', False),
        'search_strategy': body.get('search_strategy', 'unknown'),
        'execution_time_ms': body.get('execution_time_ms', 0),
        'opensearch_time_ms': body.get('opensearch_time_ms', 0),
        'adaptive_k_values': body.get('adaptive_k_values', {}),
        'visual_ratio': body.get('visual_ratio', 0),
        'text_ratio': body.get('text_ratio', 0),
        'feature_context': body.get('feature_context', ''),

        # Filter usage
        'filters_applied': body.get('filters_applied', {}),
        'filters_used': body.get('filters_used', False),
        'filtered_count': body.get('filtered_count', 0),

        # User interaction
        'time_to_first_click': body.get('time_to_first_click', 0),
        'properties_clicked': body.get('properties_clicked', []),

        # Additional context
        'referrer': event.get('headers', {}).get('Referer', ''),
        'search_sequence_number': body.get('search_sequence_number', 1),
        'previous_query': body.get('previous_query', ''),

        'ttl': ttl
    }

    # Convert floats to Decimal for DynamoDB
    item = convert_floats_to_decimal(item)

    # Store in DynamoDB
    search_logs_table.put_item(Item=item)

    # Update session
    update_session_record(session_id, search_query, ip_address, user_agent, body.get('device_type'))

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'query_id': query_id,
            'session_id': session_id,
            'success': True
        })
    }


def log_feedback(event, headers):
    """Log property feedback"""
    body = json.loads(event.get('body', '{}'))

    # Generate ID
    feedback_id = str(uuid.uuid4())
    timestamp = int(time.time() * 1000)
    ttl = int((datetime.now() + timedelta(days=90)).timestamp())

    # IP address
    ip_address = event.get('headers', {}).get('X-Forwarded-For', '').split(',')[0].strip()
    if not ip_address:
        ip_address = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')

    # Build item
    item = {
        'feedback_id': feedback_id,
        'timestamp': timestamp,
        'session_id': body.get('session_id'),
        'query_id': body.get('query_id'),
        'search_query': body.get('search_query', ''),

        # Property details
        'zpid': body.get('zpid'),
        'property_rank': body.get('property_rank', 0),
        'property_score': Decimal(str(body.get('property_score', 0))),
        'property_address': body.get('property_address', ''),
        'property_price': body.get('property_price', 0),

        # Feedback data
        'rating': body.get('rating'),  # "thumbs_up" or "thumbs_down"
        'feedback_text': body.get('feedback_text', ''),
        'feedback_categories': body.get('feedback_categories', []),

        # Context
        'filters_active': body.get('filters_active', {}),
        'time_to_feedback': body.get('time_to_feedback', 0),

        # User info
        'user_agent': event.get('headers', {}).get('User-Agent', ''),
        'device_type': body.get('device_type', 'unknown'),
        'ip_address': ip_address,

        'ttl': ttl
    }

    # Convert floats to Decimal for DynamoDB
    item = convert_floats_to_decimal(item)

    # Store in DynamoDB
    feedback_table.put_item(Item=item)

    # Update session feedback count
    try:
        sessions_table.update_item(
            Key={'session_id': body.get('session_id'), 'session_start': body.get('session_start', timestamp)},
            UpdateExpression='SET total_feedback_submitted = if_not_exists(total_feedback_submitted, :zero) + :inc, last_activity = :now',
            ExpressionAttributeValues={':inc': 1, ':zero': 0, ':now': timestamp}
        )
    except Exception as e:
        print(f"Error updating session feedback count: {e}")

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'feedback_id': feedback_id,
            'success': True
        })
    }


def log_search_quality(event, headers):
    """Log search quality feedback"""
    body = json.loads(event.get('body', '{}'))

    # Generate ID
    quality_id = str(uuid.uuid4())
    timestamp = int(time.time() * 1000)
    ttl = int((datetime.now() + timedelta(days=90)).timestamp())

    # IP address
    ip_address = event.get('headers', {}).get('X-Forwarded-For', '').split(',')[0].strip()
    if not ip_address:
        ip_address = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')

    # Build item
    item = {
        'quality_id': quality_id,
        'timestamp': timestamp,
        'session_id': body.get('session_id'),
        'query_id': body.get('query_id'),
        'search_query': body.get('search_query', ''),

        # Rating and feedback
        'rating': body.get('rating', 0),  # 1-5 stars
        'feedback_text': body.get('feedback_text', ''),
        'feedback_categories': body.get('feedback_categories', []),

        # Search context
        'total_results': body.get('total_results', 0),
        'properties_viewed': body.get('properties_viewed', 0),
        'time_on_results': body.get('time_on_results', 0),
        'filters_active': body.get('filters_active', {}),

        # User info
        'user_agent': event.get('headers', {}).get('User-Agent', ''),
        'device_type': body.get('device_type', 'unknown'),
        'screen_resolution': body.get('screen_resolution', ''),
        'viewport_size': body.get('viewport_size', ''),
        'ip_address': ip_address,

        'ttl': ttl
    }

    # Convert floats to Decimal for DynamoDB
    item = convert_floats_to_decimal(item)

    # Store in DynamoDB - SearchQualityFeedback table
    search_quality_table = dynamodb.Table('SearchQualityFeedback')
    search_quality_table.put_item(Item=item)

    # Update session search quality count
    try:
        sessions_table.update_item(
            Key={'session_id': body.get('session_id'), 'session_start': body.get('session_start', timestamp)},
            UpdateExpression='SET total_search_quality_submitted = if_not_exists(total_search_quality_submitted, :zero) + :inc, last_activity = :now',
            ExpressionAttributeValues={':inc': 1, ':zero': 0, ':now': timestamp}
        )
    except Exception as e:
        print(f"Error updating session search quality count: {e}")

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'quality_id': quality_id,
            'success': True
        })
    }


def report_issue(event, headers):
    """Report a bug or issue"""
    body = json.loads(event.get('body', '{}'))

    # Generate ID
    issue_id = str(uuid.uuid4())
    timestamp = int(time.time() * 1000)
    ttl = int((datetime.now() + timedelta(days=180)).timestamp())

    # IP address
    ip_address = event.get('headers', {}).get('X-Forwarded-For', '').split(',')[0].strip()
    if not ip_address:
        ip_address = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')

    # Build item
    item = {
        'issue_id': issue_id,
        'timestamp': timestamp,
        'session_id': body.get('session_id'),
        'query_id': body.get('query_id', ''),

        # Issue details
        'issue_type': body.get('issue_type', 'other'),
        'description': body.get('description', ''),
        'severity': 'user_reported',
        'status': 'new',

        # Context
        'current_url': body.get('current_url', ''),
        'last_search_query': body.get('last_search_query', ''),
        'console_errors': body.get('console_errors', []),
        'browser_info': body.get('browser_info', {}),
        'ip_address': ip_address,

        # User info
        'user_agent': event.get('headers', {}).get('User-Agent', ''),
        'device_type': body.get('device_type', 'unknown'),

        'ttl': ttl
    }

    # Store in DynamoDB
    issues_table.put_item(Item=item)

    # Update session bug count
    try:
        sessions_table.update_item(
            Key={'session_id': body.get('session_id'), 'session_start': body.get('session_start', timestamp)},
            UpdateExpression='SET total_bug_reports = if_not_exists(total_bug_reports, :zero) + :inc, last_activity = :now',
            ExpressionAttributeValues={':inc': 1, ':zero': 0, ':now': timestamp}
        )
    except Exception as e:
        print(f"Error updating session bug count: {e}")

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'issue_id': issue_id,
            'success': True
        })
    }


def update_session(event, headers):
    """Update session activity timestamp"""
    body = json.loads(event.get('body', '{}'))

    session_id = body.get('session_id')
    timestamp = int(time.time() * 1000)

    try:
        sessions_table.update_item(
            Key={'session_id': session_id, 'session_start': body.get('session_start', timestamp)},
            UpdateExpression='SET last_activity = :now, is_active = :active',
            ExpressionAttributeValues={':now': timestamp, ':active': 'true'}
        )

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'session_active': True})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }


def end_session(event, headers):
    """Mark session as ended"""
    body = json.loads(event.get('body', '{}'))

    session_id = body.get('session_id')
    timestamp = int(time.time() * 1000)

    try:
        # Calculate duration
        session_start = body.get('session_start', timestamp)
        duration = (timestamp - session_start) / 1000 / 60  # minutes

        sessions_table.update_item(
            Key={'session_id': session_id, 'session_start': session_start},
            UpdateExpression='SET session_end = :end, session_duration = :duration, is_active = :active',
            ExpressionAttributeValues={
                ':end': timestamp,
                ':duration': Decimal(str(round(duration, 2))),
                ':active': 'false'
            }
        )

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'session_ended': True})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }


def update_session_record(session_id, search_query, ip_address, user_agent, device_type):
    """Update or create session record"""
    timestamp = int(time.time() * 1000)
    ttl = int((datetime.now() + timedelta(days=90)).timestamp())

    try:
        # Try to get existing session
        response = sessions_table.query(
            KeyConditionExpression='session_id = :sid',
            ExpressionAttributeValues={':sid': session_id},
            ScanIndexForward=False,
            Limit=1
        )

        if response['Items']:
            # Update existing session
            item = response['Items'][0]
            session_start = item['session_start']

            # Build update expression dynamically
            unique_queries = item.get('unique_queries', [])
            if search_query not in unique_queries:
                unique_queries.append(search_query)

            query_pattern = item.get('query_refinement_pattern', [])
            query_pattern.append(search_query)

            search_timestamps = item.get('search_timestamps', [])
            search_timestamps.append(timestamp)

            sessions_table.update_item(
                Key={'session_id': session_id, 'session_start': session_start},
                UpdateExpression='''SET
                    last_activity = :now,
                    total_searches = if_not_exists(total_searches, :zero) + :inc,
                    unique_queries = :uq,
                    query_refinement_pattern = :qrp,
                    search_timestamps = :st,
                    is_active = :active
                ''',
                ExpressionAttributeValues={
                    ':now': timestamp,
                    ':inc': 1,
                    ':zero': 0,
                    ':uq': unique_queries,
                    ':qrp': query_pattern,
                    ':st': search_timestamps,
                    ':active': 'true'
                }
            )
        else:
            # Create new session
            sessions_table.put_item(Item={
                'session_id': session_id,
                'session_start': timestamp,
                'session_end': 0,
                'session_duration': Decimal('0'),
                'is_active': 'true',
                'last_activity': timestamp,
                'total_searches': 1,
                'total_property_clicks': 0,
                'total_feedback_submitted': 0,
                'total_bug_reports': 0,
                'unique_queries': [search_query],
                'query_refinement_pattern': [search_query],
                'search_timestamps': [timestamp],
                'bounce_rate': False,
                'conversion_rate': Decimal('0'),
                'device_type': device_type or 'unknown',
                'user_agent': user_agent,
                'ip_address': ip_address,
                'geographic_location': '',
                'ttl': ttl
            })

    except Exception as e:
        print(f"Error updating session: {e}")


# Dashboard query endpoints

def get_overview(event, headers):
    """Get overview metrics"""
    # Get time range
    params = event.get('queryStringParameters', {}) or {}
    hours = int(params.get('hours', 24))

    cutoff_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

    # Query recent searches
    response = search_logs_table.scan(
        FilterExpression='#ts > :cutoff',
        ExpressionAttributeNames={'#ts': 'timestamp'},
        ExpressionAttributeValues={':cutoff': cutoff_time}
    )
    searches = response['Items']

    # Query recent feedback
    response = feedback_table.scan(
        FilterExpression='#ts > :cutoff',
        ExpressionAttributeNames={'#ts': 'timestamp'},
        ExpressionAttributeValues={':cutoff': cutoff_time}
    )
    feedbacks = response['Items']

    # Query recent issues
    response = issues_table.scan(
        FilterExpression='#ts > :cutoff',
        ExpressionAttributeNames={'#ts': 'timestamp'},
        ExpressionAttributeValues={':cutoff': cutoff_time}
    )
    issues = response['Items']

    # Query active sessions
    response = sessions_table.scan(
        FilterExpression='is_active = :active',
        ExpressionAttributeValues={':active': 'true'}
    )
    active_sessions = response['Items']

    # Calculate metrics
    total_searches = len(searches)
    total_feedback = len(feedbacks)
    total_issues = len(issues)
    thumbs_up = len([f for f in feedbacks if f.get('rating') == 'up'])
    thumbs_up_percent = (thumbs_up / total_feedback * 100) if total_feedback > 0 else 0

    # Top queries
    query_counts = {}
    for search in searches:
        query = search.get('search_query', '')
        query_counts[query] = query_counts.get(query, 0) + 1

    top_queries = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'total_searches': total_searches,
            'total_feedback': total_feedback,
            'total_issues': total_issues,
            'active_sessions': len(active_sessions),
            'thumbs_up_percent': round(thumbs_up_percent, 1),
            'top_queries': [{'query': q, 'count': c} for q, c in top_queries]
        }, default=decimal_default)
    }


def get_searches(event, headers):
    """Get search logs with pagination"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 50))

    # Scan with limit
    response = search_logs_table.scan(Limit=limit)

    items = response['Items']

    # Sort by timestamp descending
    items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'searches': items,
            'count': len(items)
        }, default=decimal_default)
    }


def get_feedback(event, headers):
    """Get feedback records with pagination"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 50))

    # Scan with limit
    response = feedback_table.scan(Limit=limit)

    items = response['Items']

    # Sort by timestamp descending
    items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'feedback': items,
            'count': len(items)
        }, default=decimal_default)
    }


def get_sessions(event, headers):
    """Get session list with pagination"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 50))

    # Scan with limit
    response = sessions_table.scan(Limit=limit)

    items = response['Items']

    # Sort by session_start descending
    items.sort(key=lambda x: x.get('session_start', 0), reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'sessions': items,
            'count': len(items)
        }, default=decimal_default)
    }


def get_session_detail(session_id, headers):
    """Get detailed session journey"""
    # Get session
    response = sessions_table.query(
        KeyConditionExpression='session_id = :sid',
        ExpressionAttributeValues={':sid': session_id}
    )

    if not response['Items']:
        return {
            'statusCode': 404,
            'headers': headers,
            'body': json.dumps({'error': 'Session not found'})
        }

    session = response['Items'][0]

    # Get all searches for this session
    response = search_logs_table.query(
        KeyConditionExpression='session_id = :sid',
        ExpressionAttributeValues={':sid': session_id}
    )
    searches = response['Items']

    # Get all feedback for this session
    response = feedback_table.query(
        IndexName='session_id-index',
        KeyConditionExpression='session_id = :sid',
        ExpressionAttributeValues={':sid': session_id}
    )
    feedbacks = response['Items']

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'session': session,
            'searches': searches,
            'feedback': feedbacks
        }, default=decimal_default)
    }


def get_top_clicked_properties(event, headers):
    """Get most clicked properties"""
    # Scan all searches and count property clicks
    response = search_logs_table.scan()
    searches = response['Items']

    zpid_clicks = {}
    for search in searches:
        for zpid in search.get('properties_clicked', []):
            zpid_clicks[zpid] = zpid_clicks.get(zpid, 0) + 1

    # Sort by click count
    top_properties = sorted(zpid_clicks.items(), key=lambda x: x[1], reverse=True)[:20]

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'properties': [{'zpid': z, 'clicks': c} for z, c in top_properties]
        })
    }


def get_top_rated_properties(event, headers):
    """Get best rated properties"""
    # Scan all feedback
    response = feedback_table.scan()
    feedbacks = response['Items']

    # Group by ZPID and calculate thumbs up %
    zpid_ratings = {}
    for feedback in feedbacks:
        zpid = feedback.get('zpid')
        rating = feedback.get('rating')

        if zpid not in zpid_ratings:
            zpid_ratings[zpid] = {'thumbs_up': 0, 'thumbs_down': 0}

        if rating == 'thumbs_up':
            zpid_ratings[zpid]['thumbs_up'] += 1
        elif rating == 'thumbs_down':
            zpid_ratings[zpid]['thumbs_down'] += 1

    # Calculate percentages and filter
    rated_properties = []
    for zpid, ratings in zpid_ratings.items():
        total = ratings['thumbs_up'] + ratings['thumbs_down']
        if total >= 3:  # Minimum 3 ratings
            thumbs_up_percent = (ratings['thumbs_up'] / total) * 100
            rated_properties.append({
                'zpid': zpid,
                'thumbs_up': ratings['thumbs_up'],
                'thumbs_down': ratings['thumbs_down'],
                'thumbs_up_percent': round(thumbs_up_percent, 1),
                'total_ratings': total
            })

    # Sort by thumbs up %
    rated_properties.sort(key=lambda x: x['thumbs_up_percent'], reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'properties': rated_properties[:20]
        })
    }


def get_issues(event, headers):
    """Get bug reports"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 50))
    status_filter = params.get('status', 'all')

    if status_filter != 'all':
        response = issues_table.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': status_filter},
            Limit=limit
        )
    else:
        response = issues_table.scan(Limit=limit)

    items = response['Items']

    # Sort by timestamp descending
    items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'issues': items,
            'count': len(items)
        }, default=decimal_default)
    }


def update_issue_status(issue_id, event, headers):
    """Update issue status"""
    body = json.loads(event.get('body', '{}'))
    new_status = body.get('status', 'new')

    # Find the issue to get its timestamp
    response = issues_table.scan(
        FilterExpression='issue_id = :iid',
        ExpressionAttributeValues={':iid': issue_id},
        Limit=1
    )

    if not response['Items']:
        return {
            'statusCode': 404,
            'headers': headers,
            'body': json.dumps({'error': 'Issue not found'})
        }

    issue = response['Items'][0]

    # Update status
    issues_table.update_item(
        Key={'issue_id': issue_id, 'timestamp': issue['timestamp']},
        UpdateExpression='SET #status = :status',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={':status': new_status}
    )

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({'success': True, 'status': new_status})
    }


def get_searches_over_time(event, headers):
    """Get searches grouped by hour for the last 24 hours"""
    params = event.get('queryStringParameters', {}) or {}
    hours = int(params.get('hours', 24))

    cutoff_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)

    # Get all searches in time range
    response = search_logs_table.scan(
        FilterExpression='#ts > :cutoff',
        ExpressionAttributeNames={'#ts': 'timestamp'},
        ExpressionAttributeValues={':cutoff': cutoff_time}
    )
    searches = response['Items']

    # Group by hour
    hourly_counts = {}
    for search in searches:
        timestamp = search.get('timestamp', 0)
        hour = datetime.fromtimestamp(timestamp / 1000).replace(minute=0, second=0, microsecond=0)
        hour_str = hour.strftime('%H:%M')
        hourly_counts[hour_str] = hourly_counts.get(hour_str, 0) + 1

    # Generate labels for last N hours
    now = datetime.now()
    labels = []
    values = []
    for i in range(hours, 0, -1):
        hour = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
        hour_str = hour.strftime('%H:%M')
        labels.append(hour_str)
        values.append(hourly_counts.get(hour_str, 0))

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'labels': labels,
            'values': values
        })
    }


def get_feedback_summary(event, headers):
    """Get thumbs up/down summary"""
    response = feedback_table.scan()
    feedbacks = response['Items']

    thumbs_up = len([f for f in feedbacks if f.get('rating') == 'up'])
    thumbs_down = len([f for f in feedbacks if f.get('rating') == 'down'])

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'thumbs_up': thumbs_up,
            'thumbs_down': thumbs_down
        }, default=decimal_default)
    }


def get_recent_activity(event, headers):
    """Get combined recent activity from searches, feedback, and issues"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 20))

    # Get recent searches
    searches_response = search_logs_table.scan(Limit=limit)
    searches = searches_response['Items']

    # Get recent feedback
    feedback_response = feedback_table.scan(Limit=limit)
    feedbacks = feedback_response['Items']

    # Get recent issues
    issues_response = issues_table.scan(Limit=limit)
    issues = issues_response['Items']

    # Combine and format
    activities = []

    for search in searches:
        activities.append({
            'timestamp': search.get('timestamp', 0),
            'type': 'search',
            'description': search.get('search_query', 'Unknown query'),
            'device_type': search.get('device_type', 'unknown'),
            'session_id': search.get('session_id', '')
        })

    for fb in feedbacks:
        rating = 'Thumbs up' if fb.get('rating') == 'up' else 'Thumbs down'
        activities.append({
            'timestamp': fb.get('timestamp', 0),
            'type': 'feedback',
            'description': f"{rating} on property {fb.get('zpid', 'unknown')}",
            'device_type': fb.get('device_type', 'unknown'),
            'session_id': fb.get('session_id', '')
        })

    for issue in issues:
        activities.append({
            'timestamp': issue.get('timestamp', 0),
            'type': 'issue',
            'description': f"{issue.get('issue_type', 'unknown')}: {issue.get('description', '')[:50]}...",
            'device_type': issue.get('device_type', 'unknown'),
            'session_id': issue.get('session_id', '')
        })

    # Sort by timestamp descending
    activities.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'activities': activities[:limit]
        }, default=decimal_default)
    }


def get_search_quality(event, headers):
    """Get search quality metrics"""
    response = search_logs_table.scan()
    searches = response['Items']

    if not searches:
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'avg_results': 0,
                'zero_results': 0,
                'llm_success_rate': 0,
                'avg_execution_time': 0
            })
        }

    total_results = sum([int(s.get('total_results', 0)) for s in searches])
    zero_results = len([s for s in searches if int(s.get('total_results', 0)) == 0])
    llm_successes = len([s for s in searches if s.get('llm_success', False)])
    total_time = sum([float(s.get('execution_time_ms', 0)) for s in searches])

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'avg_results': round(total_results / len(searches), 1),
            'zero_results': zero_results,
            'llm_success_rate': round((llm_successes / len(searches)) * 100, 1),
            'avg_execution_time': round(total_time / len(searches), 0)
        }, default=decimal_default)
    }


def get_top_queries(event, headers):
    """Get top queries with aggregated stats"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 10))

    response = search_logs_table.scan()
    searches = response['Items']

    # Group by query
    query_stats = {}
    for search in searches:
        query = search.get('search_query', '')
        if query not in query_stats:
            query_stats[query] = {
                'search_query': query,
                'count': 0,
                'total_results': 0,
                'llm_successes': 0,
                'total_time': 0
            }

        query_stats[query]['count'] += 1
        query_stats[query]['total_results'] += search.get('total_results', 0)
        if search.get('llm_success', False):
            query_stats[query]['llm_successes'] += 1
        query_stats[query]['total_time'] += float(search.get('execution_time_ms', 0))

    # Calculate averages and format
    queries = []
    for query, stats in query_stats.items():
        count = stats['count']
        queries.append({
            'search_query': query,
            'count': count,
            'avg_results': round(stats['total_results'] / count, 1) if count > 0 else 0,
            'llm_success_rate': round((stats['llm_successes'] / count) * 100, 1) if count > 0 else 0,
            'avg_time_ms': round(stats['total_time'] / count, 0) if count > 0 else 0
        })

    # Sort by count descending
    queries.sort(key=lambda x: x['count'], reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'queries': queries[:limit]
        }, default=decimal_default)
    }


def get_recent_searches(event, headers):
    """Get recent searches with details"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 20))

    response = search_logs_table.scan(Limit=limit)
    searches = response['Items']

    # Sort by timestamp descending
    searches.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'searches': searches[:limit]
        }, default=decimal_default)
    }


def get_feedback_details(event, headers):
    """Get detailed feedback statistics"""
    response = feedback_table.scan()
    feedbacks = response['Items']

    thumbs_up = len([f for f in feedbacks if f.get('rating') == 'up'])
    thumbs_down = len([f for f in feedbacks if f.get('rating') == 'down'])
    total = thumbs_up + thumbs_down

    with_text = len([f for f in feedbacks if f.get('feedback_text', '').strip()])
    with_categories = len([f for f in feedbacks if f.get('feedback_categories', [])])

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'thumbs_up': thumbs_up,
            'thumbs_up_percent': round((thumbs_up / total) * 100, 1) if total > 0 else 0,
            'thumbs_down': thumbs_down,
            'thumbs_down_percent': round((thumbs_down / total) * 100, 1) if total > 0 else 0,
            'with_text': with_text,
            'with_categories': with_categories
        }, default=decimal_default)
    }


def get_all_feedback(event, headers):
    """Get all feedback records"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 100))

    response = feedback_table.scan(Limit=limit)
    feedbacks = response['Items']

    # Sort by timestamp descending
    feedbacks.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    # Format for frontend
    formatted_feedback = []
    for fb in feedbacks:
        formatted_feedback.append({
            'timestamp': fb.get('timestamp', 0),
            'rating': fb.get('rating', ''),
            'zpid': fb.get('zpid', ''),
            'search_query': fb.get('search_query', ''),
            'categories': fb.get('feedback_categories', []),
            'feedback_text': fb.get('feedback_text', '')
        })

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'feedback': formatted_feedback
        }, default=decimal_default)
    }


def get_user_journey(event, headers):
    """Get user journey metrics"""
    response = sessions_table.scan()
    sessions = response['Items']

    if not sessions:
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'total_sessions': 0,
                'avg_duration_minutes': 0,
                'avg_searches_per_session': 0,
                'conversion_rate': 0
            })
        }

    total_duration = sum([float(s.get('session_duration', 0)) for s in sessions])
    total_searches = sum([int(s.get('total_searches', 0)) for s in sessions])
    sessions_with_feedback = len([s for s in sessions if int(s.get('total_feedback_submitted', 0)) > 0])

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'total_sessions': len(sessions),
            'avg_duration_minutes': round(total_duration / len(sessions), 1) if len(sessions) > 0 else 0,
            'avg_searches_per_session': round(total_searches / len(sessions), 1) if len(sessions) > 0 else 0,
            'conversion_rate': round((sessions_with_feedback / len(sessions)) * 100, 1) if len(sessions) > 0 else 0
        }, default=decimal_default)
    }


def get_properties_summary(event, headers):
    """Get properties summary metrics"""
    # Get all searches
    searches_response = search_logs_table.scan()
    searches = searches_response['Items']

    # Get all feedback
    feedback_response = feedback_table.scan()
    feedbacks = feedback_response['Items']

    # Count unique properties
    unique_zpids = set()
    for search in searches:
        zpids = search.get('results_zpids', [])
        unique_zpids.update(zpids)

    # Count properties with feedback
    properties_with_feedback = set([f.get('zpid') for f in feedbacks if f.get('zpid')])

    # Find highest rated
    zpid_ratings = {}
    for fb in feedbacks:
        zpid = fb.get('zpid')
        if zpid:
            if zpid not in zpid_ratings:
                zpid_ratings[zpid] = {'up': 0, 'down': 0}
            if fb.get('rating') == 'up':
                zpid_ratings[zpid]['up'] += 1
            else:
                zpid_ratings[zpid]['down'] += 1

    highest_rated_zpid = None
    highest_score = -999
    for zpid, ratings in zpid_ratings.items():
        score = ratings['up'] - ratings['down']
        if score > highest_score:
            highest_score = score
            highest_rated_zpid = zpid

    # Find most viewed (most appearances in search results)
    zpid_counts = {}
    for search in searches:
        for zpid in search.get('results_zpids', []):
            zpid_counts[zpid] = zpid_counts.get(zpid, 0) + 1

    most_viewed_zpid = max(zpid_counts, key=zpid_counts.get) if zpid_counts else None

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'unique_properties': len(unique_zpids),
            'properties_with_feedback': len(properties_with_feedback),
            'highest_rated_zpid': highest_rated_zpid,
            'most_viewed_zpid': most_viewed_zpid
        }, default=decimal_default)
    }


def get_property_performance(event, headers):
    """Get property performance details"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 50))

    # Get all searches and feedback
    searches_response = search_logs_table.scan()
    searches = searches_response['Items']

    feedback_response = feedback_table.scan()
    feedbacks = feedback_response['Items']

    # Count appearances
    zpid_appearances = {}
    for search in searches:
        for zpid in search.get('results_zpids', []):
            zpid_appearances[zpid] = zpid_appearances.get(zpid, 0) + 1

    # Count ratings and categories
    zpid_feedback = {}
    for fb in feedbacks:
        zpid = fb.get('zpid')
        if zpid:
            if zpid not in zpid_feedback:
                zpid_feedback[zpid] = {'thumbs_up': 0, 'thumbs_down': 0, 'categories': []}

            if fb.get('rating') == 'up':
                zpid_feedback[zpid]['thumbs_up'] += 1
            else:
                zpid_feedback[zpid]['thumbs_down'] += 1

            categories = fb.get('feedback_categories', [])
            zpid_feedback[zpid]['categories'].extend(categories)

    # Build performance list
    properties = []
    for zpid in zpid_appearances.keys():
        fb = zpid_feedback.get(zpid, {'thumbs_up': 0, 'thumbs_down': 0, 'categories': []})

        # Get most common issues
        common_issues = []
        if fb['categories']:
            from collections import Counter
            issue_counts = Counter(fb['categories'])
            common_issues = [issue for issue, count in issue_counts.most_common(3)]

        properties.append({
            'zpid': zpid,
            'appearances': zpid_appearances[zpid],
            'thumbs_up': fb['thumbs_up'],
            'thumbs_down': fb['thumbs_down'],
            'common_issues': common_issues
        })

    # Sort by appearances
    properties.sort(key=lambda x: x['appearances'], reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'properties': properties[:limit]
        }, default=decimal_default)
    }


def get_issues_summary(event, headers):
    """Get issues summary by type"""
    response = issues_table.scan()
    issues = response['Items']

    total = len(issues)
    search_error = len([i for i in issues if i.get('issue_type') == 'search_error'])
    wrong_results = len([i for i in issues if i.get('issue_type') == 'wrong_results'])
    ui_bug = len([i for i in issues if i.get('issue_type') == 'ui_bug'])

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'total': total,
            'search_error': search_error,
            'wrong_results': wrong_results,
            'ui_bug': ui_bug
        }, default=decimal_default)
    }


def get_all_issues(event, headers):
    """Get all issues"""
    params = event.get('queryStringParameters', {}) or {}
    limit = int(params.get('limit', 100))

    response = issues_table.scan(Limit=limit)
    issues = response['Items']

    # Sort by timestamp descending
    issues.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'issues': issues[:limit]
        }, default=decimal_default)
    }


def export_issues(event, headers):
    """Export issues to CSV format"""
    response = issues_table.scan()
    issues = response['Items']

    # Convert to CSV rows
    csv_rows = []
    csv_rows.append('Timestamp,Type,Description,Last Query,Device,Session ID')

    for issue in issues:
        timestamp = datetime.fromtimestamp(issue.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S')
        issue_type = issue.get('issue_type', '')
        description = issue.get('description', '').replace('"', '""')
        last_query = issue.get('last_search_query', '').replace('"', '""')
        device = issue.get('device_type', 'unknown')
        session_id = issue.get('session_id', '')

        csv_rows.append(f'"{timestamp}","{issue_type}","{description}","{last_query}","{device}","{session_id}"')

    csv_content = '\n'.join(csv_rows)

    return {
        'statusCode': 200,
        'headers': {
            **headers,
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename="issues_export.csv"'
        },
        'body': csv_content
    }


def export_feedback(event, headers):
    """Export feedback to CSV format"""
    # Scan all feedback
    response = feedback_table.scan()
    feedbacks = response['Items']

    # Convert to CSV rows
    csv_rows = []
    csv_rows.append('Timestamp,Query,ZPID,Rank,Rating,Categories,Feedback Text,Session ID')

    for feedback in feedbacks:
        timestamp = datetime.fromtimestamp(feedback.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S')
        query = feedback.get('search_query', '').replace('"', '""')
        zpid = feedback.get('zpid', '')
        rank = feedback.get('property_rank', 0)
        rating = feedback.get('rating', '')
        categories = '|'.join(feedback.get('feedback_categories', []))
        text = feedback.get('feedback_text', '').replace('"', '""')
        session_id = feedback.get('session_id', '')

        csv_rows.append(f'"{timestamp}","{query}","{zpid}",{rank},"{rating}","{categories}","{text}","{session_id}"')

    csv_content = '\n'.join(csv_rows)

    return {
        'statusCode': 200,
        'headers': {
            **headers,
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename="feedback_export.csv"'
        },
        'body': csv_content
    }


def export_searches(event, headers):
    """Export searches to CSV format"""
    # Scan all searches
    response = search_logs_table.scan()
    searches = response['Items']

    # Convert to CSV rows
    csv_rows = []
    csv_rows.append('Timestamp,Query,Results,Strategy,LLM Success,Execution Time (ms),Session ID')

    for search in searches:
        timestamp = datetime.fromtimestamp(search.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S')
        query = search.get('search_query', '').replace('"', '""')
        results = search.get('total_results', 0)
        strategy = search.get('search_strategy', '')
        llm_success = 'Yes' if search.get('llm_success') else 'No'
        exec_time = search.get('execution_time_ms', 0)
        session_id = search.get('session_id', '')

        csv_rows.append(f'"{timestamp}","{query}",{results},"{strategy}","{llm_success}",{exec_time},"{session_id}"')

    csv_content = '\n'.join(csv_rows)

    return {
        'statusCode': 200,
        'headers': {
            **headers,
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename="searches_export.csv"'
        },
        'body': csv_content
    }
