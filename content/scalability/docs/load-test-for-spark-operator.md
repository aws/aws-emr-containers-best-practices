# **Run Large Scale Jobs by EMR on EKS Spark Operator**

This scalability recommendation is focused on EMR on EKS's Spark Operator performance in a large-scale environment. It offers insights derived from extensive benchmarking and testing across various configurations and workloads. The study explores key factors influencing Spark Operator efficiency, including cluster setup, resource allocation, and job submission patterns.

Our findings provide a valuable reference for optimizing EMR Spark Operator workloads on Amazon EKS, addressing challenges unique to high-volume, distributed computing environments. The recommendations outlined here aim to help customers achieve a balance between performance, scalability, and resource utilization. By considering these best practices, organizations can enhance their EMR on EKS deployments, ensuring robust and efficient Spark job processing while managing infrastructure costs effectively. This overview serves as a foundation for IT professionals and data engineers seeking to maximize the potential of their Spark applications in cloud-native Kubernetes environments.

## Large Scale Load Benchmark 

* For these benchmark, we tuned following settings for EKS:
    * **EKS cluster version**: 1.30
    * **SparkOperator version:** `emr-6.11.0 (``v1beta2-1.3.8-3.1.1)`
        * The current version of EMR Spark Operator has limited API exposed for users to tune the performance, in this article, we keen to use the below set up for Spark Operators:
    * **Pre-warm the EKS control plane**
    * Isolated the Operational services and Spark application pods.
        * `controllerThreads=30` , Higher operator worker than default 10.
        * To minimise the impacts caused by other services, eg.: spark job pods, prometheus pods, etc, we allocated the Spark Operator(s), Prometheus operators in the dedicated operational node groups accordingly.
        * Please see details for Spark Operator(s) and Spark Job Set up in the following best practice section.
    * To utilize the cluster resources, we have tested the following techniques and settings.
        * EKS Autoscaler or Karpenter
        * Binpacking stragtegy is enabled and accompany with either Autoscaler and Karpenter accordingly. 
    * The cluster resides a VPC with 6 subnets (2 public subnets and 4 private subnets with S3 endpoint attached):
        * The 4 private subnets are allocated into 2 AZs evenly.
        * All Node groups are created in the 4 private subnets, and for each NodeGroup, the subnets associated are in the same AZ, e.g: NodeGroup-AZ1, NodeGroup-AZ2.
* The benchmark results are based on the Spark Testing job with spec as below;
    * Driver: 1 Core, 512mb
    * Executor: 1 Core 512mb each, for 10 executors. 
        * *Due to default value of `spark.scheduler.minRegisteredResourcesRatio` = 0.8, then Spark job will start to run with min of 8 executors are allocated. Ref Document: [link](https://spark.apache.org/docs/3.5.1/configuration.html#kubernetes:~:text=spark.scheduler.minRegisteredResourcesRatio)*
    * Each Spark Job is expected to run between 12 ~ 16 mins, which does NOT include the spark submission & pod scheduling time consume.
    * Testing Job Script is stored in s3, the code submitted with `hadoopConf` and `sparkConf` configmaps.
    * Endabled `nodeSelector` to ensure the Spark Jobs will be assigned into Worker Node Groups.


### Benchmark Results

|Test Scenario	|Cluster Scaler	|job start time in utc	|Job Type	|**Spark Operator Job Submission Rate**
 (per EKS cluster)	|Spark Operator Numbers	|Runtime for the test	|Max Number of Active Jobs / Driver Pods	|Spark Job Running Time	|Avg Job Duration (Since Job submitted till completed)	|Executors/job	|# of Worker Nodes	|# of Spark jobs	|# of Concurrent pods	|
|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|
|Job with default configurations (no spark driver retries and no initContainer)	|AutoScaler	|2024-10-31 14:10	|batch	|279 jobs/min	|13	|200 mins	|3710	|500 ~ 800s	|720 ~960s	|10 pods	|698	|55767	|38722	|
|Job with default configurations (no spark driver retries and no initContainer)	|AutoScaler	|2024-11-06 13:21	|batch	|118 jobs/min	|10	|200 mins	|1511	|500 ~ 800s	|720 ~960s	|20 pods	|540	|23749	|30447	|
|Job with default configurations (no spark driver retries and with **initContainers** enabled for 2s sleep for pods creation)	|AutoScaler	|2024-11-04 08:52	|batch	|212 jobs/min	|15	|200 mins	|2882	|500 ~ 800s	|720 ~960s	|10 pods	|532	|42926	|30329	|
|Job with default configurations (no spark driver retries and no initContainer)	|Karpenter	|2024-10-28 07:06	|batch	|272 jobs/min	|10	|200 mins	|3490	|500 ~ 800s	|720 ~960s	|10 pods	|464	|54576	|35962	|


### Metrics Explanation 

* **Spark Operator Job Submission Rate (per EKS cluster):**
    * The average submitted jobs per minute, eg: Total jobs submitted / Test Time.
* **Spark Operator Numbers:**                                               
    * The number of spark operators to be used for the test.
* **Max Number of Active Jobs / Driver Pods:**
    * The max number of Spark Driver pods running concurrently.
* **Spark Job Running Time**
    * The time spent on the spark job execution, the time is vary due to testing spark job, to pick a random number within the time range, to mimic the real workloads.
* **Number of Worker Nodes:**
    * The total worker instances created by EKS cluster, Operational Instances exclusive.
* **Number of Spark jobs :**
    * The total job submitted from Client.
* **Number of Concurrent pods**
    * The max number of spark job pods (Drivers & Executors) running concurrently during the testing
* **API Server Request Latency - p99 (for create Pod calls) :**
    * This metric provides the 99th percentile of API server response times for POST requests to create pods in an EKS cluster over the last 5 minutes.


### Notes about the Limitations

* Pod template is not available in the current version, this feature has been added into OSS Spark Operator [Roadmap](https://github.com/kubeflow/spark-operator/issues/2193#:~:text=Pod%20template%20support%20(%5BFEATURE%5D%20Use%20pod%20template%20feature%20in%20spark%2Dsubmit%20for%20Spark%203.x%20applications%C2%A0%232101)). Users can only put the configurations via spark job yaml file at the current stage. 
* With property `spark.scheduler.minRegisteredResourcesRatio` has default value `0.8` for[KUBERNETES mode](https://spark.apache.org/docs/3.5.1/configuration.html#:~:text=spark.scheduler.minRegisteredResourcesRatio), then it would be hard to get the accurate numbers of how many spark jobs are running with sufficient executor pods with code changes or without Gang Scheduling enabled. Thus, from the benchmark results, there are 2 `Max Jobs Concurrent Running` , from Spark Operator Metrics and collected via how many driver pods are running as reference.
* Need to increase the bucket limit and the refill rate for `DescribeInstances` ,eg: Bucket size 140 and Refill rate 60. Have observed this issue in both CAS and Karpenter as the cluster scaler.
* There is limited performance tuning parameters are available on Spark Operator, eg: bucketQPS / bucketSize are hardcoded in the current version of Spark Operator
* The current EMR Spark Operator Version cannot handle, for a single operator to monitor the multiple specified job name spaces. Can only work as one operator one job namespaces or one operator for all namespaces. https://github.com/kubeflow/spark-operator/issues/2052, the limitation has been fixed at OSS V2.

 


## Best practice / recommendation to use Spark Operator on EKS:

### Spark Operator numbers

The number of Spark Operator has significant impacts on the performance of submitting the jobs from client to eks cluster. Here are the recommendations when using multiple EMR Spark Operators on EKS cluster 

* **Use Multiple Spark Operators for High-Volume Tasks**

For large-scale workload, deploying multiple Spark Operators significantly improves performance. A single operator can handle about 20-30 task submissions per minute. Beyond this, you'll see better results with multiple operators, especially before the submission workload hitting the threshold of eks ectd or api server side.

With our testing job set up, for submission rates between 250-270 tasks per minute, there is no significant performance difference between 10 or 15 Spark Operators in overall. However, lower operator number can provide better stability than higher operator number. This setup maintains high performance with minimal task failures (less than 0.1%). 

*Be cautious when exceeding 270 submissions per minute.* *We've observed increased failure rates regardless of the number of operators in**(10, 15, or 20).*

The number of spark operator may be impacted by the submission rate and also the job configs, e.g.: The Spark job with initContainers enabled, will lead to more events will be submitted to API server from Spark Operators, and then the size of etcd database will be increased more faster than the jobs without initContainers enabled.

    * For the spark job without initContainers:
        * Each Spark Operator can submit 20~30 jobs per min in average.
    * For the spark job with initContainers:
        * Each Spark Operator can submit 12~18 jobs per min in average, which vary in different spark job configs.
* **Balancing Operator Numbers for Long-Running Tests**

For extended operations (e.g., 200-minute tests), slightly fewer operators could be beneficial. This is represented by the API request latency, which shows a slight increase with more operators, from the Spark Operator to the API server. This could be due to 10 operators placing less strain on the API server and etcd while maintaining good performance compared to 15 operators. We observed that the situation worsens further with 20 operators.


* **Do not use too small Operators for large volume of workload.**

Please aware, if the number of Spark Operators are too small for large workload, e.g.: 5 Operator for 250 min submission rate could cause the Spark Operator throttling internally. 

The symptoms of Spark Operator throttling could be either or both:

    *  The number of Jobs in `New` State (also known as `Null` State) or the number of Jobs in `Succeeding` are keep increasing, but the number of jobs in `Submitted` state is reducing.
    * In addition, you may also see the Spark Operator metrics API provides the wrong data, e.g.: The running application number is much less than the number of running Driver Pods.
* **System Health Considerations**

Based on the given testing job, to keep submission rates below 250 tasks per minute for optimal system health. Please aware, the number of 250/min submission rate is a reference, as it could be impacted by other factors, such as spark job config maps, the size of pods settings, etc.
Please monitor etcd size closely, especially during high-volume operations. We've seen it exceed 7.4GB, risking going over the 8GB mark despite EKS's automatic compaction.

Please note, these recommendations are based on our specific test environment - your optimal settings may vary slightly based on your unique infrastructure and workload characteristics.


### **Formula to determine  the number of Operators :** 

The number of EKS cluster required for Spark Job is not relating to how many operators, as if set the right number of the operators, then the bottleneck will be on API Server & etcd DB size. Please see the below formula as a reference to determine how many eks cluster needed for workload.

* Job Submission Rate (**submission_rate**) = Average number of jobs submitted per minute
* Average Job Duration (**avg_job_runtime**) = Average job runtime in minutes
* Pods per Job (**avg_pods_per_job**) = Average number of pods per job
* Max Concurrent Pods (**max_concur_pods**) = Maximum number of pods that can run concurrently in the cluster


**Formula**

```
Est_cluster_numbers = (submission_rate * avg_job_runtime * avg_pods_per_job) 
                        / (max_concur_pods * (1 - buffer_ratio))
```

* `buffer_ratio` is recommended to decide the number of eks cluster to use. eg: `buffer_ratio` = 0.1, to ensure the cluster can reserve 10% of buffer for apiserver & etcd DB to handle workloads, instead of hit the benchmark results.
* `Est_cluster_numbers`, the number of eks clusters needed is vary in the pod sizes of spark jobs, the formula above is a starting point to have a roughly understanding.


*Please aware, this formula applies on the eks cluster environment as [EMR on EKS Spark Operator Load Testing Env Setting up Manual](https://quip-amazon.com/MbH5AcPj4pIl) suggested. And all recommendation suggested in this article has been implemented.*


### Instance Sizes

Based on the testing benchmark results with the instance types as below:

```
- m5.8xlarge  & r5.8xlarge
- m5.16xlarge
- m5.24xlarge & c5.metal
```

The experiment data reveals that medium-sized EC2 instances demonstrate more consistent and favorable performance in this Spark cluster configuration:

1. These instances maintain a more stable Driver/Total Pods ratio, typically below 12.6%.
2. They show consistent performance across key metrics such as submission rates, job concurrency, and latency.

Compared to larger instance types, medium-sized instances exhibit a better balance of efficiency and stability in this specific setup, suggesting they are well-suited for the current cluster configuration.



### Spark Operator Configuration best practice:

To Isolate the Operational services and Spark application pods is recommended in both performance and operational consideration.

* To minimise the impacts caused by other services, e.g.: spark job pods, prometheus pods, etc, we allocated the Spark Operator(s), Prometheus operators in the dedicated operational node groups accordingly.
    * Operational NodeGroup for Spark Operator, we use `r5.4xlarge` for each spark Operator.
    * Operational NodeGroup (`r5.8xlarge` ) for Monitoring tools, Binpackking, Karpenter (if applied).
* To set up `controllerThreads` with higher number, the default is 10. 

We have also tested very large numbers, eg: 50/100, etc.
But not helpful on the Operator performance, as the bucketSize and qps was hard coded. Thus, with higher workers does not help on the performance.

* To use `podAntiAffinity` to ensure the multiple Spark Operations will `NOT` to be allocated in the same operational node:

```
*We have also tested very large numbers, eg: 50/100, etc. 
But not helpful on the Operator performance, as the bucketSize and qps was hard coded.
With higher workers does not help.*
```

```
## For workers of spark operator,
## we found out the 30 seems can provide the better performance.
## It would be vary in different spark jobmission object size.
controllerThreads: 30


nodeSelector:
cluster-worker: "true" ## this label is managed on EKS Nodegroup side.
## To define the nodeSelector label for Spark Operator pods,
## Ensure all operators will be running on the operational Nodegroup.


## Use pod affinity:
## to ensure only one Spark Operator will be running on one Operational Node
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
## To define the nodeSelector label for Spark Operator pods,
## Ensure all operators will be running on the operational Nodegroup.

```

Please aware, for other operational service like prometheus, Binpacking, Node Scaler (CAS), Karpenter, etc. We use the same approach as above to ensure the operational services will be running in the Operational Node group(s) only.

#### For spark job drivers and executor pods:

Similar as operational pods, utilzing `nodeSelector` with label feature, to ensure the spark job pods will be allocated to worker NodeGroup or Karpenter nodepools.

```
    driver:
      nodeSelector:
      cluster-worker: "true" 
## This label needs to match with EKS nodegroup kubernates label or kapenter nodepool

    executor:
      nodeSelector:
      cluster-worker: "true" 
## This label needs to match with EKS nodegroup kubernates label or kapenter nodepool
```


As a reference, we have below configs for test job:

```
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



### EKS cluster scaler & scheduler set up

* **Autoscaler**

With Autoscaler, we’ve tested on the following worker node instances types, mixture the below patterns to avoid the EC2 capacity issue. The benchmark in this article is mainly focused on the CPU utilization, but not memory utilization on the worker instances.

    * m5.8xlarge & r5.8xlarge, each instance has 32 Cores.
    * m5.16xlarge, each instance has 64 Cores.
    * m5.24xlarge & c5.metal, each instance has 96 Cores.

To minimise the impacts of job running slowness which may be caused due to the pods of one job are allocated into multiple nodes, or crossing AZs. 

    * Sett up the kubernates label on the node groups in different AZs, and then to ensure the `nodeSelector` for both the drivers and executors to be specified in the Spark Job yaml file. By doing this set up, the pods of a single job will be allocated into the same NodeGroup (e.g.: NodeGroup-AZ1), instead of the pods to be allocated into 2 or more AZs.
    * Set up `Binpacking Custom Scheduler ` to prevent pods from being spread out. Please check the `Bindpacking` scheduler part from below for details.

To schedule the large volume of pods, need to increase the qps and burst for `NodeScaler`.

```
nodeSelector:
 ## Kubernates label for pod allocation.
podAnnotations:
  cluster-autoscaler.kubernetes.io/safe-to-evict: 'false'
...
extraArgs:
...
  kube-client-qps: 300
  kube-client-burst: 400
```

* **Karpenter**

With Karpenter cluster, we have the setting up as below:

    * To allocate the operational pods, e.g.: Spark Operator, Prometheus, Karpenter, Binpacking, etc in the Operational EKS NodeGroup, which not controlled by Karpenter via setting up `nodeSelector` on the operational pods.
    * Karpneter Nodepool configs:
        * Utilize the `provisioner` label to separate the spark driver pods and spark executor pods. As the driver pods will be creating earlier than executor pods, and then each driver pod will create 10 executors, which can improve the pending pods in short period of time.
        * To align with NodeGroup on CAS, and also minimise the networking level noisy, to utilize the `topology.kubernetes.io/zone` when submitting karpenter spark jobs, to ensure all pods of a single job will be allocated into the same AZ.
    * We’ve testing the below instance pattens:
        * Instance family: m5, c5, r5
        * Instance size: 12xlarge, 16xlarge, 24xlarge, metal.
        * In terms of IP related configuration, please see below `IP address utilisation & settings`  → `With Karpenter Scaler ` 




* **Binpacking Custom Scheduler**

Setting up Binpacking will very helpful on the job execution especially beneficial on the pod allocation.

    * We use the default `MostAllocated strategy` for Binpacking, has the below settings:

```
                scoringStrategy:
                  resources:
                      - name: cpu
                        weight: 1
                      - name: memory
                        weight: 1
                  type: MostAllocated
```

    * The `MostAllocated` strategy scores the nodes based on the utilization of resources, favoring the ones with higher allocation.
    * Binpacking Custom Scheduler is enabled and accompany with either Autoscaler or Karpenter accordingly. Please learn more about the Scheduler via [link](https://aws.github.io/aws-emr-containers-best-practices/performance/docs/binpack/).
    * When running the large volume of test, which may cause Binpacking throttling. To solve this issue, can increase the rate as below when install the Binpacking scheduler:

```
    apiVersion: kubescheduler.config.k8s.io/v1
    kind: KubeSchedulerConfiguration
    profiles:
    ....
    clientConnection:
      burst: 400
      qps: 300
```

* **Implementing Retry Mechanisms**

Set up retry configurations to handle the small percentage of task failures that may occur. Different from EKS StartJobRun API, in spark operator, setting up retry does not impact the overall performance from the load testing. 




### IP address utilisation & settings:

#### With EKS AutoScaluer:

When to use the worker instance type: `m5.24xlarge` and `c5.metal` which both have the 96 Cores and 50 IP address per ENI and 15 max ENIs. If to leave the following default settings unchanged: 

* `WARM_ENI_TARGET=1`
* `WARM_IP_TARGET=None`
* `MINIMUM_IP_TARGET=None`

If a single worker node only utilizes 50~100 IP address, then the node will reserve 150 IPs from the Subnet, and over 50 IP addresses will be wasted.

**Best Practice:** If we know the maximum number of IPs needed for each worker node, it is recommended to set the `MINIMUM_IP_TARGET` equal to the “maximum number of IPs”, to set `WARM_IP_TARGET` to 1~5 as a buffer. 
Please note, you should alway keep `MINIMUM_IP_TARGET` + `WARM_IP_TARGET` <= IP-address-per-ENI-number * integer, e.g.:

```
kubectl set env daemonset aws-node -n kube-system WARM_IP_TARGET=5
kubectl set env daemonset aws-node -n kube-system MINIMUM_IP_TARGET=95
```

* `MINIMUM_IP_TARGET` will ensure for each instances of the eks cluster will reserve the number of the IP addresses while the node is ready to use by Kubernates.
* `WARM_IP_TARGET` will ensure the number of IP address specified is hot standby in a warm IP pool, and if any of the IP to be allocated to a Pod, then the pool will refill the IPs from Subnet to ensure the warm IP pool.
* Please check our [document](https://github.com/aws/amazon-vpc-cni-k8s/tree/master?tab=readme-ov-file#warm_eni_target) for the Best Practice of the Targets for your own EKS workload.
* To find out the default IP address and ENI number of ec2 instances, please check document: [Maximum IP addresses per network interface.](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AvailableIpPerENI.html)

The reason for setting `MINIMUM_IP_TARGET` to a large number, e.g.: equal to the “maximum IP usage per node” is to prevent/minimize the API calls to the EC2 service for getting IP addresses, as it may cause API throttling and impact performance. 

*However, please note, it may not be the ideal solution for using Karpenter as the EKS Scaler, especially the Instance types of Karpenter NodePool are including small and large sizes, eg: The NodePool has 16 Cores and 96 Cores. If you are setting the both Targets as above, 95+5, which means for 16 Cores instance that created by Karpenter will also take 100 IPs. Please check Best Practice in Karpenter part.*

It is recommended to run a small load test with fewer nodes and concurrent jobs using default settings to get a clear picture of how the pods/IP usage will be on a node. Then, set up the `MINIMUM_IP_TARGET` and `WARM_IP_TARGET` accordingly.


#### With Karpenter Node Provisioner: 

With Karpenter eks cluster, it is recommend to follow one of the following options:

* Least IP wastage but limited on the instances Cores strategy. 

To select the instance types and sizes in the karpenter nodepools, with the same/close number of Cores.

    * e.g.: Using `m5.16xlarge` and `r5.16xlarge` for the karpenter nodepools, as both of them have 64 Cores, and with the `1-Core-1-pod-1-IP` pattern of the spark job sepc, the max number of IP usage per node should be around 64, to leave some buffer we can set up the IP targets as below (_*please aware, for each node, it may be a few operational pods may or may not consume IP, it’s vary in the different eks addons setting*_):

```
kubectl set env daemonset aws-node -n kube-system WARM_IP_TARGET=3
kubectl set env daemonset aws-node -n kube-system MINIMUM_IP_TARGET=65
```

* Balanced in Cores and IP per ENI strategy, with more bundle of instance types and sized, may waste IPs slightly:

To select the instance types and sizes, which the Cores of the instance are multiple of it’s IP per ENI:

    * e.g.: Using `m5.24xlarge` and `m5.12xlarge`, 
        * `m5.24xlarge`: 96 Cores with 50 IP per ENI.
        * `m5.12xlarge`: 48 Cores with 30 IP per ENI.
        * In this bundle, we can unset the both IP targets, but enable `MAX_ENI` = 2:

```
kubectl set env daemonset aws-node -n kube-system WARM_IP_TARGET-
kubectl set env daemonset aws-node -n kube-system MINIMUM_IP_TARGET-

kubectl set env daemonset aws-node -n kube-system MAX_ENI=2
```

    * With this setting, for each instances of the nodepool:
        * `m5.24xlarge` will reserve 100 IPs when the node is ready, which includes the 50 IPs from one active ENI and 50 IPs from one WARM_ENI pool. The maximum IPs to be consumed by the node will be 100, as we have set the 2 as the `MAX_ENI` . 
        * `m5.12xlarge` will reserve 60 IPs when the node is ready, which includes the 30 IPs from one active ENI and 30 IPs from one WARM_ENI pool. The maximum IPs to be consumed by the node will be 60, as we have set the 2 as the `MAX_ENI` . 
        * Thus, almost no IP wastage on the `m5.24xlarge` instance, as It will run up to 99 pods. For `m5.12xlarge` instances with up to 50 pods running, there is up to 10 IPs will be wasted.
    * For the this balanced strategy, if to select `m5.16xlarge` as the candidate of the nodepool instance:
        * `m5.16xlarge` will reserve 100 IPs, however, as only 64 Cores available to use and up to 67 pods are running, then it will waste over 30 IPs for each instance.

### Minimise the Config Maps and initContainer spec

When using Spark Operator on EKS, excessive use of `[initContainers](https://github.com/kubeflow/spark-operator/blob/f56ba30d5c36feeaaba5c89ddd48a3f663060f0d/docs/api-docs.md?plain=1#L3118)` and large sparkConf/hadoopConf configurations can increase API server events and pod object sizes, potentially impacting etcd performance. 

To optimize this situation, please try:

* To utilize other solutions to replace the `initContainers` when running the large volume workloads. e.g.: To mount disk in EKS cluster level when creating a new eks or updating the running eks.
*  Minimize ConfigMap quantity and size, include only essential sparkConf/hadoopConf settings.

### TODO TASK:

Use a single operator to support more namespaces, eg: to achieve 100+ EMR on EKS job namespaces. This use case may fit on the customer’s real-world cases in production envirnoment. Refer to OSS Spark Operator V2. https://github.com/kubeflow/spark-operator/issues/2052


## Appendix

### Artifact Reference
* [Load Test Set up Guide for EMR on EKS](https://github.com/aws-samples/load-test-for-emr-on-eks)
* [Grafana & Prometheus Dashboard for monitoring](https://github.com/aws-samples/load-test-for-emr-on-eks/tree/main/grafana)








