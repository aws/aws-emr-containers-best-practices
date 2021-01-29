# **EMR Containers integration with Hive Metastore**


### **Hive metastore Database through JDBC**

In this example, Spark application is configured to connect to a Hive Metastore database (provisioned with RDS Aurora MySql). The RDS and EKS cluster should be in same VPC or else Spark job will not be able to connect to RDS.   
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

*In this example we are connecting to mysql db, so mariadb-connector-java.jar* needs to be passed with *--jars* option. If you are using postgres, oracle or any other database, appropriate connector jar needs to be included.  

**Configuration of interest:**

```
--jars s3://<s3 prefix>/mariadb-connector-java.jar
--conf spark.hadoop.javax.jdo.option.ConnectionDriverName=org.mariadb.jdbc.Driver 
--conf spark.hadoop.javax.jdo.option.ConnectionUserName=<connection-user-name>  
--conf spark.hadoop.javax.jdo.option.ConnectionPassword=<connection-password>
--conf spark.hadoop.javax.jdo.option.ConnectionURL**=<JDBC-Connection-string>
```



**hivejdbc.py**

```
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

The above job lists databases from remote RDS Hive Metastore, creates a new table and query it as well.

### **Hive metastore thrift service through thrift:// protocol**

In this example, spark application is configured to connect to an external Hive metastore thrift server. Thrift server is on EMR’s master node and RDS Aurora is used as database for Hive Metastore.   



**thriftscript.py:**   
`hive.metastore.uris` config needs to be set to read from external Hive metastore.

```
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
```
cat > Spark-Python-in-s3-hms-thrift.json << EOF
{
  "name": "spark-python-in-s3-hms-thrift", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/thriftscript.py", 
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

aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-hms-thrift.json


```

The above job lists databases from remote Hive Metastore, creates a new table and query it as well.
