# **EKS Node Placement**
## **Single AZ placement**

EKS cluster can span across multiple AZ in a VPC. Spark application whose driver and executor pods are distributed across multiple AZ incur data transfer cost. 

**Request:**

```
cat >spark-python-in-s3-nodeselector.json << EOF
{
  "name": "spark-python-in-s3-nodeselector", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count.py", 
       "sparkSubmitParameters": "--conf spark.kubernetes.node.selector.topology.kubernetes.io/zone='<availability zone>' --conf spark.driver.cores=5  --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.dynamicAllocation.enabled":"false"
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
When the job gets started the driver pod and executor pods are scheduled only on those EKS worker nodes with the label `topology.kubernetes.io/zone: <availability zone>`.
This ensures the spark job is run within a single AZ. If there are not enough resource within the specified AZ, the pods will be in pending state until the Autoscaler(if configured) to kick in or more resources to be available.
 
[Spark on kubernetes Node selector configuration](https://spark.apache.org/docs/latest/running-on-kubernetes.html#pod-spec)  
[Kubernetes Node selector reference](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)

**Configuration of interest -**  


```
--conf spark.kubernetes.node.selector.zone='<availability zone>'
```

`zone` is a built in label that EKS assigns to every EKS worker Node. The above config will make sure to schedule the driver and executor pod on those EKS worker nodes with label - `topology.kubernetes.io/zone: <availability zone>`.  
However [user defined labels](https://eksctl.io/usage/eks-managed-nodes/#managing-labels) can also be assigned to EKS worker nodes and used as node selector.

Other common use cases are using node labels to force the job to run on on demand/spot, machine type, etc.  


## **Single AZ and ec2 instance type placement**  

Multiple key value pairs for spark.kubernetes.node.selector.[labelKey] can be passed to add filter conditions for selecting the EKS worker node. If you want to schedule on EKS worker nodes in `<availability zone>` and instance-type as m5.4xlarge - it is done as below  
 
 **Request:**

```
{
  "name": "spark-python-in-s3-nodeselector", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5  --conf spark.kubernetes.pyspark.pythonVersion=3 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6 --conf spark.sql.shuffle.partitions=1000"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.dynamicAllocation.enabled":"false",
          "spark.kubernetes.node.selector.topology.kubernetes.io/zone":"<availability zone>",
          "spark.kubernetes.node.selector.node.kubernetes.io/instance-type":"m5.4xlarge"
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
  }
}
```


**[Configuration of interest](http://spark.apache.org/docs/latest/running-on-kubernetes.html)**  

`spark.kubernetes.node.selector.[labelKey] - Adds to the node selector of the driver pod and executor pods, with key labelKey and the value as the configuration's value. For example, setting spark.kubernetes.node.selector.identifier to myIdentifier will result in the driver pod and executors having a node selector with key identifier and value myIdentifier. Multiple node selector keys can be added by setting multiple configurations with this prefix.`


