# **EKS Fargate Node Placement**
## **Fargate Node Placement**

AWS Fargate is a technology that provides on-demand, right-sized compute capacity for containers. With AWS Fargate, you don't have to provision, configure, or scale groups of EC2 instances on your own to run containers. You also don't need to choose server types, decide when to scale your node groups, or optimize cluster packing. Instead you can control which pods start on Fargate and how they run with Fargate profiles.

## AWS Fargate profile 
Before you can schedule pods on Fargate in your cluster, you must define at least one Fargate profile that specifies which pods use Fargate when launched.  You must define a namespace for every selector. The Fargate profile allows an administrator to declare which pods run on Fargate. This declaration is done through the profile’s selectors. If a namespace selector is defined without any labels, Amazon EKS attempts to schedule all pods that run in that namespace onto Fargate using the profile.

A Spark application whose driver and executor pods are distributed across multiple AZs can incur inter-AZ data transfer costs. To minimize or eliminate inter-AZ data transfer costs, you can configure the application to only run on the nodes within a single AZ.  In this example, we use the kubernetes [node selector](https://spark.apache.org/docs/latest/running-on-kubernetes.html#pod-spec) to specify which AZ should the job run on.


**Create Fargate Profile**
Create your Fargate profile with the following eksctl command, replacing the `<variable text>` (including <>) with your own values. You're required to specify a namespace. However, the `--labels` option is not required.

```
eksctl create fargateprofile \
    --cluster <cluster_name> \
    --name <fargate_profile_name> \
    --namespace <virtual_cluster's_mapped_namespace> \
    --labels spark-node-placement=fargate
```

### 1- Place entire job including driver pod on Fargate 

When both Driver and Executor are labled that matches the Fargate Selector, the entire job including the driver pod could run on Fargate. 
**Request:**
```
cat >spark-python-in-s3-nodeselector.json << EOF
{
  "name": "spark-python-in-s3-fargate-nodeselector", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.3.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=4  --conf spark.executor.memory=20G --conf spark.driver.memory=20G --conf spark.executor.cores=4"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
            "spark.kubernetes.driver.label.spark-node-placement": "fargate",
            "spark.kubernetes.executor.label.spark-node-placement": "fargate"
         }
      }
    ], 
    "monitoringConfiguration": {
      "cloudWatchMonitoringConfiguration": {
        "logGroupName": "/emr-containers/jobs", 
        "logStreamNamePrefix": "demo"
      }, 
      "s3MonitoringConfiguration": {
        "logUri": "s3://joblogs"
      }
    }
  }
}
EOF
aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-nodeselector.json
```

**Observed Behavior:**  
When the job starts the driver pod and executor pods are scheduled only on fargate since both are labeled with the `spark-node-placement: fargate`. This is useful when we want to run the entire job on Fargate nodes. The maximum vCPU available for the driver pod is 4vCPU. 

### 2- Place driver pod on EC2 and executor pod on Fargate 
When the driver pod needs more resources(> 4 vCPU), Removing the driver's pod label configuration, will have driver pod not scheduled by the Fargate selector.

**Request:**
```
cat >spark-python-in-s3-nodeselector.json << EOF
{
  "name": "spark-python-in-s3-fargate-nodeselector", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.3.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5  --conf spark.executor.memory=20G --conf spark.driver.memory=30G --conf spark.executor.cores=4"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
            "spark.kubernetes.executor.label.spark-node-placement": "fargate"
         }
      }
    ], 
    "monitoringConfiguration": {
      "cloudWatchMonitoringConfiguration": {
        "logGroupName": "/emr-containers/jobs", 
        "logStreamNamePrefix": "demo"
      }, 
      "s3MonitoringConfiguration": {
        "logUri": "s3://joblogs"
      }
    }
  }
}
EOF
aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-nodeselector.json
```

**Observed Behavior:**  
When the job starts, the driver pod is scheduled on an EC2 instance. EKS picks an instance from the first Node Group that has matching resources available to the driver pod.


### 3- Define a NodeSelector in Pod Templates 
Beginning with Amazon EMR versions 5.33.0 or 6.3.0, Amazon EMR on EKS supports Spark’s pod template feature. Pod templates are specifications that determine how to run each pod. You can use pod template files to define the driver or executor pod’s configurations that Spark configurations do not support. For example spark configurations do not support defining indivisual node selectors for the driver pod and the executor pods. Since we desire to have the driver pod  schedule on specific node group, we would need to define a node selector **only** for the driver pod and let the Fargate Profile schedule the executor pods.

**Driver Pod Template**

```apiVersion: v1
kind: Pod
spec:
  volumes:
    - name: source-data-volume
      emptyDir: {}
    - name: metrics-files-volume
      emptyDir: {}
  nodeSelector:
    <ec2-instance-node-label-key>: <ec2-instance-node-label-value>
  containers:
  - name: spark-kubernetes-driver # This will be interpreted as Spark driver container
  ```

  The pod template need to be stored onto a S3 location:

  ``` aws s3 cp /driver-pod-template.yaml s3://<your-bucket-name>/driver-pod-template.yaml```


**Request**

```
cat >spark-python-in-s3-nodeselector.json << EOF
{
  "name": "spark-python-in-s3-fargate-nodeselector", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.3.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5  --conf spark.executor.memory=20G --conf spark.driver.memory=30G --conf spark.executor.cores=4"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
            "spark.kubernetes.executor.label.spark-node-placement": "fargate",
            "spark.kubernetes.driver.podTemplateFile": "s3://<your-bucket-name>/driver-pod-template.yaml"
         }
      }
    ], 
    "monitoringConfiguration": {
      "cloudWatchMonitoringConfiguration": {
        "logGroupName": "/emr-containers/jobs", 
        "logStreamNamePrefix": "demo"
      }, 
      "s3MonitoringConfiguration": {
        "logUri": "s3://joblogs"
      }
    }
  }
}
EOF
aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-nodeselector.json
```