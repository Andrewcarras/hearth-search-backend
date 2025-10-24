#!/bin/bash
# Create DynamoDB table for Search Quality Feedback

echo "Creating SearchQualityFeedback DynamoDB table..."

aws dynamodb create-table \
    --table-name SearchQualityFeedback \
    --attribute-definitions \
        AttributeName=quality_id,AttributeType=S \
        AttributeName=timestamp,AttributeType=N \
    --key-schema \
        AttributeName=quality_id,KeyType=HASH \
        AttributeName=timestamp,KeyType=RANGE \
    --provisioned-throughput \
        ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --region us-east-1

echo "Waiting for table to be created..."
aws dynamodb wait table-exists --table-name SearchQualityFeedback --region us-east-1

echo "✅ SearchQualityFeedback table created successfully!"

# Enable TTL
echo "Enabling TTL on the table..."
aws dynamodb update-time-to-live \
    --table-name SearchQualityFeedback \
    --time-to-live-specification "Enabled=true, AttributeName=ttl" \
    --region us-east-1

echo "✅ TTL enabled (90-day retention)"
echo ""
echo "Table ARN:"
aws dynamodb describe-table --table-name SearchQualityFeedback --region us-east-1 | jq -r '.Table.TableArn'
