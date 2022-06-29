# **Troubleshoot Spark application**
To obtain application error details, find the CloudWatch log or s3 log location defined by your job submission script. 
For example the driver log is stored in s3://S3BUCKET_NAME/emr-containers-log/CLUSTER_ID/jobs/JOB_ID/containers/spark-JOB_ID/spark-JOB_ID-driver/stderr.gz defined by the following submission config:
```bash
--configuration-overrides '{
    "monitoringConfiguration": {
      "s3MonitoringConfiguration": {"logUri": "s3://'$S3BUCKET'/emr-containers-log"}}}'
```

##**Scenario 1 - "PersistentVolumeClaims is forbidden"**

Running Spark jobs that require creation, listing or deletion of Persistent Volume Claims (PVC) is not supported before EMR6.8. Jobs that require these permissions will fail with the exception “persistentvolumeclaims is forbidden". Looking into application logs, you can see the driver log shows an error something look like this: `persistentvolumeclaims is forbidden. User "system:serviceaccount:emr:emr-containers-sa-spark-client-93ztm12rnjz163mt3rgdb3bjqxqfz1cgvqh1e9be6yr81" cannot create resource "persistentvolumeclaims" in API group "" in namesapce "emr".`

###**Cause:** 
This is due to the default Kubernetes role: “emr-containers” missing the required PVC permissions. As a result, the `emr-containers` primary role can’t dynamically create necessary permissions in its childern roles of Spark driver, Spark executor or Spark client when submit a job. 

###**Solution:**
Add the required permissions to emr-containers related roles in EKS.

###**Verification**
To verify whether your **emr-containers** role has the necessary permissions, run the command:
```bash
export NAMESPACE=YOUR_VALUE
kubectl describe role emr-containers -n ${NAMESPACE}
```
In addition, verify whether the spark driver/client roles have the necessary permissions with:
```bash
kubectl describe role emr-containers-role-spark-driver -n ${NAMESPACE}
kubectl describe role emr-containers-role-spark-client -n ${NAMESPACE}
```
If the permissions aren’t there, proceed with the **Patch** steps:

###**Patch via automated script**

1.If there’s any job(s) running that needs the PVC permissions and failing, stop the job(s).

2.Download the python script [`rbac_patch.py`](https://github.com/aws/aws-emr-containers-best-practices/blob/main/tools/pvc-permission/rbac_patch.py), then execute it:
```python
python3 rbac_patch.py -n ${NAMESPACE} 
```
3.After running the command, it will show a kubectl diff between the new permissions and the old ones. Press `y` to patch the role.

4.Verify the impacted roles have additional permissions:
```bash
kubectl describe role -n ${NAMESPACE}
```
5.Submit your EMR on EKS job again.

###**Manual patch**

If the permission required is not included by the PVC rules addressed previously, you can modify the patch script above or manually adjust the Kubernetes permission as needed.

NOTE: the “emr-containers” is a primary role, which must provide all the necessary permissions before changing your underlying Driver or Client roles.

1.Download the current permissions into yaml files by running the commands:
```bash
kubectl get role -n ${NAMESPACE} emr-containers -o yaml >> emr-containers-role-patch.yaml
kubectl get role -n ${NAMESPACE} emr-containers-role-spark-driver -o yaml >> driver-role-patch.yaml
kubectl get role -n ${NAMESPACE} emr-containers-role-spark-client -o yaml >> client-role-patch.yaml
```
2.Edit each yaml file and add additional rules, based on the permission your application required:

For example:
**emr-containers-role-patch.yaml**
```yaml
- apiGroups: [""]
  resources: ["persistentvolumeclaims"]
  verbs: ["create", "delete", "list"]
```
**driver-role-patch.yaml**
```yaml
- apiGroups: [""]
  resources: ["persistentvolumeclaims"]
  verbs: ["create", "delete", "list"]
- apiGroups: [""]
  resources: ["services"]
  verbs: ["get", "describe", "list", "create", "delete", "watch"]
```
**client-role-patch.yaml**
```yaml
- apiGroups: [""]
  resources: ["persistentvolumeclaims"]
  verbs:  ["create", "delete", "list"]
```
3.Remove the following attributes and their values. This is necessary to be able to apply the update, or else an error will pop up:
    - creationTimestamp
    - resourceVersion
    - uid
4.Finally run the patch:
```bash
kubectl apply -f emr-containers-role-patch.yaml
kubectl apply -f driver-role-patch.yaml
kubectl apply -f client-role-patch.yaml
```
5.Submit your EMR on EKS job again.