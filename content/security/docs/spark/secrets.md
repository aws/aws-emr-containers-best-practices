# ** Using Secrets in EMR on EKS**

Secrets can be credentials to APIs, Databases or other resources. There are various ways these secrets can be passed to your containers, some of them are pod environment variable or Kubernetes Secrets. These methods are not secure, as for environment variable, secrets are stored in clear text and any authorized user who has access to Kubernetes cluster with admin privileges can read those secrets. Storing secrets using Kubernetes secrets is also not secure because they are not encrypted and only base36 encoded.

There is a secure method to expose these secrets in EKS through the [Secrets Store CSI Driver](https://github.com/aws/secrets-store-csi-driver-provider-aws). 

The Secrets Store CSI Driver integrate with a secret store like [AWS Secrets manager](https://aws.amazon.com/secrets-manager/) and mount the secrets as volume that can be accessed through your application code.
This document describes how to set and use AWS Secrets Manager with EMR on EKS through the Secrets Store CSI Driver.


### Deploy Secrets Store CSI Drivers and AWS Secrets and Configuration Provider


#### Secrets Store CSI Drivers

Configure EKS Cluster with `Secrets Store CSI Driver`. 
To learn more about AWS Secrets Manager CSI Driver you can refer to this [link](https://docs.aws.amazon.com/secretsmanager/latest/userguide/integrating_csi_driver.html)
```
helm repo add secrets-store-csi-driver \
  https://kubernetes-sigs.github.io/secrets-store-csi-driver/charts

helm install -n kube-system csi-secrets-store \
  --set syncSecret.enabled=true \
  --set enableSecretRotation=true \
  secrets-store-csi-driver/secrets-store-csi-driver

```

Deploy the `AWS Secrets and Configuration Provider` to use AWS Secrets Manager

#### AWS Secrets and Configuration Provider

```
kubectl apply -f https://raw.githubusercontent.com/aws/secrets-store-csi-driver-provider-aws/main/deployment/aws-provider-installer.yaml
```

### Define the `SecretProviderClass`

The `SecretProviderClass` is how you present present your secret in Kubernetes, below you find a definition of a `SecretProviderClass`. 
There are few parameters that are important:

- The `provider` must be set to `aws`.
- The `objectName` must be the name of the secret you want to use as defined in AWS. 
Here the secret is called `db-creds`.
- The `objectType` must be set to `secretsmanager`.

```
cat > db-cred.yaml << EOF

apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: mysql-spark-secret
spec:
  provider: aws
  parameters:
    objects: |
        - objectName: "db-creds"
          objectType: "secretsmanager"
EOF
```

```
kubectl apply -f db-cred.yaml -n <NAMESPACE>
```
In the terminal apply the above command to create `SecretProviderClass`, 
The `kubectl` command must include the namespace where your job will be executed. 

### Pod Template

In the executor podtemplate you should define it as follow to mount the secret. The example below show how you can define it.
There are few points that are important to mount the secret:

- `secretProviderClass`: this should have the same name as the one define above. In this case it is `mysql-spark-secret`.
- `mountPath`: Is where the secret is going to be available to the pod. In this example it will be in `/var/secrets`
When defining the `mountPath` make sure you do not specify the ones reserved by EMR on EKS as defined [here](https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/pod-templates.html). 

```
apiVersion: v1
kind: Pod

spec:
  containers:
    - name: spark-kubernetes-executors
      volumeMounts:
        - mountPath: "/var/secrets"
          name: mysql-cred
          readOnly: true
  volumes:
      - name: mysql-cred
        csi:
          driver: secrets-store.csi.k8s.io
          readOnly: true
          volumeAttributes:
            secretProviderClass: mysql-spark-secret
```

This podtemplate must be uploaded to S3 and referenced in the job submit command as shown below.

**Note** You must make sure that the RDS instance or your Database allow traffic from the instances where your driver and executors pods are running.  

### PySpark code

The example below shows pyspark code for connecting with a MySQL DB. The example assume the secret is stored in AWS secrets manager as defined above. The `username` is the `key` to retrieve the database `user` as stored in AWS Secrets Manager, and `password` is the `key` to retrieve the database password.


It shows how you can retrieve the credentials from the mount point `/var/secrets/`. 
The secret is stored in a file with the same name as it is defined in AWS in this case it is `db-creds`.
This has been set in the podTemplate above.

```
from pyspark.sql import SparkSession
import json

secret_path = "/var/secrets/db-creds"

f = open(secret_path, "r")
mySecretDict = json.loads(f.read())

spark = SparkSession.builder.getOrCreate()

str_jdbc_url="jdbc:<DB endpoint>"
str_Query= <QUERY>
str_username=mySecretDict['username']
str_password=mySecretDict['password']
driver = "com.mysql.jdbc.Driver"

jdbcDF = spark.read \
    .format("jdbc") \
    .option("url", str_jdbc_url) \
    .option("driver", driver)\
    .option("query", str_Query) \
    .option("user", str_username) \
    .option("password", str_password) \
    .load()

jdbcDF.show()
```

### Execute the job

The command below can be used to run a job.

**Note**: The supplied execution role **MUST** have access an IAM policy that allow it access to the secret defined in `SecretProviderClass` above. 
The IAM policy below shows the IAM actions that are needed.

```
{
    "Version": "2012-10-17",
    "Statement": [ {
        "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
        "Resource": [<SECRET-ARN>]
    }]
}
```

```
    aws emr-containers start-job-run --virtual-cluster-id <EMR-VIRTUAL-CLUSTER-ID> --name spark-jdbc --execution-role-arn <EXECUTION-ROLE-ARN> --release-label emr-6.7.0-latest --job-driver '{
    "sparkSubmitJobDriver": {
    "entryPoint": "<S3-URI-FOR-PYSPARK-JOB-DEFINED-ABOVE>",
    "sparkSubmitParameters": "--conf spark.executor.instances=2 --conf spark.executor.memory=2G --conf spark.executor.cores=2 --conf spark.driver.cores=1 --conf spark.jars=<S3-URI-TO-MYSQL-JDBC-JAR>"
    }
    }' --configuration-overrides '{
    "applicationConfiguration": [
    {
    "classification": "spark-defaults", 
    "properties": {
    "spark.hadoop.hive.metastore.client.factory.class": "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
    "spark.sql.catalogImplementation": "hive",
    "spark.dynamicAllocation.enabled":"true",
    "spark.dynamicAllocation.minExecutors": "8",
    "spark.dynamicAllocation.maxExecutors": "40",
    "spark.kubernetes.allocation.batch.size": "8",
    "spark.dynamicAllocation.executorAllocationRatio": "1",
    "spark.dynamicAllocation.shuffleTracking.enabled": "true",
    "spark.dynamicAllocation.shuffleTracking.timeout": "300s",
    "spark.kubernetes.driver.podTemplateFile":<S3-URI-TO-DRIVER-POD-TEMPLATE>,
    "spark.kubernetes.executor.podTemplateFile":<S3-URI-TO-EXECUTOR-POD-TEMPLATE>
    }
    }
    ],
    "monitoringConfiguration": {
        "persistentAppUI": "ENABLED",
        "cloudWatchMonitoringConfiguration": {
            "logGroupName": "/aws/emr-containers/",
            "logStreamNamePrefix": "default"
        }
    }
    }'
```
