# **EMR Containers integration with Hive Metastore**


### **Hive metastore Database through JDBC**

In this example, a Spark application is configured to connect to a Hive Metastore database provisioned with [Amazon RDS Aurora](https://aws.amazon.com/rds/aurora/) MySql. The Amazon RDS and [EKS](https://aws.amazon.com/eks/) cluster should be in same VPC or else the Spark job will not be able to connect to RDS. 

For more details, check out the [github repository](https://github.com/melodyyangaws/hive-emr-on-eks), which includes CDK/CFN templates that help you setup the test environment.

**Request:**  

```
cat > Spark-Python-in-s3-hms-jdbc.json << EOF
{
  "name": "spark-python-in-s3-hms-jdbc", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/hivejdbc.py", 
       "sparkSubmitParameters": "--jars s3://<s3 prefix>/mariadb-connector-java.jar --conf spark.hadoop.javax.jdo.option.ConnectionDriverName=org.mariadb.jdbc.Driver --conf spark.hadoop.javax.jdo.option.ConnectionUserName=<connection-user-name> --conf spark.hadoop.javax.jdo.option.ConnectionPassword=<connection-password> --conf spark.hadoop.javax.jdo.option.ConnectionURL=<JDBC-Connection-string> --conf spark.driver.cores=5 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.dynamicAllocation.enabled":"false"
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

aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-hms-jdbc.json


```

In this example we are connecting to mysql db, so `mariadb-connector-java.jar` needs to be passed with `--jars` option. If you are using postgres, Oracle or any other database, the appropriate connector jar needs to be included.  

**Configuration of interest:**

```
--jars s3://<s3 prefix>/mariadb-connector-java.jar
--conf spark.hadoop.javax.jdo.option.ConnectionDriverName=org.mariadb.jdbc.Driver 
--conf spark.hadoop.javax.jdo.option.ConnectionUserName=<connection-user-name>  
--conf spark.hadoop.javax.jdo.option.ConnectionPassword=<connection-password>
--conf spark.hadoop.javax.jdo.option.ConnectionURL**=<JDBC-Connection-string>
```



**hivejdbc.py**

```python
from os.path import expanduser, join, abspath
from pyspark.sql import SparkSession
from pyspark.sql import Row
# warehouse_location points to the default location for managed databases and tables
warehouse_location = abspath('spark-warehouse')
spark = SparkSession \
    .builder \
    .config("spark.sql.warehouse.dir", warehouse_location) \
    .enableHiveSupport() \
    .getOrCreate()
spark.sql("SHOW DATABASES").show()
spark.sql("CREATE EXTERNAL TABLE `ehmsdb`.`sparkemrnyc5`( `dispatching_base_num` string, `pickup_datetime` string, `dropoff_datetime` string, `pulocationid` bigint, `dolocationid` bigint, `sr_flag` bigint) STORED AS PARQUET LOCATION 's3://<s3 prefix>/nyctaxi_parquet/'")
spark.sql("SELECT count(*) FROM ehmsdb.sparkemrnyc5 ").show()
spark.stop()
```

The above job lists databases from a remote RDS Hive Metastore, creates a new table and then queries it.

### **Hive metastore thrift service through thrift:// protocol**

In this example, the spark application is configured to connect to an external Hive metastore thrift server. The thrift server is running on `EMR on EC2's master node` and AWS RDS Aurora is used as database for the Hive metastore.   


**thriftscript.py:**   
`hive.metastore.uris` config needs to be set to read from external Hive metastore. The URI format looks like this: `thrift://EMR_ON_EC2_MASTER_NODE_DNS_NAME:9083`

```python
from os.path import expanduser, join, abspath
from pyspark.sql import SparkSession
from pyspark.sql import Row
# warehouse_location points to the default location for managed databases and tables
warehouse_location = abspath('spark-warehouse')
spark = SparkSession \
    .builder \
    .config("spark.sql.warehouse.dir", warehouse_location) \
    .config("hive.metastore.uris","<hive metastore thrift uri>") \
    .enableHiveSupport() \
    .getOrCreate()
spark.sql("SHOW DATABASES").show()
spark.sql("CREATE EXTERNAL TABLE ehmsdb.`sparkemrnyc2`( `dispatching_base_num` string, `pickup_datetime` string, `dropoff_datetime` string, `pulocationid` bigint, `dolocationid` bigint, `sr_flag` bigint) STORED AS PARQUET LOCATION 's3://<s3 prefix>/nyctaxi_parquet/'")
spark.sql("SELECT * FROM ehmsdb.sparkemrnyc2").show()
spark.stop()
```

**Request:**

The below job lists databases from remote Hive Metastore, creates a new table and then queries it.

```bash
cat > Spark-Python-in-s3-hms-thrift.json << EOF
{
  "name": "spark-python-in-s3-hms-thrift", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/thriftscript.py", 
       "sparkSubmitParameters": "--jars s3://<s3 prefix>/mariadb-connector-java.jar --conf spark.driver.cores=5 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.dynamicAllocation.enabled":"false"
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

aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-hms-thrift.json


```

###**Connect Hive metastore via thrift service hosted on EKS**
In this example, our Spark application connects to a standalone Hive metastore service (HMS) running in EKS.

Simply replace the environment varaibles in the following command, then install the [HMS helm chart](https://github.com/melodyyangaws/hive-emr-on-eks/tree/main/hive-metastore-chart) in EKS:

```bash
cd hive-emr-on-eks/hive-metastore-chart

sed -i '' -e 's/{RDS_JDBC_URL}/"jdbc:mysql:\/\/'$YOUR_HOST_NAME':3306\/'$YOUR_DB_NAME'?createDatabaseIfNotExist=true"/g' values.yaml 
sed -i '' -e 's/{RDS_USERNAME}/'$YOUR_USER_NAME'/g' values.yaml 
sed -i '' -e 's/{RDS_PASSWORD}/'$YOUR_PASSWORD'/g' values.yaml
sed -i '' -e 's/{S3BUCKET}/s3:\/\/'$YOUR_S3BUCKET'/g' values.yaml

helm repo add hive-metastore https://melodyyangaws.github.io/hive-metastore-chart 
helm install hive hive-metastore/hive-metastore -f values.yaml --namespace=emr --debug
```

**hivethrift_eks.py**

```python
from os import environ
import sys
from pyspark.sql import SparkSession

spark = SparkSession \
    .builder \
    .config("spark.sql.warehouse.dir",environ['warehouse_location']) \
    .config("hive.metastore.uris","thrift://"+environ['HIVE_METASTORE_SERVICE_HOST']+":9083") \
    .enableHiveSupport() \
    .getOrCreate()

spark.sql("SHOW DATABASES").show()
spark.sql("CREATE DATABASE IF NOT EXISTS `demo`")
spark.sql("DROP TABLE IF EXISTS demo.amazonreview3")
spark.sql("CREATE EXTERNAL TABLE IF NOT EXISTS `demo`.`amazonreview3`( `marketplace` string,`customer_id`string,`review_id` string,`product_id` string,`product_parent` string,`product_title` string,`star_rating` integer,`helpful_votes` integer,`total_votes` integer,`vine` string,`verified_purchase` string,`review_headline` string,`review_body` string,`review_date` date,`year` integer) STORED AS PARQUET LOCATION '"+sys.argv[1]+"/app_code/data/toy/'")

``` 
An environment variable `HIVE_METASTORE_SERVICE_HOST` appears in your Spark application pods automatically, once the standalone HMS is up running in EKS. You can directly set the `hive.metastore.uris` to `thrift://"+environ['HIVE_METASTORE_SERVICE_HOST']+":9083"`.

Can set the `spark.sql.warehouse.dir` property to a S3 location as your hive warehouse storage. The s3 location can be dynamic, which is based on an argument passed in or an environament vairable.

**Request:**

```bash
#!/bin/bash
aws emr-containers start-job-run \
--virtual-cluster-id $VIRTUAL_CLUSTER_ID \
--name spark-hive-via-thrift \
--execution-role-arn $EMR_ROLE_ARN \
--release-label emr-6.2.0-latest \
--job-driver '{
  "sparkSubmitJobDriver": {
      "entryPoint": "s3://'$S3BUCKET'/app_code/job/hivethrift_eks.py",
      "entryPointArguments":["s3://'$S3BUCKET'"],
      "sparkSubmitParameters": "--conf spark.driver.cores=1 --conf spark.executor.memory=4G --conf spark.driver.memory=1G --conf spark.executor.cores=2"}}' \
--configuration-overrides '{
    "monitoringConfiguration": {
      "s3MonitoringConfiguration": {"logUri": "s3://'$S3BUCKET'/elasticmapreduce/emr-containers"}}}'
      ```
      
###**Run thrift service as a sidecar in Spark Driver's pod**

This advanced approach runs the standalone HMS thrift service inside each Spark driver as a sidecar.

If you are trying it out against an existing EKS cluster, the prerequisite details can be found in the [github repository](https://github.com/melodyyangaws/hive-emr-on-eks#41-run-the-thrift-service-as-a-sidecar-in-spark-drivers-pod)

**sidecar_hivethrift_eks.py:**

```python
import sys
from pyspark.sql import SparkSession

spark = SparkSession \
    .builder \
    .config("spark.sql.warehouse.dir",environ['warehouse_location']) \
    .enableHiveSupport() \
    .getOrCreate()

spark.sql("SHOW DATABASES").show()
spark.sql("CREATE DATABASE IF NOT EXISTS `demo`")
spark.sql("DROP TABLE IF EXISTS demo.amazonreview4")
spark.sql("CREATE EXTERNAL TABLE `demo`.`amazonreview4`( `marketplace` string,`customer_id`string,`review_id` string,`product_id` string,`product_parent` string,`product_title` string,`star_rating` integer,`helpful_votes` integer,`total_votes` integer,`vine` string,`verified_purchase` string,`review_headline` string,`review_body` string,`review_date` date,`year` integer) STORED AS PARQUET LOCATION '"+sys.argv[1]+"/app_code/data/toy/'")

spark.stop()
```

**Request:**

Now that the HMS is running inside your application, the `spark.hive.metastore.uris` can set to "thrift://localhost:9083". Don't forget to assign the sidecar pod template to the Spark Driver like this `"spark.kubernetes.driver.podTemplateFile": "s3://'$S3BUCKET'/app_code/job/sidecar_hms_pod_template.yaml"` 

For more details, check out the [github repo](https://github.com/melodyyangaws/hive-emr-on-eks#41-run-the-thrift-service-as-a-sidecar-in-spark-drivers-pod)

```bash
#!/bin/bash
# test HMS sidecar on EKS
aws emr-containers start-job-run \
--virtual-cluster-id $VIRTUAL_CLUSTER_ID \
--name sidecar-hms \
--execution-role-arn $EMR_ROLE_ARN \
--release-label emr-6.3.0-latest \
--job-driver '{
  "sparkSubmitJobDriver": {
      "entryPoint": "s3://'$S3BUCKET'/app_code/job/sidecar_hivethrift_eks.py",
      "entryPointArguments":["s3://'$S3BUCKET'"],
      "sparkSubmitParameters": "--conf spark.driver.cores=1 --conf spark.executor.memory=4G --conf spark.driver.memory=1G --conf spark.executor.cores=2"}}' \
--configuration-overrides '{
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.kubernetes.driver.podTemplateFile": "s3://'$S3BUCKET'/app_code/job/sidecar_hms_pod_template.yaml",
          "spark.hive.metastore.uris": "thrift://localhost:9083"
        }
      }
    ], 
    "monitoringConfiguration": {
      "s3MonitoringConfiguration": {"logUri": "s3://'$S3BUCKET'/elasticmapreduce/emr-containers"}}}'
```

###**Hudi + Remote Hive metastore integration**

Starting from Hudi 0.9.0, we can synchronize Hudi table's latest schema to Hive metastore in HMS sync mode, like this `'hoodie.datasource.hive_sync.mode': 'hms'`. 

This example runs a Hudi job with EMR on EKS, and interact with hive metastore to create a table. As a serverless option, it can interact with AWS Glue catalog. check out the [AWS Glue](./aws-glue.md) section for more information.

**HudiEMRonEKS.py**

```python
from os import environ
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

print("After {}".format(spark.catalog.listTables()))

```
**Request:**

The latest Hudi-spark3-bundle is needed to support the HMS hive sync functionality. The jar is downloaded from the maven repository in the following script with EMR 6.3. However, it will be included from EMR 6.5+.

```bash
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
          "spark.hive.metastore.uris": "thrift://localhost:9083",
	      "spark.kubernetes.driver.podTemplateFile": "s3://'$S3BUCKET'/app_code/job/sidecar_hms_pod_template.yaml"
        }}
    ], 
    "monitoringConfiguration": {
      "s3MonitoringConfiguration": {"logUri": "s3://'$S3BUCKET'/elasticmapreduce/emr-containers"}}}'
```
