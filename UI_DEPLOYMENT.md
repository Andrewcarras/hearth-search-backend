# Hearth UI Deployment Guide

## Quick Deployment

To deploy the UI to the EC2 instance:

```bash
./deploy_ui.sh i-03e61f15aa312c332
```

## Infrastructure

### EC2 Instance
- **Instance ID:** `i-03e61f15aa312c332`
- **Public IP:** `54.234.198.245`
- **URL:** http://54.234.198.245/
- **Type:** t3.nano (cheapest, 2 vCPU, 0.5 GB RAM)
- **AMI:** Amazon Linux 2
- **Web Server:** nginx

### API Gateway
- **Endpoint:** `https://f2o144zh31.execute-api.us-east-1.amazonaws.com`
- **Routes:**
  - `POST /search` - Search properties
  - `GET /listings/{zpid}` - Get single listing

### Lambda Function
- **Name:** `hearth-search-v2`
- **Runtime:** Python 3.13
- **Timeout:** 300 seconds

## Making Changes to the UI

1. Edit `ui/search.html` in this repository
2. Run deployment script:
   ```bash
   ./deploy_ui.sh i-03e61f15aa312c332
   ```
3. Test at http://54.234.198.245/

## Manual Deployment

If the script doesn't work:

```bash
# Upload to S3
aws s3 cp ui/search.html s3://demo-hearth-data/ui/search.html

# Deploy to EC2
aws ssm send-command \
    --instance-ids i-03e61f15aa312c332 \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "sudo aws s3 cp s3://demo-hearth-data/ui/search.html /usr/share/nginx/html/index.html",
        "sudo nginx -s reload"
    ]'
```

## Security Group

- **ID:** `sg-027bb1c86efc90e90`
- **Allows:** HTTP (80), HTTPS (443) from anywhere

## IAM Role

- **Name:** `EC2-SSM-Role`
- **Policies:**
  - AmazonSSMManagedInstanceCore (for SSM access)
  - AmazonS3ReadOnlyAccess (for downloading UI from S3)

## Troubleshooting

### Site not loading
```bash
# Check instance status
aws ec2 describe-instance-status --instance-ids i-03e61f15aa312c332

# Check nginx status via SSM
aws ssm send-command \
    --instance-ids i-03e61f15aa312c332 \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["sudo systemctl status nginx"]'
```

### Search not working
```bash
# Test API directly
curl -X POST https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search \
  -H "Content-Type: application/json" \
  -d '{"q": "modern home", "size": 3, "index": "listings-v2"}'
```

### Redeployment needed
Just run `./deploy_ui.sh i-03e61f15aa312c332` again - it's safe to run multiple times.
