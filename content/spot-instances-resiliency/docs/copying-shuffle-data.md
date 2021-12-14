# **Spot instances interruption resiliency by copying shuffle data**

[Amazon EC2 Spot Instances](https://aws.amazon.com/ec2/spot/) allow AWS customers to run EC2 instances at steep discounts by tapping into EC2 spare capacity pools. Using Amazon EKS’s managed node groups, EKS can provision and manage the underlying Spot Instances (worker nodes) that provide compute capacity to EKS clusters. Using an EKS cluster with Spot instances to run EMR on EKS jobs allows customers to provision and maintain the desired capacity while benefiting from steep cost savings. 

However, Spot Instances can be interrupted with a two-minute notification when EC2 needs the capacity back. Termination of the Spot instance will result in termination of the executors on the node. The shuffle data and cached RDD data on these nodes will be lost and may need to be recalculated. This operation is very costly and will result in a high increase in the execution time of EMR on EKS jobs.

This section shows how to use a new [Apache Spark feature](https://issues.apache.org/jira/browse/SPARK-20629) that allows you to store the shuffle data and cached RDD blocks present on the terminating executors to peer executors before a Spot node gets decommissioned. Consequently, your job does not need to recalculate the shuffle and RDD blocks of the terminating executor that would otherwise be lost, thus allowing the job to have minimal delay in completion. 

This feature is supported for releases EMR 6.3.0+.

### How does it work?

When <code>spark.decommission.enabled</code> is true, Spark will try its best to shutdown the executor gracefully. <code>spark.storage.decommission.enabled</code> will enable migrating data stored on the executor. Spark will try to migrate all the cached RDD blocks (controlled by <code>spark.storage.decommission.rddBlocks.enabled</code>) and shuffle blocks (<code>controlled by spark.storage.decommission.shuffleBlocks.enabled</code>) from the decommissioning executor to all remote executors when spark decommission is enabled. Relevant Spark configurations for using node decommissioning in the jobs are

|Configuration|Description|Default Value|
|-----|-----|-----|
|spark.decommission.enabled|Whether to enable decommissioning|false|
|spark.storage.decommission.enabled|Whether to decommission the block manager when decommissioning executor|false|
|spark.storage.decommission.rddBlocks.enabled|Whether to transfer RDD blocks during block manager decommissioning.|false|
|spark.storage.decommission.shuffleBlocks.enabled|Whether to transfer shuffle blocks during block manager decommissioning. Requires a migratable shuffle resolver (like sort based shuffle)|false|
|spark.storage.decommission.maxReplicationFailuresPerBlock|Maximum number of failures which can be handled for migrating shuffle blocks when block manager is decommissioning and trying to move its existing blocks.|3|
|spark.storage.decommission.shuffleBlocks.maxThreads|Maximum number of threads to use in migrating shuffle files.|8|

This feature can currently be enabled through a temporary workaround on EMR 6.3.0+ releases. To enable it, Spark’s decom.sh file permission must be modified using a [custom image](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/docker-custom-images.html). Once the code is fixed, the page will be updated.

**Dockerfile for custom image:**

```
FROM <release account id>.dkr.ecr.<aws region>.amazonaws.com/spark/<release>
USER root
WORKDIR /home/hadoop
RUN chown hadoop:hadoop /usr/bin/decom.sh
```

**Setting decommission timeout:**

Each executor has to be decommissioned within a certain time limit controlled by the pod’s terminationGracePeriodSeconds configuration.  The default value is 30 secs but can be modified using a [custom pod template](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/pod-templates.html). The pod template for this modification would look like 
```
apiVersion: v1
kind: Pod
spec:
  terminationGracePeriodSeconds: <seconds>
```
  
**Note: terminationGracePeriodSeconds timeout should be lesser than spot instance timeout with around 5 seconds buffer kept aside for triggering the node termination**

  
**Request:**
  
```
cat >spark-python-with-node-decommissioning.json << EOF
{
   "name": "my-job-run-with-node-decommissioning",
   "virtualClusterId": "<virtual-cluster-id>",
   "executionRoleArn": "<execution-role-arn>",
   "releaseLabel": "emr-6.3.0-latest", 
   "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6"
    }
   }, 
   "configurationOverrides": {
    "applicationConfiguration": [
      {
       "classification": "spark-defaults",
       "properties": {
       "spark.kubernetes.container.image": "<account_id>.dkr.ecr.<region>.amazonaws.com/<custom_image_repo>",
       "spark.executor.instances": "5",
        "spark.decommission.enabled": "true",
        "spark.storage.decommission.rddBlocks.enabled": "true",
        "spark.storage.decommission.shuffleBlocks.enabled" : "true",
        "spark.storage.decommission.enabled": "true"
       }
      }
    ], 
    "monitoringConfiguration": {
      "cloudWatchMonitoringConfiguration": {
        "logGroupName": "<log group>", 
        "logStreamNamePrefix": "<log-group-prefix>"
      }, 
      "s3MonitoringConfiguration": {
        "logUri": "<S3 URI>"
      }
    }
   } 
}
EOF
```
  
**Observed Behavior:**
  
When executors begin decommissioning, its shuffle data gets migrated to peer executors instead of recalculating the shuffle blocks again. If sending shuffle blocks to an executor fails, <code>spark.storage.decommission.maxReplicationFailuresPerBlock</code> will give the number of retries for migration. The driver log’s stderr will see log lines `Updating map output for <shuffle_id> to BlockManagerId(<executor_id>, <ip_address>, <port>, <topology_info>)` denoting details about shuffle block <shuffle_id>‘s migration. This feature does not emit any other metrics for validation as of yet.
  
**Node decommissioning with fallback storage**

Spark supports a fallback storage configuration (spark.storage.decommission.fallbackStorage.path) and it can be used if migrating shuffle blocks to peer executors fails. However, there is an [existing issue](https://issues.apache.org/jira/browse/SPARK-18105) in Spark where these blocks cannot be read from the fallback path properly and a job fails with exception `java.io.IOException: Stream is corrupted, net.jpountz.lz4.LZ4Exception: Error decoding offset <offset_id> of input buffer`.