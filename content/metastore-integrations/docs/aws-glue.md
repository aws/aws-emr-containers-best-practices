# **EMR Containers integration with AWS Glue**

#### **AWS Glue catalog in same account as EKS**
In the below example a Spark application will be configured to use [AWS Glue data catalog](https://docs.aws.amazon.com/glue/latest/dg/components-overview.html) as the hive metastore.  

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



#### **AWS Glue catalog in different account**
The Spark application is submitted to EMR Virtual cluster in Account A and is configured to connect to [AWS Glue catalog in Account B.](https://docs.aws.amazon.com/glue/latest/dg/cross-account-access.html) The IAM policy attached to the job execution role `("executionRoleArn": "<execution-role-arn>") `is in Account A

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
To specify the accountID where the AWS Glue catalog is defined reference the following: 

[Spark-Glue integration](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-spark-glue.html)

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

#### **Sync Hudi table with AWS Glue catalog**
In this example, a Spark application will be configured to use [AWS Glue data catalog](https://docs.aws.amazon.com/glue/latest/dg/components-overview.html) as the hive metastore. 

Starting from Hudi 0.9.0, we can synchronize Hudi table's latest schema to Glue catalog via the Hive Metastore Service (HMS) in hive sync mode. This example runs a Hudi ETL job with EMR on EKS, and interact with AWS Glue metaStore to create a table. It provides you the native and serverless capabilities to manage your technical metadata. Also you can query Hudi tables in Athena straigt away after the ETL job, which provides your end user an easy data access and shortens the time to insight.

**HudiEMRonEKS.py**

```
cat > HudiEMRonEKS.py <<EOF
import sys
from pyspark.sql import SparkSession

spark = SparkSession \
    .builder \
    .config("spark.sql.warehouse.dir", sys.argv[1]+"/warehouse/" ) \
    .enableHiveSupport() \
    .getOrCreate()

# Create a DataFrame
inputDF = spark.createDataFrame(
    [
        ("100", "2015-01-01", "2015-01-01T13:51:39.340396Z"),
        ("101", "2015-01-01", "2015-01-01T12:14:58.597216Z"),
        ("102", "2015-01-01", "2015-01-01T13:51:40.417052Z"),
        ("103", "2015-01-01", "2015-01-01T13:51:40.519832Z"),
        ("104", "2015-01-02", "2015-01-01T12:15:00.512679Z"),
        ("105", "2015-01-02", "2015-01-01T13:51:42.248818Z"),
    ],
    ["id", "creation_date", "last_update_time"]
)

# Specify common DataSourceWriteOptions in the single hudiOptions variable
test_tableName = "hudi_tbl"
hudiOptions = {
'hoodie.table.name': test_tableName,
'hoodie.datasource.write.recordkey.field': 'id',
'hoodie.datasource.write.partitionpath.field': 'creation_date',
'hoodie.datasource.write.precombine.field': 'last_update_time',
'hoodie.datasource.hive_sync.enable': 'true',
'hoodie.datasource.hive_sync.table': test_tableName,
'hoodie.datasource.hive_sync.database': 'default',
'hoodie.datasource.write.hive_style_partitioning': 'true',
'hoodie.datasource.hive_sync.partition_fields': 'creation_date',
'hoodie.datasource.hive_sync.partition_extractor_class': 'org.apache.hudi.hive.MultiPartKeysValueExtractor',
'hoodie.datasource.hive_sync.mode': 'hms'
}


# Write a DataFrame as a Hudi dataset
inputDF.write \
.format('org.apache.hudi') \
.option('hoodie.datasource.write.operation', 'bulk_insert') \
.options(**hudiOptions) \
.mode('overwrite') \
.save(sys.argv[1]+"/hudi_hive_insert")
EOF
```

NOTE: configure the `warehouse dir` property to point to a S3 location as your hive warehouse storage. The s3 location can be dynamic, which is based on an argument passed in or an environament vairable.
```
.config("spark.sql.warehouse.dir", sys.argv[1]+"/warehouse/" )
```

**Request**

```
export S3BUCKET=YOUR_S3_BUCKET_NAME

aws emr-containers start-job-run \
--virtual-cluster-id $VIRTUAL_CLUSTER_ID \
--name hudi-test1 \
--execution-role-arn $EMR_ROLE_ARN \
--release-label emr-6.3.0-latest \
--job-driver '{
  "sparkSubmitJobDriver": {
      "entryPoint": "s3://'$S3BUCKET'/app_code/job/HudiEMRonEKS.py",
      "entryPointArguments":["s3://'$S3BUCKET'"],
      "sparkSubmitParameters": "--jars https://repo1.maven.org/maven2/org/apache/hudi/hudi-spark3-bundle_2.12/0.9.0/hudi-spark3-bundle_2.12-0.9.0.jar --conf spark.executor.cores=1 --conf spark.executor.instances=2"}}' \
--configuration-overrides '{
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
          "spark.sql.hive.convertMetastoreParquet": "false",
          "spark.hadoop.hive.metastore.client.factory.class": "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory"
        }}
    ], 
    "monitoringConfiguration": {
      "s3MonitoringConfiguration": {"logUri": "s3://'$S3BUCKET'/elasticmapreduce/emr-containers"}}}'
```
NOTE: To get a correct verison of hudi library, we directly download the jar from the maven repository with the synctax of `"sparkSubmitParameters": "--jars https://repo1.maven.org/maven2/org/apache/hudi/hudi-spark3-bundle_2.12/0.9.0/hudi-spark3-bundle_2.12-0.9.0.jar`. Starting from EMR 6.5, the Hudi-spark3-bundle library will be included in EMR docker images.