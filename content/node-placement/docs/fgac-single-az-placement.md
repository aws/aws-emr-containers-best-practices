# **Single-AZ Placement for FGAC-enabled Jobs**

## **The problem**

When a job runs with [Lake Formation fine-grained access control (FGAC)](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/security_iam_fgac-lf.html) on EMR on EKS, a single job run creates pods in two namespaces:

| Namespace | Pods | Who controls placement |
|---|---|---|
| User namespace (mapped to the virtual cluster) | job submitter, user driver, user executors | You, through `spark.kubernetes.*.node.selector.*` and the `emr-job-submitter` classification |
| System namespace (from the security configuration) | system job submitter, system driver, system executors | EMR. Your `StartJobRun` node selectors are not applied to these pods |

The [single AZ technique](eks-node-placement.md#single-az-placement) on the EKS Node Placement page pins only the user-namespace pods. The system-namespace pods go wherever the scheduler and the autoscaler (Karpenter or Cluster Autoscaler) find capacity, and on a multi-AZ node pool that is often a different AZ.

The system executors read the data and do most of the shuffle, so a job that spreads them across AZs pays for every shuffle byte that crosses an AZ boundary. In our [benchmark](#measured-impact), that cross-AZ layout made jobs 49% slower and cost 5x as much per job, because the inter-AZ transfer charge was 4x the compute cost.

You also can't fix this with a `nodeSelector` or `nodeAffinity` on the system namespace: EMR creates and owns those pod specs, and pinning the whole system namespace to one AZ would put every FGAC job in the cluster into that AZ.

## **Measured impact**

We ran a TPC-H SF100 benchmark (q3, q5, q9, q18, all read through Lake Formation FGAC) on EMR 7.13 in us-west-2: 7 executors ran in every run, each with 4 vCPU and 14 GiB, on-demand pricing, 3 runs per case. Network bytes come from cAdvisor (`container_network_transmit_bytes_total`). Cross-AZ bytes are an estimate: each executor's transmitted bytes × the share of the job's other system pods that sat in a different AZ.

* **Case A, multi-AZ:** user pods in AZ a, system submitter and driver in AZ b, system executors spread across 3 AZs.
* **Case B, single-AZ:** every pod of the job in one AZ, enforced by the policy below.

| Metric (mean of 3 runs) | A: multi-AZ | B: single-AZ | A vs B |
|---|---|---|---|
| Job wall-clock (s) | 371 | 249 | +49% |
| All 4 queries (s) | 260 | 195 | +33% |
| q3, includes executor startup (s) | 151 | 84 | +81% |
| q5 + q9 + q18, warm executors (s) | 109 | 112 | -2% |
| Estimated cross-AZ traffic (GiB) | 20.1 | 0 | |
| Compute cost, EMR + EC2 ($) | 0.103 | 0.097 | +7% |
| Inter-AZ transfer cost ($) | 0.403 | 0 | |
| **Total cost per job ($)** | **0.506** | **0.097** | **+424%** |

Pricing: EMR on EKS uplift plus the EC2 on-demand per-vCPU share for compute, and $0.01/GB in each direction for inter-AZ transfer (us-west-2, November 2026). The more a job shuffles, the larger the transfer charge grows compared with the compute bill.

## **Solution: copy the submitter's AZ to every pod in the job, at admission time**

Every pod that EMR creates for a job run, in both namespaces, carries the label `emr-containers.amazonaws.com/job.id`. A mutating admission policy can use that label to pin all pods of a job to the AZ that you chose for the user-namespace job submitter:

1. **Pick the AZ on the client.** Set `jobsubmitter.node.selector.topology.kubernetes.io/zone` in the `emr-job-submitter` classification. The client picks a different AZ for each job (round-robin, or based on capacity), which spreads the load across AZs.
2. **Copy the AZ to the rest of the job.** A [Kyverno](https://kyverno.io/) policy intercepts every new pod in the job, looks up the submitter pod with the same `job.id`, and copies its zone into the new pod's `nodeSelector`. This covers the user driver and executors, as well as the system submitter, driver, and executors that you can't configure directly.
3. **Fall back to pod affinity.** If a job is submitted without a zone, the policy adds required pod affinity on `job.id` with `topologyKey: topology.kubernetes.io/zone`. The first pod of the job to be scheduled picks the AZ, and every later pod must follow it.

Because the zone becomes a hard `nodeSelector` before the pod reaches the scheduler, the outcome doesn't depend on which pod is scheduled first. Karpenter also sees the zone constraint and provisions nodes in the right AZ.

### Prerequisites

* An EKS cluster whose node pool (Karpenter NodePool or managed node groups) spans the AZs you plan to use.
* Kyverno 1.11 or later, installed with Helm:

```bash
helm repo add kyverno https://kyverno.github.io/kyverno/
helm install kyverno kyverno/kyverno -n kyverno --create-namespace
```

* The Kyverno admission controller must be able to list pods across namespaces, because the policy uses an API call to find the submitter pod. To check:

```bash
kubectl auth can-i list pods -A \
  --as=system:serviceaccount:kyverno:kyverno-admission-controller
```

### Step 1: Install the Kyverno policy

Change the `namespaces` patterns so they match your user and system namespaces. The example uses `emr-*` for both.

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: emr-job-pods-same-az
  annotations:
    policies.kyverno.io/title: EMR on EKS Spark Job Single-AZ Co-location
    policies.kyverno.io/category: Scheduling
    policies.kyverno.io/subject: Pod
spec:
  admission: true
  # The rules read {{ request.object }}, which exists only during admission.
  background: false
  rules:
    # Rule 1: copy the zone from the zone-pinned job submitter to every other pod of the job.
    - name: inherit-submitter-zone
      skipBackgroundRequests: true
      match:
        any:
          - resources:
              kinds: [Pod]
              operations: [CREATE]
              namespaces: ["emr-*"]
              selector:
                matchExpressions:
                  - key: emr-containers.amazonaws.com/job.id
                    operator: Exists
      context:
        # User and system job-runner pods both have component=job.submitter.
        # Only the user-namespace submitter carries the zone nodeSelector.
        - name: submitterZone
          apiCall:
            urlPath: >-
              /api/v1/pods?labelSelector=emr-containers.amazonaws.com/job.id={{ request.object.metadata.labels."emr-containers.amazonaws.com/job.id" }},emr-containers.amazonaws.com/component=job.submitter
            jmesPath: >-
              items[?spec.nodeSelector."topology.kubernetes.io/zone"]
              | [0].spec.nodeSelector."topology.kubernetes.io/zone" || ''
      preconditions:
        all:
          # Leave pods that already select a zone alone, including the submitter itself.
          - key: '{{ request.object.spec.nodeSelector."topology.kubernetes.io/zone" || '''' }}'
            operator: Equals
            value: ""
          # No zone-pinned submitter: skip, and let Rule 2 handle the job.
          - key: "{{ submitterZone }}"
            operator: NotEquals
            value: ""
      mutate:
        patchStrategicMerge:
          spec:
            nodeSelector:
              topology.kubernetes.io/zone: "{{ submitterZone }}"

    # Rule 2: fallback for jobs submitted without a zone.
    # The first scheduled pod picks the AZ; all later pods of the same job follow it,
    # across both the user and system namespaces.
    - name: colocate-job-pods-in-one-zone
      skipBackgroundRequests: true
      match:
        any:
          - resources:
              kinds: [Pod]
              operations: [CREATE]
              namespaces: ["emr-*"]
              selector:
                matchExpressions:
                  - key: emr-containers.amazonaws.com/job.id
                    operator: Exists
      mutate:
        patchStrategicMerge:
          spec:
            affinity:
              podAffinity:
                requiredDuringSchedulingIgnoredDuringExecution:
                  - labelSelector:
                      matchLabels:
                        emr-containers.amazonaws.com/job.id: >-
                          {{ request.object.metadata.labels."emr-containers.amazonaws.com/job.id" }}
                    # Match pods in any namespace, so system pods follow user pods.
                    namespaceSelector:
                      matchExpressions:
                        - key: kubernetes.io/metadata.name
                          operator: Exists
                    topologyKey: topology.kubernetes.io/zone
```

```bash
kubectl apply -f emr-job-pods-same-az.yaml
kubectl get clusterpolicy emr-job-pods-same-az   # READY should be True
```

The policy applies only to pods created after you install it. It doesn't move pods that are already running.

### Step 2: Spread jobs across AZs from the client, one AZ per job

This step splits AZ placement into two parts:

* **The client spreads jobs across AZs.** Each `StartJobRun` call pins only the user-namespace job submitter, through `jobsubmitter.node.selector.topology.kubernetes.io/zone`. The client rotates that zone round-robin, so successive jobs go to AZ a, b, c, a, b, c, and so on.
* **Kyverno keeps each job in its AZ.** Every other pod of the job, in both the user and system namespaces, is a follower of that submitter. Rule 1 of the policy copies the submitter's zone into each follower's `nodeSelector` at admission time.

The following samples come from the [load-test-for-emr-on-eks](https://github.com/aws-samples/load-test-for-emr-on-eks/blob/1d5f966a9031c390df6bef905b5ddeb22b99483b/locust/locustfiles/emr-job-run.sh#L35-L40) harness, which uses this pattern at scale.

**2a. Pick the next AZ in round-robin order.** Use a shared counter instead of `random.choice()`. Random picks carry no memory of earlier picks, so small batches often come out lopsided: over 2 AZs and 8 jobs, there is about a 29% chance of a 75/25 split or worse. Because each job is pinned to one AZ, an AZ that gets too many jobs also limits Karpenter to that one AZ's Spot pools. A counter splits jobs evenly by construction:

```python
import os
import subprocess
import threading

JOB_AZS = ["us-west-2a", "us-west-2b", "us-west-2c"]
_az_counter = 0
_az_lock = threading.Lock()

def next_az(job_azs=JOB_AZS):
    """Return the next AZ in round-robin order, or None if no AZs were given."""
    global _az_counter
    if not job_azs:
        return None
    with _az_lock:
        az = job_azs[_az_counter % len(job_azs)]
        _az_counter += 1
    return az

# For each job submission:
env = {**os.environ, "SELECTED_AZ": next_az() or ""}
subprocess.run(["sh", "emr-job-run.sh"], env=env, check=True)
```

If you run several submitter processes, each keeps its own counter. Each process still cycles evenly through the AZs, so the jobs stay balanced overall.

**2b. Pin only the job submitter to that AZ.** In the submission script, add the zone selector only when an AZ was chosen. An empty value must not turn into `"...zone": ""`: that is a node selector that matches no node, so the submitter would stay `Pending` forever instead of falling back to any zone. The trailing comma is inside the fragment, so the JSON stays valid when the fragment is empty.

```bash
# emr-job-run.sh
SUBMITTER_AZ_SELECTOR=""
if [ -n "$SELECTED_AZ" ]; then
  SUBMITTER_AZ_SELECTOR='"jobsubmitter.node.selector.topology.kubernetes.io/zone": "'$SELECTED_AZ'",'
fi

aws emr-containers start-job-run \
  --virtual-cluster-id $VIRTUAL_CLUSTER_ID \
  --name fgac-single-az \
  --execution-role-arn $EMR_ROLE_ARN \
  --release-label emr-7.13.0-latest \
  --job-driver '{
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/job.py",
      "sparkSubmitParameters": "--conf spark.executor.cores=4 --conf spark.executor.memory=14g"
    }
  }' \
  --configuration-overrides '{
    "applicationConfiguration": [
      {
        "classification": "emr-job-submitter",
        "properties": {
          '"$SUBMITTER_AZ_SELECTOR"'
          "jobsubmitter.container.image.pullPolicy": "IfNotPresent"
        }
      }
    ]
  }'
```

Don't set a zone on the Spark driver or executors. Leaving them without one makes the Kyverno policy the only thing that places them, so you can attribute the result to the policy. It also covers the system-namespace pods, which you can't configure anyway.

**2c. Kyverno puts the followers in the submitter's AZ.** For each job, the pods are created in this order:

1. The user-namespace job submitter is created with `nodeSelector: topology.kubernetes.io/zone=<SELECTED_AZ>`. Rule 1 skips it, because it already has a zone.
2. Each follower pod (system job submitter, user and system drivers, user and system executors) carries the same `emr-containers.amazonaws.com/job.id` label. When a follower is created, Rule 1 looks up the zone-pinned submitter with that `job.id` and copies its zone into the follower's `nodeSelector`.
3. The scheduler and Karpenter see a fixed zone on every pod, so all pods of the job run in `<SELECTED_AZ>`. Karpenter provisions new nodes in that AZ.

If `SELECTED_AZ` is empty, Rule 1 does nothing and Rule 2's pod affinity still keeps the job in one AZ. Without the client-side rotation, though, nothing spreads jobs across AZs.

### Step 3: Verify the placement

```bash
JOB_ID=<job-run-id>
kubectl get pods -A -l emr-containers.amazonaws.com/job.id=${JOB_ID} \
  -o custom-columns='NS:.metadata.namespace,POD:.metadata.name,ROLE:.metadata.labels.emr-containers\.amazonaws\.com/component,ZONE_SELECTOR:.spec.nodeSelector.topology\.kubernetes\.io/zone,NODE:.spec.nodeName'

# Map each node to its AZ
kubectl get nodes -L topology.kubernetes.io/zone
```

Every pod of the job, in both the user and system namespaces, should show the same zone.

**Observed behavior:** We submitted 24 concurrent FGAC jobs with a round-robin over us-west-2a/b/c. The jobs split 8/8/8 across the three AZs, no job had pods in more than one AZ, and all 24 completed.

## **Considerations**

* **Use the client-side zone in production, not just the fallback.** Rule 2 keeps each job in one AZ, but it doesn't spread jobs across AZs. In our tests, 24 jobs submitted without a zone all landed in the same AZ, because the first pod of each job went to whichever AZ already had free capacity. Rule 1, with a zone chosen by the client, is what spreads the load.
* **Capacity per AZ.** A pinned job can only use nodes in its AZ. If that AZ runs out of capacity or Spot pools, pods stay `Pending` and don't fail over to another AZ. Make sure the node pool allows several instance types in each AZ, and set the client's AZ choice based on available capacity if your AZs aren't equally sized.
* **Fail-open webhooks.** If Kyverno is installed with `failurePolicy: Ignore` (recommended for high-churn Spark clusters, so that a Kyverno outage doesn't block every pod), a pod admitted while Kyverno is unavailable gets no zone constraint. Run the admission controller with 3 replicas, a PodDisruptionBudget, and its own node group. See the [Kyverno high availability guide](https://kyverno.io/docs/installation/methods/#high-availability-installation).
* **Admission latency at scale.** Rule 1 makes one API server call per pod creation. At high pod churn, raise the Kyverno admission controller's client rate limits (`--clientRateLimitQPS`, `--clientRateLimitBurst`), and disable admission reports and background scans, which this policy doesn't use.
* **Kyverno API changes.** Recent Kyverno releases mark `ClusterPolicy` as deprecated in favor of the CEL-based `MutatingPolicy`. The logic above maps directly onto the new API. Check the [migration guide](https://kyverno.io/docs/guides/migration-to-cel/) before you upgrade.
* **Non-FGAC jobs.** The same policy also works for jobs without FGAC: it puts the job submitter, driver, and executors in one AZ from a single `emr-job-submitter` setting, so you don't have to repeat the zone selector in the Spark configuration.

**References**

* Source policy and load-test harness: [aws-samples/load-test-for-emr-on-eks](https://github.com/aws-samples/load-test-for-emr-on-eks/tree/main/resources/kyverno)
* [Kyverno mutate rules](https://kyverno.io/docs/writing-policies/mutate/) and [external data sources (apiCall)](https://kyverno.io/docs/writing-policies/external-data-sources/)
* [Kubernetes inter-pod affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#inter-pod-affinity-and-anti-affinity)
* [Amazon EC2 data transfer pricing](https://aws.amazon.com/ec2/pricing/on-demand/#Data_Transfer_within_the_same_AWS_Region)
