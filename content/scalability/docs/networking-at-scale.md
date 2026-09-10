# **Networking at Scale**

Running large-scale Spark workloads with Amazon EMR on EKS places significant demands on VPC networking. Every Spark driver and executor runs as a Kubernetes pod, and by default every pod consumes a VPC IP address. At high concurrency (tens of thousands of pods), IP address consumption and VPC-level limits become the primary scaling constraints — often before compute capacity does.

This article explains the key limits to understand, how to mitigate them with VPC CNI prefix delegation, the trade-offs of prefix delegation under IPv4, and longer-term options such as IPv6 and additional CIDR ranges.

## **Understand the Network Address Usage (NAU) Limit**

[Network Address Usage (NAU)](https://docs.aws.amazon.com/vpc/latest/userguide/network-address-usage.html) is a metric applied to resources in a VPC to help you plan for and monitor the size of your VPC. NAU is a hard, VPC-level constraint:

* Each VPC has a default quota of 64,000 NAU units, which can be increased to a maximum of **256,000**.
* Without prefix delegation, **one NAU unit is consumed per IP address**, and each non-`hostNetwork` pod (i.e., every Spark driver and executor pod) requires one IP address.
* In practice, the usable pod capacity is considerably lower than the raw NAU quota, because:
    1. Other AWS services and resources in the same VPC (load balancers, endpoints, EFA interfaces, etc.) also consume NAU units, and some of them do not support prefix delegation.
    2. IP addresses warmed or allocated to EC2 worker nodes but not yet assigned to pods still count against the limit.

For a shared VPC hosting multiple EKS clusters and other workloads, it is common for the realistic pod ceiling to be well under half of the theoretical NAU quota. **Monitor NAU utilization** (available through CloudWatch when you enable the *Network Address Usage metrics* setting on the VPC) before it becomes an incident: NAU exhaustion manifests as instance launch and network interface allocation failures across the entire VPC, not just one cluster.

## **Enable VPC CNI Prefix Delegation**

[Prefix delegation](https://docs.aws.amazon.com/eks/latest/best-practices/prefix-mode-linux.html) is the single most effective mitigation for both NAU pressure and per-node pod density under IPv4:

* Instead of attaching individual secondary IP addresses to a node's ENIs, the VPC CNI attaches **/28 prefixes (16 IP addresses each)**, and **each prefix consumes only one NAU unit**.
* This changes the math dramatically: 192,000 NAU units support only 192,000 IP addresses without prefix delegation, but theoretically up to ~3 million IP addresses with it.
* It also increases the maximum number of pods per node, which matters for densely packed Spark executors.

To enable it on the VPC CNI:

```bash
kubectl set env daemonset aws-node -n kube-system ENABLE_PREFIX_DELEGATION=true
kubectl set env daemonset aws-node -n kube-system WARM_PREFIX_TARGET=1
```

Recommendations:

* Set `WARM_PREFIX_TARGET=1` (the recommended minimum). A higher value speeds up pod startup during scale-out bursts but reserves more unused addresses per node.
* Prefix delegation requires nitro-based instances and **contiguous /28 blocks** of free addresses in the subnet. Enable it on new node groups / fresh subnets where possible — fragmented subnets that have long been used for individual IP allocation may not have contiguous blocks available.
* Roll nodes (or restart the CNI) after enabling; existing nodes keep their previous allocation mode until replaced.

## **Remaining Challenges with Prefix Delegation on IPv4**

Prefix delegation relieves NAU pressure, but it does not eliminate IPv4 constraints, and it introduces new utilization trade-offs:

1. **IPv4 address exhaustion.** Prefix delegation consumes subnet address space in /28 chunks. Large Spark fleets can still exhaust the private IPv4 space allocated to a VPC, and expanding subnets or adding CIDR ranges is often slow in enterprise environments where address space is centrally managed.
2. **Inefficient IP address utilization.**
    * Each allocated /28 prefix provides 16 IP addresses, but a node may only use a few of them, stranding the rest.
    * With `WARM_PREFIX_TARGET=1`, every node holds at least one full warm prefix — a floor of 16 reserved-but-unused addresses per node. Across thousands of nodes this adds up to a substantial amount of provisioned-but-idle address space.
3. **Uneven prefix consumption across subnets.** Cluster autoscalers such as Karpenter are not aware of per-subnet prefix availability when placing nodes. Some subnets can run out of contiguous /28 blocks while sibling subnets still have plenty, causing pod scheduling failures even though the VPC as a whole has spare capacity. Mitigations include keeping subnets uniformly sized, spreading node provisioning across subnets, and alarming on per-subnet free-prefix counts rather than free-IP counts.
4. **Hard caps on subnet growth.** Organizations frequently cap the maximum subnet CIDR size (for example at /18) and the total address space per network segment. If your workload has grown by an order of magnitude over a few years, a one-time subnet expansion buys time but is not a durable answer — plan for one of the structural options below.

Sharding EMR on EKS clusters across multiple VPCs or network segments is sometimes proposed as a workaround for IPv4 exhaustion. Be aware of the operational cost: each additional segment typically means another deployment target for cluster pipelines, more security group rules to keep cross-segment connectivity working, and more places for networking configuration to drift. Treat sharding as a last resort rather than a scaling strategy.

## **Structural Options for IP Address Scalability**

### **Option 1: IPv6 (Recommended Long-Term Direction)**

Running EKS clusters in [IPv6 mode](https://docs.aws.amazon.com/eks/latest/userguide/cni-ipv6.html) permanently removes IP address scarcity:

1. IPv6 eliminates the address shortage problem outright. An EKS IPv6 cluster VPC receives a /56 CIDR, and every subnet is a fixed /64 — **2^64 (roughly 18 quintillion) addresses per subnet**. IP capacity effectively ceases to be a planning dimension.
2. Each node receives a single IPv6 prefix that is large enough for all of its pods, so nodes never need to request additional prefixes at runtime. This removes prefix-allocation latency during scale-out and the associated EC2 API throttling risk.
3. NAU efficiency improves further: one prefix per node, one NAU unit per node — regardless of how many pods the node runs.
4. Uneven prefix utilization across subnets disappears, because subnets can no longer run out of prefixes.
5. Cluster management is simplified: many clusters can share one VPC/network segment without IPv4 capacity planning.

Considerations before adopting IPv6:

1. **Organizational readiness.** Many enterprises have adopted IPv6 only for internet-facing services. Internal service-to-service paths (DNS, proxies, firewalls, on-premises connectivity) must support IPv6 or provide translation (NAT64/DNS64, or the egress-only IPv4 support built into EKS IPv6 clusters).
2. **Service support.** Verify that the EMR on EKS release and features you depend on support IPv6 clusters, and check the current status in the [EMR on EKS documentation](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/emr-eks.html) before committing to a migration.
3. IPv6 mode is set at **EKS cluster creation time** and cannot be changed later, so adoption means standing up new EKS clusters and migrating workloads to them.

### **Option 2: Secondary CIDR Ranges with Custom Networking**

You can extend an IPv4 VPC by associating secondary CIDR blocks — the [EKS best practices guide](https://docs.aws.amazon.com/eks/latest/best-practices/ip-opt.html) recommends the [RFC 6598](https://datatracker.ietf.org/doc/html/rfc6598) carrier-grade NAT range `100.64.0.0/10`, which rarely conflicts with corporate address plans — and using [VPC CNI custom networking](https://docs.aws.amazon.com/eks/latest/best-practices/custom-networking.html) to place pods in those subnets while nodes remain in the primary ranges.

* **IP capacity:** each secondary CIDR block can be at most a /16 (65,536 addresses), but you can associate multiple blocks (default quota: 5 CIDR blocks per VPC, adjustable up to 50). Drawing from `100.64.0.0/10` alone, a VPC at the maximum quota can reach **~3.2 million pod IP addresses (50 × /16)** — and the full `100.64.0.0/10` range holds ~4.2 million addresses if spread across VPCs. For most Spark fleets, the practical ceiling arrives first at the NAU limit or the route/CIDR quotas, not the address space itself.
* This provides significant new pod address space without touching the primary corporate address allocation.
* Trade-offs: pods in non-routable ranges need NAT for traffic leaving the VPC, custom networking disables the primary ENI for pods (slightly reducing per-node pod density), and it adds configuration complexity (`ENIConfig` per AZ).
* Note that secondary-CIDR addresses still consume NAU units, so this addresses IPv4 scarcity but not the NAU ceiling — combine it with prefix delegation.

A related, lower-friction variant: if your pods do not need separate subnets/security groups from nodes, [enhanced subnet discovery](https://aws.amazon.com/blogs/containers/amazon-vpc-cni-introduces-enhanced-subnet-discovery/) (VPC CNI ≥ 1.18, `ENABLE_SUBNET_DISCOVERY=true` by default) lets the CNI automatically use additional tagged subnets from new CIDR blocks without `ENIConfig` objects.

## **Summary of Recommendations**

AWS network (the VPC) has a fixed pool of IP addresses, and when the pool runs dry, new executors simply fail to start — the job queue backs up even though you have plenty of compute available. Think of network addresses as one more cluster resource to plan and monitor, alongside vCPUs and memory.

The recommendations are:

1. **Know your address budget and watch it like a resource metric.** Ask your networking team to raise the VPC's Network Address Usage (NAU) quota, turn on the [NAU CloudWatch metrics](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-cloudwatch.html#nau-monitoring-enable) (`NetworkAddressUsage` and `NetworkAddressUsagePeered` metrics in the `AWS/EC2` CW namespace, reported every 24 hours), and [set an alarm](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-cloudwatch.html#nau-cloudwatch-alarm-example) well before the pool is exhausted. Running out of addresses is a whole-VPC outage, not a single-job failure.
2. **Turn on prefix delegation everywhere.** It is a one-line configuration change (`ENABLE_PREFIX_DELEGATION=true`, `WARM_PREFIX_TARGET=1`) that hands out IP addresses in blocks of 16 instead of one at a time. It roughly multiplies how many Spark pods the same network can hold, with very little risk. Do this first.
3. **Monitor the right thing: free address blocks per subnet, not just free addresses.** A subnet can look half-empty yet have no contiguous 16-address blocks left, and executors will fail to schedule there. Keep subnets similar in size and let nodes spread across them evenly.
4. **Decide on a long-term plan before you hit the wall.** If your Spark usage keeps growing, one-time network expansions only buy months. Moving to IPv6 removes address limits permanently and is the recommended destination; adding secondary address ranges (custom networking) is the proven intermediate step that can add roughly 3 million pod addresses to a VPC without touching your company's main address plan.
5. **Resist splitting into more clusters or networks just to get more addresses.** Every extra network segment means more deployment pipelines, more firewall rules, and more ways for jobs to fail mysteriously. Use the options above first; treat splitting as a last resort.

## **References**

* [Network Address Usage — Amazon VPC User Guide](https://docs.aws.amazon.com/vpc/latest/userguide/network-address-usage.html)
* [Prefix Mode for Linux — Amazon EKS Best Practices Guide](https://docs.aws.amazon.com/eks/latest/best-practices/prefix-mode-linux.html)
* [Assign IPv6 addresses to clusters, pods, and services — Amazon EKS User Guide](https://docs.aws.amazon.com/eks/latest/userguide/cni-ipv6.html)
* [Custom Networking — Amazon EKS Best Practices Guide](https://docs.aws.amazon.com/eks/latest/best-practices/custom-networking.html)
* [Optimizing IP Address Utilization — Amazon EKS Best Practices Guide](https://docs.aws.amazon.com/eks/latest/best-practices/ip-opt.html)
* [VPC CIDR blocks — Amazon VPC User Guide](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-cidr-blocks.html)
* Public case studies from large-scale EKS adopters describe production experience with large-scale IP management and IPv6 on EKS: [Spark on Amazon EKS networking at Pinterest — Part 1](https://aws.amazon.com/blogs/containers/spark-on-amazon-eks-networking-part-1/) and [Part 2](https://aws.amazon.com/blogs/containers/spark-on-amazon-eks-networking-part-2/), and [The journey to IPv6 on Amazon EKS — Part 1](https://aws.amazon.com/blogs/containers/the-journey-to-ipv6-on-amazon-eks-foundation-part-1/) and [Part 2](https://aws.amazon.com/blogs/containers/the-journey-to-ipv6-on-amazon-eks-implementation-patterns-part-2/).
