# **Karpenter**

Karpenter is an open-source cluster autoscaler for kubernetes (EKS) that automatically provisions new nodes in response to unschedulable pods. Until Karpenter was introduced, EKS would use its implementation of "CAS" Cluster Autoscaler, which creates Managed-NodeGroups to provision nodes.

The challenge with Managed-NodeGroups is that, it can only create nodes with a single instance-type. In-order to provision nodes with different instance-types for different workloads, multiple nodegroups have to be created. Karpenter on the other hand can provision nodes of different types by working with EC2-Fleet-API. 
The best practices to configure the Provisioners are documented at https://aws.github.io/aws-eks-best-practices/karpenter/

This guide helps the user troubleshoot common problems with Karpenter.

### Logs of Karpenter Controller

Karpenter is a Custom Kubernetes Controller, and the following steps would help find Karpenter Logs.

Step 1: Identify the namespace where Karpenter is running. In most cases, `helm` would be used to deploy Karpenter packages. The `helm ls` command would list the namespace where karpenter would be installed.
```
# Example

% helm ls --all-namespaces
NAME     	NAMESPACE	REVISION	UPDATED                             	STATUS  	CHART            	APP VERSION
karpenter	karpenter	1       	2023-05-15 14:16:03.726908 -0500 CDT	deployed	karpenter-v0.27.3	0.27.3
```

Step 2: Setup kubectl
```
brew install kubectl

aws --region <region> eks update-kubeconfig --name <eks-cluster-name>
```

Step 3: Check the status of the pods of Karpenter
```
# kubectl get pods -n <namespace>

% kubectl get pods -n karpenter
NAME                         READY   STATUS    RESTARTS   AGE
karpenter-7b455dccb8-prrzx   1/1     Running   0          7m18s
karpenter-7b455dccb8-x8zv8   1/1     Running   0          7m18s
```

Step 4: The `kubectl logs` command would help read the Karpenter logs. The below example, karpenter pod logs depict that an `t3a.large` instance was launched.
```
# kubectl logs <karpenter pod name> -n <namespace>

% kubectl logs karpenter-7b455dccb8-prrzx -n karpenter
..
..

2023-05-15T19:16:20.546Z	DEBUG	controller	discovered region	{"commit": "***-dirty", "region": "us-west-2"}
2023-05-15T19:16:20.666Z	DEBUG	controller	discovered cluster endpoint	{"commit": "**-dirty", "cluster-endpoint": "https://******.**.us-west-2.eks.amazonaws.com"}
..
..
2023-05-15T19:16:20.786Z	INFO	controller.provisioner	starting controller	{"commit": "**-dirty"}
2023-05-15T19:16:20.787Z	INFO	controller.deprovisioning	starting controller	{"commit": "**-dirty"}
..
2023-05-15T19:16:20.788Z	INFO	controller	Starting EventSource	{"commit": "**-dirty", "controller": "node", "controllerGroup": "", "controllerKind": "Node", "source": "kind source: *v1.Pod"}
..
2023-05-15T20:34:56.718Z	INFO	controller.provisioner.cloudprovider	launched instance	{"commit": "d7e22b1-dirty", "provisioner": "default", "id": "i-03146cd4d4152a935", "hostname": "ip-*-*-*-*.us-west-2.compute.internal", "instance-type": "t3a.large", "zone": "us-west-2d", "capacity-type": "on-demand", "capacity": {"cpu":"2","ephemeral-storage":"20Gi","memory":"7577Mi","pods":"35"}}
```

### Error while decoding JSON: json: unknown field "iamIdentityMappings"

**Problem**
The Create-Cluster command https://karpenter.sh/v0.27.3/getting-started/getting-started-with-karpenter/#3-create-a-cluster throws an error
```
Error: loading config file "karpenter.yaml": error unmarshaling JSON: while decoding JSON: json: unknown field "iamIdentityMappings"
```

**Solution**
The `eksctl` cli was not able to understand the kind `iamIdentityMappings`. This is because, the `eksctl` version is old, and its schema doesn't support this kind. 

The solution is to upgrade the `eksctl` cli, and re-run the cluster creation commands
```bash
brew upgrade eksctl
```