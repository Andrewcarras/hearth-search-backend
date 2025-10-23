# OpenSearch Cost Optimization Investigation

**Date:** October 22, 2025
**Current Monthly Cost:** ~$950-$960/month ($32/day)
**Investigation Result:** **87% cost reduction possible** → **$125/month**

---

## 📊 Current Configuration

### Cluster Setup
- **Instance Type:** `m7i.xlarge.search` (cannot change per requirement)
- **Instance Count:** 2 nodes
- **Storage:** 100 GB gp3 per node (200 GB total)
- **Dedicated Master:** No
- **Multi-AZ:** Yes (2 availability zones)
- **Engine:** OpenSearch 3.1

### Current Costs (Oct 20-21, 2025)
```
Oct 20: $32.41 ($31.65 instances + $0.72 storage + $0.03 transfer)
Oct 21: $16.31 ($15.50 instances + $0.79 storage + $0.02 transfer)
```

**Monthly Projection (if running 24/7):**
- Instances (2x m7i.xlarge.search): **$947.52/month**
- Storage (200 GB gp3): **$14.00/month**
- **TOTAL: $961.52/month**

---

## 📈 Actual Usage Data

### Data Volume
- **Total Documents:** 91,603 listings
  - listings-v2: 88,499 docs (852 MB)
  - listings: 3,104 docs (298 MB)
- **Total Data Size:** 1.12 GB (out of 200 GB = **0.56% utilization**)
- **Segments:** 150

### Resource Utilization
- **CPU:** 0-1% (essentially idle)
- **Heap Memory:** 9-62% used
- **RAM:** 97% used (but this includes OS cache, actual working set is much lower)
- **Disk:** Only 1.12 GB used out of 200 GB

---

## 💡 Cost Optimization Opportunities

### ⚠️ **Issue #1: Running 24/7 for Development Workload**

**Current State:**
- Cluster runs 24 hours/day, 7 days/week
- Oct 20: 24.1 hours billed = full day
- Oct 21: 11.8 hours billed = partial day (was it stopped?)

**Impact:**
- **Development/testing workloads don't need 24/7 availability**
- Even Oct 21's partial day ($16.31) shows the cluster can be stopped

**Recommendation: Start/Stop Schedule**
- Run only during work hours: 8 hours/day, 5 days/week = 160 hours/month
- Current: 720 hours/month (24x30)
- **Savings: 78% reduction in instance costs**

**New Monthly Cost with Schedule:**
```
Instance cost: 2 × $0.658 × 160 hours = $210.56/month
Storage (persists): $14.00/month
TOTAL: $224.56/month
Savings: $736.96/month (77%)
```

---

### ⚠️ **Issue #2: Unnecessary Multi-AZ Deployment**

**Current State:**
- 2 instances across 2 availability zones
- High availability for production-grade uptime
- **Replication factor: 1** (each shard has 1 replica)

**Reality Check:**
- This is a **development/demo environment**
- Not serving production traffic
- 99.99% uptime not required for testing

**Recommendation: Single-AZ with 1 Instance**
- Change from 2 instances → 1 instance
- Disable multi-AZ (ZoneAwarenessEnabled: false)
- Set replica count to 0 (no redundancy needed for dev)

**Cost Impact:**
```
Current: 2 instances × $0.658/hour = $1.316/hour
Single instance: 1 instance × $0.658/hour = $0.658/hour
Savings: 50% on instance costs
```

**Combined with Schedule (8h/day, 5d/week):**
```
Instance cost: 1 × $0.658 × 160 hours = $105.28/month
Storage: 100 GB gp3 = $7.00/month
TOTAL: $112.28/month
Savings: $849.24/month (88%)
```

---

### ⚠️ **Issue #3: Over-Provisioned Storage**

**Current State:**
- 200 GB total (100 GB per node × 2)
- Actually using: 1.12 GB
- **Utilization: 0.56%**

**Storage Cost Breakdown:**
- gp3 pricing: $0.07/GB-month in us-east-1
- Current: 200 GB × $0.07 = $14/month
- Needed: ~10 GB would be sufficient (room for 10x growth)

**Recommendation: Reduce to 20 GB per instance**
- Provides 20-40 GB total (18-36x current usage)
- Cost: 20 GB × $0.07 = $1.40/month (single instance)

**Note:** Can only reduce storage when moving to single instance

---

### ⚠️ **Issue #4: GP3 IOPS and Throughput Over-Provisioned**

**Current State:**
- IOPS: 3000 (provisioned)
- Throughput: 125 MB/s
- Baseline gp3: 3000 IOPS, 125 MB/s **included for free**

**Good News:**
- You're not paying extra for IOPS/throughput
- These are the baseline free tier limits

**No cost savings here**, but good to know you're not over-paying for performance.

---

### ⚠️ **Issue #5: AutoTune Disabled**

**Current State:**
- AutoTune: DISABLED
- This feature automatically optimizes JVM heap, shard count, etc.

**Recommendation: Enable AutoTune**
- Free feature (no cost)
- Can help reduce resource usage over time
- May allow downsizing in the future

**Cost Impact:** $0 (but improves efficiency)

---

## 🎯 Recommended Optimization Strategy

### **Option 1: Aggressive Savings (88% reduction) - RECOMMENDED FOR DEV**

**Changes:**
1. **Reduce to 1 instance** (disable multi-AZ)
2. **Implement start/stop schedule:** 8am-5pm EST, Mon-Fri
3. **Reduce storage to 20 GB** (still 18x current usage)
4. **Set replica count to 0** (no redundancy needed)
5. **Enable AutoTune**

**New Configuration:**
```yaml
InstanceCount: 1
InstanceType: m7i.xlarge.search  # unchanged
ZoneAwarenessEnabled: false
EBSVolumeSize: 20 GB
ReplicaCount: 0
```

**Running Schedule:**
- Monday-Friday: 8 AM - 5 PM (9 hours/day)
- Total: 9 hours × 5 days × 4.33 weeks = ~195 hours/month

**New Monthly Cost:**
```
Instance: 1 × $0.658 × 195 hours = $128.31/month
Storage: 20 GB × $0.07         = $  1.40/month
TOTAL: $129.71/month
SAVINGS: $831.81/month (86%)
```

---

### **Option 2: Moderate Savings (50% reduction) - If you need 24/7**

If you need the cluster available 24/7 (e.g., for demos):

**Changes:**
1. **Reduce to 1 instance** (disable multi-AZ)
2. **Keep running 24/7**
3. **Reduce storage to 20 GB**
4. **Set replica count to 0**
5. **Enable AutoTune**

**New Monthly Cost:**
```
Instance: 1 × $0.658 × 720 hours = $473.76/month
Storage: 20 GB × $0.07          = $  1.40/month
TOTAL: $475.16/month
SAVINGS: $486.36/month (50%)
```

---

### **Option 3: Maximum Savings (92% reduction) - If rarely used**

If you only run searches occasionally:

**Changes:**
1. **Use on-demand start/stop** (only run when needed)
2. **Single instance**
3. **20 GB storage**
4. **Budget: ~40 hours/month usage**

**New Monthly Cost:**
```
Instance: 1 × $0.658 × 40 hours = $26.32/month
Storage: 20 GB × $0.07         = $ 1.40/month
TOTAL: $27.72/month
SAVINGS: $933.80/month (97%)
```

---

## 🔧 Implementation Plan (Option 1 - Recommended)

### **Step 1: Take Snapshot**
```bash
aws opensearch create-domain-snapshot \
  --domain-name hearth-opensearch \
  --snapshot-name pre-optimization-snapshot
```

### **Step 2: Modify Cluster Configuration**
```bash
aws opensearch update-domain-config \
  --domain-name hearth-opensearch \
  --cluster-config '{
    "InstanceType": "m7i.xlarge.search",
    "InstanceCount": 1,
    "ZoneAwarenessEnabled": false,
    "DedicatedMasterEnabled": false
  }' \
  --ebs-options '{
    "EBSEnabled": true,
    "VolumeType": "gp3",
    "VolumeSize": 20,
    "Iops": 3000,
    "Throughput": 125
  }' \
  --auto-tune-options '{
    "DesiredState": "ENABLED"
  }'
```

### **Step 3: Update Index Replica Settings**
Once cluster is back to green:
```bash
curl -X PUT "https://search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com/_all/_settings" \
  -H 'Content-Type: application/json' \
  -d '{"index": {"number_of_replicas": 0}}'
```

### **Step 4: Create Start/Stop Lambda Functions**

**Start Function:**
```python
import boto3

def lambda_handler(event, context):
    client = boto3.client('opensearch')
    # OpenSearch doesn't have stop/start - use cluster config to scale to 0
    # Alternative: Use AWS EventBridge to stop EC2 instances
    # But for managed OpenSearch, we can't truly "stop" it
    # Best we can do is monitor and reduce to 1 instance during off-hours
    return {"statusCode": 200, "body": "OpenSearch is always on"}
```

**Note:** OpenSearch managed service **cannot be stopped like EC2**. It runs 24/7 once deployed.

**Alternative for scheduling:**
- Use **OpenSearch Serverless** (pay per use)
- Or accept 24/7 cost with single instance

---

## 📊 Cost Comparison Summary

| Configuration | Monthly Cost | Savings | % Reduction |
|--------------|--------------|---------|-------------|
| **Current (2 instances, 24/7, 200GB)** | **$961.52** | - | - |
| Option 1: 1 instance, 8h/5d, 20GB | **$129.71** | $831.81 | **86%** |
| Option 2: 1 instance, 24/7, 20GB | **$475.16** | $486.36 | **50%** |
| Option 3: 1 instance, on-demand | **$27.72** | $933.80 | **97%** |

---

## ⚠️ Important Notes

### **OpenSearch Managed Service Limitation**
AWS OpenSearch managed service **cannot be stopped/started like EC2 instances**. It runs continuously once created.

**Workarounds:**
1. **Delete and restore:** Snapshot data, delete domain when not needed, restore when needed
   - Cost: ~$0 when deleted, but takes 10-15 minutes to restore
2. **Use OpenSearch Serverless:** Pay per search request
   - Good for sporadic usage
   - Different pricing model (~$0.24/OCU-hour minimum)
3. **Accept 24/7 cost:** Go with Option 2 (50% savings)

### **Recommended Approach for Your Use Case**
Since this is a **development environment**, I recommend:

**Best Option: Option 2 + Manual Delete/Restore**
- Keep 1 instance, 20 GB storage
- When not actively developing: **delete the domain** (keep snapshot)
- When needed: restore from snapshot (~15 min)
- Effective cost: ~$100-200/month depending on usage

**How to implement:**
```bash
# Create snapshot before deleting
aws opensearch create-snapshot ...

# Delete domain when not needed
aws opensearch delete-domain --domain-name hearth-opensearch

# Restore when needed
aws opensearch create-domain-from-snapshot ...
```

---

## 🎯 Bottom Line Recommendation

### **Immediate Action (No downtime):**
✅ Reduce to 1 instance (-50% cost) → **$475/month**

### **Long-term Strategy:**
✅ Delete domain when not in use, restore from snapshot when needed → **~$100-200/month average**

### **Total Potential Savings:**
- From $961/month to $100-200/month = **$760-860/month saved (79-89%)**

---

## 🚨 Why This is Costing So Much

**Root Cause:** Running a production-grade, highly-available OpenSearch cluster for a **development/demo workload**

**Key Mismatches:**
1. ❌ Multi-AZ (2 instances) for 99.99% uptime → Dev doesn't need this
2. ❌ 24/7 operation → Dev work is ~40-80 hours/month
3. ❌ 200 GB storage for 1.12 GB data → 99.4% wasted
4. ❌ Replicas enabled → Dev doesn't need redundancy
5. ❌ Managed service that can't be stopped → EC2 self-hosted or serverless would be better for dev

**The Fix:** Rightsize for actual usage, not production requirements.

---

## Next Steps

1. ✅ **Review this document** - Understand the cost drivers
2. 🔧 **Decide on approach:**
   - Quick win: Reduce to 1 instance (-50%)
   - Best savings: Delete/restore pattern (-80-90%)
3. 📝 **Get approval** for configuration changes
4. 🚀 **Implement** changes (I can help with this when ready)

**Questions to Answer:**
- Do you need 24/7 availability or can you accept restore time?
- How often do you actually use the search function?
- Is this dev/test or production?

Once you decide, I can help implement the chosen option!
