# Hearth UI Deployment Guide

## Overview

The Hearth UI now includes a comprehensive admin panel with CRUD operations, allowing your team to:
- ✅ Search properties with natural language
- ✅ Add new listings with photo uploads
- ✅ Update any field for any listing
- ✅ Delete listings (soft or hard delete)
- ✅ All changes immediately searchable (no reindexing needed)

## Live Instances

### NEW Instance (with Admin Panel) ⭐
- **URL:** http://54.227.66.148
- **Instance ID:** i-07d177bfc28f76d22
- **SSH Key:** `/tmp/hearth-ui-key.pem`
- **Features:**
  - 🔍 Property search
  - ⚙️ Admin panel with CRUD operations
  - 📸 Image upload with AI processing
  - 🔄 Auto-updates from S3 on boot
  - 🔐 SSH access enabled
  - 🤖 SSM Session Manager enabled

### OLD Instance (Search Only)
- **URL:** http://34.228.111.56
- **Instance ID:** i-03ff1ef6cfad509e0
- **Status:** Running (kept for zero-downtime)
- **Note:** No SSH access, basic search UI only

## How to Update the UI

### Method 1: Upload to S3 (Recommended - Affects All Instances)

This is the easiest method and will update the UI on the new instance automatically on next boot/update.

```bash
# 1. Edit your UI file locally
# 2. Upload to S3
aws s3 cp /path/to/your/index.html s3://demo-hearth-data/ui/index.html --region us-east-1

# 3. Update the live instance
ssh -i /tmp/hearth-ui-key.pem ec2-user@54.227.66.148 'sudo update-ui'
```

The `update-ui` command:
- Downloads latest UI from S3
- Reloads nginx
- Takes ~2 seconds
- Zero downtime

### Method 2: Direct SSH Update

For quick changes without S3:

```bash
# Connect to instance
ssh -i /tmp/hearth-ui-key.pem ec2-user@54.227.66.148

# Edit UI directly
sudo nano /var/www/html/index.html

# Reload nginx
sudo systemctl reload nginx
```

### Method 3: SSM Session Manager (No SSH Key Needed)

```bash
# Start session
aws ssm start-session --target i-07d177bfc28f76d22 --region us-east-1

# Once connected:
sudo update-ui
```

### Method 4: Automatic Updates on Boot

The instance automatically downloads the latest UI from S3 on every boot:

```bash
# Reboot to get latest UI
aws ec2 reboot-instances --instance-ids i-07d177bfc28f76d22 --region us-east-1
```

## Admin Panel Features

### 1. Add New Listing
- Fill in property details (price, beds, baths, address, etc.)
- Upload up to 20 photos (drag & drop supported)
- Optional: Enable AI image processing to generate searchable tags
- Custom ZPID or auto-generate
- **Result:** Listing immediately searchable

### 2. Update Listing
- Enter ZPID
- Specify field to update (e.g., `price`, `status`, `custom_field`)
- Enter new value
- **Result:** Updates OpenSearch instantly, no reindexing needed

### 3. Delete Listing
- Enter ZPID
- Choose soft delete (mark as deleted, keep data) or hard delete (permanent)
- **Result:** Removes from search results

### 4. Search Listings
- Natural language search (e.g., "granite countertops", "pool")
- View property details
- Edit or delete directly from property modal

## Architecture

```
┌─────────────────┐
│   Developer     │
│  Updates HTML   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  S3: demo-hearth-data   │
│   ui/index.html         │
└────────┬────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  EC2: i-07d177bfc28f76d22    │
│  - Auto-downloads from S3     │
│  - Nginx serves UI            │
│  - Proxies /api/* to Lambda   │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  API Gateway + Lambda Functions  │
│  - POST /search                   │
│  - GET /listings/{zpid}           │
│  - POST /listings                 │
│  - PATCH /listings/{zpid}         │
│  - DELETE /listings/{zpid}        │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────┐
│  OpenSearch + S3 Data    │
└──────────────────────────┘
```

## Configuration Files

### Instance Configuration
- **IAM Role:** hearth-ec2-role
- **Instance Profile:** hearth-ec2-profile
- **Security Group:** sg-0943819ff3521ac9e (allows HTTP :80)
- **Nginx Config:** `/etc/nginx/conf.d/hearth.conf`
- **Update Script:** `/usr/local/bin/update-ui`
- **Auto-update Service:** `/etc/systemd/system/hearth-ui-update.service`

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name _;
    root /var/www/html;
    index index.html;

    # Proxy API requests to Lambda
    location /api/ {
        proxy_pass https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### UI not updating after upload to S3
```bash
ssh -i /tmp/hearth-ui-key.pem ec2-user@54.227.66.148 'sudo update-ui'
```

### Check nginx status
```bash
ssh -i /tmp/hearth-ui-key.pem ec2-user@54.227.66.148 'sudo systemctl status nginx'
```

### View nginx logs
```bash
ssh -i /tmp/hearth-ui-key.pem ec2-user@54.227.66.148 'sudo tail -f /var/log/nginx/error.log'
```

### Recreate instance (if needed)
```bash
# Terminate old instance
aws ec2 terminate-instances --instance-ids i-07d177bfc28f76d22 --region us-east-1

# Launch new one (UI auto-downloads from S3)
aws ec2 run-instances \
  --image-id ami-091d7d61336a4c68f \
  --instance-type t3.micro \
  --key-name hearth-ui-key \
  --security-group-ids sg-0943819ff3521ac9e \
  --iam-instance-profile Name=hearth-ec2-profile \
  --user-data file://scripts/ec2_userdata.sh \
  --region us-east-1 \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=hearth-ui-admin}]'
```

## Cost Analysis

### EC2 Instance
- **Type:** t3.micro
- **Cost:** ~$7.50/month (730 hours × $0.0104/hour)
- **Included:** 750 hours/month free tier (first 12 months)

### Data Transfer
- **S3 to EC2:** Free (same region)
- **UI updates:** ~34 KB each = negligible
- **User traffic:** First 100 GB/month free, then $0.09/GB

### Total: ~$0-7.50/month depending on free tier eligibility

## Security Notes

### Current Setup
- ✅ HTTP only (no HTTPS) - suitable for internal/testing
- ✅ SSH key authentication
- ✅ IAM role with minimal permissions (S3 read, SSM)
- ✅ Security group allows HTTP :80 from anywhere

### For Production
Consider adding:
- 🔐 HTTPS with SSL certificate (AWS Certificate Manager)
- 🔐 CloudFront distribution
- 🔐 API authentication (Cognito)
- 🔐 IP allowlisting for admin operations
- 🔐 WAF rules

## Team Access

### For Developers
Share the URL: **http://54.227.66.148**

They can:
1. Search properties naturally
2. Click "Admin" tab to access CRUD operations
3. Upload new listings with photos
4. Edit or delete any listing
5. No authentication required (internal use)

### For DevOps
Share SSH key for updates:
```bash
# Key location: /tmp/hearth-ui-key.pem
# Copy to your team:
cp /tmp/hearth-ui-key.pem ~/team-shared/hearth-ui-key.pem
chmod 400 ~/team-shared/hearth-ui-key.pem
```

## Next Steps

1. **Test the admin panel:** http://54.227.66.148 → Click "Admin" tab
2. **Create a test listing** with photos to verify everything works
3. **Share URL with team** for testing and feedback
4. **Switch DNS/load balancer** from old instance (34.228.111.56) to new one (54.227.66.148) when ready
5. **Terminate old instance** after verifying new one works perfectly

## Quick Reference

| Task | Command |
|------|---------|
| Update UI | `ssh -i /tmp/hearth-ui-key.pem ec2-user@54.227.66.148 'sudo update-ui'` |
| View UI | http://54.227.66.148 |
| SSH Access | `ssh -i /tmp/hearth-ui-key.pem ec2-user@54.227.66.148` |
| Check Status | `aws ec2 describe-instances --instance-ids i-07d177bfc28f76d22 --region us-east-1` |
| Reboot | `aws ec2 reboot-instances --instance-ids i-07d177bfc28f76d22 --region us-east-1` |
| Upload to S3 | `aws s3 cp index.html s3://demo-hearth-data/ui/index.html --region us-east-1` |

---

**Instance Ready! 🎉**
- New UI with Admin Panel: http://54.227.66.148
- Old UI (Search Only): http://34.228.111.56
