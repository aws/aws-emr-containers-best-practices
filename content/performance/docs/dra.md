# **Dynamic Resource Allocation**

DRA is available in Spark 3 (EMR 6.x) without the need for an external shuffle service. Spark on Kubernetes doesn't support external shuffle service as of spark 3.1, but DRA can be achieved by enabling [shuffle tracking](https://spark.apache.org/docs/latest/configuration.html#dynamic-allocation).

**Spark DRA with storage configuration:**  

When using [dynamic provisioning PVC/Volumes](../../storage/docs/spark/ebs.md#dynamic-provisioning) with Spark, you must disable PVC reuse to prevent multi-attach errors. The default configuration attempts to reuse PVCs, which causes EBS volumes to attach to multiple pods and leads to application failure. Set the following configurations:
```
"spark.kubernetes.driver.ownPersistentVolumeClaim": "false"
"spark.kubernetes.driver.reusePersistentVolumeClaim": "false"
"spark.kubernetes.driver.waitToReusePersistentVolumeClaim": "false"
```
For workloads requiring PVC reuse with DRA, use storage solutions supporting multi-attach like EFS / FSx for Lustre instead of EBS.

**Spark DRA without external shuffle service:**  
With DRA, the spark driver spawns the initial number of executors and then scales up the number until the specified maximum number of executors is met to process the pending tasks. Idle executors are terminated when there are no pending tasks, the executor idle time exceeds the idle timeout(`spark.dynamicAllocation.executorIdleTimeout)`and it doesn't have any cached or shuffle data.

If the executor idle threshold is reached and it has cached data, then it has to exceed the cache data idle timeout(`spark.dynamicAllocation.cachedExecutorIdleTimeout) ` and if the executor doesn't have shuffle data, then the idle executor is terminated.

If the executor idle threshold is reached and it has shuffle data, then without external shuffle service the executor will never be terminated. These executors will be terminated when the job is completed. This behavior is enforced by `"spark.dynamicAllocation.shuffleTracking.enabled":"true" and "spark.dynamicAllocation.enabled":"true"`

If `"spark.dynamicAllocation.shuffleTracking.enabled":"false"and "spark.dynamicAllocation.enabled":"true"` then the spark application will error out since external shuffle service is not available.

**Request:**

```
cat >spark-python-in-s3-dra.json << EOF
{
  "name": "spark-python-in-s3-dra", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
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
          "spark.dynamicAllocation.enabled":"true",
          "spark.dynamicAllocation.shuffleTracking.enabled":"true",
          "spark.dynamicAllocation.minExecutors":"5",
          "spark.dynamicAllocation.maxExecutors":"100",
          "spark.dynamicAllocation.initialExecutors":"10"
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
```

```
aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-dra.json
```

**Observed Behavior:**
When the job gets started, the driver pod gets created and 10 executors are initially created. (`"spark.dynamicAllocation.initialExecutors":"10"`) Then the number of executors can scale up to a maximum of 100 (`"spark.dynamicAllocation.maxExecutors":"100"`).   
**Configurations to note:**   

`spark.dynamicAllocation.shuffleTracking.enabled` - `**`Experimental`**`. Enables shuffle file tracking for executors, which allows dynamic allocation without the need for an external shuffle service. This option will try to keep alive executors that are storing shuffle data for active jobs.

`spark.dynamicAllocation.shuffleTracking.timeout` - When shuffle tracking is enabled, controls the timeout for executors that are holding shuffle data. The default value means that Spark will rely on the shuffles being garbage collected to be able to release executors. If for some reason garbage collection is not cleaning up shuffles quickly enough, this option can be used to control when to time out executors even when they are storing shuffle data.

