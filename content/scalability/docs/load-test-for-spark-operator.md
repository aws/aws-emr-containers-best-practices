# **Run Large Scale Jobs with EMR on EKS Spark Operator**

This scalability recommendation focuses on EMR on EKS Spark Operator performance in large-scale environments. It offers insights derived from extensive benchmarking and testing across various configurations and workloads. The study explores key factors influencing Spark Operator efficiency, including cluster setup, resource allocation, and job submission patterns.

Our findings provide a valuable reference for optimizing EMR Spark Operator workloads on Amazon EKS, addressing challenges unique to high-volume, distributed computing environments. The recommendations outlined here aim to help customers achieve a balance between performance, scalability, and resource utilization. By considering these best practices, organizations can enhance their EMR on EKS deployments, ensuring robust and efficient Spark job processing while managing infrastructure costs effectively. This overview serves as a foundation for IT professionals and data engineers seeking to maximize the potential of their Spark applications in cloud-native Kubernetes environments.

## Table of Contents
1. [Large Scale Load Benchmark](#large-scale-load-benchmark)
    - [Benchmark Results](#benchmark-results)
    - [Metrics Explanation](#metrics-explanation)
    - [Notes about the Limitations](#notes-about-the-limitations)
2. [Best Practices / Recommendations](#best-practices-recommendations-to-use-spark-operator-on-eks)
    - [1. Spark Operator Numbers](#1-spark-operator-numbers)
    - [2. Instance Sizes](#2-instance-sizes)
    - [3. Spark Operator Configuration](#3-spark-operator-configuration-best-practices)
    - [4. EKS Cluster Scaler & Scheduler](#4-eks-cluster-scaler-scheduler-setup)
        - [4.1 Autoscaler](#41-autoscaler)
        - [4.2 Karpenter](#42-karpenter)
        - [4.3 Binpacking Custom Scheduler](#43-binpacking-custom-scheduler)
    - [5. IP Address Utilization & Settings](#5-ip-address-utilization-settings)
        - [5.1 With EKS Autoscaler](#51-with-eks-autoscaler)
        - [5.2 With Karpenter Node Provisioner](#52-with-karpenter-node-provisioner)
    - [6. Config Maps and initContainers](#6-minimize-the-config-maps-and-initcontainers-spec)
3. [Appendix](#7-appendix)
    - [7.1 Artifact Reference](#71-artifact-reference)

## Large Scale Load Benchmark 

For these benchmarks, we tuned the following settings for EKS:

**EKS Cluster Configuration:**
- **EKS cluster version**: 1.30
- **Spark Operator version**: `emr-6.11.0 (v1beta2-1.3.8-3.1.1)`
  - The current version of EMR Spark Operator has limited API exposed for users to tune performance. In this article, we use the following setup for Spark Operators:
- **Pre-warmed the EKS control plane**
- Isolated operational services and Spark application pods
  - `controllerThreads=30` - Higher operator worker count than default 10
  - To minimize impacts caused by other services (e.g., Spark job pods, Prometheus pods), we allocated Spark Operator(s) and Prometheus operators to dedicated operational node groups
  - See details for Spark Operator(s) and Spark Job setup in the following best practices section

**Cluster Resource Utilization:**
- Tested with the following techniques and settings:
  - EKS Autoscaler or Karpenter
  - Binpacking strategy enabled and used with either Autoscaler or Karpenter

**Network Configuration:**
- The cluster resides in a VPC with 6 subnets (2 public subnets and 4 private subnets with S3 endpoint attached)
  - The 4 private subnets are allocated into 2 AZs evenly
  - All node groups are created in the 4 private subnets, and for each NodeGroup, the subnets associated are in the same AZ (e.g., NodeGroup-AZ1, NodeGroup-AZ2)

**Benchmark Test Job Specifications:**

| Component | Configuration |
|-----------|---------------|
| **Driver** | 1 Core, 512MB memory |
| **Executor** | 1 Core, 512MB memory each, 10 executors total |
| **Job Runtime** | 12-16 minutes (excluding submission & pod scheduling time) |
| **Job Script** | Stored in S3, submitted with `hadoopConf` and `sparkConf` configmaps |
| **Node Selector** | Enabled to ensure Spark jobs are assigned to Worker Node Groups |

*Note: Due to the default value of `spark.scheduler.minRegisteredResourcesRatio` = 0.8, Spark jobs will start running with a minimum of 8 executors allocated. [Reference documentation](https://spark.apache.org/docs/3.5.1/configuration.html#kubernetes:~:text=spark.scheduler.minRegisteredResourcesRatio)*

### Benchmark Results

<img src="https://github.com/aws/aws-emr-containers-best-practices/raw/main/content/scalability/docs/resources/images/EMR_Spark_Operator_Benchmark.png" alt="EMR Spark Operator Benchmark Results" style="width: 100%; height: auto;">

### Metrics Explanation 

| Metric | Description |
|--------|-------------|
| **Spark Operator Job Submission Rate (per EKS cluster)** | Average submitted jobs per minute (Total jobs submitted / Test time) |
| **Spark Operator Numbers** | Number of Spark operators used for the test |
| **Max Number of Active Jobs / Driver Pods** | Maximum number of Spark Driver pods running concurrently |
| **Spark Job Running Time** | Time spent on Spark job execution; varies based on testing job configuration to mimic real workloads |
| **Number of Worker Nodes** | Total worker instances created by EKS cluster (operational instances excluded) |
| **Number of Spark Jobs** | Total jobs submitted from client |
| **Number of Concurrent Pods** | Maximum number of Spark job pods (Drivers & Executors) running concurrently during testing |
| **API Server Request Latency - p99 (for create Pod calls)** | 99th percentile of API server response times for POST requests to create pods in an EKS cluster over the last 5 minutes |

### Notes about the Limitations

- **Pod templates not available**: Pod template support is not available in the current version. This feature has been added to the OSS Spark Operator [roadmap](https://github.com/kubeflow/spark-operator/issues/2193#:~:text=Pod%20template%20support%20(%5BFEATURE%5D%20Use%20pod%20template%20feature%20in%20spark%2Dsubmit%20for%20Spark%203.x%20applications%C2%A0%232101)). Users can only configure settings via the Spark job YAML file at the current stage.

- **Accurate concurrent job measurement**: With the property `spark.scheduler.minRegisteredResourcesRatio` having a default value of `0.8` for [KUBERNETES mode](https://spark.apache.org/docs/3.5.1/configuration.html#:~:text=spark.scheduler.minRegisteredResourcesRatio), it is difficult to get accurate numbers for how many Spark jobs are running with sufficient executor pods without code changes to Spark Operator internally or without Gang Scheduling enabled. From the benchmark results, for the metric `Max Jobs Concurrent Running`, we evaluate this by counting how many drivers are running and the ratio of `total_executor_pods_running` / `total_driver_pods_running`. If the ratio is greater than 8, we collect the `Max Driver Pods Concurrent Running` as `Max Jobs Concurrent Running`.

- **EC2 API limits**: Need to increase the bucket limit and refill rate for `DescribeInstances` (e.g., Bucket size: 140, Refill rate: 60). This issue has been observed with both Cluster Autoscaler and Karpenter.

- **Limited performance tuning parameters**: There are limited performance tuning parameters available for Spark Operator. For example, `bucketQPS` and `bucketSize` are hardcoded in the current version of Spark Operator.

- **Namespace monitoring limitation**: The current EMR Spark Operator version cannot handle a single operator monitoring multiple specified job namespaces. It can only work as one operator per job namespace or one operator for all namespaces. See [GitHub issue #2052](https://github.com/kubeflow/spark-operator/issues/2052). This limitation has been fixed in OSS V2.

## Best Practices / Recommendations to use Spark Operator on EKS

### 1. Spark Operator Numbers

The number of Spark Operators has a significant impact on the performance of submitting jobs from client to EKS cluster. Here are the recommendations when using multiple EMR Spark Operators on an EKS cluster:

#### 1.1 **Use Multiple Spark Operators for High-Volume Tasks**

For large-scale workloads, deploying multiple Spark Operators significantly improves performance. A single operator can handle about **20-30 task submissions per minute**. Beyond this rate, you'll see better results with multiple operators, especially before the submission workload hits the threshold of EKS etcd or API server limits.

With our testing job setup, for submission rates between **250-270 tasks per minute**, there is no significant performance difference between 10 or 15 Spark Operators overall. However, a lower operator count provides better stability than a higher operator count. This setup maintains high performance with minimal task failures (less than 0.1%).

!!! warning "Caution"
    Be cautious when exceeding 270 submissions per minute. We've observed increased failure rates regardless of the number of operators (10, 15, or 20).

The number of Spark operators may be impacted by the submission rate and job configurations. For example, Spark jobs with `initContainers` enabled will generate more events submitted to the API server from Spark Operators, causing the etcd database size to increase faster than jobs without `initContainers` enabled.

**Performance by Job Type:**

| Job Configuration | Jobs per Operator per Minute |
|-------------------|------------------------------|
| Without initContainers | 20-30 jobs/min |
| With initContainers | 12-18 jobs/min (varies by config) |

[^ back to top](#table-of-contents)

#### 1.2 **Balancing Operator Numbers for Long-Running Tests**

For extended operations (e.g., 200-minute tests), slightly fewer operators could be beneficial. This is represented by the API request latency, which shows a slight increase with more operators from the Spark Operator to the API server. This could be due to 10 operators placing less strain on the API server and etcd while maintaining good performance compared to 15 operators. We observed that the situation worsens further with 20 operators.

[^ back to top](#table-of-contents)

#### 1.3 **Do Not Use Too Few Operators for Large Workloads**

Be aware that if the number of Spark Operators is too small for large workloads (e.g., 5 operators for 250/min submission rate), it could cause Spark Operator throttling internally.

**Symptoms of Spark Operator throttling:**

- The number of jobs in `New` state (also known as `Null` state) or the number of jobs in `Succeeding` state keeps increasing, but the number of jobs in `Submitted` state is decreasing
- Additionally, you may see the Spark Operator metrics API providing incorrect data (e.g., the running application number is much less than the number of running Driver pods)

[^ back to top](#table-of-contents)

#### 1.4 **System Health Considerations**

Based on the given testing job, keep submission rates **below 250 tasks per minute** for optimal system health. Please be aware that the 250/min submission rate is a reference, as it can be impacted by other factors such as Spark job configmaps, pod size settings, etc.

**Monitor etcd size closely**, especially during high-volume operations. We've seen it exceed 7.4GB, risking going over the 8GB limit despite EKS's automatic compaction.

!!! note "Important"
    These recommendations are based on our specific test environment - your optimal settings may vary slightly based on your unique infrastructure and workload characteristics.

[^ back to top](#table-of-contents)

#### 1.5 **Formula to Determine the Number of Operators**

The number of EKS clusters required for Spark jobs is not directly related to the number of operators. If you set the right number of operators, the bottleneck will be on the API Server & etcd DB size. Use the formula below as a reference to determine how many EKS clusters are needed for your workload.

**Variables:**

| Variable | Description |
|----------|-------------|
| **submission_rate** | Average number of jobs submitted per minute |
| **avg_job_runtime** | Average job runtime in minutes |
| **avg_pods_per_job** | Average number of pods per job |
| **max_concur_pods** | Maximum number of pods that can run concurrently in the cluster |
| **buffer_ratio** | Recommended buffer to reserve cluster capacity (e.g., 0.1 = 10% buffer) |

**Formula:**

```
Est_cluster_numbers = (submission_rate × avg_job_runtime × avg_pods_per_job)
                      / (max_concur_pods × (1 - buffer_ratio))
```

**Example:**
- If submission_rate = 250 jobs/min
- avg_job_runtime = 15 minutes
- avg_pods_per_job = 11 (1 driver + 10 executors)
- max_concur_pods = 5000
- buffer_ratio = 0.1 (10% buffer)

```
Est_cluster_numbers = (250 × 15 × 11) / (5000 × 0.9) = 41,250 / 4,500 ≈ 9.2 clusters
```

You would need approximately **10 EKS clusters** for this workload.

!!! note "Important"
    This formula applies to EKS cluster environments as suggested in [EMR Spark Operator on EKS Benchmark Utility](https://github.com/aws-samples/load-test-for-emr-on-eks), with all recommendations in this article implemented. The number of EKS clusters needed varies based on pod sizes of Spark jobs; this formula is a starting point for rough estimation.

[^ back to top](#table-of-contents)

### 2. Instance Sizes

Based on testing benchmark results with the following instance types:

```
- m5.8xlarge  & r5.8xlarge
- m5.16xlarge
- m5.24xlarge & c5.metal
```

The experiment data reveals that **medium-sized EC2 instances** (8xlarge, 16xlarge) demonstrate more consistent and favorable performance in this Spark cluster configuration:

1. These instances maintain a more stable Driver/Total Pods ratio, typically below 12.6%
2. They show consistent performance across key metrics such as submission rates, job concurrency, and latency

Compared to larger instance types, medium-sized instances exhibit a better balance of efficiency and stability in this specific setup, suggesting they are well-suited for the current cluster configuration.

[^ back to top](#table-of-contents)

### 3. Spark Operator Configuration Best Practices

#### 3.1 Isolate Operational Services and Spark Application Pods

It is recommended to run operational services on dedicated NodeGroups from both performance and operational considerations.

**Recommended NodeGroup Configuration:**

| Service Type | Instance Type | Purpose |
|--------------|---------------|---------|
| **Spark Operators** | r5.4xlarge | Each Spark Operator on dedicated node |
| **Monitoring & Infrastructure** | r5.8xlarge | Prometheus, Binpacking, Karpenter (if used) |

**Implementation:** Use `podAntiAffinity` to ensure multiple Spark Operators are **NOT** allocated to the same operational node:

```yaml
nodeSelector:
  cluster-worker: "true"
  ## This label is managed on the EKS NodeGroup side.
  ## Define the nodeSelector label for Spark Operator pods
  ## to ensure all operators run on the operational NodeGroup.

## Use pod anti-affinity to ensure only one Spark Operator
## runs on each operational node
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchExpressions:
        - key: app.kubernetes.io/name
          operator: Exists
      topologyKey: "kubernetes.io/hostname"

webhook:
  enable: true
  nodeSelector:
    cluster-worker: "true"
    ## Define the nodeSelector label for Spark Operator webhook pods
    ## to ensure all operators run on the operational NodeGroup.
```

!!! note "Important"
    For other operational services like Prometheus, Binpacking, Node Scaler (CAS), and Karpenter, use the same approach to ensure these services run only in operational node group(s).

[^ back to top](#table-of-contents)

#### 3.2 Set Up `controllerThreads` with Higher Value

The default value of Spark Operator worker number (`controllerThreads`) is 10. Increasing it from 10 improves performance.

```yaml
# For workers of Spark Operator,
# we found that 30 provides better performance.
# This may vary based on different Spark job submission object sizes.
# We also tested very large numbers (e.g., 50/100),
# but it was not helpful for Operator performance since bucketSize and
# QPS are hardcoded. Higher worker counts do not improve performance.

controllerThreads: 30
```

[^ back to top](#table-of-contents)

#### 3.3 For Spark Job Drivers and Executor Pods

Similar to operational pods, utilize `nodeSelector` with labels to ensure Spark job pods are allocated to worker NodeGroups or Karpenter node pools.

```yaml
driver:
  nodeSelector:
    cluster-worker: "true"
    ## This label must match EKS nodegroup kubernetes label or Karpenter nodepool

executor:
  nodeSelector:
    cluster-worker: "true"
    ## This label must match EKS nodegroup kubernetes label or Karpenter nodepool
```

#### 3.4 **Implementing Retry Mechanisms**

Set up retry configurations to handle the small percentage of task failures that may occur. Unlike EKS StartJobRun API, setting up retry in Spark Operator does not impact overall performance based on load testing.

As a reference, we have the following configurations for test jobs:

```yaml
hadoopConf:
  # EMRFS filesystem
  fs.s3.customAWSCredentialsProvider: com.amazonaws.auth.WebIdentityTokenCredentialsProvider
  fs.s3.impl: com.amazon.ws.emr.hadoop.fs.EmrFileSystem
  fs.AbstractFileSystem.s3.impl: org.apache.hadoop.fs.s3.EMRFSDelegate
  fs.s3.buffer.dir: /mnt/s3
  fs.s3.getObject.initialSocketTimeoutMilliseconds: "2000"
  mapreduce.fileoutputcommitter.algorithm.version.emr_internal_use_only.EmrFileSystem: "2"
  mapreduce.fileoutputcommitter.cleanup-failures.ignored.emr_internal_use_only.EmrFileSystem: "true"

sparkConf:
  spark.executor.heartbeatInterval: 3000s
  spark.scheduler.maxRegisteredResourcesWaitingTime: 40s
  spark.network.timeout: 120000s
  # Required for EMR Runtime
  spark.driver.extraClassPath: /usr/lib/hadoop-lzo/lib/*:/usr/lib/hadoop/hadoop-aws.jar:/usr/share/aws/aws-java-sdk/*:/usr/share/aws/emr/emrfs/conf:/usr/share/aws/emr/emrfs/lib/*:/usr/share/aws/emr/emrfs/auxlib/*:/usr/share/aws/emr/security/conf:/usr/share/aws/emr/security/lib/*:/usr/share/aws/hmclient/lib/aws-glue-datacatalog-spark-client.jar:/usr/share/java/Hive-JSON-Serde/hive-openx-serde.jar:/usr/share/aws/sagemaker-spark-sdk/lib/sagemaker-spark-sdk.jar:/home/hadoop/extrajars/*
  spark.driver.extraLibraryPath: /usr/lib/hadoop/lib/native:/usr/lib/hadoop-lzo/lib/native:/docker/usr/lib/hadoop/lib/native:/docker/usr/lib/hadoop-lzo/lib/native
  spark.executor.extraClassPath: /usr/lib/hadoop-lzo/lib/*:/usr/lib/hadoop/hadoop-aws.jar:/usr/share/aws/aws-java-sdk/*:/usr/share/aws/emr/emrfs/conf:/usr/share/aws/emr/emrfs/lib/*:/usr/share/aws/emr/emrfs/auxlib/*:/usr/share/aws/emr/security/conf:/usr/share/aws/emr/security/lib/*:/usr/share/aws/hmclient/lib/aws-glue-datacatalog-spark-client.jar:/usr/share/java/Hive-JSON-Serde/hive-openx-serde.jar:/usr/share/aws/sagemaker-spark-sdk/lib/sagemaker-spark-sdk.jar:/home/hadoop/extrajars/*
  spark.executor.extraLibraryPath: /usr/lib/hadoop/lib/native:/usr/lib/hadoop-lzo/lib/native:/docker/usr/lib/hadoop/lib/native:/docker/usr/lib/hadoop-lzo/lib/native
```

[^ back to top](#table-of-contents)

### 4. EKS Cluster Scaler & Scheduler Setup

#### 4.1 **Autoscaler**

With Autoscaler, we tested the following worker node instance types, mixing the patterns below to avoid EC2 capacity issues. The benchmark in this article mainly focuses on CPU utilization, not memory utilization on worker instances.

**Tested Instance Types:**

| Instance Type | Cores |
|---------------|-------|
| m5.8xlarge & r5.8xlarge | 32 |
| m5.16xlarge | 64 |
| m5.24xlarge & c5.metal | 96 |

**To minimize impacts of job slowness** caused by pods of one job being allocated to multiple nodes or crossing AZs:

- Set up Kubernetes labels on node groups in different AZs, then specify `nodeSelector` for both drivers and executors in the Spark job YAML file. With this setup, pods of a single job will be allocated to the same NodeGroup (e.g., NodeGroup-AZ1) instead of being spread across 2 or more AZs.
- Set up `Binpacking Custom Scheduler` to prevent pods from being spread out. See the `Binpacking` scheduler section below for details.

**To schedule large volumes of pods**, increase the QPS and burst for `Cluster Autoscaler`:

```yaml
nodeSelector:
  ## Kubernetes label for pod allocation
podAnnotations:
  cluster-autoscaler.kubernetes.io/safe-to-evict: 'false'
...
extraArgs:
  ...
  kube-client-qps: 300
  kube-client-burst: 400
```

[^ back to top](#table-of-contents)

#### 4.2 **Karpenter**

With Karpenter cluster, we configured the following setup:

**Configuration:**

- Allocate operational pods (e.g., Spark Operator, Prometheus, Karpenter, Binpacking) to operational EKS NodeGroups (not controlled by Karpenter) via `nodeSelector` settings on operational pods.

**Karpenter NodePool Configuration:**
- Utilize the `provisioner` label to separate Spark driver pods and Spark executor pods. Driver pods are created earlier than executor pods, and each driver pod creates 10 executors, which improves pending pod scheduling in short periods.
- To align with NodeGroups on Cluster Autoscaler and minimize networking noise, utilize `topology.kubernetes.io/zone` when submitting Karpenter Spark jobs to ensure all pods of a single job are allocated to the same AZ.

**Tested Instance Patterns:**
- Instance families: m5, c5, r5
- Instance sizes: 12xlarge, 16xlarge, 24xlarge, metal

For IP-related configuration, see [IP Address Utilization & Settings](#5-ip-address-utilization-settings) → [With Karpenter Node Provisioner](#52-with-karpenter-node-provisioner)

[^ back to top](#table-of-contents)

#### 4.3 **Binpacking Custom Scheduler**

Setting up Binpacking is very helpful for job execution, especially beneficial for pod allocation.

**Configuration:** We use the default `MostAllocated` strategy for Binpacking with the following settings:

```yaml
scoringStrategy:
  resources:
    - name: cpu
      weight: 1
    - name: memory
      weight: 1
  type: MostAllocated
```

**Strategy Details:**
- The `MostAllocated` strategy scores nodes based on resource utilization, favoring nodes with higher allocation.
- Binpacking Custom Scheduler is enabled and used with either Autoscaler or Karpenter. Learn more about the scheduler via [this link](https://aws.github.io/aws-emr-containers-best-practices/performance/docs/binpack/).

**For Large Volume Tests:** When running large volume tests, Binpacking may throttle. To solve this issue, increase the rate as below when installing the Binpacking scheduler:

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  ...
clientConnection:
  burst: 400
  qps: 300
```

[^ back to top](#table-of-contents)

### 5. IP Address Utilization & Settings

#### 5.1 With EKS Autoscaler

When using worker instance types `m5.24xlarge` and `c5.metal` (both have 96 cores, 50 IP addresses per ENI, and 15 max ENIs), if the following default settings are left unchanged:

- `WARM_ENI_TARGET=1`
- `WARM_IP_TARGET=None`
- `MINIMUM_IP_TARGET=None`

A single worker node utilizing only 50-100 IP addresses will reserve 150 IPs from the subnet, wasting over 50 IP addresses.

**Best Practice:** If you know the maximum number of IPs needed for each worker node, it is recommended to set `MINIMUM_IP_TARGET` equal to the "maximum number of IPs" and set `WARM_IP_TARGET` to 1-5 as a buffer.

!!! note "Important"
    Always keep `MINIMUM_IP_TARGET` + `WARM_IP_TARGET` ≤ IP-address-per-ENI-number × integer

**Example:**

```bash
kubectl set env daemonset aws-node -n kube-system WARM_IP_TARGET=5
kubectl set env daemonset aws-node -n kube-system MINIMUM_IP_TARGET=95
```

**Explanation:**
- `MINIMUM_IP_TARGET` ensures each EKS cluster instance reserves the specified number of IP addresses when the node is ready for Kubernetes
- `WARM_IP_TARGET` ensures the specified number of IP addresses are kept in a hot standby warm IP pool. If any IP is allocated to a pod, the pool refills IPs from the subnet to maintain the warm IP pool
- Check our [documentation](https://github.com/aws/amazon-vpc-cni-k8s/tree/master?tab=readme-ov-file#warm_eni_target) for best practices for these targets for your own EKS workload
- To find default IP addresses and ENI numbers for EC2 instances, see [Maximum IP addresses per network interface](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AvailableIpPerENI.html)

**Why set a large `MINIMUM_IP_TARGET`?**

Setting `MINIMUM_IP_TARGET` to a large number (e.g., equal to "maximum IP usage per node") prevents/minimizes API calls to the EC2 service for getting IP addresses, which may cause API throttling and impact performance.

!!! warning "Karpenter Consideration"
    This may not be ideal for Karpenter as the EKS scaler, especially when Karpenter NodePool instance types include both small and large sizes (e.g., 16 cores and 96 cores). If you set both targets as above (95+5), a 16-core instance created by Karpenter will also take 100 IPs. See best practices in the Karpenter section.

**Recommendation:** Run a small load test with fewer nodes and concurrent jobs using default settings to get a clear picture of pod/IP usage per node. Then set `MINIMUM_IP_TARGET` and `WARM_IP_TARGET` accordingly.

[^ back to top](#table-of-contents)

#### 5.2 With Karpenter Node Provisioner

With Karpenter EKS clusters, it is recommended to follow one of the following options:

**Option 1: Least IP Wastage (Limited Core Strategy)**

Select instance types and sizes in Karpenter node pools with the same or close number of cores.

**Example:** Using `m5.16xlarge` and `r5.16xlarge` for Karpenter node pools (both have 64 cores). With the `1-core-1-pod-1-IP` pattern of the Spark job spec, the maximum IP usage per node should be around 64. Leave some buffer and set IP targets as below:

*Note: Each node may have a few operational pods that may or may not consume IPs; this varies based on different EKS addon settings.*

```bash
kubectl set env daemonset aws-node -n kube-system WARM_IP_TARGET=3
kubectl set env daemonset aws-node -n kube-system MINIMUM_IP_TARGET=65
```

**Option 2: Balanced Cores and IP per ENI Strategy**

Use more instance types and sizes where instance cores are multiples of IP per ENI. This may waste IPs slightly.

**Example:** Using `m5.24xlarge` and `m5.12xlarge`:

| Instance Type | Cores | IP per ENI |
|---------------|-------|------------|
| m5.24xlarge | 96 | 50 |
| m5.12xlarge | 48 | 30 |

For this bundle, unset both IP targets but enable `MAX_ENI=2`:

```bash
kubectl set env daemonset aws-node -n kube-system WARM_IP_TARGET-
kubectl set env daemonset aws-node -n kube-system MINIMUM_IP_TARGET-
kubectl set env daemonset aws-node -n kube-system MAX_ENI=2
```

**With this setting, for each instance in the node pool:**

- **m5.24xlarge** will reserve 100 IPs when the node is ready (50 IPs from one active ENI + 50 IPs from one WARM_ENI pool). Maximum IPs consumed will be 100 (since we set `MAX_ENI=2`). Almost no IP wastage, as it will run up to 99 pods.

- **m5.12xlarge** will reserve 60 IPs when the node is ready (30 IPs from one active ENI + 30 IPs from one WARM_ENI pool). Maximum IPs consumed will be 60. With up to 50 pods running, up to 10 IPs will be wasted.

**For this balanced strategy, if selecting `m5.16xlarge` as a node pool instance candidate:**
- **m5.16xlarge** will reserve 100 IPs; however, with only 64 cores available and up to 67 pods running, it will waste over 30 IPs per instance.

[^ back to top](#table-of-contents)

### 6. Minimize the Config Maps and initContainers Spec

When using Spark Operator on EKS, excessive use of [`initContainers`](https://github.com/kubeflow/spark-operator/blob/f56ba30d5c36feeaaba5c89ddd48a3f663060f0d/docs/api-docs.md?plain=1#L3118) and large sparkConf/hadoopConf configurations can increase API server events and pod object sizes, potentially impacting etcd performance.

**To optimize this situation:**

- Utilize alternative solutions to replace `initContainers` when running large volume workloads. For example, mount disks at the EKS cluster level when creating a new EKS cluster or updating a running one.
- Minimize ConfigMap quantity and size; include only essential sparkConf/hadoopConf settings.

[^ back to top](#table-of-contents)

## 7. Appendix

### 7.1 Artifact Reference

- [Load Test Setup Guide for EMR on EKS](https://github.com/aws-samples/load-test-for-emr-on-eks)
- [Grafana & Prometheus Dashboard for Monitoring](https://github.com/aws-samples/load-test-for-emr-on-eks/tree/main/grafana)
