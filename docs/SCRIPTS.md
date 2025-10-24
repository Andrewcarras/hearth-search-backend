# Scripts Reference

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [DEPLOYMENT.md](DEPLOYMENT.md), [DATA_SCHEMA.md](DATA_SCHEMA.md)

Complete reference for all scripts in the Hearth Search project.

---

## Table of Contents

1. [Deployment Scripts](#deployment-scripts)
2. [Data Scripts](#data-scripts)
3. [Utility Scripts](#utility-scripts)
4. [Archived Scripts](#archived-scripts)

---

## Deployment Scripts

### deploy_lambda.sh

**Purpose**: Deploy hearth-search-v2 Lambda function

**Location**: [deploy_lambda.sh](../deploy_lambda.sh)

**Usage**:
```bash
./deploy_lambda.sh
```

**What It Does**:
1. Creates deployment package with dependencies
2. Zips Lambda code into deployment.zip
3. Updates hearth-search-v2 Lambda function
4. Sets environment variables

**Critical Configuration** (Line 17):
```bash
OS_INDEX=listings-v2  # MUST be listings-v2 (NOT "listings")
```

**Environment Variables Set**:
```bash
OS_HOST=your-opensearch-endpoint.us-east-1.es.amazonaws.com
OS_INDEX=listings-v2
BEDROCK_MODEL=us.anthropic.claude-3-haiku-20240307-v1:0
CLIP_MODEL=openai/clip-vit-base-patch32
```

**Requirements**:
- AWS CLI configured
- Lambda function `hearth-search-v2` must exist
- IAM permissions for lambda:UpdateFunctionCode

**Verification**:
```bash
# Check Lambda was updated
aws lambda get-function-configuration --function-name hearth-search-v2 \
  --query 'LastModified'

# Verify index config
aws lambda get-function-configuration --function-name hearth-search-v2 \
  --query 'Environment.Variables.OS_INDEX'
# Should return: "listings-v2"
```

**Troubleshooting**:
- **Error: "deployment.zip not found"** → Run from project root
- **Error: "Function not found"** → Create Lambda first via AWS Console
- **Error: "Access denied"** → Check IAM permissions

---

### deploy_production_ui.sh

**Purpose**: Deploy production UI to EC2 instance

**Location**: [deploy_production_ui.sh](../deploy_production_ui.sh)

**Usage**:
```bash
./deploy_production_ui.sh
```

**What It Does**:
1. Copies ui/production.html to EC2 instance
2. Deploys to /var/www/html/index.html
3. Restarts nginx (if needed)

**Target**:
- Instance: i-044e6ddd7ab8353f9
- IP: 54.226.26.203
- Path: /var/www/html/index.html

**Requirements**:
- SSH key for EC2 instance
- SSH access to 54.226.26.203

**IMPORTANT**: Production UI is on EC2, NOT S3.

**Verification**:
```bash
# Check if file was updated
curl -I http://54.226.26.203/

# Should return: HTTP/1.1 200 OK
```

**Manual Deployment**:
```bash
scp -i your-key.pem ui/production.html ec2-user@54.226.26.203:/var/www/html/index.html
```

---

### deploy_crud_api.sh

**Purpose**: Deploy hearth-crud-listings Lambda function

**Location**: [deploy_crud_api.sh](../deploy_crud_api.sh)

**Usage**:
```bash
./deploy_crud_api.sh
```

**What It Does**:
1. Packages CRUD Lambda code
2. Zips and deploys to hearth-crud-listings
3. Sets environment variables

**Environment Variables**:
```bash
OS_HOST=your-opensearch-endpoint.us-east-1.es.amazonaws.com
OS_INDEX=listings-v2
BEDROCK_MODEL=us.anthropic.claude-3-haiku-20240307-v1:0
```

---

### create_search_quality_table.sh

**Purpose**: Create SearchQualityFeedback DynamoDB table

**Location**: [create_search_quality_table.sh](../create_search_quality_table.sh)

**Usage**:
```bash
./create_search_quality_table.sh
```

**What It Does**:
1. Creates DynamoDB table with:
   - Primary key: quality_id (String)
   - Sort key: timestamp (Number)
   - TTL: 90 days (on ttl attribute)
2. Enables TTL for automatic data expiration
3. Sets provisioned capacity (5 read, 5 write units)

**Output**:
```json
{
  "TableDescription": {
    "TableName": "SearchQualityFeedback",
    "TableStatus": "CREATING",
    ...
  }
}
```

**Verification**:
```bash
aws dynamodb describe-table --table-name SearchQualityFeedback
```

---

## Data Scripts

### upload_listings.py

**Purpose**: Upload property listings from Zillow JSON to OpenSearch

**Location**: [upload_listings.py](../upload_listings.py)

**Usage**:
```bash
python3 upload_listings.py slc_listings.json
```

**Parameters**:
- `slc_listings.json`: Path to Zillow JSON file

**What It Does**:
1. Reads Zillow JSON data
2. For each property:
   - Extracts fields (zpid, address, price, etc.)
   - **Extracts livingArea (house sqft) and lotSize (lot sqft)** correctly
   - Downloads property images
   - Generates text embedding (Claude Vision API)
   - Generates image embedding (CLIP)
   - Classifies architecture style (2-tier)
   - Extracts property features as tags
   - Uploads to OpenSearch listings-v2 index
3. Logs progress and errors

**Critical Fix (2025-10-24)**: Lines 209-213
```python
# CORRECT:
living_area = _num(lst.get("livingArea") or lst.get("livingAreaValue"))  # House sqft
lot_size = _num(lst.get("lotSize") or lst.get("lotAreaValue"))  # Lot sqft

# ...

"livingArea": float(living_area),  # House square footage
"lotSize": float(lot_size)  # Lot size
```

**Performance**:
- ~30-60 seconds per property
- 3,902 properties ≈ 2 hours total
- Bedrock API rate limits may slow down processing

**Requirements**:
- Zillow JSON file
- AWS credentials (Bedrock, OpenSearch access)
- Python dependencies (requests, boto3, transformers)

**Verification**:
```bash
# Check index count
curl "your-opensearch-endpoint/listings-v2/_count"
# Should increase by number of properties uploaded
```

---

### fix_living_area.py

**Purpose**: Fix livingArea and lotSize fields for existing properties

**Location**: [fix_living_area.py](../fix_living_area.py)

**Usage**:
```bash
python3 fix_living_area.py slc_listings.json 50
```

**Parameters**:
- `slc_listings.json`: Source Zillow data with correct values
- `50`: Batch size (number of properties per batch)

**What It Does**:
1. Loads correct livingArea/lotSize from Zillow JSON
2. For each property in OpenSearch:
   - Fetches current data
   - Compares with source data
   - If different, updates via CRUD API
   - Uses preserve_embeddings=true (no regeneration)
3. Logs progress to /tmp/living_area_update.log

**Output**:
```
Loaded 3,902 properties
Processing batch 1/79...
  ✅ Updated 123456: 47916 → 2100 sqft
  ✅ Updated 234567: 43560 → 1800 sqft
  ⏭️  Skipped 345678: No livingArea in source
...
✅ Update complete!
Total: 3,153 updated, 0 failures, 749 skipped
```

**Uses**: CRUD API endpoint
```python
url = "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/listings/{zpid}?index=listings-v2"
```

**Results (2025-10-24)**:
- 3,153 properties updated successfully
- 0 failures
- 749 skipped (no data in source)

---

### update_architecture_fast.py

**Purpose**: Batch update architecture styles for properties

**Location**: [update_architecture_fast.py](../update_architecture_fast.py)

**Usage**:
```bash
python3 update_architecture_fast.py
```

**What It Does**:
1. Fetches properties without architecture_style from OpenSearch
2. For each property:
   - Downloads property images
   - Calls Claude Vision API for classification
   - Gets Tier 1 + Tier 2 architecture styles
   - Updates via CRUD API with preserve_embeddings=true
3. Processes in batches of 50
4. Logs progress to /tmp/architecture_update.log
5. Saves checkpoint after each batch

**Progress (2025-10-23)**:
- ~2,800 properties updated
- ~1,100 remaining
- Batch size: 50 properties
- Time per batch: ~2-3 minutes

**Resume from Checkpoint**:
```bash
python3 update_architecture_fast.py --resume
```

**Claude Vision Prompt**:
```python
prompt = """
Analyze this property image and classify its architectural style.

Return JSON with:
- tier1_style: broad category (e.g., "modern", "craftsman", "victorian")
- tier2_style: specific sub-style (e.g., "mid_century_modern", "craftsman_bungalow")
- confidence: 0-1
- reasoning: brief explanation

Supported styles: {list of styles}
"""
```

**Checkpoint File**: `architecture_update_checkpoint.json`
```json
{
  "last_processed": "zpid_123456",
  "total_processed": 2800,
  "batch_number": 56,
  "timestamp": "2025-10-23T18:30:00"
}
```

---

## Utility Scripts

### production_analytics.py

**Purpose**: Lambda function for analytics logging

**Location**: [production_analytics.py](../production_analytics.py)

**Deployment**:
```bash
zip -r analytics.zip production_analytics.py
aws lambda update-function-code \
  --function-name hearth-production-analytics \
  --zip-file fileb://analytics.zip
```

**Endpoints Handled**:
- POST /log-search
- POST /log-rating
- POST /log-search-quality

**What It Does**:
- Logs search queries to SearchQueryLogs table
- Logs property ratings to PropertyRatings table
- Logs search quality feedback to SearchQualityFeedback table
- Sets 90-day TTL on all records

**DynamoDB Tables**:
- SearchQueryLogs
- SearchQualityFeedback
- PropertyRatings

---

### architecture_style_mappings.py

**Purpose**: Architecture style synonym mapping system

**Location**: [architecture_style_mappings.py](../architecture_style_mappings.py)

**Usage** (testing):
```bash
python3 architecture_style_mappings.py
```

**Functions**:
```python
# Map user input to supported styles
map_user_style_to_supported("Eichler")
# Returns: {"styles": ["mid_century_modern"], "confidence": 0.9, ...}

# Get style family
get_style_family("mid_century_modern")
# Returns: "mid_century_modern"

# Get user-friendly message
get_user_friendly_message("Victorian", ["victorian_queen_anne", "victorian_italianate"])
# Returns: "Showing Victorian Queen Anne and Victorian Italianate homes"
```

**Data Structures**:
- `ALL_SUPPORTED_STYLES`: Set of 60+ supported styles
- `STYLE_SYNONYMS`: Dict mapping 100+ colloquial names to styles
- `STYLE_FAMILIES`: Dict of style hierarchies
- `STYLE_SIMILARITY`: Dict of style similarity scores

**Used By**: hearth-search-v2 Lambda for architecture style search

---

### process_remaining_batches.sh

**Purpose**: Process remaining architecture style update batches

**Location**: [process_remaining_batches.sh](../process_remaining_batches.sh)

**Usage**:
```bash
./process_remaining_batches.sh
```

**What It Does**:
1. Loops through batches 7-29
2. For each batch, runs update_architecture_fast.py
3. Checks for "Update complete" in logs
4. Displays progress

**Output**:
```
Processing batch 7...
✅ Batch 7: COMPLETE

Processing batch 8...
🔄 Batch 8: In progress

Processing batch 9...
⏳ Batch 9: Not started
```

---

## Archived Scripts

**Location**: [archive/investigation_scripts/](../archive/investigation_scripts/)

### Investigation Scripts (Archived)

These scripts were used during debugging and investigation. They are no longer actively used but preserved for reference.

**analyze_search.py**:
- Purpose: Analyze search result quality
- Status: Archived (investigation complete)

**fetch_specific_searches.py**:
- Purpose: Fetch and analyze specific search queries
- Status: Archived

**investigate_degradation_window.py**:
- Purpose: Investigate search degradation during specific time window
- Status: Archived (issue resolved)

**test_architecture_classification.py**:
- Purpose: Test architecture style classification accuracy
- Status: Archived

**audit_data_quality.py**:
- Purpose: Audit property data quality
- Status: Archived (data quality issues fixed)

### Data Quality Scripts (Archived)

**migrate_split_visual_features.py**:
- Purpose: Split visual features into separate fields
- Status: Archived (migration complete)

---

## Script Dependencies

### Python Dependencies

**All Python scripts require**:
```bash
pip install boto3 requests transformers pillow
```

**Specific dependencies**:
- `boto3`: AWS SDK (Bedrock, OpenSearch, DynamoDB)
- `requests`: HTTP requests (CRUD API, image downloads)
- `transformers`: CLIP model for image embeddings
- `pillow`: Image processing

### AWS Credentials

**Required for all AWS operations**:
```bash
# Configure AWS CLI
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

### Shell Scripts

**Bash scripts require**:
- Bash 4.0+
- AWS CLI installed and configured
- SSH key (for deploy_production_ui.sh)

---

## Script Execution Order

### Full Deployment

```bash
# 1. Deploy Lambda functions
./deploy_lambda.sh
./deploy_crud_api.sh

# 2. Create DynamoDB tables (first time only)
./create_search_quality_table.sh

# 3. Upload property data
python3 upload_listings.py slc_listings.json

# 4. Update architecture styles
python3 update_architecture_fast.py

# 5. Fix data quality issues (if needed)
python3 fix_living_area.py slc_listings.json 50

# 6. Deploy production UI
./deploy_production_ui.sh
```

### Data Updates Only

```bash
# Upload new properties
python3 upload_listings.py new_listings.json

# OR fix specific fields
python3 fix_living_area.py slc_listings.json 50

# OR update architecture styles
python3 update_architecture_fast.py
```

### Code Updates Only

```bash
# Update search Lambda
./deploy_lambda.sh

# Update CRUD Lambda
./deploy_crud_api.sh

# Update UI
./deploy_production_ui.sh
```

---

## Common Script Patterns

### Error Handling

**All data scripts should handle**:
1. Network errors (retry with backoff)
2. API rate limits (sleep and retry)
3. Invalid data (skip and log)
4. Partial failures (checkpoint and resume)

**Example**:
```python
import time
import requests

def update_with_retry(zpid, data, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.patch(url, json=data, timeout=30)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            print(f"Failed to update {zpid}: {e}")
            return False
```

### Logging

**All scripts should log**:
1. Progress (every N items processed)
2. Errors (with zpid and error message)
3. Summary (total processed, succeeded, failed)

**Example**:
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/script.log'),
        logging.StreamHandler()
    ]
)

logging.info(f"Processing batch {batch_num}...")
logging.error(f"Failed to update {zpid}: {error}")
logging.info(f"Complete: {success_count} updated, {fail_count} failed")
```

### Checkpointing

**Long-running scripts should**:
1. Save checkpoint after each batch
2. Resume from checkpoint on restart
3. Store: last processed ID, batch number, timestamp

**Example**:
```python
import json

def save_checkpoint(zpid, batch_num):
    checkpoint = {
        "last_processed": zpid,
        "batch_number": batch_num,
        "timestamp": datetime.now().isoformat()
    }
    with open('checkpoint.json', 'w') as f:
        json.dump(checkpoint, f)

def load_checkpoint():
    try:
        with open('checkpoint.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
```

---

## See Also

- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment procedures
- [DATA_SCHEMA.md](DATA_SCHEMA.md) - Data ingestion details
- [API.md](API.md) - API endpoints used by scripts
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Script troubleshooting
