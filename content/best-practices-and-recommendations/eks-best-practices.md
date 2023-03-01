# **EKS Best Practices and Recommendations**

Amazon EMR on EKS team has run scale tests on EKS cluster and has compiled a list of recommendations. The purpose of this document is to share our recommendations for running large scale EKS clusters supporting EMR on EKS.

### **Amazon VPC CNI Best practices**

#### **Recommendation 1: Improve IP Address Utilization**

EKS clusters can run out of IP addresses for pods when they reached between 400 and 500 nodes. With the default CNI settings, each node can request more IP addresses than is required. To ensure that you don’t run out of IP addresses, there are two solutions:

1. Set **MINIMUM_IP_TARGET** and **WARM_IP_TARGET** instead of the default setting of **WARM_ENI_TARGET=1**. The values of these settings will depend on your instance type, expected pod density, and workload. More info about these CNI settings can be found [here](https://github.com/aws/amazon-vpc-cni-k8s/blob/master/docs/eni-and-ip-target.md). The maximum number of IP addresses per node (and thus maximum number of pods per node) depends on instance type and can be looked up [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-eni.html#AvailableIpPerENI).

2. If you have found the right CNI settings as described above, the subnets created by eksctl still do not provide enough addresses (by default eksctl creates a “/19” subnet for each nodegroup, which contains ~8.1k addresses). You can configure CNI to take addresses from (larger) subnets that you create. For example, you could create a few “/16” subnets, which contain ~65k IP addresses per subnet. You should implement this option after you have configured the CNI settings as described in #1. To configure your pods to use IP addresses from larger manually-created subnets, use CNI custom networking (see below for more information):

**CNI custom networking**

By default, the CNI assigns the Pod’s IP address from the worker node's primary elastic network interface's (ENI) security groups and subnet. If you don’t have enough IP addresses in the worker node subnet, or prefer that the worker nodes and Pods reside in separate subnets to avoid IP address allocation conflicts between Pods and other resources in the VPC, you can use [CNI custom networking](https://docs.aws.amazon.com/eks/latest/userguide/cni-custom-network.html).

Enabling a custom network removes an available elastic network interface (and all of its available IP addresses for pods) from each worker node that uses it. The worker node's primary network interface is not used for pod placement when a custom network is enabled.

If you want the CNI to assign IP addresses for Pods from a different subnet, you can set `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG` environment variable to `true`.

```shell
kubectl set env daemonset aws-node \
-n kube-system AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG=true
```

When `AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG=true`, the CNI will assign Pod IP address from a subnet defined in `ENIConfig`. The `ENIConfig` custom resource is used to define the subnet in which Pods will be scheduled. 

```yaml
apiVersion: crd.k8s.amazonaws.com/v1alpha1
kind: ENIConfig
metadata: 
  name: us-west-2a
spec: 
  securityGroups: 
    - sg-0dff111a1d11c1c11
  subnet: subnet-011b111c1f11fdf11
```

You will need to create an `ENIconfig` custom resource for each subnet you want to use for Pod networking. 

* The `securityGroups` field should have the ID of the security group attached to the worker nodes. 

* The `name` field should be the name of the Availability Zone in your VPC. If you name your ENIConfig custom resources after each Availability Zone in your VPC, you can enable Kubernetes to automatically apply the corresponding ENIConfig for the worker node Availability Zone with the following command.

```shell
kubectl set env daemonset aws-node \
-n kube-system ENI_CONFIG_LABEL_DEF=failure-domain.beta.kubernetes.io/zone
```

!!! Note
    Upon creating the `ENIconfig` custom resources, you will need to create new worker nodes. The existing worker nodes and Pods will remain unaffected.

#### **Recommendation 2: Prevent EC2 VPC API throttling from AssignPrivateIpAddresses & AttachNetworkInterface**

Often EKS cluster scale-out time can increase because the CNI is being throttled by the EC2 VPC APIs. The following steps can be taken to prevent these issues:

1. Use CNI version 1.8.0 or later as it reduces the calls to EC2 VPC APIs than earlier versions.

2. Configure the **MINIMUM_IP_TARGET** and **WARM_IP_TARGET** parameters instead of the default parameter of **WARM_ENI_TARGET=1**. Only those IP addresses that are necessary are requested from EC2. The values of these settings will depend on your instance type and expected pod density. More info about these settings [here](https://github.com/aws/amazon-vpc-cni-k8s/blob/master/docs/eni-and-ip-target.md).

3. Request an API limit increase on the EC2 VPC APIs that are getting throttled. This option should be considered only after steps 1 & 2 have been done.

### **Other Recommendations for Amazon VPC CNI**

#### **Plan for growth**

Size the subnets you will use for Pod networking for growth. If you have insufficient IP addresses available in the subnet that the CNI uses, your pods will not get an IP address. The pods will remain in the pending state until an IP address becomes available. This may impact application autoscaling and compromise its availability.

#### **Monitor IP address inventory**

You can monitor the IP addresses inventory of subnets using the [CNI Metrics Helper](https://docs.aws.amazon.com/eks/latest/userguide/cni-metrics-helper.html), and set [CloudWatch alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html) to get notified if a subnet is running out of IP addresses.

#### **SNAT setting**

Source Network Address Translation (source-nat or SNAT) allows traffic from a private network to go out to the internet. Virtual machines launched on a private network can get to the internet by going through a gateway capable of performing SNAT. If your Pods with private IP address need to communicate with other private IP address spaces (for example, Direct Connect, VPC Peering or Transit VPC), then you should enable [external SNAT](https://docs.aws.amazon.com/eks/latest/userguide/external-snat.html) in the CNI:

```shell
kubectl set env daemonset \
-n kube-system aws-node AWS_VPC_K8S_CNI_EXTERNALSNAT=true
```

### **CoreDNS Best practices**

#### **Prevent CoreDNS from being overwhelmed (UnknownHostException in spark jobs and other pods)**

CoreDNS is a deployment, which means it runs a fixed number of replicas and thus does not scale out with the cluster. This can be a problem for workloads that do a lot of DNS lookups. One simple solution is to install [dns-autoscaler](https://kubernetes.io/docs/tasks/administer-cluster/dns-horizontal-autoscaling/#enablng-dns-horizontal-autoscaling), which adjusts the number of replicas of the CoreDNS deployment as the cluster grows and shrinks.

#### **Monitor CoreDNS metrics**

CoreDNS is a deployment, which means it runs a fixed number of replicas and thus does not scale out with the cluster. This can cause workloads to timeout with unknownHostException as spark-executors will do a lot of DNS lookups which registering themselves to spark-driver. One simple solution to fix this is to install [dns-autoscaler](https://kubernetes.io/docs/tasks/administer-cluster/dns-horizontal-autoscaling/#enablng-dns-horizontal-autoscaling), which adjusts the number of replicas of the CoreDNS deployment as the cluster grows and shrinks.

## **Cluster Autoscaler Best practices**

#### **Increase cluster-autoscaler memory to avoid unnecessary exceptions**

Cluster-autoscaler can require a lot of memory to run because it stores a lot of information about the state of the cluster, such as data about every pod and every node. If the cluster-autoscaler has insufficient memory, it can lead to the cluster-autoscaler crashing.  Ensure that you provide the cluster-autoscaler deployment more memory, e.g., 1Gi memory instead of the default 300Mi. Useful information about configuring the cluster-autoscaler for improved scalability and performance can be found [here](https://docs.aws.amazon.com/eks/latest/userguide/cluster-autoscaler.html#ca-deployment-considerations)

#### **Avoid job failures when Cluster Autoscaler attempts scale-in**

Cluster Autoscaler will attempt scale-in action for any under utilized instance within your EKScluster. When scale-in action is performed, all pods from that instance is relocated to another node. This could cause disruption for critical workloads. For example, if driver pod is restarted, the entire job needs to restart. For this reason, we recommend using Kubernetes annotations on all critical pods (especially driver pods) and for cluster autoscaler deployment. Please see [here](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/FAQ.md#what-types-of-pods-can-prevent-ca-from-removing-a-node) for more info

```yaml
cluster-autoscaler.kubernetes.io/safe-to-evict=false
```

#### **Configure overprovisioning with Cluster Autoscaler for higher priority jobs**

If the required resources is not available in the cluster, pods go into pending state. Cluster Autoscaler uses this metric to scale out the cluster and this activity can be time-consuming (several minutes) for higher priority jobs. In order to minimize time required for scaling, we recommend [overprovisioning](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/FAQ.md#how-can-i-configure-overprovisioning-with-cluster-autoscaler) resources. You can launch pause pods(dummy workloads which sleeps until it receives SIGINT or SIGTERM) with negative priority to reserve EC2 capacity. Once the higher priority jobs are scheduled, these pause pods are preempted to make room for high priority pods which in turn scales out additional capacity as a buffer. You need to be aware that this is a trade-off as it adds slightly higher cost while minimizing scheduling latency. You can read more about over provisioning best practice [here](https://aws.github.io/aws-eks-best-practices/cluster-autoscaling/#overprovisioning).

## EKS Control Plane Best practices 

#### **API server overwhelmed**

System pods, workload pods, and external systems can make many calls to the Kubernetes API server. This can decrease performance and also increase EMR on EKS job failures. There are multiple ways to avoid API server availability issues including but not limited to:

  * By default, the EKS API servers are automatically scaled to meet your workload demand. If you see increased latencies, please contact AWS via a support ticket and work with engineering team to resolve the issue.

  * Consider reducing the scan interval of [cluster-autoscaler from the 10 second](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/FAQ.md#how-does-scale-up-work) default value. Each time the cluster-autoscaler runs, it makes many calls to the API server. However, this will result in the cluster scaling-out less frequently and in larger steps (and same with scaling back in when load is reduced). More information can be found about the cluster-autoscaler [here](https://docs.aws.amazon.com/eks/latest/userguide/cluster-autoscaler.html#ca-deployment-considerations). This is not recommended if you need jobs to start ASAP.

  * If you are running your own deployment of fluentd, an increased load on the APIserver can be observed. Consider using fluent-bit instead which makes fewer calls to the API server. More info can be found [here](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-EKS-logs.html)

#### **Monitor Control Plane Metrics**

Monitoring Kubernetes API metrics can give you insights into control plane performance and identify issues. An unhealthy control plane can compromise the availability of the workloads running inside the cluster. For example, poorly written controllers can overload the API servers, affecting your application's availability.

Kubernetes exposes control plane metrics at the  `/metrics` endpoint. 

You can view the metrics exposed using `kubectl`:

```shell
kubectl get --raw /metrics
```

These metrics are represented in a [Prometheus text format](https://github.com/prometheus/docs/blob/master/content/docs/instrumenting/exposition_formats.md). 

You can use Prometheus to collect and store these metrics. In May 2020, CloudWatch added support for monitoring Prometheus metrics in CloudWatch Container Insights. So you can also use Amazon CloudWatch to monitor the EKS control plane. You can follow the [Tutorial for Adding a New Prometheus Scrape Target: Prometheus KPI Server Metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ContainerInsights-Prometheus-Setup-configure.html#ContainerInsights-Prometheus-Setup-new-exporters) to collect metrics and create CloudWatch dashboard to monitor your cluster’s control plane.

You can also find Kubernetes API server metrics [here](https://github.com/kubernetes/apiserver/blob/master/pkg/endpoints/metrics/metrics.go). For example, `apiserver_request_duration_seconds` can indicate how long API requests are taking to run. 

Consider monitoring these control plane metrics:

### API Server

| Metric | Description  |
|:--|:--|
|  `apiserver_request_total` | Counter of apiserver requests broken out for each verb, dry run value, group, version, resource, scope, component, client, and HTTP response contentType and code. |
| `apiserver_request_duration_seconds*`  | Response latency distribution in seconds for each verb, dry run value, group, version, resource, subresource, scope, and component. |
| `rest_client_request_duration_seconds` | Request latency in seconds. Broken down by verb and URL. |
| `apiserver_admission_controller_admission_duration_seconds` | Admission controller latency histogram in seconds, identified by name and broken out for each operation and API resource and type (validate or admit). | 
| `rest_client_request_duration_seconds` | Request latency in seconds. Broken down by verb and URL. |
| `rest_client_requests_total`  | Number of HTTP requests, partitioned by status code, method, and host. | 

### etcd

| Metric | Description  |
|:--|:--|
| `etcd_request_duration_seconds` | Etcd request latency in seconds for each operation and object type. | 

You can visualize and monitor these Kubernetes API server requests, latency and etcD metrics on Grafana via [Grafana dashboard 12006](https://grafana.com/grafana/dashboards/12006).