#!/bin/bash
set -e

# Create CloudWatch Alarms for Search Quality Monitoring
# This script creates automated alerts for search performance and quality issues

REGION="us-east-1"
LOG_GROUP="/aws/lambda/hearth-search-v2"
SNS_TOPIC_NAME="SearchQualityAlerts"

echo "======================================"
echo "Search Quality Alert Creation"
echo "======================================"
echo ""

# Create SNS topic for alerts (if needed)
echo "1. Creating SNS topic for alerts..."
SNS_TOPIC_ARN=$(aws sns create-topic --name "$SNS_TOPIC_NAME" --region "$REGION" --query 'TopicArn' --output text)
echo "   Topic ARN: $SNS_TOPIC_ARN"

# Optional: Subscribe your email to the topic
# Uncomment and add your email:
# aws sns subscribe --topic-arn "$SNS_TOPIC_ARN" --protocol email --notification-endpoint your-email@example.com

echo ""
echo "2. Creating CloudWatch Metric Filters..."

# Metric Filter 1: High Error Rate
echo "   - Creating filter for search errors..."
aws logs put-metric-filter \
  --log-group-name "$LOG_GROUP" \
  --filter-name "SearchErrors" \
  --filter-pattern '[time, request_id, level=ERROR*, ...]' \
  --metric-transformations \
    metricName=SearchErrorCount,\
metricNamespace=Hearth/Search,\
metricValue=1,\
unit=Count

# Metric Filter 2: Slow Searches (>5 seconds)
echo "   - Creating filter for slow searches..."
aws logs put-metric-filter \
  --log-group-name "$LOG_GROUP" \
  --filter-name "SlowSearches" \
  --filter-pattern '{ $.total_time_ms > 5000 }' \
  --metric-transformations \
    metricName=SlowSearchCount,\
metricNamespace=Hearth/Search,\
metricValue=1,\
unit=Count

# Metric Filter 3: Poor Quality Results (low avg_score)
echo "   - Creating filter for poor quality results..."
aws logs put-metric-filter \
  --log-group-name "$LOG_GROUP" \
  --filter-name "PoorQualitySearches" \
  --filter-pattern '{ $.quality_score < 0.2 }' \
  --metric-transformations \
    metricName=PoorQualitySearchCount,\
metricNamespace=Hearth/Search,\
metricValue=1,\
unit=Count

echo ""
echo "3. Creating CloudWatch Alarms..."

# Alarm 1: High error rate
echo "   - Creating alarm for high error rate..."
aws cloudwatch put-metric-alarm \
  --alarm-name "Search-HighErrorRate" \
  --alarm-description "Alert when search error rate exceeds 10% in 5 minutes" \
  --metric-name SearchErrorCount \
  --namespace Hearth/Search \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --treat-missing-data notBreaching \
  --region "$REGION"

# Alarm 2: Slow searches
echo "   - Creating alarm for slow searches..."
aws cloudwatch put-metric-alarm \
  --alarm-name "Search-SlowQueries" \
  --alarm-description "Alert when >5 searches take longer than 5 seconds in 5 minutes" \
  --metric-name SlowSearchCount \
  --namespace Hearth/Search \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --treat-missing-data notBreaching \
  --region "$REGION"

# Alarm 3: Poor quality results
echo "   - Creating alarm for poor quality results..."
aws cloudwatch put-metric-alarm \
  --alarm-name "Search-PoorQuality" \
  --alarm-description "Alert when >10 searches have poor quality (low feature match) in 5 minutes" \
  --metric-name PoorQualitySearchCount \
  --namespace Hearth/Search \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --treat-missing-data notBreaching \
  --region "$REGION"

# Alarm 4: Lambda execution errors
echo "   - Creating alarm for Lambda execution errors..."
aws cloudwatch put-metric-alarm \
  --alarm-name "Search-LambdaErrors" \
  --alarm-description "Alert when Lambda function has execution errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --dimensions Name=FunctionName,Value=hearth-search-v2 \
  --statistic Sum \
  --period 60 \
  --evaluation-periods 2 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --treat-missing-data notBreaching \
  --region "$REGION"

# Alarm 5: Lambda throttling
echo "   - Creating alarm for Lambda throttling..."
aws cloudwatch put-metric-alarm \
  --alarm-name "Search-LambdaThrottles" \
  --alarm-description "Alert when Lambda function is being throttled" \
  --metric-name Throttles \
  --namespace AWS/Lambda \
  --dimensions Name=FunctionName,Value=hearth-search-v2 \
  --statistic Sum \
  --period 60 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions "$SNS_TOPIC_ARN" \
  --treat-missing-data notBreaching \
  --region "$REGION"

echo ""
echo "======================================"
echo "Alert Creation Complete!"
echo "======================================"
echo ""
echo "Created Alarms:"
echo "  1. Search-HighErrorRate    - Errors > 10 in 5 minutes"
echo "  2. Search-SlowQueries      - >5 queries >5s in 5 minutes"
echo "  3. Search-PoorQuality      - >10 poor quality searches in 5 minutes"
echo "  4. Search-LambdaErrors     - Lambda execution errors > 5 in 2 minutes"
echo "  5. Search-LambdaThrottles  - Any Lambda throttling"
echo ""
echo "SNS Topic: $SNS_TOPIC_ARN"
echo ""
echo "To subscribe your email to alerts, run:"
echo "  aws sns subscribe --topic-arn $SNS_TOPIC_ARN --protocol email --notification-endpoint your-email@example.com"
echo ""
echo "To view alarms:"
echo "  aws cloudwatch describe-alarms --alarm-name-prefix Search-"
echo ""
