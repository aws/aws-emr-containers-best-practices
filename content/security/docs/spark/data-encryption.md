# **EMR Containers Spark - In transit and At Rest data encryption**

### **Encryption at Rest**   
####Amazon S3 Client-Side Encryption

To utilize [S3 Client side encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingClientSideEncryption.html), you will need to create a KMS Key to be used to encrypt and decrypt data. If you do not have an KMS key, please follow this guide - [AWS KMS create keys](https://docs.aws.amazon.com/kms/latest/developerguide/create-keys.html). Also please note the job execution role needs access to this key, please see [Add to Key policy](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html#key-policy-default-allow-users) for instructions on how to add these permissions.

**trip-count-encrypt-write.py:**

```
cat> trip-count-encrypt-write.py<<EOF
import sys

from pyspark.sql import SparkSession


if __name__ == "__main__":

    spark = SparkSession\
        .builder\
        .appName("trip-count-join-fsx")\
        .getOrCreate()

    df = spark.read.parquet('s3://<s3 prefix>/trip-data.parquet')
    print("Total trips: " + str(df.count()))

    df.write.parquet('s3://<s3 prefix>/write-encrypt-trip-data.parquet')
    print("Encrypt - KMS- CSE writew to s3 compeleted")
    spark.stop()
    EOF
    
```

**Request:** 

```
cat > spark-python-in-s3-encrypt-cse-kms-write.json <<EOF
{
  "name": "spark-python-in-s3-encrypt-cse-kms-write", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>trip-count-encrypt-write.py", 
       "sparkSubmitParameters": "--conf spark.executor.instances=10 --conf spark.driver.cores=2  --conf spark.executor.memory=20G --conf spark.driver.memory=20G --conf spark.executor.cores=2"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.dynamicAllocation.enabled":"false"
         }
       },
       {
         "classification": "emrfs-site", 
         "properties": {
          "fs.s3.cse.enabled":"true",
          "fs.s3.cse.encryptionMaterialsProvider":"com.amazon.ws.emr.hadoop.fs.cse.KMSEncryptionMaterialsProvider",
          "fs.s3.cse.kms.keyId":"<KMS Key Id>"
         }
      }
    ], 
    "monitoringConfiguration": {
      "persistentAppUI": "ENABLED", 
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

aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-encrypt-cse-kms-write.json


```

In the above request, EMRFS encrypts the parquet file with the specified KMS key and the encrypted object is persisted to the specified s3 location.

To verify the encryption - use the same KMS key to decrypt - the KMS key used is a symmetric key ( the same key can be used to both encrypt and decrypt)

**trip-count-encrypt-read.py**  

```
cat > trip-count-encrypt-read.py<<EOF
import sys

from pyspark.sql import SparkSession


if __name__ == "__main__":

    spark = SparkSession\
        .builder\
        .appName("trip-count-join-fsx")\
        .getOrCreate()

    df = spark.read.parquet('s3://<s3 prefix>/trip-data.parquet')
    print("Total trips: " + str(df.count()))

    df_encrypt = spark.read.parquet('s3://<s3 prefix>/write-encrypt-trip-data.parquet')
    print("Encrypt data - Total trips: " + str(df_encrypt.count()))
    spark.stop()
   EOF
```

**Request**

```
cat > spark-python-in-s3-encrypt-cse-kms-read.json<<EOF
{
  "name": "spark-python-in-s3-encrypt-cse-kms-read", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>trip-count-encrypt-write.py", 
       "sparkSubmitParameters": "--conf spark.executor.instances=10 --conf spark.driver.cores=2  --conf spark.executor.memory=20G --conf spark.driver.memory=20G --conf spark.executor.cores=2"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.dynamicAllocation.enabled":"false"
         }
       },
       {
         "classification": "emrfs-site", 
         "properties": {
          "fs.s3.cse.enabled":"true",
          "fs.s3.cse.encryptionMaterialsProvider":"com.amazon.ws.emr.hadoop.fs.cse.KMSEncryptionMaterialsProvider",
          "fs.s3.cse.kms.keyId":"<KMS Key Id>"
         }
      }
    ], 
    "monitoringConfiguration": {
      "persistentAppUI": "ENABLED", 
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

aws emr-containers start-job-run --cli-input-json file:///spark-python-in-s3-encrypt-cse-kms-read.json





```

**Validate encryption:** Try to read the encrypted data without specifying `"fs.s3.cse.enabled":"true"` - will get an error message in the driver and executor logs because the content is encrypted and cannot be read without decryption.
