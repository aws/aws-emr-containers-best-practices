# **Dynamic Resource Allocation**

DRA is available in Spark 3 (EMR 6.x) without the need for an external shuffle service. Spark on Kubernetes doesn't support external shuffle service as of spark 3.1, but DRA can be achieved by enabling [shuffle tracking](https://spark.apache.org/docs/latest/configuration.html#dynamic-allocation).

**Spark DRA with storage configuration:**  

When using [dynamic provisioning PVC/Volumes](../../storage/docs/spark/ebs.md#dynamic-provisioning) with Spark's DRA, to avoid multi-attach errors from the PVC, ensure your storage class is configured with the `WaitForFirstConsumer` mode and reclaim policy is `Retain`. See the exmaple below:
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
parameters:
  fsType: ext4
  type: gp3
provisioner: kubernetes.io/aws-ebs
reclaimPolicy: Retain # for pvc reuse
volumeBindingMode: WaitForFirstConsumer
```

Then enable PVC reuse by setting the following configurations in Spark. If your Spark version is lower than 3.4, don't enable the PVC reuse:
```yaml
"spark.kubernetes.driver.ownPersistentVolumeClaim": "true"
"spark.kubernetes.driver.reusePersistentVolumeClaim": "true"
"spark.kubernetes.driver.waitToReusePersistentVolumeClaim": "true"
```
Importantly,to enable shuffle data recovery feature and avoid the "Shuffle Fetch Failures", leverage Spark's built-in plugin:
```yaml
"spark.shuffle.sort.io.plugin.class": "org.apache.spark.shuffle.KubernetesLocalDiskShuffleDataIO"
```

**Spark DRA without External Shuffle Service:**  
With DRA enabled (`spark.dynamicAllocation.enabled`), Spark driver spawns the initial number of executors and gradually scales them up to meet processing demands. This scaling continues until reaching the maximum number of executors specified by `spark.dynamicAllocation.maxExecutors`. Spark intelligently manages compute resources by terminating idle executors, but only under the following specific conditions:

1. An executor becomes eligible for termination when it has no pending tasks and exceeds the configured idle timeout (`spark.dynamicAllocation.executorIdleTimeout`) without any cached or shuffle data. 
2. For executors holding cached data, termination occurs only after exceeding both the executor idle timeout and an additional cached data idle timeout (`spark.dynamicAllocation.cachedExecutorIdleTimeout`). 
3. A crucial consideration is the shuffle data handling by Spark. Without relying on an External Shuffle Service (ESS), Spark tracks shuffle data via the setting `spark.dynamicAllocation.shuffleTracking.enabled` to achieve the DRA. To avoid losing shuffle files, executors cannot be scale down during the job's execution, even if they remain idle. They will only be removed once the shuffle data tracking exeeds configured timeout (`spark.dynamicAllocation.shuffleTracking.timeout`) or until job completion. 

If shuffleTracking is disabeld but DRA is enabled, Spark applications will error out since External Shuffle Service is not available.

**DRA Example:**

```batch
cat >spark-python-in-s3-dra.json << EOF
{
  "name": "spark-python-in-s3-dra", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.15.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=2 --conf spark.executor.memory=10G --conf spark.driver.memory=5G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.dynamicAllocation.enabled":"true",
          "spark.dynamicAllocation.shuffleTracking.enabled":"true",
          "spark.dynamicAllocation.minExecutors":"0",
          "spark.dynamicAllocation.maxExecutors":"50",
          "spark.dynamicAllocation.executorIdleTimeout":"30s"
         }
      }
    ]
  }
}
EOF

aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-dra.json
```

**DRA + PVC reuse Example:**

```bash
cat >spark-dra-pvc-demo.json << EOF
{
  "name": "spark-dra-pvc-demo", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.15.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=2 --conf spark.executor.memory=10G --conf spark.driver.memory=5G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.dynamicAllocation.enabled":"true",
          "spark.dynamicAllocation.shuffleTracking.enabled":"true",
          "spark.dynamicAllocation.minExecutors":"0",
          "spark.dynamicAllocation.maxExecutors":"50",
          "spark.dynamicAllocation.executorIdleTimeout":"30s"

          "spark.kubernetes.driver.ownPersistentVolumeClaim":"true",
          "spark.kubernetes.driver.reusePersistentVolumeClaim":"true",
          "spark.kubernetes.driver.waitToReusePersistentVolumeClaim":"true",

          "spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.options.claimName":"OnDemand",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.options.sizeLimit": "5Gi",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.options.storageClass":"gp3",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.mount.path":"/data1",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-1.mount.readOnly":"false",
          
          "spark.shuffle.sort.io.plugin.class":"org.apache.spark.shuffle.KubernetesLocalDiskShuffleDataIO"
         }
      }
    ]
  }
}
EOF

aws emr-containers start-job-run --cli-input-json file:///spark-dra-pvc-demo.json
```


**Observed Behavior:**
When the job gets started, the driver pod gets created and 10 executors are initially created due to the default batch size by `spark.kubernetes.allocation.batch.size`. The maximun number of executors will reach to 50 (`"spark.dynamicAllocation.maxExecutors":"50"`).

When using `OnDemand` claimName to create dynamic PVCs, each executor mounts a dedicated Persistent Volume Claim (PVC) with a size of 5GB. In total, 50 PVCs should be created. Due to the `Retain` claim policy in the storage class gp3, these PVCs persist and cannot be dynamically reduced, even if some executors were removed. The PVCs will only be eligible for cleanup after the entire Spark job completes. This behavior needs to be carefully considered when planning storage resources and costs.

**Configurations to note:**   

`spark.dynamicAllocation.shuffleTracking.enabled` - `**`Experimental`**`. Enables shuffle file tracking for executors, which allows dynamic allocation without the need for an external shuffle service. This option will try to keep alive executors that are storing shuffle data for active jobs.

`spark.dynamicAllocation.shuffleTracking.timeout` - When shuffle tracking is enabled, controls the timeout for executors that are holding shuffle data. The default value means that Spark will rely on the shuffles being garbage collected to be able to release executors. If for some reason garbage collection is not cleaning up shuffles quickly enough, this option can be used to control when to time out executors even when they are storing shuffle data.

`spark.dynamicAllocation.executorIdleTimeout` - If dynamic allocation is enabled and an executor has been idle for more than this duration, the executor will be removed.