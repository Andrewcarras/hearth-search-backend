# Hearth Frontend - Setup Guide

Quick setup guide for the Hearth real estate search UI.

## Prerequisites

- Node.js 16+ and npm
- Access to Hearth search API endpoint

## Installation

```bash
# Install dependencies
npm install

# Configure API endpoint
# Edit src/config.js and set SEARCH_API_URL

# Start development server
npm start
```

## Environment Configuration

Create `.env` file:

```
REACT_APP_API_URL=https://your-api-gateway-url.amazonaws.com
REACT_APP_REGION=us-east-1
```

## Building for Production

```bash
npm run build
```

Outputs to `build/` directory ready for deployment to S3/CloudFront.

## Features

- Natural language search input
- Real-time search results
- Property cards with images
- Architecture style filtering
- Map view with proximity search
- Responsive design

## Deployment

```bash
# Deploy to S3
aws s3 sync build/ s3://your-frontend-bucket/ --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id YOUR_DIST_ID \
  --paths "/*"
```

For detailed documentation, see [README.md](README.md).
