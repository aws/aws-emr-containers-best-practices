# **EMR Containers integration with AWS Glue**

#### **AWS Glue catalog in same account as EKS**
In the below example spark application will be configured to use AWS Glue catalog as the hive metastore  

**gluequery.py**

```
cat > gluequery.py <<EOF
from os.path import expanduser, join, abspath
from pyspark.sql import SparkSession
from pyspark.sql import Row
# warehouse_location points to the default location for managed databases and tables
warehouse_location = abspath('spark-warehouse')
spark = SparkSession \
    .builder \
    .appName("Python Spark SQL Hive integration example") \
    .config("spark.sql.warehouse.dir", warehouse_location) \
    .enableHiveSupport() \
    .getOrCreate()
spark.sql("CREATE EXTERNAL TABLE `sparkemrnyc`( `dispatching_base_num` string, `pickup_datetime` string, `dropoff_datetime` string, `pulocationid` bigint, `dolocationid` bigint, `sr_flag` bigint) STORED AS PARQUET LOCATION 's3://<s3 prefix>/trip-data.parquet/'")
spark.sql("SELECT count(*) FROM sparkemrnyc").show()
spark.stop()
EOF
```

```
LOCATION 's3://<s3 prefix>/trip-data.parquet/'
```

Configure the above property to point to the S3 location containing the data. 

**Request**

```
cat > Spark-Python-in-s3-awsglue-log.json << EOF
{
  "name": "spark-python-in-s3-awsglue-log", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/gluequery.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=3 --conf spark.executor.memory=8G --conf spark.driver.memory=6G --conf spark.executor.cores=3"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.hadoop.hive.metastore.client.factory.class":"com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
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

aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-awsglue-log.json








```

Output from driver logs - Displays the number of rows.

```
+----------+
|  count(1)|
+----------+
|2716504499|
+----------+
```



####**AWS Glue catalog in different account**
Spark application is submitted to EMR Virtual cluster in Account A and is configured to connect to [AWS Glue catalog in Account B](https://docs.aws.amazon.com/glue/latest/dg/cross-account-access.html)

IAM policy attached to the job execution role `("executionRoleArn": "<execution-role-arn>") `in Account A

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "glue:*"
            ],
            "Resource": [
                "arn:aws:glue:<region>:<account>:catalog",
                "arn:aws:glue:<region>:<account>:database/default",
                "arn:aws:glue:<region>:<account>:table/default/sparkemrnyc"
            ]
        }
    ]
}
```


IAM policy attached to the AWS Glue catalog in Account B

```
{
  "Version" : "2012-10-17",
  "Statement" : [ {
    "Effect" : "Allow",
    "Principal" : {
      "AWS" : "<execution-role-arn>"
    },
    "Action" : "glue:*",
    "Resource" : [ "arn:aws:glue:<region>:<account>:catalog", "arn:aws:glue:<region>:<account>:database/default", "arn:aws:glue:<region>:<account>:table/default/sparkemrnyc" ]
  } ]
}
```


**Request**

```
cat > Spark-Python-in-s3-awsglue-crossaccount.json << EOF
{
  "name": "spark-python-in-s3-awsglue-crossaccount", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/gluequery.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5  --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6 "
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.hadoop.hive.metastore.client.factory.class":"com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
          "spark.hadoop.hive.metastore.glue.catalogid":"<account B>",
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

aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-awsglue-crossaccount.json



```

**Configuration of interest**   
Specify the account id where the AWS Glue catalog is defined. [Spark-Glue integration](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-spark-glue.html)

```
"spark.hadoop.hive.metastore.glue.catalogid":"<account B>",
```

Output from driver logs - displays the number of rows.

```
+----------+
|  count(1)|
+----------+
|2716504499|
+----------+
```

