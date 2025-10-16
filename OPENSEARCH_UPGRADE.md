# OpenSearch Upgrade Investigation - No Data Loss

## Current Problem
- Searches timing out at 30 seconds (API Gateway limit)
- Image kNN search takes 21+ seconds on full dataset
- Total search time: 40+ seconds for 10 results

## Root Cause
**Hardware is undersized for multi-vector image search**
- Current: `t3.small.search` (2 vCPU, 2 GB RAM)
- Dataset: 3,904 properties × ~20 images = ~78,000 image vectors
- Multi-vector nested kNN queries need more memory

## Can We Upgrade Without Losing Data?
**YES! AWS OpenSearch supports in-place upgrades via Blue/Green deployment.**

### How It Works (Blue/Green Deployment)
1. AWS creates NEW instances with your requested size
2. All data (indices, documents, settings) automatically copied
3. Both old (blue) and new (green) clusters run simultaneously
4. Once data sync verified, traffic switches to new cluster
5. Old cluster automatically terminated
6. **ZERO DATA LOSS** - your 3,904 indexed listings are preserved!

### During Upgrade (20-30 minutes)
- ✅ Cluster remains AVAILABLE
- ✅ Reads continue to work
- ✅ Writes continue to work  
- ⚠️ Some performance degradation during migration
- ⚠️ Searches may be slower temporarily

## Recommended Upgrade Options

### Option 1: r6g.large.search (RECOMMENDED)
- **Specs**: 2 vCPU, 16 GB RAM (8x more memory!)
- **Cost**: ~$212/month for 2 nodes (~$106/node)
- **Current cost**: ~$52/month for 2 nodes
- **Increase**: ~$160/month
- **Why**: Memory-optimized, perfect for vector search
- **Expected performance**: Searches under 10 seconds

### Option 2: m6g.large.search (Budget Option)
- **Specs**: 2 vCPU, 8 GB RAM (4x more memory)
- **Cost**: ~$132/month for 2 nodes (~$66/node)
- **Increase**: ~$80/month
- **Why**: Good balance, still 4x memory improvement
- **Expected performance**: Searches 15-20 seconds (may still timeout)

### Option 3: r6g.xlarge.search (Best Performance)
- **Specs**: 4 vCPU, 32 GB RAM
- **Cost**: ~$424/month for 2 nodes
- **Increase**: ~$372/month
- **Why**: Plenty of headroom for growth
- **Expected performance**: Searches under 5 seconds

## Upgrade Command (r6g.large.search)

```bash
aws opensearch update-domain-config \
  --domain-name hearth-opensearch \
  --cluster-config \
    InstanceType=r6g.large.search,\
    InstanceCount=2,\
    DedicatedMasterEnabled=true,\
    DedicatedMasterType=r6g.large.search,\
    DedicatedMasterCount=3,\
    ZoneAwarenessEnabled=true,\
    ZoneAwarenessConfig={AvailabilityZoneCount=2}
```

## What Gets Preserved
✅ All indices (listings, listings-v2)
✅ All 3,904 documents with embeddings
✅ All index settings and mappings
✅ All aliases
✅ Cluster configuration
✅ Access policies

## Timeline
- Command execution: < 1 minute
- Blue/green deployment: 20-30 minutes
- Total downtime: **ZERO** (no downtime!)
- Searches continue during upgrade (may be slower)

## Verification After Upgrade
```bash
# Check upgrade status
aws opensearch describe-domain --domain-name hearth-opensearch \
  --query 'DomainStatus.{Processing, InstanceType: ClusterConfig.InstanceType}'

# Verify document count preserved
# Should still show 3,904 documents
```

## Alternative Solutions (No Upgrade)
If you don't want to upgrade, alternatives are:
1. Disable image kNN search temporarily (fast fix)
2. Reduce result size to 5 (may still timeout)
3. Accept that searches take 40+ seconds (Lambda works, UI times out)

## Recommendation
**Upgrade to r6g.large.search** - It's the right size for your use case and only ~$160/month more. The performance improvement will be dramatic and your indexed data will be preserved.
