# **Mount EBS Volume to spark driver and executor pods**

[Amazon EBS volumes](https://aws.amazon.com/ebs/) can be mounted on Spark driver and executor pods through [static](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#static) and [dynamic](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#dynamic) provisioning.

[EKS support for EBS CSI driver](https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html)  

[Documentation for EBS CSI driver](https://github.com/kubernetes-sigs/aws-ebs-csi-driver)


### **Static Provisioning**
### **Static Provisioning**

#### EKS Admin Tasks

First, create your EBS volumes:

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

Create Persistent Volume(PV) that has the EBS volume created above hardcoded:

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

Create Persistent Volume Claim(PVC) for the Persistent Volume created above:

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

PVC - `ebs-static-pvc` can be used by spark developer to mount to the spark pod  

**NOTE**: Pods running in EKS worker nodes can only attach to the EBS volume provisioned in the same AZ as the EKS worker node. Use [node selectors](../../../node-placement/docs/eks-node-placement.md) to schedule pods on EKS worker nodes the specified AZ.

#### Spark Developer Tasks

**Request**

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
When the job gets started, the pre-provisioned EBS volume is mounted to driver pod. You can exec into the driver container to verify that the EBS volume is mounted. Also you can verify the mount from the driver pod's spec.

```
kubectl get pod <driver pod name> -n <namespace> -o yaml --export
```

### Dynamic Provisioning

Dynamic Provisioning of volumes is supported for both, driver and executors for EMR versions >= 6.3.0

#### EKS Admin Tasks

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

create Persistent Volume for the EBS storage class - `demo-gp2-sc`

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

#### Spark Developer Tasks

**Request**

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
When the job gets started an EBS volume is provisioned dynamically by the EBS CSI driver and mounted to the driver pod. You can exec into the driver container to verify that the EBS volume is mounted. Also, you can verify the mount from driver pod spec.  


```
kubectl get pod <driver pod name> -n <namespace> -o yaml --export
```

