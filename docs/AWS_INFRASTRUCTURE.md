# AWS Infrastructure

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [DEPLOYMENT.md](DEPLOYMENT.md), [API.md](API.md)

Complete AWS infrastructure documentation for Hearth Search.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [OpenSearch](#opensearch)
3. [Lambda Functions](#lambda-functions)
4. [DynamoDB Tables](#dynamodb-tables)
5. [API Gateway](#api-gateway)
6. [S3 Buckets](#s3-buckets)
7. [EC2 Instances](#ec2-instances)
8. [IAM Roles](#iam-roles)
9. [CloudWatch](#cloudwatch)

---

## Architecture Overview

```
User/Browser
    ↓
API Gateway
    ↓
┌─────────────────┬──────────────────────┬─────────────────────┐
│ Lambda:         │ Lambda:              │ Lambda:             │
│ hearth-search-v2│ hearth-crud-listings │ hearth-production-  │
│                 │                      │ analytics           │
└────────┬────────┴──────────┬───────────┴──────────┬──────────┘
         │                   │                       │
    ┌────▼───────┐     ┌────▼───────┐         ┌────▼────────┐
    │ OpenSearch │     │ OpenSearch │         │  DynamoDB   │
    │listings-v2 │     │listings-v2 │         │  - Logs     │
    │            │     │            │         │  - Ratings  │
    └────────────┘     └────────────┘         │  - Feedback │
                                               └─────────────┘

Production UI (EC2/nginx) ────> API Gateway
    http://54.226.26.203/
```

---

## OpenSearch

### Domain Information

**Domain Name**: `hearth-search` (assumed)
**Version**: OpenSearch 2.x
**Instance Type**: t3.small.search (or similar)
**Region**: us-east-1

### Indexes

#### listings-v2 (PRIMARY - CURRENT)

**Status**: ACTIVE
**Documents**: 3,902
**Purpose**: Main property search index

**Key Settings**:
```json
{
  "number_of_shards": 1,
  "number_of_replicas": 0,
  "index.knn": true,
  "index.knn.space_type": "cosinesimil"
}
```

**Critical Configuration**:
- kNN enabled for vector search
- Cosine similarity for embeddings
- HNSW algorithm for fast kNN

#### listings (DEPRECATED - DO NOT USE)

**Status**: OUTDATED
**Documents**: 3,104 (stale)
**Purpose**: Old index, replaced by listings-v2

**IMPORTANT**: All Lambda functions MUST use `listings-v2`, NOT `listings`.

### Index Mappings

See [DATA_SCHEMA.md](DATA_SCHEMA.md#opensearch-mapping) for complete field mappings.

**Key Fields**:
- `text_embedding`: knn_vector, 1024 dimensions, HNSW
- `image_embedding`: knn_vector, 512 dimensions, HNSW
- `property_features`: text with keyword multi-field
- `architecture_style`: keyword
- `architecture_substyle`: keyword

### Performance

**Query Latency**:
- BM25 search: 50-100ms
- kNN search: 100-200ms
- Combined (RRF): 150-300ms

**Throughput**:
- Reads: ~100 req/sec sustained
- Writes: ~10 req/sec sustained

---

## Lambda Functions

### hearth-search-v2 (Main Search)

**Function Name**: `hearth-search-v2`
**Runtime**: Python 3.11
**Memory**: 512 MB (or configured)
**Timeout**: 30 seconds
**Role**: Lambda execution role with OpenSearch access

**Environment Variables**:
```bash
OS_HOST=your-opensearch-endpoint.us-east-1.es.amazonaws.com
OS_INDEX=listings-v2  # CRITICAL: Must be listings-v2
BEDROCK_MODEL=us.anthropic.claude-3-haiku-20240307-v1:0
CLIP_MODEL=openai/clip-vit-base-patch32
```

**Trigger**: API Gateway (mqgsb4xb2g)

**Endpoint**: `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search`

**Functionality**:
- Multi-query decomposition
- 3-strategy search (BM25, text kNN, image kNN)
- RRF fusion
- Adaptive weighting
- Tag boosting

**Deployment**:
```bash
./deploy_lambda.sh
```

### hearth-crud-listings (CRUD Operations)

**Function Name**: `hearth-crud-listings`
**Runtime**: Python 3.11
**Memory**: 512 MB
**Timeout**: 60 seconds
**Role**: Lambda execution role with OpenSearch + Bedrock access

**Environment Variables**:
```bash
OS_HOST=your-opensearch-endpoint.us-east-1.es.amazonaws.com
OS_INDEX=listings-v2
BEDROCK_MODEL=us.anthropic.claude-3-haiku-20240307-v1:0
```

**Trigger**: API Gateway (mwf1h5nbxe)

**Endpoint**: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`

**Functionality**:
- Create property: POST /listings
- Update property: PATCH /listings/{zpid}
- Delete property: DELETE /listings/{zpid}
- Preserve embeddings option
- Regenerate embeddings option

**Deployment**:
```bash
./deploy_crud_api.sh
```

### hearth-production-analytics (Analytics)

**Function Name**: `hearth-production-analytics`
**Runtime**: Python 3.11
**Memory**: 256 MB
**Timeout**: 30 seconds
**Role**: Lambda execution role with DynamoDB access

**Environment Variables**:
```bash
DYNAMODB_REGION=us-east-1
SEARCH_LOGS_TABLE=SearchQueryLogs
QUALITY_FEEDBACK_TABLE=SearchQualityFeedback
RATINGS_TABLE=PropertyRatings
```

**Trigger**: API Gateway (mwf1h5nbxe, same as CRUD)

**Endpoints**:
- POST /log-search - Log search query
- POST /log-rating - Log property rating
- POST /log-search-quality - Log search quality feedback

**Functionality**:
- Search query logging
- Property rating collection
- Search quality feedback
- 90-day TTL on all data

**Deployment**:
```bash
zip -r analytics.zip production_analytics.py
aws lambda update-function-code \
  --function-name hearth-production-analytics \
  --zip-file fileb://analytics.zip
```

---

## DynamoDB Tables

### SearchQueryLogs

**Table Name**: `SearchQueryLogs`
**Primary Key**: `query_id` (String, Hash)
**Sort Key**: `timestamp` (Number)
**TTL**: 90 days (on `ttl` attribute)

**Purpose**: Log all search queries for analytics

**Item Structure**:
```json
{
  "query_id": "query_abc123",
  "timestamp": 1698765432000,
  "session_id": "user_session_xyz",
  "query": "modern homes with pool",
  "filters": {
    "minPrice": 300000,
    "maxPrice": 600000
  },
  "total_results": 42,
  "search_time_ms": 234,
  "ttl": 1706541432
}
```

**Capacity**:
- Read: 5 units
- Write: 5 units
- Auto-scaling: Enabled (recommended)

### SearchQualityFeedback

**Table Name**: `SearchQualityFeedback`
**Primary Key**: `quality_id` (String, Hash)
**Sort Key**: `timestamp` (Number)
**TTL**: 90 days

**Purpose**: Collect user feedback on search quality

**Item Structure**:
```json
{
  "quality_id": "quality_abc123",
  "timestamp": 1698765432000,
  "session_id": "user_session_xyz",
  "query_id": "query_abc123",
  "search_query": "modern homes",
  "rating": 4,
  "feedback_text": "Good results, missing some options",
  "feedback_categories": ["relevant", "missing_options"],
  "total_results": 42,
  "properties_viewed": 5,
  "time_on_results": 120000,
  "ttl": 1706541432
}
```

**Creation Script**:
```bash
./create_search_quality_table.sh
```

### PropertyRatings

**Table Name**: `PropertyRatings`
**Primary Key**: `rating_id` (String, Hash)
**Sort Key**: `timestamp` (Number)
**TTL**: 90 days

**Purpose**: Track property-specific user ratings

**Item Structure**:
```json
{
  "rating_id": "rating_abc123",
  "timestamp": 1698765432000,
  "session_id": "user_session_xyz",
  "query_id": "query_abc123",
  "zpid": "123456",
  "rating": 5,
  "comment": "Perfect home!",
  "ttl": 1706541432
}
```

---

## API Gateway

### Search API Gateway

**API ID**: `mqgsb4xb2g`
**Stage**: `prod`
**Region**: us-east-1

**Base URL**: `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod`

**Routes**:
- GET /search → hearth-search-v2 Lambda

**CORS**: Enabled
**Throttling**: Default (10,000 req/sec burst)

### CRUD/Analytics API Gateway

**API ID**: `mwf1h5nbxe`
**Stage**: `prod`
**Region**: us-east-1

**Base URL**: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`

**Routes**:
- POST /listings → hearth-crud-listings
- PATCH /listings/{zpid} → hearth-crud-listings
- DELETE /listings/{zpid} → hearth-crud-listings
- POST /log-search → hearth-production-analytics
- POST /log-rating → hearth-production-analytics
- POST /log-search-quality → hearth-production-analytics

**CORS**: Enabled

---

## S3 Buckets

### UI Hosting Bucket (if used)

**Purpose**: Host internal testing UI (NOT production UI)
**Bucket Name**: (to be determined)
**Region**: us-east-1

**Static Website Hosting**: Enabled
**Public Access**: Enabled (for UI)

**Note**: Production UI is NOT hosted on S3. It's on EC2/nginx.

---

## EC2 Instances

### Production UI Server

**Instance ID**: `i-044e6ddd7ab8353f9`
**Type**: t2.micro (or similar)
**Public IP**: `54.226.26.203`
**Region**: us-east-1

**Purpose**: Host production demo UI

**Web Server**: nginx
**Document Root**: `/var/www/html/`
**Index File**: `index.html`

**URL**: http://54.226.26.203/

**Deployment**:
```bash
./deploy_production_ui.sh
```

**Manual Access**:
```bash
ssh -i your-key.pem ec2-user@54.226.26.203
```

**Nginx Config** (typical):
```nginx
server {
    listen 80;
    server_name 54.226.26.203;
    root /var/www/html;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
}
```

---

## IAM Roles

### Lambda Execution Roles

**hearth-search-v2 Role**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost"
      ],
      "Resource": "arn:aws:es:us-east-1:*:domain/hearth-search/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

**hearth-crud-listings Role**:
- Same as hearth-search-v2
- Plus es:ESHttpPut, es:ESHttpDelete

**hearth-production-analytics Role**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/SearchQueryLogs",
        "arn:aws:dynamodb:us-east-1:*:table/SearchQualityFeedback",
        "arn:aws:dynamodb:us-east-1:*:table/PropertyRatings"
      ]
    }
  ]
}
```

---

## CloudWatch

### Log Groups

**hearth-search-v2**:
- Log Group: `/aws/lambda/hearth-search-v2`
- Retention: 7 days (or configured)
- Logs: Query execution, errors, performance metrics

**hearth-crud-listings**:
- Log Group: `/aws/lambda/hearth-crud-listings`
- Retention: 7 days
- Logs: CRUD operations, embedding generation, errors

**hearth-production-analytics**:
- Log Group: `/aws/lambda/hearth-production-analytics`
- Retention: 7 days
- Logs: Analytics events, DynamoDB writes

### Viewing Logs

```bash
# Tail search Lambda logs
aws logs tail /aws/lambda/hearth-search-v2 --follow

# Tail CRUD Lambda logs
aws logs tail /aws/lambda/hearth-crud-listings --follow --since 1m

# Filter for errors
aws logs tail /aws/lambda/hearth-search-v2 --follow --filter-pattern "ERROR"
```

### CloudWatch Metrics

**Lambda Metrics**:
- Invocations
- Duration
- Errors
- Throttles
- Concurrent Executions

**OpenSearch Metrics**:
- Search latency
- Indexing latency
- CPU utilization
- Storage space

**DynamoDB Metrics**:
- Read/Write capacity units
- Throttled requests

---

## Resource Summary

| Resource Type | Resource Name | Purpose | Region |
|---------------|---------------|---------|--------|
| OpenSearch Index | listings-v2 | Property search | us-east-1 |
| Lambda | hearth-search-v2 | Search API | us-east-1 |
| Lambda | hearth-crud-listings | CRUD API | us-east-1 |
| Lambda | hearth-production-analytics | Analytics | us-east-1 |
| DynamoDB | SearchQueryLogs | Search logging | us-east-1 |
| DynamoDB | SearchQualityFeedback | User feedback | us-east-1 |
| DynamoDB | PropertyRatings | Property ratings | us-east-1 |
| API Gateway | mqgsb4xb2g | Search endpoint | us-east-1 |
| API Gateway | mwf1h5nbxe | CRUD/Analytics endpoint | us-east-1 |
| EC2 | i-044e6ddd7ab8353f9 | Production UI | us-east-1 |

---

## Cost Estimation

**Monthly AWS Costs** (approximate):

- **OpenSearch**: $30-50/month (t3.small.search)
- **Lambda**: $5-10/month (3 functions, moderate usage)
- **DynamoDB**: $2-5/month (on-demand, 90-day TTL)
- **API Gateway**: $1-3/month (REST API requests)
- **EC2**: $5-10/month (t2.micro)
- **Bedrock (Claude)**: $10-20/month (embedding generation)
- **CloudWatch**: $1-2/month (logs)

**Total**: ~$54-100/month

---

## Disaster Recovery

### Backup Strategy

**OpenSearch Snapshots**:
- Automated snapshots: Daily
- Retention: 14 days
- Manual snapshots: Before major updates

**DynamoDB Backups**:
- Point-in-time recovery: Enabled
- On-demand backups: Before major changes

**Lambda Code**:
- Version control: GitHub
- Deployment artifacts: S3 (optional)

### Recovery Procedures

**OpenSearch Index Recovery**:
```bash
# Restore from snapshot
aws opensearch restore-snapshot \
  --domain-name hearth-search \
  --snapshot-name snapshot_name
```

**Lambda Recovery**:
```bash
# Rollback to previous version
aws lambda update-alias \
  --function-name hearth-search-v2 \
  --name prod \
  --function-version $PREVIOUS_VERSION
```

---

## Monitoring & Alerts

**Recommended CloudWatch Alarms**:

1. **Lambda Errors > 10 in 5 minutes**
2. **OpenSearch CPU > 80% for 5 minutes**
3. **API Gateway 5xx errors > 50 in 5 minutes**
4. **Lambda Duration > 25 seconds**

**Setup Example**:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name hearth-search-errors \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --dimensions Name=FunctionName,Value=hearth-search-v2 \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

---

## See Also

- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment procedures
- [API.md](API.md) - API endpoint details
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Infrastructure troubleshooting
