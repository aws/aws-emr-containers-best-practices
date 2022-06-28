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
2.Create a script file named `RBAC_Patch.py`:
```python
import os
import subprocess as sp
import tempfile as temp
import json
import argparse
import uuid


def delete_if_exists(dictionary: dict, key: str):
    if dictionary.get(key, None) is not None:
        del dictionary[key]


def doTerminalCmd(cmd):
    with temp.TemporaryFile() as f:
        process = sp.Popen(cmd, stdout=f, stderr=f)
        process.wait()
        f.seek(0)
        msg = f.read().decode()
    return msg


def patchRole(roleName, namespace, extraRules, skipConfirmation=False):
    cmd = f"kubectl get role {roleName} -n {namespace} --output json".split(" ")
    msg = doTerminalCmd(cmd)
    if "(NotFound)" in msg and "Error" in msg:
        print(msg)
        return False
    role = json.loads(msg)
    rules = role["rules"]
    rulesToAssign = extraRules[::]
    passedRules = []
    for rule in rules:
        apiGroups = set(rule["apiGroups"])
        resources = set(rule["resources"])
        verbs = set(rule["verbs"])
        for extraRule in extraRules:
            passes = 0
            apiGroupsExtra = set(extraRule["apiGroups"])
            resourcesExtra = set(extraRule["resources"])
            verbsExtra = set(extraRule["verbs"])
            passes += len(apiGroupsExtra.intersection(apiGroups)) >= len(apiGroupsExtra)
            passes += len(resourcesExtra.intersection(resources)) >= len(resourcesExtra)
            passes += len(verbsExtra.intersection(verbs)) >= len(verbsExtra)
            if passes >= 3:
                if extraRule not in passedRules:
                    passedRules.append(extraRule)
                    if extraRule in rulesToAssign:
                        rulesToAssign.remove(extraRule)
                break
    prompt_text = "Apply Changes?"
    if len(rulesToAssign) == 0:
        print(f"The role {roleName} seems to already have the necessary permissions!")
        prompt_text = "Proceed anyways?"
    for ruleToAssign in rulesToAssign:
        role["rules"].append(ruleToAssign)
    delete_if_exists(role, "creationTimestamp")
    delete_if_exists(role, "resourceVersion")
    delete_if_exists(role, "uid")
    new_role = json.dumps(role, indent=3)
    uid = uuid.uuid4()
    filename = f"Role-{roleName}-New_Permissions-{uid}-TemporaryFile.json"
    try:
        with open(filename, "w+") as f:
            f.write(new_role)
            f.flush()
        prompt = "y"
        if not skipConfirmation:
            prompt = input(
                doTerminalCmd(f"kubectl diff -f {filename}".split(" ")) + f"\n{prompt_text} y/n: "
            ).lower().strip()
            while prompt != "y" and prompt != "n":
                prompt = input("Please make a valid selection. y/n: ").lower().strip()
        if prompt == "y":
            print(doTerminalCmd(f"kubectl apply -f {filename}".split(" ")))
    except Exception as e:
        print(e)
    os.remove(f"./{filename}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--namespace",
                        help="Namespace of the Role. By default its the VirtualCluster's namespace",
                        required=True,
                        dest="namespace"
                        )

    parser.add_argument("-p", "--no-prompt",
                        help="Applies the patches without asking first",
                        dest="no_prompt",
                        default=False,
                        action="store_true"
                        )
    args = parser.parse_args()

    emrRoleRules = [
        {
            "apiGroups": [""],
            "resources": ["persistentvolumeclaims"],
            "verbs": ["list", "create", "delete"]
        
    ]

    driverRoleRules = [
        {
            "apiGroups": [""],
            "resources": ["persistentvolumeclaims"],
            "verbs": ["list", "create", "delete"]
        },
        {
            "apiGroups": [""],
            "resources": ["services"],
            "verbs": ["get", "list", "describe", "create", "delete", "watch"]
        }
    ]

    clientRoleRules = [
        {
            "apiGroups": [""],
            "resources": ["persistentvolumeclaims"],
            "verbs": ["list", "create", "delete"]
        }
    ]

    patchRole("emr-containers", args.namespace, emrRoleRules, args.no_prompt)
    patchRole("emr-containers-role-spark-driver", args.namespace, driverRoleRules, args.no_prompt)
    patchRole("emr-containers-role-spark-client", args.namespace, clientRoleRules, args.no_prompt)
```
3.Run the python script:
```python
python3 RBAC_Patch.py -n ${NAMESPACE} 
```
4.After running the command, it will show a kubectl diff between the new permissions and the old ones. Press `y` to patch the role.

5.Verify the impacted roles have additional permissions:
```bash
kubectl describe role -n ${NAMESPACE}
```
6.Submit your EMR on EKS job again.

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
- apiGroups:
  - ""
  resources:
  - persistentvolumeclaims
  verbs:
  - list
  - create
  - delete
```
**driver-role-patch.yaml**
```yaml
- apiGroups:
  - ""
  resources:
  - persistentvolumeclaims
  verbs:
  - list
  - create
  - delete
- apiGroups:
  - ""
  resources:
  - services
  verbs:
  - get 
  - list 
  - describe 
  - create
  - delete 
  - watch
```
**client-role-patch.yaml**
```yaml
- apiGroups:
  - ""
  resources:
  - persistentvolumeclaims
  verbs:
  - list
  - create
  - delete
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