# **Troubleshooting EMR on EKS issues**

In this section, you will find several scenarios for troubleshooting described with errors and solutions. You can find these errors using one of these methods

1. using [EMR on EKS describe API call](https://docs.aws.amazon.com/cli/latest/reference/emr-containers/describe-job-run.html)
2. using CloudWatch Logs. In the job submission example below, you can find logs in `/emr-containers/jobs` location
3. using logs shipped to s3. In the job submission example below, you can find logs in `s3://'$S3BUCKET'/emr-containers-log` path. For driver logs, you need traverse few folders to find the logs. For example, `s3://S3BUCKET_NAME/emr-containers-log/CLUSTER_ID/jobs/JOB_ID/containers/spark-JOB_ID/spark-JOB_ID-driver/stderr.gz`

```bash
--configuration-overrides '{
    "monitoringConfiguration": {
      "cloudWatchMonitoringConfiguration": {
        "logGroupName": "/emr-containers/jobs", 
        "logStreamNamePrefix": "demo"
      },               
      "s3MonitoringConfiguration": {
        "logUri": "s3://'$S3BUCKET'/emr-containers-log"
        }
      }
    }'
```
##**Error - "PersistentVolumeClaims is forbidden"**

Occassionally, there is a drift in RBAC permission required for EMR on EKS and Managed endpoint (EMR Studio) installation to work with EKS clusters. This can happen due to upstream changes in Kubernetes RBAC policies. Here is an example of one such [change in Kubernetes v1.22](https://kubernetes.io/blog/2021/07/14/upcoming-changes-in-kubernetes-1-22/#api-changes). Previously, EMR needed permissions for `ingresses.extensions` to create managed endpoint. But for Kubernetes v1.22 or higher versions, EMR needs `ingresses.networking.k8s.io` permissions as well. 

In addition, EMR adds newer features that require newer set of RBAC permissions. For example, Spark jobs that require creation, listing or deletion of Persistent Volume Claims (PVC) was not supported before EMR6.8. Jobs that require these permissions will fail with the exception “persistentvolumeclaims is forbidden". Looking into driver logs, you may see an error like this: 
```
persistentvolumeclaims is forbidden. User "system:serviceaccount:emr:emr-containers-sa-spark-client-93ztm12rnjz163mt3rgdb3bjqxqfz1cgvqh1e9be6yr81" cannot create resource "persistentvolumeclaims" in API group "" in namesapce "emr".
```
You may encounter this error because the default Kubernetes role `emr-containers` is missing the required RBAC permissions. As a result, the `emr-containers` primary role can’t dynamically create necessary permissions for additional roles such as Spark driver, Spark executor or Spark client when you submit a job. Because EMR on EKS and Managed endpoint can be installed using different tooling (AWS CLI, SDK, eksctl, terraform, cdk), there can be slight delay in adding most current RBAC permissions into the tooling 

###**Solution:**
Add the required permissions to `emr-containers`. 

Here are the complete RBAC permissions for EMR on EKS: 

* [emr-containers.yaml](https://github.com/aws/aws-emr-containers-best-practices/blob/main/tools/k8s-rbac-policies/emr-containers.yaml)

You can compare whether you have complete RBAC permissions using the steps below, 
```bash
export NAMESPACE=YOUR_VALUE
kubectl describe role emr-containers -n ${NAMESPACE}
```

If the permissions don't match, proceed to apply latest permissions

```bash
export NAMESPACE=YOUR_VALUE
kubectl apply -f https://github.com/aws/aws-emr-containers-best-practices/blob/main/tools/k8s-rbac-policies/emr-containers.yaml -n ${NAMESPACE}
```
You can delete other two spark driver/client roles bcoz they will be dynamically created when you run next job. 
