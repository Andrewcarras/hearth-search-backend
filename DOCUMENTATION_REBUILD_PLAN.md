# Documentation Rebuild Plan

**Generated**: 2025-10-24
**Purpose**: Complete documentation restructure for Hearth Search Backend

---

## Current State

**What We Have**: 64 files, 1.2MB
- Most are outdated (wrong endpoints, wrong index references)
- 29 investigation/analysis files (no longer needed)
- Duplication and poor organization

**Critical Issues**:
- Wrong index references ("listings" instead of "listings-v2")
- Outdated API endpoints
- Missing docs for major features

---

## New Structure: 10 Essential Documents

```
docs/
├── README.md                      # 1. Main hub - project overview, navigation, quick reference
├── DEPLOYMENT.md                  # 2. How to deploy everything (Lambda, UI, data)
├── API.md                         # 3. All API endpoints (Search, CRUD, Analytics)
├── SEARCH_SYSTEM.md              # 4. How search works (multi-query, RRF, embeddings)
├── ARCHITECTURE_STYLES.md        # 5. 2-tier style classification system
├── DATA_SCHEMA.md                # 6. OpenSearch schema + data ingestion
├── AWS_INFRASTRUCTURE.md         # 7. Lambda, OpenSearch, DynamoDB setup
├── UI_APPS.md                    # 8. Production UI + Internal testing UI
├── TROUBLESHOOTING.md            # 9. Common issues and fixes
└── SCRIPTS.md                    # 10. All scripts reference (deploy, data, utilities)
```

---

## Document Details

### 1. README.md (Main Hub)
**Purpose**: Central navigation and quick reference

**Contents**:
- Project overview (1 paragraph)
- **Quick Reference** (copy-paste ready):
  - Search API: `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search`
  - CRUD API: `https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod`
  - Production UI: `http://54.226.26.203/`
  - Index: `listings-v2` (NEVER "listings")
  - Lambda: `hearth-search-v2`
- Links to all 9 other documents
- Current system status (properties, features)

---

### 2. DEPLOYMENT.md
**Purpose**: How to deploy everything

**Sections**:
- **Lambda Deployment**: `./deploy_lambda.sh` (OS_INDEX=listings-v2)
- **Production UI**: `./deploy_production_ui.sh` (EC2/nginx)
- **Internal Testing UI**: S3 deployment
- **Data Upload**: `python3 upload_listings.py`
- **Environment Variables**: Complete reference
- **Verification Steps**: How to confirm deployments worked

---

### 3. API.md
**Purpose**: All API endpoints in one place

**Sections**:
- **Search API** (`hearth-search-v2`):
  - Endpoint, request params, response format
  - Example queries
- **CRUD API** (`hearth-crud-listings`):
  - Create, update, delete operations
  - preserve_embeddings option
  - Batch operations
- **Analytics API** (`hearth-production-analytics`):
  - Search logging
  - Property ratings
  - Search quality feedback

---

### 4. SEARCH_SYSTEM.md
**Purpose**: How search works end-to-end

**Sections**:
- **Multi-Query Decomposition**: LLM breaks query into subqueries
- **3-Strategy Search**:
  - BM25 tag-based search
  - Text kNN (Claude embeddings)
  - Image kNN (CLIP embeddings)
- **Reciprocal Rank Fusion**: Score merging (formula, k-values)
- **Adaptive Weighting**: Query classification adjusts weights
- **Tag Boosting**: Property feature match multipliers
- **Query Classification**: visual_style, color, specific_feature

---

### 5. ARCHITECTURE_STYLES.md
**Purpose**: 2-tier architecture style system

**Sections**:
- **Tier 1 Styles**: 30 broad categories
- **Tier 2 Styles**: 30 specific sub-styles
- **Synonym Mapping**: architecture_style_mappings.py
- **Search Integration**: How queries map to styles
- **Examples**: "mid century modern homes" → mid_century_modern

---

### 6. DATA_SCHEMA.md
**Purpose**: OpenSearch schema + data pipeline

**Sections**:
- **Complete Schema**: All fields with types
- **Key Fields**:
  - livingArea (house sqft) vs lotSize (lot sqft)
  - text_embedding, image_embedding
  - Tag fields (property_features, exterior_materials, etc.)
  - architecture_style (Tier 1 + Tier 2)
- **Data Ingestion**: upload_listings.py
- **Field Extraction**: How Zillow data maps to schema
- **Embedding Generation**: Claude Vision API

---

### 7. AWS_INFRASTRUCTURE.md
**Purpose**: AWS services setup

**Sections**:
- **OpenSearch**: Index config (listings-v2), mappings
- **Lambda Functions**:
  - hearth-search-v2 (search)
  - hearth-crud-listings (CRUD)
  - hearth-production-analytics (analytics)
- **DynamoDB Tables**:
  - SearchQueryLogs
  - SearchQualityFeedback
  - PropertyRatings
- **S3 Buckets**: UI hosting
- **CloudWatch**: Logs and monitoring

---

### 8. UI_APPS.md
**Purpose**: UI applications

**Sections**:
- **Production UI**:
  - URL: http://54.226.26.203/
  - Features: Search, filters, ratings, feedback
  - Deployment: ./deploy_production_ui.sh (EC2/nginx)
- **Internal Testing UI**:
  - Features: Index selection, analytics
  - Deployment: S3
- **Example Queries**: Architecture styles, features

---

### 9. TROUBLESHOOTING.md
**Purpose**: Common issues and solutions

**Sections**:
- **Search Issues**:
  - "No results found" → Check OS_INDEX=listings-v2
  - Architecture style search fails → Check architecture_style_mappings.py
  - Wrong index → Update Lambda environment variables
- **Data Issues**:
  - Wrong square footage → Check livingArea vs lotSize
  - Missing embeddings → Rerun upload_listings.py
- **Deployment Issues**:
  - Lambda deployment fails → Check deploy_lambda.sh
  - UI not updating → Use correct deployment script
- **Index Issues**:
  - listings vs listings-v2 mismatch

---

### 10. SCRIPTS.md
**Purpose**: All scripts reference

**Sections**:
- **Deployment Scripts**:
  - deploy_lambda.sh (Lambda deployment)
  - deploy_production_ui.sh (Production UI to EC2)
- **Data Scripts**:
  - upload_listings.py (Zillow data ingestion)
  - fix_living_area.py (Fix square footage)
  - update_architecture_fast.py (Batch architecture updates)
- **Utility Scripts**:
  - create_search_quality_table.sh (DynamoDB setup)
  - production_analytics.py (Analytics Lambda)

---

## Documentation Standards

Every document includes:
1. **Header**: Last Updated date, Related Docs links
2. **Real Examples**: Working code/queries
3. **Current Values**: listings-v2, correct endpoints
4. **Code References**: File paths and line numbers
5. **Troubleshooting**: Common issues for that topic

---

## Implementation Plan

### Step 1: Backup & Delete (2 minutes)
```bash
tar -czf docs_backup_20251024.tar.gz docs/
rm -rf docs/
mkdir docs
```

### Step 2: Create 10 Documents (3 hours)
- Order: README → API → SEARCH_SYSTEM → Others
- Focus: Accuracy, examples, current values
- Cross-link related documents

### Step 3: Verify (15 minutes)
- Check all endpoints correct
- Verify no "listings" references (only "listings-v2")
- Test all example queries/code

---

## Success Criteria

✅ All docs fit in 10 files
✅ No wrong index/endpoint references
✅ Every major feature documented
✅ Real working examples
✅ Quick reference in README

---

## Next Steps

1. Get approval
2. Backup existing docs
3. Delete old docs
4. Create 10 new documents

**Estimated Time**: 3-4 hours total
