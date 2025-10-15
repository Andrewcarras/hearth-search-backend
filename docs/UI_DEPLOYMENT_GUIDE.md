# UI Deployment Guide

**Last Updated:** 2025-01-14
**EC2 Instance:** i-07d177bfc28f76d22 (54.227.66.148)
**UI Location:** http://54.227.66.148

---

## Quick Reference

**TL;DR - Deploy UI in 3 Steps:**

```bash
# 1. Upload to S3
cd ui && aws s3 cp search.html s3://demo-hearth-data/ui/search.html --region us-east-1

# 2. Download to EC2 and copy to BOTH locations
aws ssm send-command --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["aws s3 cp s3://demo-hearth-data/ui/search.html /home/ec2-user/search.html --region us-east-1 && sudo cp /home/ec2-user/search.html /var/www/html/search.html && sudo cp /home/ec2-user/search.html /var/www/html/index.html && echo UI deployed successfully"]' \
  --region us-east-1

# 3. Verify deployment
curl -s "http://54.227.66.148/?t=$(date +%s)" | head -20
```

---

## Understanding the EC2 Setup

### Web Server Configuration

The EC2 instance runs **nginx** with the following setup:

**Nginx Config Location:** `/etc/nginx/conf.d/*.conf`

**Key Configuration:**
```nginx
server {
    listen 80;
    server_name _;
    root /var/www/html;          # ← ACTUAL WEB ROOT
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy to Lambda
    location /api/ {
        proxy_pass https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/;
    }
}
```

### Critical File Locations

| Location | Purpose | Used By |
|----------|---------|---------|
| `/var/www/html/index.html` | **Main UI file (served at `/`)** | ✅ Nginx root |
| `/var/www/html/search.html` | UI file (served at `/search.html`) | ✅ Nginx |
| `/home/ec2-user/search.html` | Temporary download location | ❌ NOT served |
| `/usr/share/nginx/html/` | Default nginx directory | ❌ NOT USED |

**⚠️ IMPORTANT:**
- The web root is `/var/www/html/`, NOT `/usr/share/nginx/html/`
- You must copy to BOTH `index.html` and `search.html` in `/var/www/html/`
- Files in `/home/ec2-user/` are NOT served by nginx

---

## Step-by-Step Deployment Process

### Step 1: Upload UI to S3

```bash
cd ui
aws s3 cp search.html s3://demo-hearth-data/ui/search.html --region us-east-1
```

**What this does:**
- Uploads the local `ui/search.html` to S3 bucket
- Makes it available for EC2 to download (EC2 has IAM role for S3 access)

**Verify upload:**
```bash
aws s3 ls s3://demo-hearth-data/ui/ --region us-east-1
```

---

### Step 2: Download to EC2 and Copy to Web Root

**Single command (recommended):**

```bash
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["aws s3 cp s3://demo-hearth-data/ui/search.html /home/ec2-user/search.html --region us-east-1 && sudo cp /home/ec2-user/search.html /var/www/html/search.html && sudo cp /home/ec2-user/search.html /var/www/html/index.html && echo UI deployed successfully"]' \
  --region us-east-1 \
  --output json | jq -r '.Command.CommandId'
```

**What this does:**
1. Downloads `search.html` from S3 to `/home/ec2-user/search.html` (using EC2's IAM role)
2. Copies to `/var/www/html/search.html` (accessible at http://54.227.66.148/search.html)
3. Copies to `/var/www/html/index.html` (accessible at http://54.227.66.148/)
4. Returns command ID for verification

**Check command status:**

```bash
# Replace COMMAND_ID with the ID from previous command
aws ssm get-command-invocation \
  --command-id COMMAND_ID \
  --instance-id i-07d177bfc28f76d22 \
  --region us-east-1 \
  | jq -r '.StandardOutputContent, .StandardErrorContent'
```

**Expected output:**
```
Completed 69.5 KiB/69.5 KiB with 1 file(s) remaining
download: s3://demo-hearth-data/ui/search.html to ../../home/ec2-user/search.html
UI deployed successfully
```

---

### Step 3: Verify Deployment

**Check file exists on server:**

```bash
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["ls -lh /var/www/html/*.html"]' \
  --region us-east-1 \
  --output json | jq -r '.Command.CommandId'
```

**Test HTTP access:**

```bash
# Check file size (should match local file)
curl -s http://54.227.66.148/ | wc -c

# Check for specific content (example)
curl -s http://54.227.66.148/ | grep -i "hearth search"

# Force refresh (bypass cache)
curl -s -H "Cache-Control: no-cache" "http://54.227.66.148/?t=$(date +%s)" | head -20
```

**Check in browser:**
1. Open http://54.227.66.148
2. Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
3. Verify changes are visible

---

## Common Issues and Solutions

### Issue 1: "Access Denied" when downloading from S3

**Problem:** EC2 can't download from S3

**Cause:** S3 bucket has public access blocked, EC2 IAM role lacks permissions

**Solution:** Verify EC2 IAM role has S3 read permissions

```bash
# Check EC2 IAM role
aws iam get-role --role-name hearth-ec2-role

# Add S3 read policy if missing
aws iam put-role-policy \
  --role-name hearth-ec2-role \
  --policy-name S3ReadAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::demo-hearth-data/*",
        "arn:aws:s3:::demo-hearth-data"
      ]
    }]
  }'
```

---

### Issue 2: File uploaded but changes not visible

**Problem:** UI looks the same after deployment

**Cause:** File copied to wrong location or browser cache

**Solution:**

1. **Verify file is in correct location:**
   ```bash
   aws ssm send-command \
     --instance-ids i-07d177bfc28f76d22 \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["ls -lh /var/www/html/index.html /var/www/html/search.html"]' \
     --region us-east-1
   ```

2. **Check file content on server:**
   ```bash
   aws ssm send-command \
     --instance-ids i-07d177bfc28f76d22 \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["head -50 /var/www/html/index.html | tail -20"]' \
     --region us-east-1
   ```

3. **Clear browser cache:**
   - Hard refresh: Ctrl+Shift+R or Cmd+Shift+R
   - Or open in incognito/private window

4. **Bypass cache in curl:**
   ```bash
   curl -s -H "Cache-Control: no-cache" "http://54.227.66.148/?t=$(date +%s)"
   ```

---

### Issue 3: File in wrong location

**Problem:** File copied to `/home/ec2-user/` or `/usr/share/nginx/html/`

**Cause:** Using wrong paths

**Solution:** Always copy to `/var/www/html/`

```bash
# If file is in /home/ec2-user/
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["sudo cp /home/ec2-user/search.html /var/www/html/index.html && sudo cp /home/ec2-user/search.html /var/www/html/search.html"]' \
  --region us-east-1

# If file is in /usr/share/nginx/html/
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["sudo cp /usr/share/nginx/html/search.html /var/www/html/index.html && sudo cp /usr/share/nginx/html/search.html /var/www/html/search.html"]' \
  --region us-east-1
```

---

### Issue 4: Need to reload nginx

**Problem:** Changes not taking effect

**Solution:** Reload nginx (rarely needed, but doesn't hurt)

```bash
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["sudo nginx -s reload && echo Nginx reloaded"]' \
  --region us-east-1
```

---

## Debugging Commands

### Find all search.html files on server

```bash
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["sudo find / -name search.html 2>/dev/null"]' \
  --region us-east-1
```

### Check nginx configuration

```bash
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["sudo cat /etc/nginx/conf.d/*.conf"]' \
  --region us-east-1
```

### Check web server process

```bash
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["ps aux | grep nginx | grep -v grep"]' \
  --region us-east-1
```

### Check file sizes

```bash
# Local file
ls -lh ui/search.html

# S3 file
aws s3 ls s3://demo-hearth-data/ui/ --region us-east-1

# Server files
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["ls -lh /var/www/html/*.html"]' \
  --region us-east-1

# Served file
curl -s http://54.227.66.148/ | wc -c
```

### Compare file content

```bash
# Get first 100 lines from local file
head -100 ui/search.html

# Get first 100 lines from server
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["head -100 /var/www/html/index.html"]' \
  --region us-east-1

# Get first 100 lines from served file
curl -s http://54.227.66.148/ | head -100
```

---

## Testing Checklist

After deployment, verify:

- [ ] File uploaded to S3: `aws s3 ls s3://demo-hearth-data/ui/`
- [ ] File downloaded to EC2: Check SSM command output
- [ ] File in `/var/www/html/index.html`: `ls -lh /var/www/html/index.html`
- [ ] File in `/var/www/html/search.html`: `ls -lh /var/www/html/search.html`
- [ ] HTTP accessible: `curl http://54.227.66.148/`
- [ ] Correct file size: Compare `wc -c` output
- [ ] Specific content present: `curl ... | grep "unique string"`
- [ ] Browser shows changes: Hard refresh + check visually

---

## Alternative Deployment Methods

### Method 1: Direct S3 to Web Root (Current Method)

```bash
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["aws s3 cp s3://demo-hearth-data/ui/search.html /home/ec2-user/search.html --region us-east-1 && sudo cp /home/ec2-user/search.html /var/www/html/index.html && sudo cp /home/ec2-user/search.html /var/www/html/search.html"]' \
  --region us-east-1
```

**Pros:** Works reliably, uses EC2 IAM role
**Cons:** Requires S3 upload first

---

### Method 2: Base64 Encoding (For Small Files)

```bash
# Encode file
base64 ui/search.html > /tmp/search_base64.txt

# Deploy (if file < 48KB base64 encoded)
FILE_CONTENT=$(cat /tmp/search_base64.txt)
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"echo '$FILE_CONTENT' | base64 -d | sudo tee /var/www/html/index.html > /dev/null\"]" \
  --region us-east-1
```

**Pros:** No S3 needed
**Cons:** SSM has 48KB command limit, base64 increases size by ~33%

---

### Method 3: SCP (If SSH Access Available)

```bash
scp -i ~/.ssh/hearth-ui-key.pem ui/search.html ec2-user@54.227.66.148:/tmp/search.html
ssh -i ~/.ssh/hearth-ui-key.pem ec2-user@54.227.66.148 "sudo cp /tmp/search.html /var/www/html/index.html && sudo cp /tmp/search.html /var/www/html/search.html"
```

**Pros:** Fast, direct
**Cons:** Requires SSH key configured

---

## Architecture Reference

```
┌─────────────────────────────────────────────────────┐
│ Local Development                                   │
│ /Users/andrewcarras/hearth_backend_new/ui/         │
│   └── search.html                                   │
└─────────────────┬───────────────────────────────────┘
                  │ aws s3 cp
                  ▼
┌─────────────────────────────────────────────────────┐
│ S3 Bucket: demo-hearth-data                         │
│   └── ui/search.html                                │
└─────────────────┬───────────────────────────────────┘
                  │ EC2 IAM role: aws s3 cp
                  ▼
┌─────────────────────────────────────────────────────┐
│ EC2 Instance: i-07d177bfc28f76d22 (54.227.66.148) │
│                                                     │
│ /home/ec2-user/search.html (temp download)         │
│           │                                         │
│           │ sudo cp (via SSM)                       │
│           ▼                                         │
│ /var/www/html/                                      │
│   ├── index.html    ← Served at http://.../       │
│   └── search.html   ← Served at http://.../search.html
│                                                     │
│ Nginx Config: /etc/nginx/conf.d/*.conf             │
│   root /var/www/html;                               │
└─────────────────────────────────────────────────────┘
```

---

## Quick Tips

1. **Always deploy to BOTH files:**
   - `/var/www/html/index.html` (for root `/`)
   - `/var/www/html/search.html` (for `/search.html`)

2. **Use cache busting when testing:**
   ```bash
   curl -s "http://54.227.66.148/?t=$(date +%s)"
   ```

3. **Check file size match:**
   - Local: `ls -lh ui/search.html`
   - Served: `curl -s http://54.227.66.148/ | wc -c`
   - Should match exactly

4. **Wait a few seconds after SSM command:**
   ```bash
   sleep 3 && aws ssm get-command-invocation ...
   ```

5. **Hard refresh browser:**
   - Chrome/Edge: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
   - Firefox: Ctrl+F5 (Windows) or Cmd+Shift+R (Mac)
   - Safari: Cmd+Option+R (Mac)

---

## Emergency Rollback

If deployment breaks the UI:

```bash
# Restore from S3 backup (if you have one)
aws ssm send-command \
  --instance-ids i-07d177bfc28f76d22 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["aws s3 cp s3://demo-hearth-data/ui/search.html.backup /home/ec2-user/search.html --region us-east-1 && sudo cp /home/ec2-user/search.html /var/www/html/index.html && sudo cp /home/ec2-user/search.html /var/www/html/search.html"]' \
  --region us-east-1

# Or restore from git
git checkout HEAD~1 ui/search.html
# Then redeploy
```

---

## Contact Information

- **EC2 Instance ID:** i-07d177bfc28f76d22
- **Public IP:** 54.227.66.148
- **UI URL:** http://54.227.66.148
- **API URL:** https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod
- **S3 Bucket:** demo-hearth-data
- **Region:** us-east-1

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-01-14 | Created comprehensive deployment guide | Claude |
| 2025-01-14 | Fixed deployment to use correct web root (/var/www/html) | Claude |
| 2025-01-14 | Added troubleshooting for S3 access and file locations | Claude |
