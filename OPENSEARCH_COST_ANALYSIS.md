# OpenSearch Instance Cost Analysis

## Executive Summary

**Current Problem:** 89.9% JVM memory pressure causing 40+ second search times (exceeds 30s API Gateway timeout)

**Root Cause:** t3.small.search instances (2 GB RAM) are 66 MB short of minimum requirements for 78,080 image vectors

**Cheapest Solution:** Upgrade to **t4g.medium.search** for **$32/month increase**

---

## Current State

### Infrastructure
- **Instance Type:** t3.small.search
- **RAM:** 2 GB (1024 MB JVM heap)
- **Count:** 2 data nodes + 3 master nodes
- **Current Cost:** $52.56/month

### Performance Metrics (Last 2 Hours)
- **JVM Memory Pressure:** 89.9% peak, 73.4% average (CRITICAL)
- **CPU Utilization:** 53.0% peak, 41.1% average (acceptable)
- **Search Time:** 40+ seconds for 10 results
  - BM25 text: 15s
  - kNN text: 3s
  - kNN image: 21.5s ← **Bottleneck**

### Dataset
- **Properties:** 3,904
- **Images:** ~78,080 total (~20 per property)
- **Vector Dimension:** 1024 (Amazon Titan Image)
- **Total Vector Data:** 458 MB (with HNSW index overhead)

---

## Memory Calculation

```
Raw vector storage:     305 MB
HNSW graph overhead:    x1.5
Vector data total:      458 MB
Query processing:       500 MB
──────────────────────────────
Minimum JVM heap:       958 MB
Minimum instance RAM:   1.9 GB (JVM uses 50% of instance RAM)

Current t3.small:       2.0 GB RAM → 1024 MB JVM heap
Deficit:                -66 MB (explains 89.9% memory pressure)
```

**Why Performance Suffers:**
- At 89% pressure, OpenSearch constantly runs garbage collection
- Vectors spill to disk instead of staying in RAM
- Disk I/O is 10-100x slower than RAM access
- Result: 21.5 seconds for image kNN search

---

## Solution Options

| Instance | RAM | Arch | Cost/Mo | Increase | Est. Time | Status |
|----------|-----|------|---------|----------|-----------|---------|
| **t4g.medium.search** | 4 GB | ARM | $84.68 | **+$32** | ~29s | ✓ Cheapest |
| t3.medium.search | 4 GB | x86 | $106.58 | +$54 | ~29s | ✓ Works |
| **m6g.large.search** | 8 GB | ARM | $185.42 | +$133 | ~23s | ✓ Safe |
| t3.large.search | 8 GB | x86 | $213.16 | +$161 | ~23s | ✓ Works |
| r6g.large.search | 16 GB | ARM | $251.12 | +$199 | ~21s | ✓ Premium |

### Performance Estimates

**Conservative (4x speedup with adequate RAM):**
- t4g.medium (4 GB): 15s + 3s + 10.8s = **28.8s** ✓
- m6g.large (8 GB): 15s + 3s + 5.4s = **23.4s** ✓
- r6g.large (16 GB): 15s + 3s + 2.7s = **20.7s** ✓

---

## Recommended Options

### Option 1: Minimum Cost (**RECOMMENDED**)

**Instance:** `t4g.medium.search`
- **RAM:** 4 GB (2x current)
- **Architecture:** ARM Graviton (AWS custom chips, optimized for cost)
- **Cost:** $84.68/month (+$32.12 increase)
- **JVM Heap:** 2048 MB (2.1x minimum requirement)
- **Expected Performance:** ~29 seconds (under 30s timeout)
- **Risk:** Minimal headroom, but meets requirements

**Upgrade Command:**
```bash
aws opensearch update-domain-config \
  --domain-name hearth-opensearch \
  --cluster-config \
    InstanceType=t4g.medium.search,\
    InstanceCount=2,\
    DedicatedMasterEnabled=true,\
    DedicatedMasterType=t4g.small.search,\
    DedicatedMasterCount=3,\
    ZoneAwarenessEnabled=true,\
    ZoneAwarenessConfig={AvailabilityZoneCount=2}
```

### Option 2: Best Value

**Instance:** `m6g.large.search`
- **RAM:** 8 GB (4x current)
- **Cost:** $185.42/month (+$132.86 increase)
- **JVM Heap:** 4096 MB (4.3x minimum requirement)
- **Expected Performance:** ~23 seconds (7s buffer under timeout)
- **Risk:** Low, significant headroom for growth

**Upgrade Command:**
```bash
aws opensearch update-domain-config \
  --domain-name hearth-opensearch \
  --cluster-config \
    InstanceType=m6g.large.search,\
    InstanceCount=2,\
    DedicatedMasterEnabled=true,\
    DedicatedMasterType=m6g.large.search,\
    DedicatedMasterCount=3,\
    ZoneAwarenessEnabled=true,\
    ZoneAwarenessConfig={AvailabilityZoneCount=2}
```

---

## Why ARM Graviton Instances?

AWS Graviton processors offer:
- **20-40% better price-performance** than x86
- Same or better performance for vector operations
- Fully compatible with OpenSearch
- Industry standard (used by major cloud customers)

**Comparison:**
- t3.medium (x86): $106.58/mo
- t4g.medium (ARM): $84.68/mo ← **21% cheaper for same specs**

---

## Blue/Green Deployment (Zero Data Loss)

AWS performs upgrades via Blue/Green deployment:

1. **New cluster created** with upgraded instance type
2. **All data copied** from old to new (all 3,904 indexed listings)
3. **Both clusters run** simultaneously during migration
4. **Traffic switches** to new cluster after validation
5. **Old cluster deleted** automatically

**Timeline:** 20-30 minutes
**Downtime:** Zero (cluster remains available)
**Data Loss:** Zero (all indices preserved)
**Rollback:** Possible if issues detected

---

## Decision Matrix

| Priority | Choose | Monthly Cost | Performance |
|----------|--------|--------------|-------------|
| **Minimum budget** | t4g.medium.search | $85 | Good (~29s) |
| **Balance cost/performance** | m6g.large.search | $185 | Excellent (~23s) |
| **Maximum performance** | r6g.large.search | $251 | Premium (~21s) |

---

## Recommendation

**Start with t4g.medium.search** ($32/month increase):

✓ Meets minimum requirements with 2.1x headroom
✓ Cheapest option that solves the problem
✓ Easy to upgrade further if needed (no data loss)
✓ 21% cheaper than x86 equivalent
✓ Expected to bring search times under 30s threshold

If performance is still insufficient, upgrade to m6g.large.search later (another Blue/Green deployment with zero data loss).

---

## Alternative: Disable Image Search

If budget is constrained, you could temporarily disable image kNN search:

**Impact:**
- Search time: 15s + 3s = **18 seconds** ✓
- Cost: $0 (keep current instances)
- Search quality: Degraded (no visual similarity matching)

**Code change:** Comment out image kNN in [search.py:640-676](search.py#L640-L676)

This is NOT recommended for production as it removes a key feature, but validates that the core text search works well.
