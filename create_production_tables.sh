#!/bin/bash

echo "Creating Production Analytics DynamoDB Tables..."
echo ""

# Table 1: hearth-production-search-logs
echo "Creating hearth-production-search-logs..."
aws dynamodb create-table \
  --table-name hearth-production-search-logs \
  --attribute-definitions \
    AttributeName=session_id,AttributeType=S \
    AttributeName=timestamp,AttributeType=N \
    AttributeName=query_id,AttributeType=S \
    AttributeName=search_query,AttributeType=S \
    AttributeName=ip_address,AttributeType=S \
  --key-schema \
    AttributeName=session_id,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --global-secondary-indexes \
    "[
      {
        \"IndexName\": \"query_id-index\",
        \"KeySchema\": [{\"AttributeName\":\"query_id\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"timestamp-index\",
        \"KeySchema\": [{\"AttributeName\":\"timestamp\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"search_query-timestamp-index\",
        \"KeySchema\": [
          {\"AttributeName\":\"search_query\",\"KeyType\":\"HASH\"},
          {\"AttributeName\":\"timestamp\",\"KeyType\":\"RANGE\"}
        ],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"ip_address-timestamp-index\",
        \"KeySchema\": [
          {\"AttributeName\":\"ip_address\",\"KeyType\":\"HASH\"},
          {\"AttributeName\":\"timestamp\",\"KeyType\":\"RANGE\"}
        ],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      }
    ]" \
  --billing-mode PROVISIONED \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
  --region us-east-1

echo "✓ Created hearth-production-search-logs"
echo ""

# Enable TTL for search logs (90 days)
echo "Enabling TTL for search logs..."
aws dynamodb update-time-to-live \
  --table-name hearth-production-search-logs \
  --time-to-live-specification "Enabled=true, AttributeName=ttl" \
  --region us-east-1

echo "✓ Enabled TTL"
echo ""

# Table 2: hearth-production-feedback
echo "Creating hearth-production-feedback..."
aws dynamodb create-table \
  --table-name hearth-production-feedback \
  --attribute-definitions \
    AttributeName=feedback_id,AttributeType=S \
    AttributeName=timestamp,AttributeType=N \
    AttributeName=zpid,AttributeType=S \
    AttributeName=query_id,AttributeType=S \
    AttributeName=session_id,AttributeType=S \
    AttributeName=rating,AttributeType=S \
  --key-schema \
    AttributeName=feedback_id,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --global-secondary-indexes \
    "[
      {
        \"IndexName\": \"zpid-timestamp-index\",
        \"KeySchema\": [
          {\"AttributeName\":\"zpid\",\"KeyType\":\"HASH\"},
          {\"AttributeName\":\"timestamp\",\"KeyType\":\"RANGE\"}
        ],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"query_id-index\",
        \"KeySchema\": [{\"AttributeName\":\"query_id\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"rating-timestamp-index\",
        \"KeySchema\": [
          {\"AttributeName\":\"rating\",\"KeyType\":\"HASH\"},
          {\"AttributeName\":\"timestamp\",\"KeyType\":\"RANGE\"}
        ],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"session_id-index\",
        \"KeySchema\": [{\"AttributeName\":\"session_id\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"timestamp-index\",
        \"KeySchema\": [{\"AttributeName\":\"timestamp\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      }
    ]" \
  --billing-mode PROVISIONED \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
  --region us-east-1

echo "✓ Created hearth-production-feedback"
echo ""

# Enable TTL for feedback (90 days)
echo "Enabling TTL for feedback..."
aws dynamodb update-time-to-live \
  --table-name hearth-production-feedback \
  --time-to-live-specification "Enabled=true, AttributeName=ttl" \
  --region us-east-1

echo "✓ Enabled TTL"
echo ""

# Table 3: hearth-production-sessions
echo "Creating hearth-production-sessions..."
aws dynamodb create-table \
  --table-name hearth-production-sessions \
  --attribute-definitions \
    AttributeName=session_id,AttributeType=S \
    AttributeName=session_start,AttributeType=N \
    AttributeName=ip_address,AttributeType=S \
    AttributeName=is_active,AttributeType=S \
  --key-schema \
    AttributeName=session_id,KeyType=HASH \
    AttributeName=session_start,KeyType=RANGE \
  --global-secondary-indexes \
    "[
      {
        \"IndexName\": \"session_start-index\",
        \"KeySchema\": [{\"AttributeName\":\"session_start\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"ip_address-index\",
        \"KeySchema\": [{\"AttributeName\":\"ip_address\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"is_active-index\",
        \"KeySchema\": [{\"AttributeName\":\"is_active\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      }
    ]" \
  --billing-mode PROVISIONED \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
  --region us-east-1

echo "✓ Created hearth-production-sessions"
echo ""

# Enable TTL for sessions (90 days)
echo "Enabling TTL for sessions..."
aws dynamodb update-time-to-live \
  --table-name hearth-production-sessions \
  --time-to-live-specification "Enabled=true, AttributeName=ttl" \
  --region us-east-1

echo "✓ Enabled TTL"
echo ""

# Table 4: hearth-production-issues
echo "Creating hearth-production-issues..."
aws dynamodb create-table \
  --table-name hearth-production-issues \
  --attribute-definitions \
    AttributeName=issue_id,AttributeType=S \
    AttributeName=timestamp,AttributeType=N \
    AttributeName=issue_type,AttributeType=S \
    AttributeName=status,AttributeType=S \
    AttributeName=session_id,AttributeType=S \
  --key-schema \
    AttributeName=issue_id,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --global-secondary-indexes \
    "[
      {
        \"IndexName\": \"timestamp-index\",
        \"KeySchema\": [{\"AttributeName\":\"timestamp\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"issue_type-timestamp-index\",
        \"KeySchema\": [
          {\"AttributeName\":\"issue_type\",\"KeyType\":\"HASH\"},
          {\"AttributeName\":\"timestamp\",\"KeyType\":\"RANGE\"}
        ],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"status-timestamp-index\",
        \"KeySchema\": [
          {\"AttributeName\":\"status\",\"KeyType\":\"HASH\"},
          {\"AttributeName\":\"timestamp\",\"KeyType\":\"RANGE\"}
        ],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      },
      {
        \"IndexName\": \"session_id-index\",
        \"KeySchema\": [{\"AttributeName\":\"session_id\",\"KeyType\":\"HASH\"}],
        \"Projection\": {\"ProjectionType\":\"ALL\"},
        \"ProvisionedThroughput\": {\"ReadCapacityUnits\":5,\"WriteCapacityUnits\":5}
      }
    ]" \
  --billing-mode PROVISIONED \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
  --region us-east-1

echo "✓ Created hearth-production-issues"
echo ""

# Enable TTL for issues (180 days)
echo "Enabling TTL for issues..."
aws dynamodb update-time-to-live \
  --table-name hearth-production-issues \
  --time-to-live-specification "Enabled=true, AttributeName=ttl" \
  --region us-east-1

echo "✓ Enabled TTL"
echo ""

echo "========================================="
echo "All tables created successfully!"
echo "========================================="
echo ""
echo "Tables:"
echo "  1. hearth-production-search-logs (TTL: 90 days)"
echo "  2. hearth-production-feedback (TTL: 90 days)"
echo "  3. hearth-production-sessions (TTL: 90 days)"
echo "  4. hearth-production-issues (TTL: 180 days)"
echo ""
echo "Waiting for tables to become ACTIVE..."
echo ""

# Wait for all tables to become active
aws dynamodb wait table-exists --table-name hearth-production-search-logs --region us-east-1
aws dynamodb wait table-exists --table-name hearth-production-feedback --region us-east-1
aws dynamodb wait table-exists --table-name hearth-production-sessions --region us-east-1
aws dynamodb wait table-exists --table-name hearth-production-issues --region us-east-1

echo "✓ All tables are ACTIVE and ready to use!"
