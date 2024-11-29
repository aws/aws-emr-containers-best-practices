# EMR EKS Scale Recommendations for Large customers

This recommendation is to be used by EMR on EKS customers to meet their high workload demands for their EMR on EKS migration. This includes recommendations for cluster farm sizing, EKS pod concurrency and EMR on EKS throughput. EMR on EKS job submission rate is defined at the maximum number of EMR on EKS jobs submitted per minute to a single EKS cluster. EMR on EKS job submission rate is defined at a cluster level and impacted by several factors including infrastructure, control plane, and data plane components.

These recommendations are only guidelines, we recommend monitoring cluster activity to determine whether additional clusters or additional workload split across clusters is required. Lastly, both AWS EMR and EKS teams are constantly making improvements to support higher throughput. Customers can use these recommendations to continue onboarding their workloads to EMR on EKS. 

## Large Scale Load Benchmark

* For these benchmark, we tuned following settings for EKS:
    * EKS cluster version: 1.30
    * EKS control plane components:
        * API server sizing: `bundle-96cpu-768gb`
        * etcd sizing: `bundle-96cpu-768gb`
    * `vpc-cni` add-on settings:
        * `livenessProbeTimeoutSeconds` : 60 seconds
        * `readinessProbeTimeoutSeconds` : 60 seconds
        * `WARM_IP_TARGET` : 10
        * `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG` : true with custom ENIConfigs (each AZ having custom subnet of 65536 IP addresses pool for pods)
* Note that max number of active EMR on EKS jobs corresponds to maximum concurrently active jobs that have been submitted to the EKS cluster, and are not yet completed.
* Please see details around the additional Benchmarking setup in the following section [Appendix D - Load Testing Cluster Configurations](https://quip-amazon.com/7AFyAZQRMyZT#temp:C:KIV39e1c7bb993542ccab65b824a)
* Batch jobs were run with 10 executors 
* We used default pod spec for our EMR jobs
* The streaming jobs scenario were tested by first submitting all streaming jobs before running the batch jobs
* The streaming jobs were tested with constant 3 executors


### Benchmark Results

The benchmark results show the different configurations we ran with to mimic customer workloads, achieving a near 100% job completion rate for EMR on EKS. The factors we tuned were the following:

* EMR on EKS Job submission rate
* Spark Job Driver retries configuration
* Custom Webhook latency
* Duration of the EMR on EKS job run time
* Total runtime for the test
* Image pull policy

There are also some other factors that will affect the EMR job submission throughput that we didn’t tune and used their default settings:

* Pod spec (the number of containers per pod)

Based on these factors if we examine our results below we notice the following trends:

* If we enable retries on the Spark driver, we have to subsequently reduce the EMR on EKS job submission rate as adding retries also creates more K8s job objects and hence cause an increase in etcd database size and etcd requests latency due to higher number of database objects - increasing overall strain to etcd database.
* Custom Webhook latency directly impacts Kubernetes API server latencies and the scalability of EKS control plane, increasing the webhook latency leads to backpressure propagated to and leads to delays in running the EMR on EKS job. 
* `vpc-cni` add-on becomes a bottleneck during high CPU utilization. This may result in job failures due to network timeouts. 
    * **Issue 1:** `vpc-cni` experiences liveness/readiness probe failures due to high node CPU utilization. When these probes fail the nodes are marked as `NotReady` which can cause jobs to be re-scheduled on another node and fail. The settings for these we recommend to update are `livenessProbeTimeoutSeconds` and `readinessProbeTimeoutSeconds.`
    * **Issue 2:** `vpc-cni` by default maintains a pool of IP addresses for 1 ENI. For x24large this is 50 IP addresses, when these IP addresses are all used `vpc-cni` will request a 2nd ENI to be attached, this can cause some immediate issues with running out of IP addresses locally on the Node. The setting that we recommend to update to maintain a warm IP pool is `WARM_IP_TARGET.` This will instruct `vpc-cni` to always have a fixed number of IP’s as available. `vpc-cni` will automatically request new ENI to maintain a constant pool of `WARM_IP_TARGET`
    * **Issue 3**: `vpc-cni` by default assigns IP addresses to pods from the subnet of the node. The number of IP addresses available in the node’s subnet becomes bottleneck if this number is not large enough, causing pod creation to start failing. We can change the behavior of `vpc-cni` to specify a subnet to be used to assign IP addresses to pods. This behavior can be enabled by creating custom ENIConfig in the cluster and then setting `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG` variable. You can follow Steps 2 and 3 in this [EKS doc](https://docs.aws.amazon.com/eks/latest/userguide/cni-custom-network-tutorial.html) for detailed instructions on enabling custom networking for pods. After that, you will need to recreate node-groups in EKS cluster for those changes to take effect.
    * Reference: [https://aws.github.io/aws-eks-best-practices/networking/vpc-cni/](https://aws.github.io/aws-eks-best-practices/networking/vpc-cni/#handle-livenessreadiness-probe-failures)
* The bottleneck in increasing the job submission rate is usually etcd db size and the number of objects in etcd db. 
    * Etcd db has a db size limit of 8GB, beyond which db becomes readonly and you can lose access to your EKS cluster. Ideally, we recommend to not cross 7GB of etcd db size.
    * As the number of objects in etcd db increase, this leads to increased load on Kubernetes API server, causing API server requests to fail, subsequently causing EMR jobs to fail and reducing EMR job success rate.
* The Job churn rate is the operations by the job controller. If the churn rate is high, then the Job queue can’t be processed in time which lead to latency in the EKS cluster. The job churn rate is affected by the job submissions and when the jobs are terminated. It can happen when etcd requests are seeing higher latency and thereby affecting job churn rate.

|Test Scenario	|Job submission mode	|Job Type	|**EMR EKS Job Submission Rate**
 (per EKS cluster) (not finalized)	|Jobs/VC/Min	|Runtime for the test	|Max Number of Active EMR EKS Jobs	|Weighted Avg Job Duration	|Executors/job	|# of Nodes	|# of EMR jobs	|# of Concurrent pods	|**# of Pod / Node** (m5.24xlarge)	|etcd slow apply	|**API Server Request Latency - p99**
(for create Pod calls) ****	|
|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|---	|
|Job with default configurations (no spark driver retries and no webhook)	|StartJobRun	|batch	|150 jobs/min	|1	|165 mins	|1996	|10 mins	|10 pods	|351	|24556	|23007	|65	|613	|0.918	|
|Job with default configurations (no spark driver retries and no webhook, 2x executors)	|StartJobRun	|batch	|80 jobs/min	|1	|200 mins	|1066	|10 mins	|20 pods	|351	|15928	|21997	|62	|165	|0.092	|
|Job with default configurations (no spark driver retries and no webhook, 10x jobs per VC)	|StartJobRun	|batch	|150 jobs/min	|10	|60 mins	|1953	|10 mins	|10 pods	|351	|23953	|22092	|62	|1547	|0.387	|
|Job with spark driver retries and no webhook	|StartJobRun	|batch	|140 jobs/min	|1	|60 mins	|1747	|10 mins	|10 pods	|251	|8270	|20014	|79	|435	|0.14	|
|Job with webhook (up to max 2 sec delay) and retries	|StartJobRun	|batch	|140 jobs/min	|1	|200 mins	|1827	|10 mins	|10 pods	|351	|21848	|21498	|61	|546	|2.91	|
|Job with default retries
* webhook of 2 seconds
* 4500+ streaming jobs
* 4500+ batch jobs	|StartJobRun	|Streaming	|140 jobs/min	|1	|30 mins	|4080	|N/A	|3 pods	|351	|4079	|22660	|65	|855	|0.05	|
|StartJobRun	|Batch	|110 jobs/min	|1	|200 mins	|1436	|10 mins	|10 pods	|351	|21861	|15366	|44	|0.13	|
|	|	|	|	|	|	|	|	|	|	|	|	|	|	|	|



## Recommendations to meet large-scale needs

### Workload distribution

If the overall workload is larger than an individual EKS cluster, the customer needs to distribute the workload across multiple EKS clusters. Each EKS cluster can handle a portion of the workload, which is required to handle a large volume of EMR on EKS jobs without impacting the performance of the EKS clusters. For more details on how to split clusters, see [here](https://aws.github.io/aws-eks-best-practices/scalability/docs/scaling_theory/)

For estimating the number of clusters required to onboard all the expected workloads in the first 5 scenarios above, customers can use the following calculation:

* **Weighted average runtime (WAR):** Total weighted average job runtime of EMR jobs
* **Number of pods per EMR on EKS job (NOE):** This is the average number of pods for a single EMR on EKS job including executor pods, driver pod, job pods (2 in case of driver retries enabled).
* **The Peak Submission Rate (PSR):** it is calculated by summing the peak state job submit volume rate across all services. 
* **Recommended Concurrently Running EMR on EKS Pods (RCRP)**:  This is the total number of concurrently running pods in a single EKS cluster. The recommendation is to keep RCRP below 20000. *RCRP = 20000*,  we came to this conclusion by using the findings from the benchmark where it was observed that having concurrent EMR on EKS pods more than 20000 led to more strain on the etcd database that could lead to job failures.  
    * **Note:** EMR has made optimizations in its control plane and scale testing on the above number **** (RCRP) is in-progress. We plan to re-test these scenarios with the above mentioned optimization and share the updated number.

**Formula:**

```
Number of Clusters = (WAR * PSR * NOE) / RCRP
```


*NOTE: The above formula holds correct for vanilla test settings as defined in  [Appendix C - Load Testing Cluster Configurations](https://quip-amazon.com/7AFyAZQRMyZT#temp:C:KIV39e1c7bb993542ccab65b824a). Changing settings such as additional configmaps per job or using Dynamic Resource Allocation can affect the formula above as the number of objects in etcd database will increase.*

*NOTE: For the streaming scenario, the recommendation is to look at the number of streaming jobs and the number of pods per one streaming job to estimate the number of clusters required.*

*NOTE: It is assumed the load is evenly distributed across all the shards.
*


### Details about EKS Cluster configuration

#### Node instance size

In general, fewer large instances are recommended over many small instances. From other Spark on EKS customers we see 500-600 nodes for when they begin distributing load to additional clusters. Each instance requires API calls to the API server, so the more instances you have, the more load on the API server. For right sizing the node and pod cpu/memory requests for your application, please follow this guide https://aws.github.io/aws-eks-best-practices/scalability/docs/node_efficiency.

#### EKS Control plane scale config for Etcd

EKS actively monitors the load on control plane instances and automatically scales them to ensure high performance. However, high EMR job submission rates (similar to experiments in this doc) can cause etcd requests seeing high latency/timeouts, even when Etcd control plane instances are not being used to their peak performance in terms of cpu/memory (and thus are not automatically scaled by EKS control plane autoscaler). This latency issue is caused due to high network activity by the large number of Etcd objects when you are pushing the EMR load (in terms of job submission rate and the number of concurrent pods) to the above mentioned test scenarios. In this case, you may need to ensure your EKS control plane instances for etcd are properly scaled up. 

#### EKS API Server Latency 

It is important to minimize the[EKS API server latencies](https://quip-amazon.com/MwNDAG5gy8EZ/EMR-on-EKS-Scale-Recommendation-for-Salesforce#temp:C:EIca6f30b96911145518fbc53df8). Webhooks can be one potential root cause for high API server latency. The recommendation is to improve the webhook latency to less than 50 milliseconds and monitor latency by [the performance metrics](https://quip-amazon.com/MwNDAG5gy8EZ/EMR-on-EKS-Scale-Recommendation-for-Salesforce#temp:C:EIca6f30b96911145518fbc53df8) to understand health of the cluster. [K8s admission webhook best practice.](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/#best-practices-and-warnings)

### Image pull policy

In an EKS cluster, the imagePullPolicy determines how the container images are pulled from the ECR registry. There are two commonly used imagePullPolicies: Always and IfNotPresent.

EMR on EKS allows customers to set the image pull policy for Job runner, driver and executors.

For image pull policy advantages and disadvantages go to [Appendix D - Image Pull Policies and pros/cons](https://quip-amazon.com/7AFyAZQRMyZT#temp:C:KIVf5c4bf635fac419ba7efc79ed).

### EMR job driver retry strategy

In order to improve the EMR job throughput, disabling the EMR job driver retry strategy should be considered. This however, will shift the responsibility of managing retries to the customer if needed, but will reduce the number of EKS job events in the job controller queue and the number of etcd db objects.

### EMR job timeout

To enhance the success rate of EMR jobs, it is advisable that jobs that can withstand an increase in the EMR Job Timeout setting to consider doing so. This adjustment can lead to a higher probability of job completion, particularly when there is an accumulation of K8s Jobs pending in the Job Controller Queue. The EMR Job timeout setting can be configured by using the following Configuration Override while submitting the job

```
{
"configurationOverrides": {
  "applicationConfiguration": [{
      "classification": "emr-containers-defaults",
      "properties": {
          "job-start-timeout":"1800"
      }
  }]
}
```

### EKS Version Upgrade

It is recommended to keep EKS version upgraded since the enhancement of concurrency will be improved in future versions.

## Monitoring Insights and Recommendations

There are many metrics on EKS to understand the health of the cluster. Monitoring and debugging generally starts with high level big picture metrics, then getting progressively more granular or scoped in a specific resource/actions to identify root cause. The recommendation is to couple the above recommendations with the monitoring insights below while onboarding workloads and running in production. The metrics section in the appendix cover critical cluster metrics that impact EMR job completion throughput, how to plot them and general guidelines for thresholds. There can be other EKS metrics that can be useful on a case by case basis. We also recommend an EMR on EKS scalability review where we can review existing dashboards, thresholds and provide more details on the metrics. 

* Appendix A - Monitoring metrics to determine overall health and utilization of EKS cluster from EMR jobs standpoint
* Appendix B - Documentation and best practices on scalability 


# Appendix
### **Appendix A - Monitoring metrics of EKS cluster from EMR jobs standpoint**

We list the metrics below that can be used to catch scaling issues proactively, especially the ones that are important for a high EMR job submission throughput as discovered in our load-test experiments.

* **API Server Request and Error counts total:** These are the total number/rate of requests to API server that resulted in an error response code such as 4xx or 5xx. This metric helps monitoring API server health at a high level. Many different factors can be the root-cause for API server error count. Failures in API server requests will cause EMR job submission to fail or transition running EMR jobs to failed state. To resolve the API Server failures, you need to look at the underlying root-cause and resolve it.
    * 
        * Prometheus query for number of API server request by return code by 5 mins duration:
            `sum(rate``(apiserver_request_total[5m])) by (code) > 0`
    * If you find errors in the API server metrics. you can use audit logs to find more details about the errors and what client was involved.
        * Cloudwatch log insights query for finding 5xx error generators (loggroup: /aws/eks/<cluster_name>/cluster)
            * stats count(*) as count by requestURI, verb, responseStatus.code, userAgent
                | filter @logStream =~ "kube-apiserver-audit"
                | filter responseStatus.code >= 500 
                | sort count desc
        * Cloudwatch log insights query for finding 4xx error generators (loggroup: /aws/eks/<cluster_name>/cluster)
            * stats count(*) as count by requestURI, verb, responseStatus.code, userAgent
                | filter @logStream =~ "kube-apiserver-audit"
                | filter responseStatus.code >= 400
                | filter responseStatus.code < 500
                | sort count desc
* **API Request Latency by verb:** This will help show which API calls are the slowest by verb and scope. This can help narrow down which actions or resources are impacted compared to overall latency. As the EMR job submission rate increases, number of objects per resource type increases in the EKS cluster. This will cause espcially LIST calls latency to increase and in turn cause strain to etcd database and API server. This can further affect other API latencies such as POST to increase and cause EMR jobs to fail.
    * Prometheus query for P99 latency values by verb and scope (ignoring long running connections like Watch and Connect as they run longer than normal API calls):
        * `histogram_quantile(0.99, sum(rate(apiserver_request_duration_seconds_bucket{verb!~"CONNECT|WATCH"}[5m])) by (verb, scope, le)) > 0`
    * 
    * Adding the resource in the query can  give more granular information about latency by identifying when a single resource is slow or impacted:
        * `histogram_quantile(0.99, sum(rate(apiserver_request_duration_seconds_bucket{verb!~"CONNECT|WATCH"}[5m])) by (resource, verb, scope, le)) > 0`
    * 
* **API → Etcd request latency by object/action :** This metric can help to identify if the API Request latency is being driven by backend/etcd performance or if it’s being introduced at the API server. This metric increases when the strain on Etcd db is causing API server requests to experience higher latency especially when the number of objects in Etcd increases. As Etcd request latency increases, api server requests can start timing out causing EMR jobs to fail to submit or transition from running to failed state. To recover, you will need to back off by reducing the EMR job submission rate or stopping the new job submissions completely.
    * 
        * `histogram_quantile(0.99, sum(rate(etcd_request_duration_seconds_bucket[5m])) by (type, operation, le)) > 0`
* **Etcd database size:**  When you create a cluster, Amazon EKS provisions the [maximum recommended database size](https://etcd.io/docs/v3.3/dev-guide/limit/#storage-size-limit) for etcd in Kubernetes, which is 8GB. When the database size limit is exceeded, etcd emits a no space alarm and stops taking further write requests. In other words, the cluster becomes read-only, and all requests to mutate objects such as creating new pods, scaling deployments, etc., will be rejected by the cluster’s API server. Further, users won’t be able to delete objects or object revisions to reclaim etcd storage space. This will cause all subsequent EMR jobs to fail. It is very important to monitor etcd database size to keep it under limit. If your Etcd db runs into no space alarm, EKS auto recovery workflow kicks in to recover some db space. Please check this [blog post](https://aws.amazon.com/blogs/containers/managing-etcd-database-size-on-amazon-eks-clusters/) for more details on recovering Etcd db from no space alarm.
    * Etcd DB size metric
        * apiserver_storage_size_bytes
* **Node utilization:** The number of nodes, the instance types for those nodes, the EMR job submission rate combined with pods cpu/memory request limits will contribute to the node utilization going up or down. Ideally we need high node utilization for efficient EKS cluster compute usage. However, if you see all nodes in the cluster are being utilized near 100% in terms of cpu/memory, you may need to scale your EKS cluster further  by additional nodes (manually if not using an autoscaler).
    * node_cpu_seconds_total
    * node_memory_MemFree_bytes
    * node_memory_Cached_bytes
    * node_memory_Buffers_bytes
    * node_memory_MemTotal_bytes
    * You need node_exporter addon for these metrics: https://aws-quickstart.github.io/cdk-eks-blueprints/addons/prometheus-node-exporter/
    * 
    * You can find queries for the above dashboard here: https://github.com/awslabs/data-on-eks/blob/main/analytics/terraform/emr-eks-karpenter/emr-grafana-dashboard/emr-eks-grafana-dashboard.json
* ***[Only if you are using admission webhooks]* Admission Webhook request Counts** - This metric denotes the numbers of how many requests are hitting the admission webhooks by name. This can show a misconfiguration of webhooks if theres a single webhook that is both receiving a large number of requests. Misconfiguration of a webhook can cause unintended API server requests to see higher latency and cause slowness in job submission or even time-outs.
    * 
        * `sum(rate(apiserver_admission_webhook_request_total[5m])) by (name) > 0`
    * 
        * `sum(rate(apiserver_admission_webhook_request_total{rejected="true"}[5m])) by (name) > 0`
    * You can also use the “operation” label to correlate by actions.
* ***[Only if you are using admission webhooks]* Admission Webhook request Latency** This metric shows how long requests from the API servers to admission webhooks are taking. We can break that out by webhook name, success/failure, and operation.
    * This latency is useful in tandem with the API request latency metrics as the time it takes to handle webhook requests is included in the total latency. If the webhooks are taking ~3s to respond, we can expect ~3s of *additional* latency to those requests. High webhook latency can cause API server requests to time out causing EMR job failures.
        * Be wary on CPU throttling or overwhelming the Pods that are servicing webhooks. Delays or failures in admission can have a cluster wide performance impact (in worst cases it can grind a cluster to a halt) 
    * 
        * `histogram_quantile(0.99, sum(rate(apiserver_admission_webhook_admission_duration_seconds_bucket[5m])) by (name, operation, le)) > 0`
    * You can add the rejected label to the output to also get an idea how often webhooks are allowing/rejecting requests. 
        * `histogram_quantile(0.99, sum(rate(apiserver_admission_webhook_admission_duration_seconds_bucket[5m])) by (name, operation, rejected, le)) > 0`
    * 


Documentation and best practices links can be found [Appendix B - Documentation and best practices on scalability](https://quip-amazon.com/7AFyAZQRMyZT#temp:C:KIV804528e8011746b1bc13f9764)

**Dashboard that was demonstrated**: https://github.com/RiskyAdventure/Troubleshooting-Dashboards/blob/main/api-troubleshooter.json

**EKS Performance Overview Grafana Dashboard**: https://grafana.com/grafana/dashboards/6775-kubernetes-performance-overview/

**SLO / SLI reference from Upstream for baselines:  https://github.com/kubernetes/community/blob/master/sig-scalability/slos/api_call_latency.md**
* * *

### **Appendix B - Documentation and best practices on scalability**

Below points link to several EKS scalability best practices documentation. Most of these references are for educational purpose on how to monitor, scale test, and autoscale EKS cluster and are not intended to be recommendations for EMR on EKS customers.

* Blog on how EKS does scalability testing https://aws.amazon.com/blogs/containers/deep-dive-into-amazon-eks-scalability-testing/
    * This best practices page dives deeper into the metrics and SLOs that K8s community measures https://aws.github.io/aws-eks-best-practices/scalability/docs/kubernetes_slos/
    * We run 5,000 nodes and ~150k pods, churning at 50 pods/s in our load tests. But our node capacity is static and not autoscaling.
* Kubernetes scalability thresholds https://github.com/kubernetes/community/blob/master/sig-scalability/configs-and-limits/thresholds.md
    * These are where Kubernetes Scalability SIG would expect performance degradation in the cluster
    * This kubecon talk is *fantastic* background https://www.youtube.com/watch?v=t_Ww6ELKl4Q
* Some of the AWS quotas and other limitations we've seen customers hit https://aws.github.io/aws-eks-best-practices/scalability/docs/quotas/
* Reference Prometheus configuration is the kube-prometheus-stack https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack though it collects a ton of metrics and may hit issues with large clusters.
* This best practices page has some of the key metrics to gather for your cluster https://aws-observability.github.io/observability-best-practices/guides/containers/oss/eks/best-practices-metrics-collection/#control-plane-metrics
* This page discusses the prometheus metrics available from the AWS VPC CNI https://github.com/aws/amazon-vpc-cni-k8s/blob/master/cmd/cni-metrics-helper/README.md 
    * You don’t need to use the metrics helper application unless you want these available in CloudWatch. The prometheus endpoint should be available to your DataDog agents.
    * You can annotate pods to use the autoscrape config https://github.com/aws/amazon-vpc-cni-k8s/issues/327#issuecomment-466913046
* We also discussed that Kubernetes clients can impact the performance of the cluster with spammy or expensive API calls. Cloud Watch Log Insights is a powerful tool to query the audit events in your EKS clusters and can provide details like “Which userAgent is sending the slowest LIST calls in the cluster? and what are they listing?” 
    * The queries i use to troubleshoot and deep dive are listed here https://github.com/aws-samples/specialist-tam-container-dashboards/blob/main/troubleshooting-queries/CloudWatch-Logs-Troubleshooting-Queries.md
* OpenAI has done a couple of blogs discussing their journey on huge K8s clusters: 
    * https://openai.com/research/scaling-kubernetes-to-2500-nodes
    * https://openai.com/research/scaling-kubernetes-to-7500-nodes
* Kubernetes Fail stories, scale often plays a role in some of the nastier outages: https://k8s.af/
* Metrics to watch on CoreDNS https://www.datadoghq.com/blog/coredns-metrics/#metrics-to-watch-coredns_dns_responses_total-coredns_forward_responses_total
* EKS Blog on Managing and monitoring etcd DB size and Defrag: https://aws.amazon.com/blogs/containers/managing-etcd-database-size-on-amazon-eks-clusters/
* Shane’s API server Dashboard https://aws.amazon.com/blogs/containers/troubleshooting-amazon-eks-api-servers-with-prometheus/
* EKS scaling theory: https://aws.github.io/aws-eks-best-practices/scalability/docs/scaling_theory/
* Kubernetes recommendations on scalability thresholds: https://github.com/kubernetes/community/blob/master/sig-scalability/configs-and-limits/thresholds.md
* [EKS Control Plane Monitoring - EMR on EKS Best Practices](https://quip-amazon.com/OoVyAaihGDOs)

### **Appendix C -  Load Testing Cluster Configurations**

The EKS cluster setup and EMR release are maintained across the different scenarios while performing the load test

* Number of nodes: 351
* Instance type: m5.24xlarge
* Instance number of cores: 16
* Instance memory: 128 Gb
* EMR Relaese: emr-7.0.0-latest
* Eks version: 1.30
* Region: us-west-2
* Number of executors: 10
* Executor Memory: 512M
* Executor Core: 1
* Driver Core: 1
* Driver Memory: 512
* Total number of configmaps per job: 7

### **Appendix D - Image Pull Policies and pros/cons**

Here are the advantages and disadvantages of each: 

#### ImagePullPolicy: Always  (Default)

Advantages: 

* Consistent behavior: Always pulling the latest image ensures consistent behavior across deployments, as all nodes will have the same version of the image. 
*  Easy to manage: With Always, you don't need to worry about image versions or caching, as the latest image will always be pulled. 

Disadvantages: 

* Increased network traffic: Always pulling the latest image can result in increased network traffic, as the entire image is downloaded every time.
* Longer deployment times: Pulling the latest image can take longer, especially for large images, which can increase deployment times. 

#### ImagePullPolicy: IfNotPresent 

Advantages: 

* Faster deployments: IfNotPresent can lead to faster deployments, as the image is only pulled if it's not already present in the node's cache. 
* Reduced network traffic: By only pulling the image when it's not present, you can reduce network traffic and save on data transfer costs. 
* Improved performance: IfNotPresent can improve performance, as the image is cached on the node, reducing the need for subsequent pulls. 

Disadvantages: 

* Inconsistent behavior: With IfNotPresent, nodes may have different versions of the image, leading to inconsistent behavior across deployments. 
* More complex management: IfNotPresent requires more complex management, as you need to ensure that the image is properly cached and updated. 
* Potential for outdated images: If an image is not properly updated, nodes may end up with outdated versions, leading to potential issues. 