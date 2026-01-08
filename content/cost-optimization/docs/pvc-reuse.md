# **PVC Reuse for Improved Cost Performance**

## Overview

PVC (Persistent Volume Claim) Reuse is a Spark feature introduced in Spark 3.2 (EMR 6.6+) that improves job stability by preserving shuffle data on PVCs throughout an entire job runtime. When an executor pod terminates and is replaced, the new executor can reattach to the existing PVC and reuse shuffle data, avoiding costly recomputation and shuffle fetch failures.

## Use Cases and Recommendations

### ✅ When to Use PVC Reuse

1. **Shuffle-heavy workloads** with frequent shuffle fetch failures
2. **Workloads on Spot instances** with less pod churn or node interruptions
3. **Jobs with expensive recomputation** (multi-stage aggregations, joins)
4. **Medium-scale workloads** (< 30k concurrent executors) on stable-sized Spark clusters

### ❌ When NOT to Use PVC Reuse

1. **With DRA + EBS storage** (use EFS/FSx instead if DRA is needed)
2. **Short-running tasks** where recompute time < 1 minute
3. **Mission-critical jobs** requiring 100% reliability (use Remote Shuffle Service instead, e.g., Apache Celeborn)
4. **Extremely large scale** (> 30k concurrent executors)

## How PVC Reuse Improves Job Performance

### Problem Without PVC Reuse

When an executor pod terminates (due to Out-Of-Memory, Spot interruption, or scaling), its shuffle data could be deleted due to the loss of the executor pod. If you have enabled shuffle tracking (`spark.dynamicAllocation.shuffleTracking.enabled`), shuffle data could be retained on a local disk attached to the EC2 node, except in the event of "Node Termination" by Karpenter consolidation or Spot Interruption.

This causes:

1. **Shuffle fetch failures** when a Spark job tries to read/write shuffle data associated with terminated executor(s)
2. **Expensive recomputation** of lost shuffle blocks
3. **Increased job runtime** or job failure
4. **Cascading failures** when multiple executors fail simultaneously

### Solution With PVC Reuse

- **Driver owns PVCs** instead of executor pods
- **PVCs persist** throughout the job lifetime, even when executors terminate
- **New executors reattach** to existing PVCs and reuse shuffle data in `/${spark.local.dir}/blockmgr-<UUID>/`
- **Reduces shuffle fetch failures** by maintaining high data availability

<p align="center">
  <img src="../resources/images/pvc_reuse.gif" width="640" height="400"/>
</p>

## Alternative Solutions

If PVC reuse doesn't meet your requirements:

| Solution | Benefit | Trade-off | Reliability Rate |
|----------|---------|-----------|------------------|
| **Node Decommissioning** | Proactively copies shuffle data before pod termination | Increases executor pod's graceful termination period in order to complete data migration. Higher compute cost with a risk of unfinished data migration | < 50% |
| **Remote Shuffle Service** | Decouples data storage from compute. Minimizes storage cost while maximizing the compute cost saving in Spark | Additional add-on cost and maintenance overhead in EKS | 95% - 100% |


## Performance Testing Results

### Success Rate and Reliability

We conducted an internal large-scale load test with a high concurrent submmission rate (2200+ jobs/minute). Gradually ramp-up in 2.5-minute from 0 to 300 users against 10 virtual clusters on a single EKS cluster. The test results [in Appendix](#appendix-load-test-details) prove:

- **50% - 80% success rate** in preventing shuffle-related failures
- **Not 100% reliable** - cannot guarantee job completion in all scenarios
- Works best for medium-scale workload with **moderate executor churn**

!!! warning "Reliability Trade-off"
    PVC reuse improves stability but does not guarantee 100% job success. For large-scale or mission-critical workloads, especially shuffle-heavy jobs, consider the [Remote Shuffle Service (RSS) solution](https://github.com/aws-samples/emr-remote-shuffle-service) with nearly 100% job stability.

### Performance Bottleneck: EBS Reattachment Latency

The primary performance trade-off is **EBS volume detach/reattach latency**:

| Scenario | Latency |
|----------|---------|
| Best case | 30 seconds |
| Average | 2-5 minutes |
| Worst case | 10 minutes |

**PVC Reuse Recovery Timeline:**
```
Executor failure (seconds)
  → Pod termination (seconds)
  → PVC detach from old pod (seconds to minutes)
  → New pod scheduled (seconds to minutes)
  → PVC attach to new node (seconds to minutes)
  → Pod ready (seconds)
  → Task continues with existing shuffle data
```

**Total recovery time:** 30 seconds to 10 minutes (including cold start on a newly created node)

### When PVC Reuse Improves Performance

PVC reuse provides performance benefits when:

✅ **Shuffle data is large** (multiple GBs per job stage)

✅ **Recomputation is expensive** (complex transformations, multiple stages)

✅ **Shuffle fetch failures are frequent**

✅ **Task duration > 2-5 minutes** (recompute time > PVC detach plus reattach time)

### When Recomputation is Faster

For certain Spark jobs, recomputation can be faster than the PVC reuse process:

❌ **Short-running stages** (< 2 minutes)

❌ **Small shuffle partitions** (< 1 GB)

❌ **Simple transformations**

❌ **Random fetch failures** (increase `spark.shuffle.io.retryWait` & `spark.shuffle.io.maxRetries`)

**Recommendation:** Benchmark your selected workload to compare recomputation latency vs. PVC reattachment time.

## Configuration

### Basic Setup (Spark 3.2+, EMR 6.6+)

If your Spark version < 3.4, do not use PVC reuse until upgraded to 3.4+.

```bash
"spark.kubernetes.driver.ownPersistentVolumeClaim": "true",
"spark.kubernetes.driver.reusePersistentVolumeClaim": "true",
"spark.shuffle.sort.io.plugin.class": "org.apache.spark.shuffle.KubernetesLocalDiskShuffleDataIO"
```

### Enhanced Setup (Spark 3.4+, EMR 6.12+)

Since version 3.4, Spark counts the total number of PVCs the job can have, and holds new executor creation if the driver owns the maximum number of PVCs. This helps with the transition of the existing PVC from one executor to another executor.

For PVC-oriented executor allocation with improved stability:

```bash
"spark.kubernetes.driver.waitToReusePersistentVolumeClaim": "true"
```

### PVC Volume Configuration

This setting creates a pod-level EBS Volume PVC. The dynamic PVC provioning happens when the job starts.
```bash
"spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.options.claimName": "OnDemand"
```
Use `gp3` storage class with appropriate IOPS and throughput settings for shuffle-heavy workloads. Ensure your storage class has `reclaimPolicy: Delete`.
```bash
"spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.mount.readOnly": "false"
"spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.options.storageClass": "gp3"
"spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.options.sizeLimit": "20Gi"
"spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.mount.path": "/data1"
```
!!! tip "PVC Type Consideration"
    To avoid EBS performance limitations, pre-create shareable storage (EFS or FSx). Reconfigure PVC reuse via a static provisoning like this: **spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.options.claimName: example-fsx-pvc**


### Executor Registration Tuning (OPTIONAL)

!!! warning "Advanced Configuration - Use with Caution"
    Improper configuration can lead to jobs starting with insufficient resources or hanging indefinitely. Only adjust after thorough testing and monitoring.

Since EBS volume reattachment can take 2-5 minutes on average, you may need to adjust Spark's executor registration timeouts. **Understand the trade-offs before making changes.**

**Default Behavior:**

- `spark.scheduler.minRegisteredResourcesRatio`: **0.8** (80% of executors must register)
- `spark.scheduler.maxRegisteredResourcesWaitingTime`: **30s** (maximum wait time)

**Impact of Changes:**

- **Lower ratio**: Job starts faster but with fewer executors → may run slowly or fail
- **Higher timeout**: Job waits longer before start → may mask infrastructure or high concurrency issues

**Adjust only if:**

- ✅ You've confirmed frequent job failures specifically during PVC reattachment
- ✅ Your workload tolerates starting with fewer executors
- ❌ Don't adjust for time-sensitive or mission-critical jobs

**Example Configuration (use cautiously):**

```bash
# WARNING: Starting with fewer executors may impact app performance
"spark.scheduler.minRegisteredResourcesRatio": "0.6"

# WARNING: Long waits may mask infrastructure problems
"spark.scheduler.maxRegisteredResourcesWaitingTime": "1800s"
```

**Recommendation:** Start with smaller changes (e.g., `0.7` ratio, `300s` timeout) and adjust incrementally based on observed behavior.

### Executor Pod's Termination Grace Period (OPTIONAL)

!!! danger "Advanced Configuration - Extreme Caution Required"
    Reducing grace period can cause **data loss, failed shutdowns, and corrupted state**. This controls how long a pod has to shut down cleanly before being forcefully killed.

The default Kubernetes pod's attribute `terminationGracePeriodSeconds` is **30 seconds**. Reducing this speeds up PVC detachment but **comes with risks**.

**Risks by Grace Period:**

- **30s (default)**: ✅ Safe for most workloads
- **15-20s**: ⚠️ May interrupt task completion, incomplete cleanup
- **< 15s**: ❌  Risk of data loss, corrupted state

**For most workloads, keep the default 30 seconds.** Only reduce if you've confirmed through testing that executors shut down cleanly in less time, or ensure your job can tolerate abrupt terminations.

-EXAMPLE: executor-pod-template.yaml-

```yaml
apiVersion: v1
kind: Pod
spec:
  # Recommended: 20s for medium workloads, avoid going below 15s
  terminationGracePeriodSeconds: 20
```

## Key Considerations

### 1. Dynamic Resource Allocation (DRA)

**DRA Amplifies PVC Reuse Slowness**: Try **NOT** to use PVC reuse with DRA when you have a large-scale workload facing shuffle fetch failures. The high pod churn triggered by Spark's DRA amplifies EBS API bottlenecks and slows down the PVC reuse process. If possible, disable DRA or reduce the frequency of pod scaling events. Alternatively, use the [static PVC provisioning solution](../../storage/docs/spark/fsx-lustre.md#static-provisioning) backed by EFS or FSx AWS services.

**Solutions for DRA + PVC Reuse:**

Use storage with multi-attach support (ReadWriteMany):

| Storage | Performance Impact | Use Case |
|---------|-------------------|----------|
| **Amazon EFS** | 30-50% slower shuffle I/O | Medium-scale DRA workloads |
| **FSx for Lustre** | High-throughput (100+ GB/s) | Large-scale, performance-critical DRA workloads |

### 2. Application Data Cache Loss

By Spark's design, executor pod termination triggers **ShutdownHookManager** cleanup:

**Deleted:** `/${spark.local.dir}/spark-<UUID>/*` (JARs, Python resources, temp app data, or S3 fetched data)

**Preserved:** `/${spark.local.dir}/blockmgr-<UUID>/*` (spill & shuffle data)

**Performance Impact:**

- New executors must **re-download non-shuffle application data** cached by the previous executors
- Adds **10-60 seconds latency** per executor restart
- Impacts jobs with large broadcast variables (>100 MB)

**Mitigation (not ideal):** Pre-bake application files into a custom Docker image or a node's AMI image, or disable the fetch cache to accept the overhead.

```bash
# Bake application files into Docker images
spark.files=/local-path/to/pre-cache-on-volume
spark.jars=/local-path/to/pre-load-jars/* 

# Disable the caching optimizations
spark.files.useFetchCache=false
```

### 3. Pod Churn Amplification

High pod churn amplifies EBS API bottlenecks and slows PVC reattachment:

**Sources of pod churn:**

- Karpenter consolidation
- Spark Dynamic Resource Allocation
- Frequent Spot interruptions
- Aggressive auto-scaling policies

**Mitigation strategies:**

- Reduce DRA scaling frequency
- Increase `spark.dynamicAllocation.executorIdleTimeout` (default 60s)
- (Optional) Use less aggressive Karpenter consolidation to stabilize the Spark cluster, such as `WhenEmpty` instead of `WhenEmptyOrUnderutilized` consolidation rule for executor nodes. However, the compute cost will be increased.

---

## Monitoring and Validation

### Monitor PVC Status

```bash
# Check bound PVCs (successfully attached)
kubectl get pvc -A | grep Bound | wc -l

# Check pending PVCs (waiting for attachment)
kubectl get pvc -A | grep Pending | wc -l
```

High pending PVC count indicates EBS attachment bottlenecks.

### Verify Shuffle Data Reuse in Spark Logs

**Without PVC reuse** (recomputation triggered):
```
22/12/25 23:25:07 ERROR TaskSetManager: FetchFailed(BlockManagerId(...), shuffleId=1, mapId=42, reduceId=15, message=...)
22/12/25 23:25:08 INFO DAGScheduler: Resubmitting ShuffleMapStage 1 (map) due to fetch failure
22/12/25 23:25:08 INFO DAGScheduler: Recomputing lost blocks...
```

**With PVC reuse** (successful recovery):
```
22/12/25 23:42:50 INFO ShuffleStatus: Recover BlockManagerId(fallback, remote, 7337, None)
22/12/25 23:42:50 DEBUG BlockManagerMasterEndpoint: Received shuffle index block update for 0 52, updating
22/12/25 23:42:51 INFO Executor: Reusing shuffle data from /data1/blockmgr-abc123/
```

### Monitor EBS CSI Controller Metrics

Track PVC attachment performance. For more details, see the [pre-built Grafana dashboard examples](https://github.com/aws-samples/load-test-for-emr-on-eks/tree/emr-jobrun-loadtest/grafana/dashboard-template).

```bash
# Enable EBS CSI controller metrics
aws eks update-addon --cluster-name ${CLUSTER_NAME} \
  --addon-name aws-ebs-csi-driver \
  --configuration-values '{"controller":{"enableMetrics":true}}'

# Track the per-second rate of EBS CSI node operations when attaching volumes
sum(rate(csi_operations_seconds_count{driver_name="ebs.csi.aws.com", method_name=~"/csi.v1.Node/NodePublishVolume"}[5m]))
```

---

# Appendix: Load Test Details

### GitHub Project: [load-test-for-emr-on-eks](https://github.com/aws-samples/load-test-for-emr-on-eks/tree/emr-jobrun-loadtest)

- **Main branch** - load test tools for Spark Operator load test

- **emr-jobrun-loadtest branch** -  load test tools for job submissions via the job run API

### EBS API Rate For The Test

Test results are based on the following API rates, supporting **maximum 30,000 concurrent EBS Volumes/PVCs reuse, 60,000 concurrent EBS without PVC reuse**:

| API Name | Rate Applied for Load Test |
|----------|----------------------------|
| CreateVolume | L200 (burst) / 100 (qps) |
| DetachVolume | L100 / 75 |
| AttachVolume | L100 / 75 |
| DeleteVolume | L150 / 60 |
| DescribeSubnets | L135 / 70 |
| DescribeInstances | L140 / 60 |
| RunInstances | L1000 / 4 |

**Recommendation:**

- Request EBS API limit increases through AWS Support before large-scale tests or deployments
- Cautiously increase the API QPS rates in the EBS CSI controller. See the example in [patch-csi-controller.sh](https://github.com/aws-samples/load-test-for-emr-on-eks/blob/emr-jobrun-loadtest/resources/ebs/patch_csi-controller.sh)

### EBS Volume Attachment Limit Per Node

Most Nitro instances support a **maximum of 27 EBS volumes** per node ([AWS documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/volume_limits.html)).

**Best practices:**

- Limit executor node pool to **≤ 16xlarge** instance size
- Configure executor sizing (CPU & memory size) to keep **< 27 executor pods per node**
- Example: 3 cores + 6GB RAM per executor = max 22 executors on a 64-core EC2 node

### Load Test Result

| Test Case | Compute Provisioner | Job Submission Rate (per min) | Test Period | Spawn Rate | Total VCs | Actual Run | Max Concurrent Jobs | Total Jobs Submitted | Executors per Job | Total Job Nodes | Max Concurrent Executor Pods (PVCs) | Job Runtime |
|-----------|---------------------|-------------------------------|-------------|------------|-----------|------------|---------------------|---------------------|-------------------|-----------------|-------------------------------------|-------------|
| Baseline without PVC (Frequent Shuffle Fetch Failure) | Karpenter | 1,558 | 60 mins | 2 | 10 | 2h 33m | 3,260 | 240,503 | 30 | 2,113 | 66,656 | 15-122 mins |
| PVC reuse with Frequent Shuffle Fetch Failure | Karpenter | 2,232 | 60 mins | 2 | 10 | 4h 6m | 3,784 | 253,373 | 30 | 1,046 | 30,797 | 10-140 mins |

### TPCDS Job Performance Test Result

| Test Case | Notes | Query | Exec Time (s) | Total Runtime (s) |
|-----------|-------|-------|---------------|-------------------|
| **Baseline** (node interruption without PVC) | Spot interruption without DRA (30 executors) | q24a-v2.4 | 161.04 | |
| | | q24b-v2.4 | 79.73 | |
| | | q4-v2.4 | 14.91 | |
| | | q67-v2.4 | 768.61 | **1024.29** |
| Node interruption with PVC | | q24a-v2.4 | 19.55 | |
| | | q24b-v2.4 | 516.11 | |
| | | q4-v2.4 | 15.38 | |
| | | q67-v2.4 | 75.86 | **626.9** |
| **Baseline** (30 executors without PVC) | PVC reuse actually slowed down the job | q24a-v2.4 | 27.3 | |
| | | q24b-v2.4 | 79.92 | |
| | | q4-v2.4 | 15.8 | |
| | | q67-v2.4 | 316.85 | **439.87** |
| 30 executors with PVC | lost 100% exeuctors with slower PVC recovery | q24a-v2.4 | 23.87 | |
| | | q24b-v2.4 | 50.56 | |
| | | q4-v2.4 | 16.16 | |
| | | q67-v2.4 | 524.57 | **564.6** |
| **Baseline** (DRA without PVC) | PVC reuse + DRA | q24a-v2.4 | 24.93 | |
| | | q24b-v2.4 | 471.51 | |
| | | q4-v2.4 | 13.08 | |
| | | q67-v2.4 | **failed** | **509.52** |
| 30 executors with PVC | 75% job success rate | q24a-v2.4 | 39.36 | |
| | | q24b-v2.4 | **failed** | |
| | | q4-v2.4 | 13.05| |
| | | q67-v2.4 | 450.91| **463.96** |
