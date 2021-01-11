# **Mount EBS Volume to spark driver and executor pods**

EBS Volumes can be mounted on spark driver and executor pods through static and dynamic provisioning - 
**Difference between static and dynamic provisioning of Persistent Volumes:**
(Refer - https://kubernetes.io/docs/concepts/storage/persistent-volumes/#provisioning)

EKS support for EBS CSI driver - https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html
Documentation for EBS CSI driver - https://github.com/kubernetes-sigs/aws-ebs-csi-driver


## **Static Provisioning** -

### EKS Admin Tasks:

Create EBS volumes

```
aws ec2 --region <region> create-volume --availability-zone <availability zone> --size 50
{
    "AvailabilityZone": "<availability zone>", 
    "MultiAttachEnabled": false, 
    "Tags": [], 
    "Encrypted": false, 
    "VolumeType": "gp2", 
    "VolumeId": "<vol -id>", 
    "State": "creating", 
    "Iops": 150, 
    "SnapshotId": "", 
    "CreateTime": "2020-11-03T18:36:21.000Z", 
    "Size": 50
}
```

Create Persistent Volume(PV) that has the EBS volume created above hardcoded

```
cat > ebs-static-pv.yaml << EOF
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ebs-static-pv
spec:
  capacity:
    storage: 5Gi
  accessModes:
    - ReadWriteOnce
  storageClassName: gp2
  awsElasticBlockStore:
    fsType: ext4
    volumeID: <vol -id>
EOF

kubectl apply -f ebs-static-pv.yaml -n <namespace>
```

Create Persistent Volume Claim(PVC) for the Persistent Volume created above

```
cat > ebs-static-pvc.yaml << EOF
kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: ebs-static-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
  volumeName: ebs-static-pv
EOF

kubectl apply -f ebs-static-pvc.yaml -n <namespace>
```

PVC - ebs-static-pvc can be used by spark developer to mount to the spark pod
**NOTE: Pods running in EKS worker nodes can attach to only EBS volume provisioned in the same AZ as the EKS worker Node. Use node selector to schedule pods on a EKS worker node in a specified AZ**

### Spark Developer Tasks:

**Sample Request**

```
cat >spark-python-in-s3-ebs-static-localdir.json << EOF
{
  "name": "spark-python-in-s3-ebs-static-localdir", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count-fsx.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5 --conf spark.executor.instances=10 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6 "
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.kubernetes.node.selector.topology.kubernetes.io/zone":"<availability zone>",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.spark-local-dir-sparkspill.options.claimName":"ebs-static-pvc",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.spark-local-dir-sparkspill.mount.path":"/var/spark/spill/",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.spark-local-dir-sparkspill.mount.readOnly":"false",
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
aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-ebs-static-localdir.json
```

**Observed Behavior:**
When the job gets started the driver pod and executor pods are scheduled only on those EKS worker nodes with the label [topology.kubernetes.io/zone](http://topology.kubernetes.io/zone): <availability zone>.
This ensures the spark job is run within a single AZ. If there are not enough resource within the AZ the pods will be in pending state until the Autoscaler(if configured) to kick in or more resources to be available.

You can verify that the EBS volume created is mounted to driver pod and you can exec into the driver container to verify that the EBS volume is mounted. Also can verify from driver pod spec

```
kubectl get pod <driver pod name> -n <namespace> -o yaml --export
```

### Dynamic Provisioning:

### EKS Admin Tasks:

Create EBS Storage Class

```
cat >demo-gp2-sc.yaml << EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: demo-gp2-sc
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp2
reclaimPolicy: Retain
allowVolumeExpansion: true
mountOptions:
  - debug
volumeBindingMode: Immediate
EOF

kubectl apply -f demo-gp2-sc.yaml
```

create Persistent Volume for the EBS storage class - demo-gp2-sc

```
cat >ebs-demo-gp2-claim.yaml <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ebs-demo-gp2-claim
  labels:
    app: chicago
spec:
  storageClassName: demo-gp2-sc
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
EOF

kubectl apply -f ebs-demo-gp2-claim.yaml -n <namespace>
```

### Spark Developer Tasks:

**Sample Request**

```
cat >spark-python-in-s3-ebs-dynamic-localdir.json << EOF
{
  "name": "spark-python-in-s3-ebs-dynamic-localdir", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count-fsx.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5 --conf spark.executor.instances=10 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.kubernetes.node.selector.topology.kubernetes.io/zone":"<availability zone>",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.spark-local-dir-sparkspill.options.claimName":"ebs-demo-gp2-claim",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.spark-local-dir-sparkspill.mount.path":"/var/spark/spill/",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.spark-local-dir-sparkspill.mount.readOnly":"false",
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
aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-ebs-dynamic-localdir.json
```

**Observed Behavior:**
When the job gets started the driver pod and executor pods are scheduled only on those EKS worker nodes with the label [topology.kubernetes.io/zone](http://topology.kubernetes.io/zone): <availability zone>
This ensures the spark job is run within a single AZ. If there are not enough resource within the AZ the pods will be in pending state until the Autoscaler(if configured) to kick in or more resources to be available.

You can verify that the a EBS volume is provisioned dynamically by the EBS CSI driver and mounted to the driver pod. Also can verify from driver pod spec

```
kubectl get pod <driver pod name> -n <namespace> -o yaml --export
```

**POINT TO NOTE: It is not possible to use this dynamic provisioning strategy for EBS to spark executors. Not possible to mount a new EBS volume to every Spark executor. Instead use a distributed file system like Lustre, EFS, NFS to mount to executors.** 