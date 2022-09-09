# ** Managing VPC for EMR on EKS**

This section address network security at VPC level. If you want to read more on network security for Spark in EMR on EKS please refer to this [section](https://aws.github.io/aws-emr-containers-best-practices/security/docs/spark/encryption/#amazon-emr-on-eks).

## **Security Group**

The applications running on your EMR on EKS cluster often would need access to services that are running outside the cluster, 
for example, these can Amazon Redshift, Amazon Relational Database Service, a service self hosted on an EC2 instance. To access these resource you need to allow network traffic at the security group level. The default mechanism in EKS is using security groups at the node level, 
this means all the pods running on the node will inherit the rules on the security group. 
For security conscious customers, this is not a desired behavior and you would want to use security groups at the pod level.

This section address how you can use Security Groups with EMR on EKS.

### Configure EKS Cluster to use Security Groups for Pods

In order to use Security Groups at the pod level, you need to configure the VPC CNI for EKS. The following [link](https://docs.aws.amazon.com/eks/latest/userguide/security-groups-for-pods.html) guide through the prerequisites as well as configuring the EKS Cluster.

#### Define SecurityGroupPolicy

Once you have configured the VPC CNI, you need to create a SecurityGroupPolicy object. 
This object define which **security group** (up to 5) to use, **podselector** to define which pod to apply the security group to and 
the **namespace** in which the Security Group should be evaluated. Below you find an example of `SecurityGroupPolicy`.

```
apiVersion: vpcresources.k8s.aws/v1beta1
kind: SecurityGroupPolicy
metadata:
  name: <>
  namespace: <NAMESPACE FOR VC>
spec:
  podSelector: 
    matchLabels:
      role: spark
  securityGroups:
    groupIds:
      - sg-xxxxx
```

### Define pod template to use Security Group for pod

In order for the security group to be applied to the Spark driver and executors, you need to provide a podtemplate which add label(s) to the pods.
The labels should match the one defined above in the `podSelector` in our example it is `role: spark`. 
The snippet below define the pod template that you can upload in S3 and then reference when launching your job.

```
apiVersion: v1
kind: Pod
metadata:
  labels:
    role: spark
```

### Launch a job

The command below can be used to run a job.

```
    aws emr-containers start-job-run --virtual-cluster-id <EMR-VIRTUAL-CLUSTER-ID> --name spark-jdbc --execution-role-arn <EXECUTION-ROLE-ARN> --release-label emr-6.7.0-latest --job-driver '{
    "sparkSubmitJobDriver": {
    "entryPoint": "<S3-URI-FOR-PYSPARK-JOB-DEFINED-ABOVE>",
    "sparkSubmitParameters": "--conf spark.executor.instances=2 --conf spark.executor.memory=2G --conf spark.executor.cores=2 --conf spark.driver.cores=1"
    }
    }' --configuration-overrides '{
    "applicationConfiguration": [
    {
    "classification": "spark-defaults", 
    "properties": {
    "spark.hadoop.hive.metastore.client.factory.class": "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
    "spark.sql.catalogImplementation": "hive",
    "spark.dynamicAllocation.enabled":"true",
    "spark.dynamicAllocation.minExecutors": "8",
    "spark.dynamicAllocation.maxExecutors": "40",
    "spark.kubernetes.allocation.batch.size": "8",
    "spark.dynamicAllocation.executorAllocationRatio": "1",
    "spark.dynamicAllocation.shuffleTracking.enabled": "true",
    "spark.dynamicAllocation.shuffleTracking.timeout": "300s",
    "spark.kubernetes.driver.podTemplateFile":<S3-URI-TO-DRIVER-POD-TEMPLATE>,
    "spark.kubernetes.executor.podTemplateFile":<S3-URI-TO-EXECUTOR-POD-TEMPLATE>
    }
    }
    ],
    "monitoringConfiguration": {
        "persistentAppUI": "ENABLED",
        "cloudWatchMonitoringConfiguration": {
            "logGroupName": "/aws/emr-containers/",
            "logStreamNamePrefix": "default"
        }
    }
    }'
```

#### Verify a security group attached to the Pod ENI

To verify that spark driver and executor driver have the security group attached to, apply the first command to get the podname then the second one to see the annotation in pod with the ENI associated to the pod which has the secuity group defined in the **SecurityGroupPolicy**.

```
export POD_NAME=$(kubectl -n <NAMESPACE> get pods -l role=spark -o jsonpath='{.items[].metadata.name}')

kubectl -n <NAMESPACE>  describe pod $POD_NAME | head -11
```

```
Annotations:  kubernetes.io/psp: eks.privileged
              vpc.amazonaws.com/pod-eni:
                [{"eniId":"eni-xxxxxxx","ifAddress":"xx:xx:xx:xx:xx:xx","privateIp":"x.x.x.x","vlanId":1,"subnetCidr":"x.x.x.x/x"}]
```