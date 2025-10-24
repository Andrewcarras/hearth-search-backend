# Hearth Search Backend

**Last Updated**: 2025-10-24
**Status**: Current

Hearth Search is an intelligent property search system powered by multi-strategy search, reciprocal rank fusion, and Claude AI embeddings. It combines BM25 tag matching, text embeddings, and image embeddings to deliver highly relevant property results.

---

## Quick Reference

### Endpoints
- **Search API**: `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search`
- **CRUD API**: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`
- **Analytics API**: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod` (same as CRUD)
- **Production UI**: `http://54.226.26.203/`

### Core Configuration
- **OpenSearch Index**: `listings-v2` (NEVER use "listings")
- **Main Lambda**: `hearth-search-v2`
- **CRUD Lambda**: `hearth-crud-listings`
- **Analytics Lambda**: `hearth-production-analytics`
- **Region**: `us-east-1`

### Current System Status
- **Properties**: 3,902 listings (Salt Lake City area)
- **Architecture Styles**: 2-tier classification (30 Tier 1 + 30 Tier 2 styles)
- **Embeddings**: Text (Claude) + Image (CLIP)
- **Search Strategies**: BM25 + Text kNN + Image kNN with RRF fusion

---

## Documentation

### Getting Started
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deploy Lambda, UI, and data

### API Reference
- [API.md](API.md) - All API endpoints (Search, CRUD, Analytics)

### System Architecture
- [SEARCH_SYSTEM.md](SEARCH_SYSTEM.md) - How search works (multi-query, RRF, embeddings)
- [ARCHITECTURE_STYLES.md](ARCHITECTURE_STYLES.md) - 2-tier style classification
- [DATA_SCHEMA.md](DATA_SCHEMA.md) - OpenSearch schema + data ingestion
- [AWS_INFRASTRUCTURE.md](AWS_INFRASTRUCTURE.md) - Lambda, OpenSearch, DynamoDB

### User Interfaces
- [UI_APPS.md](UI_APPS.md) - Production UI + Internal testing UI

### Reference
- [SCRIPTS.md](SCRIPTS.md) - All scripts (deploy, data, utilities)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and fixes

---

## Quick Start

### Search for Properties
```bash
curl "https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=modern+homes+with+pool"
```

### Deploy Lambda
```bash
./deploy_lambda.sh
```

### Deploy Production UI
```bash
./deploy_production_ui.sh
```

### Upload Property Data
```bash
python3 upload_listings.py slc_listings.json
```

---

## Key Features

### Multi-Query Search
LLM decomposes user queries into multiple subqueries for comprehensive results
- Example: "modern homes with granite" → ["modern architecture", "granite countertops"]

### 3-Strategy Search with RRF
- **BM25**: Tag-based keyword matching (property features, materials, etc.)
- **Text kNN**: Claude text embeddings for semantic understanding
- **Image kNN**: CLIP image embeddings for visual style matching
- **RRF Fusion**: Combines all strategies with adaptive weighting

### Adaptive Weighting
Query classification automatically adjusts strategy weights:
- Visual style queries → Boost image search
- Color queries → Boost image search
- Specific feature queries → Boost BM25 tag search

### Architecture Style Classification
2-tier hierarchical system with synonym mapping:
- **Tier 1**: 30 broad styles (modern, craftsman, ranch, etc.)
- **Tier 2**: 30 specific sub-styles (mid_century_modern, mid_century_ranch, etc.)
- **Synonyms**: "MCM homes" → mid_century_modern

### User Feedback Systems
- **Property Ratings**: Star ratings for individual properties
- **Search Quality Feedback**: Overall search result quality ratings
- **Issue Reporting**: User-reported problems

---

## Common Tasks

### Fix Search Not Returning Results
1. Check Lambda environment: `OS_INDEX=listings-v2` (not "listings")
2. Verify architecture_style_mappings.py includes all styles
3. Check CloudWatch logs for errors

### Update Property Data
```bash
# Fix specific fields (e.g., livingArea)
python3 fix_living_area.py slc_listings.json 50

# Full re-upload
python3 upload_listings.py slc_listings.json
```

### Update Architecture Styles
```bash
# Batch update with CRUD API
python3 update_architecture_fast.py
```

---

## Architecture Overview

```
User Query
    ↓
Multi-Query Decomposition (LLM)
    ↓
[Subquery 1, Subquery 2, ...]
    ↓
3 Parallel Searches per Subquery:
    ├─ BM25 (Tag Matching)
    ├─ Text kNN (Claude Embeddings)
    └─ Image kNN (CLIP Embeddings)
    ↓
Reciprocal Rank Fusion (RRF)
    ↓
Adaptive Weight Adjustment
    ↓
Tag Boosting (Exact Matches)
    ↓
Greedy Diversification
    ↓
Final Results
```

---

## Technology Stack

- **Search**: AWS OpenSearch (listings-v2 index)
- **Compute**: AWS Lambda (Python 3.11)
- **Storage**: DynamoDB (analytics), S3 (images)
- **Embeddings**: Claude 3 (text), CLIP (images)
- **Frontend**: Vanilla JS (production UI), EC2/nginx hosting
- **APIs**: API Gateway (REST)

---

## Support

- **Documentation Issues**: Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Deployment Issues**: See [DEPLOYMENT.md](DEPLOYMENT.md)
- **API Issues**: Reference [API.md](API.md)

---

## Recent Changes

**2025-10-24**:
- Fixed deploy_lambda.sh to use correct index (listings-v2)
- Fixed livingArea vs lotSize data mapping
- Updated 3,153 properties with correct square footage
- Added search quality feedback system
- Rebuilt documentation (10 essential docs)

**2025-10-23**:
- Implemented 2-tier architecture style classification
- Added architecture synonym mapping
- Batch updated 2,800+ properties with styles
