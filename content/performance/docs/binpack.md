# **Custom Scheduler for Binpacking**
Binpacking directly influences the cost performance of your EKS cluster. Both Cluster Autoscaler and Karpenter, as node provisioners, can efficiently scales nodes in and out, but without a binpacking custom scheduler, you might end up with a scenario where nodes are underutilized due to inefficient pod distribution at the pod scheduling time.

-   **Better Binpacking:** When pods are tightly packed onto fewer nodes, node provisioner (Cluster Autoscaler or Karpenter) can more effectively scale down unused nodes, reducing costs.
-   **Poor Binpacking:** If pods are spread out inefficiently across many nodes, node provisioner might struggle to find opportunities to scale down, leading to resource waste.

## Demonstration
**Poor Binpacking with the default kube-scheduler:**
<p align="center">
  <img src="../resources/images/nonbinpack.gif" width="640" height="400"/>
</p>

**Better Binpacking with a Custom Scheduler:**
<p align="center">
  <img src="../resources/images/binpack.gif" width="640" height="400"/>
</p>

Before we tackle the binpacking issue in Amazon EMR on EKS, let’s install a node viewer tool - eks-node-viewer. It 
provides enhanced visibility into the EKS nodes utilization, helping with real-time monitoring, debugging, and optimization efforts. In this case, we use it to visualize dynamic node and pod allocation within an EKS cluster for tracking the binpacking performance.

## Install eks-node-viewer

eks-node-viewer：https://github.com/awslabs/eks-node-viewer

**HomeBrew**
```bash
brew tap aws/tap
brew install eks-node-viewer
```
**Manual**
```bash
go install github.com/awslabs/eks-node-viewer/cmd/eks-node-viewer@latest
```

Quick Start:
```bash
eks-node-viewer --resources cpu,memory
```

## Install Bin-packing custom scheduler

In the [scheduling-plugin](https://kubernetes.io/docs/reference/scheduling/config/#scheduling-plugins) ` NodeResourcesFit` of kube-scheduler, there are two scoring strategies that support the bin packing of resources:       `MostAllocated` and `RequestedToCapacityRatio`. We created a custom scheduler based on the **MostAllocated strategy**. See the K8s’s [Resource Bin Packing](https://kubernetes.io/docs/concepts/scheduling-eviction/resource-bin-packing/) documentation for more details.

The following customer scheduler named “my-scheduler” is created for EKS version v1.28, as the “kube-scheduler” container image version is required to match with EKS version. The KubeSchedulerConfiguration API version is stable(v1) in Kubernetes 1.25, for those cluster prior to 1.25, should use kubescheduler.config.k8s.io/v1beta2. Please adjust them accordingly if your EKS version is different.  

We do not recommend build the kube-scheduler by yourself, you can leverage the eks-distro kube-scheduler image. For example:

- **Amazon EKS 1.28 image:** public.ecr.aws/eks-distro/kubernetes/kube-scheduler:v1.28.11-eks-1-28-latest
- **Amazon EKS 1.29 image:** public.ecr.aws/eks-distro/kubernetes/kube-scheduler:v1.29.6-eks-1-29-18

NOTE: If your binpacking pod throttles for a large scale workload, please increase the QPS and Burst values in the "configmap" section:
```bash
   clientConnection:
      burst: 200
      qps: 100
```
An example of throttle error from the pod logs:
```bash
I1030 23:19:48.258159       1 request.go:697] Waited for 1.93509847s due to client-side throttling, not priority and fairness, request: POST:https://10.100.0.1:443/apis/events.k8s.io/v1/namespa...vents
I1030 23:19:58.258457       1 request.go:697] Waited for 1.905177346s due to client-side throttling, not priority and fairness, request: POST:https://10.100.0.1:443/apis/events.k8s.io/v1/namespa...
```

Run the following command against **EKS v1.28**:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-scheduler
  namespace: kube-system
---
kind: ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: my-scheduler
rules:
- apiGroups:
  - ""
  - events.k8s.io
  resources:
  - events
  verbs:
  - create
  - patch
  - update
- apiGroups:
  - ""
  resources:
  - configmaps
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - coordination.k8s.io
  resources:
  - leases
  verbs:
  - create
  - get
  - list
  - update
- apiGroups:
  - coordination.k8s.io
  resourceNames:
  - kube-scheduler
  resources:
  - leases
  verbs:
  - get
  - update
- apiGroups:
  - ""
  resources:
  - endpoints
  verbs:
  - create
- apiGroups:
  - ""
  resourceNames:
  - kube-scheduler
  resources:
  - endpoints
  verbs:
  - get
  - update
- apiGroups:
  - ""
  resources:
  - nodes
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - ""
  resources:
  - pods
  verbs:
  - delete
  - get
  - list
  - watch
- apiGroups:
  - ""
  resources:
  - bindings
  - pods/binding
  verbs:
  - create
- apiGroups:
  - ""
  resources:
  - pods/status
  verbs:
  - patch
  - update
- apiGroups:
  - ""
  resources:
  - replicationcontrollers
  - services
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - apps
  - extensions
  resources:
  - replicasets
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - apps
  resources:
  - statefulsets
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - policy
  resources:
  - poddisruptionbudgets
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - ""
  resources:
  - persistentvolumeclaims
  - persistentvolumes
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - authentication.k8s.io
  resources:
  - tokenreviews
  verbs:
  - create
- apiGroups:
  - authorization.k8s.io
  resources:
  - subjectaccessreviews
  verbs:
  - create
- apiGroups:
  - storage.k8s.io
  resources:
  - csinodes
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - ""
  resources:
  - namespaces
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - storage.k8s.io
  resources:
  - csidrivers
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - storage.k8s.io
  resources:
  - csistoragecapacities
  verbs:
  - get
  - list
  - watch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: my-scheduler-as-kube-scheduler
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: my-scheduler
subjects:
- kind: ServiceAccount
  name: my-scheduler
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: my-scheduler-as-volume-scheduler
subjects:
- kind: ServiceAccount
  name: my-scheduler
  namespace: kube-system
roleRef:
  kind: ClusterRole
  name: system:volume-scheduler
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-scheduler-config
  namespace: kube-system
data:
  my-scheduler-config.yaml: |
    apiVersion: kubescheduler.config.k8s.io/v1
    kind: KubeSchedulerConfiguration
    profiles:
      - pluginConfig:
          - args:
              apiVersion: kubescheduler.config.k8s.io/v1
              kind: NodeResourcesFitArgs
              scoringStrategy:
                  resources:
                      - name: cpu
                        weight: 1
                      - name: memory
                        weight: 1
                  type: MostAllocated
            name: NodeResourcesFit
        plugins:
          score:
              enabled:
                  - name: NodeResourcesFit
                    weight: 1
              disabled:
                  - name: "*"
          multiPoint:
              enabled:
                  - name: NodeResourcesFit
                    weight: 1
        schedulerName: my-scheduler
    leaderElection:
      leaderElect: true
      resourceNamespace: kube-system
      resourceName: my-scheduler
    clientConnection:
      burst: 200
      qps: 100
---
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    component: scheduler
    tier: control-plane
  name: my-scheduler
  namespace: kube-system
spec:
  selector:
    matchLabels:
      component: scheduler
      tier: control-plane
  replicas: 2
  template:
    metadata:
      labels:
        component: scheduler
        tier: control-plane
        version: second
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: karpenter.sh/nodepool
                operator: DoesNotExist
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                component: scheduler
                tier: control-plane
            topologyKey: kubernetes.io/hostname
      serviceAccountName: my-scheduler
      containers:
      - command:
        - /usr/local/bin/kube-scheduler
        - --bind-address=0.0.0.0
        - --config=/etc/kubernetes/my-scheduler/my-scheduler-config.yaml
        - --v=5
        image: public.ecr.aws/eks-distro/kubernetes/kube-scheduler:v1.28.11-eks-1-28-latest
        livenessProbe:
          httpGet:
            path: /healthz
            port: 10259
            scheme: HTTPS
          initialDelaySeconds: 15
        name: kube-second-scheduler
        readinessProbe:
          httpGet:
            path: /healthz
            port: 10259
            scheme: HTTPS
        resources:
          requests:
            cpu: '1'
        securityContext:
          privileged: false
        volumeMounts:
          - name: config-volume
            mountPath: /etc/kubernetes/my-scheduler
      hostNetwork: false
      hostPID: false
      volumes:
        - name: config-volume
          configMap:
               name: my-scheduler-config
EOF
```


## Validate the Custom Scheduler

- **Step1:** Launch the node viewer in a terminal:
```bash
eks-node-viewer --resources cpu,memory
```

- **Step 2:** Add the custom scheduler to an EMR on EKS job either via a Spark config or via Pod Templates. For exmaple:

sample-job.sh **(last line)**
```bash
aws emr-containers start-job-run \
--virtual-cluster-id $VIRTUAL_CLUSTER_ID \
--name $app_name \
--execution-role-arn $EMR_ROLE_ARN \
--release-label emr-7.2.0-latest \
--job-driver '{
"sparkSubmitJobDriver": {
    "entryPoint": "local:///usr/lib/spark/examples/jars/spark-examples.jar", 
    "entryPointArguments": ["1000000"],
    "sparkSubmitParameters": "--class org.apache.spark.examples.SparkPi --conf spark.executor.instances=10" }}' \
--configuration-overrides '{
"applicationConfiguration": [
    {
    "classification": "spark-defaults", 
    "properties": {
        "spark.kubernetes.node.selector.provisioner": "karpenter-binpack-test",
        "spark.kubernetes.scheduler.name": "my-scheduler" }}]}'
```
OR sample-pod-template.yaml **(line #3)**
```yaml
kind: Pod
spec:
  schedulerName: my-scheduler
  nodeSelector:
    provisioner: karpenter-binpack-test
  volumes:
    # EKS automatically mount EBS or NVMe SSD by
    # https://github.com/awslabs/amazon-eks-ami/blob/main/templates/al2/runtime/bootstrap.sh 
    - name: spark-local-dir-1
      emptyDir: {}
  containers:
  - name: spark-kubernetes-executor
    volumeMounts:
      - name: spark-local-dir-1
        mountPath: /data1
        readOnly: false    
```

Step3: Monitor via eks-node-viewer 

-Before apply the change in pod template:-
![](resources/images/before-binpack.png)

-After the change:-

*  Higher resource usage per node at pod scheduling time
*  Over 50% of cost reduction since Karpenter was terminating idle EC2 nodes at the same time 
![](resources/images/after-binpack.png)

Consideration:

1. At pod launch, the custom scheduler can optimize resource utilization by fitting as many pods as possible onto a single EC2 node. This approach minimizes pod distribution across multiple nodes, leading to higher resource utilization and improved cost efficiency.
2. Dynamic Resource Allocation (DRA) requires shuffle tracking to be enabled because Spark on Kubernetes does not yet support an external shuffle service. Consequently, we have observed that idle EC2 nodes sometimes fail to scale down due to the shuffle data tracking requirement. Using a Binpack scheduler can help reduce the likelihood of long-running idle nodes with leftover shuffle data, resulting a better DRA outcome.
3. Karpenter’s consolidation policy remains essential for reducing underutilized or empty nodes. This is particularly beneficial for long-running jobs where pods are scattered across underutilized EC2 nodes.
4. After implementing a custom scheduler for binpacking, it's recommended to adjust the consolidation frequency to be less aggressive.