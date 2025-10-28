# Hearth Deployment Servers

## Server Overview

| Purpose | URL | EC2 Instance | Instance Name | Deployment Script |
|---------|-----|--------------|---------------|-------------------|
| **Internal Demo** | http://54.234.198.245/ | i-03e61f15aa312c332 | hearth-internal-demo | `deploy_internal_demo.sh` |
| **Public Demo** | http://54.226.26.203/ | i-044e6ddd7ab8353f9 | hearth-public-demo | ⚠️ **DO NOT DEPLOY** |

## Internal Demo (http://54.234.198.245/)

**Purpose:** Internal testing and development
**Password:** hearth-internal-pass
**Deployment:** Use `./deploy_internal_demo.sh`

**Includes:**
- Main Search
- BM25 Test
- kNN Text Test
- kNN Image Test
- Admin Lookup
- CRUD Manager
- Analytics Dashboard
- Style Detector
- Multi-Query Comparison

## Public Demo (http://54.226.26.203/)

**Purpose:** Public-facing demo for external users
**⚠️ WARNING:** DO NOT deploy to this server without explicit approval
**This server should remain stable for public use**

## Deployment Instructions

### To deploy INTERNAL DEMO:
```bash
./deploy_internal_demo.sh
```

This will:
1. Upload all UI files to S3
2. Deploy to internal demo EC2 (54.234.198.245)
3. Reload Nginx
4. **Does NOT touch public demo**

### To deploy PUBLIC DEMO:
⚠️ **Not recommended** - Public demo should remain stable

If absolutely necessary, create a separate deployment script.

## Browser Cache Issues

If you see old navigation menus after deployment:

1. **Hard refresh your browser:**
   - Windows/Linux: `Ctrl + Shift + R`
   - Mac: `Cmd + Shift + R`

2. **Or clear browser cache for the specific domain**

3. **Verify server is correct:**
   ```bash
   curl -s http://54.234.198.245/admin.html | grep "Analytics Dashboard"
   ```

## EC2 Instance Names

Updated instance names for clarity:
- ~~hearth-ui-v2~~ → **hearth-internal-demo**
- ~~hearth-production-ui~~ → **hearth-public-demo**

## S3 Bucket

All UI files are backed up to: `s3://demo-hearth-data/ui/`

## Nginx Configuration

Files are deployed to: `/usr/share/nginx/html/`
