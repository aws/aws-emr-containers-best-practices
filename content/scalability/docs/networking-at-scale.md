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

1. IPv6 eliminates the address shortage problem outright — each subnet gets a /64, which is more address space than any cluster can consume.
2. Each node receives a single IPv6 prefix that is large enough for all of its pods, so nodes never need to request additional prefixes at runtime. This removes prefix-allocation latency during scale-out and the associated EC2 API throttling risk.
3. NAU efficiency improves further: one prefix per node, one NAU unit per node — regardless of how many pods the node runs.
4. Uneven prefix utilization across subnets disappears, because subnets can no longer run out of prefixes.
5. Cluster management is simplified: many clusters can share one VPC/network segment without IPv4 capacity planning.

Considerations before adopting IPv6:

1. **Organizational readiness.** Many enterprises have adopted IPv6 only for internet-facing services. Internal service-to-service paths (DNS, proxies, firewalls, on-premises connectivity) must support IPv6 or provide translation (NAT64/DNS64, or the egress-only IPv4 support built into EKS IPv6 clusters).
2. **Service support.** Verify that the EMR on EKS release and features you depend on support IPv6 clusters, and check the current status in the [EMR on EKS documentation](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/emr-eks.html) before committing to a migration.
3. **Application stack support.** Validate open-source components — including Apache Spark and its shuffle, RPC, and UI layers — against IPv6 in a staging environment. Bind-address and address-parsing assumptions in JVM applications are a common source of issues.
4. IPv6 mode is set at **cluster creation time** and cannot be changed later, so adoption means standing up new clusters and migrating workloads.

### **Option 2: Secondary CIDR Ranges with Custom Networking**

You can extend an IPv4 VPC by associating secondary CIDR blocks — commonly from the RFC 6598 carrier-grade NAT range `100.64.0.0/10`, which rarely conflicts with corporate address plans — and using [VPC CNI custom networking](https://docs.aws.amazon.com/eks/latest/best-practices/custom-networking.html) to place pods in those subnets while nodes remain in the primary ranges.

* This provides significant new pod address space without touching the primary corporate address allocation.
* Trade-offs: pods in non-routable ranges need NAT for traffic leaving the VPC, custom networking disables the primary ENI for pods (slightly reducing per-node pod density), and it adds configuration complexity (`ENIConfig` per AZ).
* Note that secondary-CIDR addresses still consume NAU units, so this addresses IPv4 scarcity but not the NAU ceiling — combine it with prefix delegation.

### **Option 3: Class E Address Space (240.0.0.0/4)**

Some very large Kubernetes operators have used the reserved Class E range (`240.0.0.0/4`) as VPC CIDR space to obtain vast private IPv4 capacity. Approach this with caution:

* The range is usable within a VPC for private communication, but it is not routable on the internet and is rejected by some operating systems, network appliances, and on-premises equipment.
* It is best suited to fully self-contained east-west traffic (for example, Spark executor-to-executor communication) where all endpoints are known to tolerate it.
* Test thoroughly against every device and OS in the traffic path before adopting it.

## **Summary of Recommendations**

1. **Raise and monitor the NAU quota** for any VPC hosting large EMR on EKS deployments; alarm well before exhaustion.
2. **Enable prefix delegation** with `WARM_PREFIX_TARGET=1` on all EMR on EKS clusters — it is the highest-leverage, lowest-risk change.
3. **Watch per-subnet contiguous-prefix availability**, not just free IP counts; keep subnets uniform and spread node placement.
4. **Plan a structural fix before you need it.** If your workload growth is sustained, IPv4 subnet expansion only buys time. Evaluate IPv6 as the long-term direction, and secondary CIDRs (or, with caution, Class E space) as intermediate steps.
5. **Avoid sharding clusters across network segments** purely for IP capacity unless you have exhausted the options above — the operational overhead compounds.

## **References**

* [Network Address Usage — Amazon VPC User Guide](https://docs.aws.amazon.com/vpc/latest/userguide/network-address-usage.html)
* [Prefix Mode for Linux — Amazon EKS Best Practices Guide](https://docs.aws.amazon.com/eks/latest/best-practices/prefix-mode-linux.html)
* [Assign IPv6 addresses to clusters, pods, and services — Amazon EKS User Guide](https://docs.aws.amazon.com/eks/latest/userguide/cni-ipv6.html)
* [Custom Networking — Amazon EKS Best Practices Guide](https://docs.aws.amazon.com/eks/latest/best-practices/custom-networking.html)
* Public case studies from large-scale EKS adopters such as Mobileye and Pinterest describe production experience with IPv6 and large-scale IP management on EKS (see the AWS Containers Blog).
