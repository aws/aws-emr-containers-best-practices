# **RBAC Permission Errors**

The following sections provide solutions to common RBAC authorization errors.

### PersistentVolumeClaims is forbidden

**Error:**
Spark jobs that require creation, listing or deletion of Persistent Volume Claims (PVC) was not supported before EMR6.8. Jobs that require these permissions will fail with the exception “persistentvolumeclaims is forbidden". Looking into driver logs, you may see an error like this: 
```
persistentvolumeclaims is forbidden. User "system:serviceaccount:emr:emr-containers-sa-spark-client-93ztm12rnjz163mt3rgdb3bjqxqfz1cgvqh1e9be6yr81" cannot create resource "persistentvolumeclaims" in API group "" in namesapce "emr".
```
You may encounter this error because the default Kubernetes role `emr-containers` is missing the required RBAC permissions. As a result, the `emr-containers` primary role can’t dynamically create necessary permissions for additional roles such as Spark driver, Spark executor or Spark client when you submit a job. 

**Solution:**
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
You can delete the spark driver and client roles because they will be dynamically created when the job is run next time. 

