# **Karpenter Best Practices**

Karpenter is an open-source node provisioning tool for Kubernetes. It can help improve the efficiency and cost of running large-scale data workloads. Karpenter's ability to dynamically provision optimal resources for heterogeneous workloads, efficiently manage large numbers of clusters, [optimize cost through consolidation](https://aws.amazon.com/blogs/compute/applying-spot-to-spot-consolidation-best-practices-with-karpenter/), and prioritize EC2 Spot instances make it the preferred auto-scaler for workloads on Amazon Elastic Kubernetes Service (EKS).

We recommend using Karpenter and Bottlerocket with EKS for data workloads, as it aligns with EC2 Spot best practices of diversification, using allocation strategy, and can manage the Spot lifecycle seamlessly. As documented in the [Spark Operator with YuniKorn DoEKS blueprint](https://awslabs.github.io/data-on-eks/docs/blueprints/data-analytics/spark-operator-yunikorn), Karpenter integrates seamlessly with Kubernetes, providing automatic, real-time adjustments to the cluster size based on observed workloads and scaling events. This enables a more efficient and cost-effective EKS cluster design that adapts to the ever-changing demands of Spark applications and other data workloads. 

More details can be found in these blogs [[1](https://aws.amazon.com/blogs/compute/applying-spot-to-spot-consolidation-best-practices-with-karpenter/), [2](https://aws.amazon.com/blogs/containers/using-amazon-ec2-spot-instances-with-karpenter/)]. 

## Key considerations
1.**[Interruption handling](https://karpenter.sh/preview/reference/cloudformation/#interruption-handling) for Spot** - to use Spot instances with Karpenter, first deploy the infrastructure [CloudFormation template](https://karpenter.sh/v1.8/reference/cloudformation/) that provisions the SQS interruption queue and related EventBridge rules, then install the Karpenter Helm chart configured to use that queue:
```bash
export KARPENTER_VERSION="1.8.6"
curl https://raw.githubusercontent.com/aws/karpenter-provider-aws/v"${KARPENTER_VERSION}"/website/content/en/preview/getting-started/getting-started-with-karpenter/cloudformation.yaml > cloudformation.yaml

aws cloudformation deploy --stack-name "karpenter-infra-${CLUSTER_NAME}" \
--template-file cloudformation.yaml
....

helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
....
--set "settings.interruptionQueue=${CLUSTER_NAME}" \
....
```
This configuration enables Karpenter to watch the SQS interruption queue for Spot interruption warnings, scheduled maintenance, and other involuntary events, and to taint, drain, and replace affected nodes before they are terminated.


2.**Separate NodePools for Spark driver and executors** - to balance cost and stability for Spark on EKS with Karpenter, create two dedicated NodePools:

**A driver NodePool** - uses `WhenEmpty` consolidation to minimize disruption

```bash
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: driver-nodepool
spec:
  disruption:
    consolidateAfter: 1m
    consolidationPolicy: WhenEmpty
  template:
    spec:
      nodeClassRef:
        name: memory-optimized-ec2
        .....
```
**An executor NodePool** - consolidate executor nodes `WhenEmptyOrUnderutilized` for aggressive cost savings.
```bash
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: executor-nodepool
spec:  
  disruption:
    consolidateAfter: 1m
    consolidationPolicy: WhenEmptyOrUnderutilized
  template:
    spec:
      nodeClassRef:
        name: memory-optimized-ec2
        .....
```


## Cost optimization with Karpenter, Spot and Graviton

To achieve high cost optimizations with Spark, we recommend using the following Karpenter nodepool configurations. 

```
- key:karpenter.sh/capacity-type
  operator: In
  values:
    - on-demand
    - spot- key:kubernetes.io/arch
  operator: In
  values:
    - amd64
    - arm64
```
For pod specs:

```
nodeAffinity:
 preferedDuringSchedulingIgnoredDuringExecution:
  - weight: 1
    preference:
     matchExpressions:
        - key:beta.kubernetes.io/arch
          operator: In
          values:
            - arm64
```
By applying this configuration, Karpenter should select the instance type in the following order, and fallback to another instance type immediately if the instance type is not available:

* arm spot
* x86 spot
* arm on-demand
* x86 on-demand

## Configure proper consolidation policy 

For Spark workloads, configure the executor nodepool:

* Enable Pod bin packing for batch jobs
* Configure Karpenter's Consolidation to "WhenEmptyOrUnderutilized"
* Increase "consolidateAfter" if needed
* Set expiry time to longest-running EMR on EKS job duration (Example: Set to 4 hours if that's your longest job run time over the entire workload)


## Capacity management and prioritize instance types based your workloads

**Capacity Management**

AWS brings a large number of instance types, but there are some circumstances that some instance types are not available due to EC2 capacity, We suggest configure instance type as many as you can especially for Spot instances. Allowing Karpenter to provision nodes from a large, diverse set of instance types will help you to stay on Spot longer and lower your costs due to Spot’s discounted pricing. Moreover, if Spot capacity becomes constrained, this instance type diversity will also increase the chances that you’ll be able to continue to launch On-Demand capacity for your workloads.

Multi-arch support is also recommended for capacity management, it will increase the instance diversity along with the performance improvement by Graviton.

**Prioritize instance types based your workloads**

Workloads have different requirements, for example, Spark workloads need high memory ratios. You can create weighted nodepools to prioritize some specific instance types like the following, Karpenter will first try using ```nodepool-high-weight```.

***Nodepool with weight to 50***

```
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: nodepool-high-weight
spec:
  template:
    metadata:
      labels:
        billing-team: my-team
      annotations:
        example.com/owner: "my-team"
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws  # Updated since only a single version will be served
        kind: EC2NodeClass
        name: default
      taints:
        - key: example.com/special-taint
          effect: NoSchedule

      expireAfter: Never
      requirements:
        - key: "karpenter.k8s.aws/instance-category"
          operator: In
          values: ["c", "m", "r"]
          # minValues here enforces the scheduler to consider at least that number of unique instance-category to schedule the pods.
          # This field is ALPHA and can be dropped or replaced at any time
          minValues: 2
        - key: "karpenter.k8s.aws/instance-family"
          operator: In
          values: ["r7g","r6g"]
        - key: "karpenter.k8s.aws/instance-cpu"
          operator: In
          values: ["4", "8", "16", "32"]
        - key: "karpenter.k8s.aws/instance-hypervisor"
          operator: In
          values: ["nitro"]
        - key: "karpenter.k8s.aws/instance-generation"
          operator: Gt
          values: ["2"]
        - key: "topology.kubernetes.io/zone"
          operator: In
          values: ["us-west-2a", "us-west-2b"]
        - key: "kubernetes.io/arch"
          operator: In
          values: ["arm64", "amd64"]
        - key: "karpenter.sh/capacity-type"
          operator: In
          values: ["spot", "on-demand", "reserved"]
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 1m | Never # Added to allow additional control over consolidation aggressiveness
    budgets:
    - nodes: 10%
    - schedule: "0 9 * * mon-fri"
      duration: 8h
      nodes: "0"
  limits:
    cpu: "1000"
    memory: 1000Gi
  weight: 50
```
***Nodepool with weight to 10***

```
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: nodepool-high-weight
spec:
  template:
    metadata:
      labels:
        billing-team: my-team
      annotations:
        example.com/owner: "my-team"
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws  # Updated since only a single version will be served
        kind: EC2NodeClass
        name: default
      taints:
        - key: example.com/special-taint
          effect: NoSchedule

      expireAfter: Never
      requirements:
        - key: "karpenter.k8s.aws/instance-category"
          operator: In
          values: ["c", "m", "r"]
          # minValues here enforces the scheduler to consider at least that number of unique instance-category to schedule the pods.
          # This field is ALPHA and can be dropped or replaced at any time
          minValues: 2
        - key: "karpenter.k8s.aws/instance-family"
          operator: In
          values: ["c5","c6i"]
        - key: "karpenter.k8s.aws/instance-cpu"
          operator: In
          values: ["4", "8", "16", "32"]
        - key: "karpenter.k8s.aws/instance-hypervisor"
          operator: In
          values: ["nitro"]
        - key: "karpenter.k8s.aws/instance-generation"
          operator: Gt
          values: ["2"]
        - key: "topology.kubernetes.io/zone"
          operator: In
          values: ["us-west-2a", "us-west-2b"]
        - key: "kubernetes.io/arch"
          operator: In
          values: ["arm64", "amd64"]
        - key: "karpenter.sh/capacity-type"
          operator: In
          values: ["spot", "on-demand", "reserved"]
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 1m | Never # Added to allow additional control over consolidation aggressiveness
    budgets:
    - nodes: 10%
    - schedule: "0 9 * * mon-fri"
      duration: 8h
      nodes: "0"
  limits:
    cpu: "1000"
    memory: 1000Gi
  weight: 10
```

## Carefully configure resource requests and limits for workloads

Rightsizing and optimizing your cluster is a shared responsibility. Karpenter effectively optimizes and scales infrastructure, but the end result depends on how well you have rightsized your pod requests and any other Kubernetes scheduling constraints. Karpenter does not consider limits or resource utilization. For most workloads with non-compressible resources, such as memory, it is generally recommended to set requests==limits because if a workload tries to burst beyond the available memory of the host, an out-of-memory (OOM) error occurs. Karpenter consolidation can increase the probability of this as it proactively tries to reduce total allocatable resources for a Kubernetes cluster. For help with rightsizing your Kubernetes pods, consider exploring Kubecost, Vertical Pod Autoscaler configured in recommendation mode, or an open source tool such as Goldilocks.


For each instance type, Karpenter reports max allocatable [resources](https://karpenter.sh/docs/reference/instance-types/) with some assumptions and after the instance overhead has been subtracted, for example, the m6g.8xlarge max allocatable resources(defaults) are as follows:

| Resource	                | Quantity |
| ------------------------- | -------- |
| cpu	                    |  31850m  |
| ephemeral-storage         |	17Gi   |
| memory	                | 118253Mi |
| pods	                    | 234      |
| vpc.amazonaws.com/pod-eni	| 54       |

For some circumstances, you may want the Karpenter to provide more resources than the defaults or the rest of the resources can not host one pod, you can adjust the ```VM_MEMORY_OVERHEAD_PERCENT``` to 0.07. The guidance is by adjusting ```VM_MEMORY_OVERHEAD_PERCENT```, one more pod can be scheduled on the Karpenter node.


## Pressure testing with Karpenter

If using a new account with Karpenter or a account that has not too much EC2 scaling especially for Spark workloads, we recommend do some pressure testing with Karpenter to know your account EC2 api throttling before go production based on your EC2 scale size because of Karpenter is extremely fast to call the following EC2 api.

The following api calls are mainly called by Karpenter
```
ModifyNetworkingInterfaceAttribute
CreateTags
AssignPrivateIpAddress
DescribeNetworkInterfaces
DescribeIamInstanceProfileAssociations
DescribeInstances
CreateFleet
DescribeTags
DeleteSecurityGroup
UnassignPrivateIpAddress
DeleteLaunchTemplate
```

## Avoid using pod anti-affinity for large scale with Karpenter

Karpenter will have more time to do the simulation of scheduling pods if there is pod anti-affinity. Starting with Karpenter v0.32.6, there are performance improvements around using hostname topologies. But we recommend do not use pod anti-affinity for large scale.
