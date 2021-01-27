# EMR Containers integration with FSx for Lustre

EMR Containers is a deployment option within EMR to run spark workloads on customer EKS clusters. EKS cluster provides the compute and ephemeral storage for the spark workloads. Ephemeral storage provided by EKS is carved from the EKS worker node disk storage and the lifecycle of the storage is bound by the lifecycle of the driver and executor pod.

**Need for durable storage:**
In cases where multiple spark applications are executed as part of a data pipeline, there are scenarios where data from one spark application is passed to subsequent spark applications - in this case data can be persisted in S3. Alternatively this data can also be persisted in [FSx for Lustre](https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html) - Lustre provides a fully managed, POSIX- compliant native filesystem interface for the data in s3, that can scale with compute provided by EKS. Storage is decoupled from compute and has its own lifecycle. 

**Difference between static and dynamic provisioning of Persistent Volumes:**
(Refer - https://kubernetes.io/docs/concepts/storage/persistent-volumes/#provisioning)

Data used in the below example is from https://registry.opendata.aws/nyc-tlc-trip-records-pds/

## **Static Provisioning** - 

### Provision a FSx for Lustre cluster:

FSx for Lustre cluster can be provisioned through the AWS console at https://us-west-2.console.aws.amazon.com/fsx/home?region=us-west-2#file-systems

FSx for Luster can also be provisioned through aws cli as below -
https://docs.aws.amazon.com/cli/latest/reference/fsx/create-file-system.html

How to decide what type of FSx for Lustre file system you need ? - https://docs.aws.amazon.com/fsx/latest/LustreGuide/LustreGuide.pdf

**Create a Security Group to attach to FSx for Lustre file system as below**
![](../../resources/FSx_Lustre_SG.png)**Points to Note:**
Security group attached to the EKS worker nodes is given access on port number 988, 1021-1023 in inbound rules.
Security group specified when creating the FSx for Lustre filesystem is given access on port number 988, 1021-1023 in inbound rules.

Fsx for Lustre Provisioning through aws cli 

```
cat fsxLustreConfig.json << EOF 
{
    "ClientRequestToken": "EMRContainers-fsxLustre-demo", 
    "FileSystemType": "LUSTRE",
    "StorageCapacity": 1200, 
    "StorageType": "SSD", 
    "SubnetIds": [
        "<subnet-id>"
    ], 
    "SecurityGroupIds": [
        "<securitygroup-id>"
    ], 
    "LustreConfiguration": {
        "ImportPath": "s3://<s3 prefix>/", 
        "ExportPath": "s3://<s3 prefix>/", 
        "DeploymentType": "PERSISTENT_1", 
        "AutoImportPolicy": "NEW_CHANGED",
        "PerUnitStorageThroughput": 200
    }
}
EOF
```

Run the aws-cli to create the FSx for Lustre filesystem as below

```
aws fsx create-file-system --cli-input-json file:///fsxLustreConfig.json
```

Response is as below

```
{
    "FileSystem": {
        "VpcId": "<vpc id>", 
        "Tags": [], 
        "StorageType": "SSD", 
        "SubnetIds": [
            "<subnet-id>"
        ], 
        "FileSystemType": "LUSTRE", 
        "CreationTime": 1603752401.183, 
        "ResourceARN": "<fsx resource arn>", 
        "StorageCapacity": 1200, 
        "LustreConfiguration": {
            "CopyTagsToBackups": false, 
            "WeeklyMaintenanceStartTime": "7:11:30", 
            "DataRepositoryConfiguration": {
                "ImportPath": "s3://<s3 prefix>", 
                "AutoImportPolicy": "NEW_CHANGED", 
                "ImportedFileChunkSize": 1024, 
                "Lifecycle": "CREATING", 
                "ExportPath": "s3://<s3 prefix>/"
            }, 
            "DeploymentType": "PERSISTENT_1", 
            "PerUnitStorageThroughput": 200, 
            "MountName": "mvmxtbmv"
        }, 
        "FileSystemId": "<filesystem id>", 
        "DNSName": "<filesystem id>.fsx.<region>.amazonaws.com", 
        "KmsKeyId": "arn:aws:kms:<region>:<account>:key/<key id>", 
        "OwnerId": "<account>", 
        "Lifecycle": "CREATING"
    }
}











```

### EKS admin tasks:

(Refer - https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/)

1. Attach IAM policy to EKS worker node IAM role to enable access to FSx for Lustre - [ReferDoc](https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/) and [Create a Security Group to…](https://quip-amazon.com/jxgRAKqNXPMi#CQe9CA6vghM)
2. Install the FSx CSI Driver in EKS - [Refer Doc](https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/)
3. Configure Storage Class for FSx for Lustre - [Refer Doc](https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/)
4. Configure Persistent Volume and Persistent Volume Claim for FSx for Lustre


FSx for Lustre file system is created as described above -[Provision a FSx for Lustre cluster:](https://quip-amazon.com/jxgRAKqNXPMi#CQe9CAPBB9A)
Once provisioned, a persistent volume - as specified below is created with direct ( hard-coded) reference to the created lustre file system. Persistent Volume claim for this persistent volume will always use the same file system.

```
cat >fsxLustre-static-pv.yaml <<EOF
apiVersion: v1
kind: PersistentVolume
metadata:
  name: fsx-pv
spec:
  capacity:
    storage: 1200Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteMany
  mountOptions:
    - flock
  persistentVolumeReclaimPolicy: Recycle
  csi:
    driver: fsx.csi.aws.com
    volumeHandle: <filesystem id>
    volumeAttributes:
      dnsname: <filesystem id>.fsx.<region>.amazonaws.com
      mountname: mvmxtbmv
EOF
```

```
kubectl apply -f fsxLustre-static-pv.yaml
```

Now, a Persistent Volume Claim ( PVC) needs to be created that references PV created above.

```
cat >fsxLustre-static-pvc.yaml <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: fsx-claim
  namespace: ns1
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""
  resources:
    requests:
      storage: 1200Gi
  volumeName: fsx-pv
EOF
```

```
kubectl apply -f fsxLustre-static-pvc.yaml -n <namespace registered with EMR on EKS Virtual Cluster>
```

### Spark Developer Tasks:

Now spark applications can use fsx-claim in their spark application config to mount the FSx for Lustre filesystem to driver and executor container volumes. 


```
cat >spark-python-in-s3-fsx.json <<EOF
{
  "name": "spark-python-in-s3-fsx", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count-repartition-fsx.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5  --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.options.claimName":"fsx-claim",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.mount.path":"/var/data/",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.mount.readOnly":"false",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.options.claimName":"fsx-claim",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.mount.path":"/var/data/",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.mount.readOnly":"false"
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
aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-fsx.json
```

**Expected Behavior:**
All spark jobs that are run with persistent volume claim as fsx-claim will mount to the statically created FSx for Lustre file system previously. 

**Use case:**

1. A data pipeline consisting of 10 spark applications can all be mounted to the statically created FSx for Lustre file system and can write the intermediate output to a particular folder. The next spark job in the data pipeline that is dependent on this data can read from FSx for Lustre. Data that needs to be persisted beyond the scope of the data pipeline can be synced to S3 by creating data repository tasks - https://docs.aws.amazon.com/fsx/latest/LustreGuide/data-repository-tasks.html
2. Data that is used often by multiple spark applications can also be stored in FSx for Lustre for improved performance.





## **Dynamic Provisioning:**

There is no need to provision a FSx for Lustre file system in advance. Need to create a Storage-class resource that instantiates the Storage class for FSx for Lustre. PVC is created and it refers to the storage class resource that was created. Whenever a pod refers to the PVC, the storage class invokes the FSx for Lustre Container Storage Interface (CSI) to provision a Lustre file system on the fly dynamically. In this model - FSx for Lustre of type `Scratch File Systems`
can be provisioned. - https://docs.aws.amazon.com/fsx/latest/LustreGuide/using-fsx-lustre.html

### EKS Admin Tasks:

(Refer - https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/)

1. Attach IAM policy to EKS worker node IAM role to enable access to FSx for Lustre - [Refer Doc](https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/) and [Create a Security Group to…](https://quip-amazon.com/jxgRAKqNXPMi#CQe9CA6vghM)
2. Install the FSx CSI Driver in EKS - [Refer Doc](https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/)
3. Configure Storage Class for FSx for Lustre - [Refer Doc](https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/)
4. Configure Persistent Volume Claim(`fsx-dynamic-claim`) for FSx for Lustre - [Refer Doc](https://aws.amazon.com/blogs/opensource/using-fsx-lustre-csi-driver-amazon-eks/)

```
cat >fsx-dynamic-claim.yaml <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: fsx-dynamic-claim
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: fsx-sc
  resources:
    requests:
      storage: 3600Gi
EOF 
```

```
kubectl apply -f fsx-dynamic-pvc.yaml -n <namespace registered with EMR on EKS Virtual Cluster>
```

### Spark Developer Tasks:

```
cat >spark-python-in-s3-fsx-dynamic.json << EOF
{
  "name": "spark-python-in-s3-fsx-dynamic", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count-repartition-fsx.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5  --conf spark.kubernetes.pyspark.pythonVersion=3 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6 --conf spark.sql.shuffle.partitions=1000"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.local.dir":"/var/spark/spill/",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.options.claimName":"fsx-claim",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.mount.path":"/var/data/",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.mount.readOnly":"false",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.options.claimName":"fsx-claim",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.mount.path":"/var/data/",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.mount.readOnly":"false",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-spill.options.claimName":"fsx-dynamic-claim",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-spill.mount.path":"/var/spark/spill/",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.spark-local-dir-spill.mount.readOnly":"false"
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
aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-fsx-dynamic.json
```

**Expected Result:**
Statically provisioned FSx for Lustre is mounted to `/var/data/` as before. For all the executors we provision a `SCRATCH 1` deployment type FSx for Lustre is provisioned on the fly dynamically by the Storage class that was created. There will be a latency before the first executor can start running - because the Lustre has to be created. Once it is created the same Lustre instance is mounted to all the executor.
Also note - `"spark.local.dir":"/var/spark/spill/"` is used to force executor to use this folder mounted to Lustre for all spill and shuffle data. Once thePod is terminated the Lustre file system is deleted or retained based on the configuration.
Also this dynamically created Lustre file system can also be linked to a S3 path like the statically created filesystem.
References:
https://docs.aws.amazon.com/eks/latest/userguide/fsx-csi.html

