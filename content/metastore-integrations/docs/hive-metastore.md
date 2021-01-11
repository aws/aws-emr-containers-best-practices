# EMR Containers integration with Hive Metastore

Submit spark jobs and configure to use hive metastore thrift server running on EMR cluster

### Configure Spark to connect to Hive metastore Database through JDBC

Use RDS Aurora MySql as Hive Metastore and connect from Spark using JDBC string. The RDS and EKS cluster shouldbe in same VPC or else Spark job will not be able to connect to RDS. Script to submit job:

```
  aws emr-containers start-job-run --virtual-cluster-id <virtual-cluster-id> --name sparkjob --execution-role-arn <execution-role-arn> --release-label emr-6.2.0-latest --job-driver '{"sparkSubmitJobDriver": {"entryPoint": "s3://<s3 prefix>/hivejdbc.py", "sparkSubmitParameters":" --jars s3://<s3 prefix>/mariadb-connector-java.jar --conf spark.executor.instances=3 --conf spark.executor.memory=2G --conf spark.driver.memory=2G --conf spark.executor.cores=1 --conf spark.driver.cores=1 --conf spark.hadoop.javax.jdo.option.ConnectionDriverName=org.mariadb.jdbc.Driver --conf spark.hadoop.javax.jdo.option.ConnectionUserName=<connection-user-name> --conf spark.hadoop.javax.jdo.option.ConnectionPassword=<connection-password> --conf spark.hadoop.javax.jdo.option.ConnectionURL=<JDBC-Connection-string>"}}' --configuration-overrides '{"applicationConfiguration": [{"classification": "spark-defaults","properties": {"spark.executor.instances": "2","spark.executor.memory": "2G"}}],"monitoringConfiguration": { "cloudWatchMonitoringConfiguration": { "logGroupName": "`/emr-containers/jobs`", "logStreamNamePrefix": "demo"}, "s3MonitoringConfiguration": { "logUri": "s3://joblogs/" }}}'
```

*In this example we are connecting to mysql db, so mariadb-connector-java.jar* needs to be passed with *--jars* option. If you are using postgres, oracle or any other database, appropriate connector jar needs to be included.Pass following for *sparkSubmitJobDriver* configuration:

```
*--**jars s3**:**//<s3 prefix>/mariadb-connector-java.jar*
*--**conf spark**.**hadoop**.**javax**.**jdo**.**option**.**ConnectionDriverName**=**org**.**mariadb**.**jdbc**.**Driver* ** 
*-**-**conf spark**.**hadoop**.**javax**.**jdo**.**option**.**ConnectionUserName**=<**connection**-**user**-**name**>* ** 
*--**conf spark**.**hadoop**.**javax**.**jdo**.**option**.**ConnectionPassword**=<**connection**-**password**>*
*--**conf spark**.**hadoop**.**javax**.**jdo**.**option**.**ConnectionURL**=<JDBC-Connection-string>*
```



hivejdbc.py

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

### Configure Spark to connect to Hive metastore thrift service through thrift:// protocol

Query from tables through an external Hive metastore thrift server. Thrift server is on EMR’s master node and RDS Aurora is used as database for Hive Metastore. Script to submit job:

```
aws emr-containers start-job-run --virtual-cluster-id <virtual-cluster-id> --name sparkjob --execution-role-arn <execution-role-arn> --release-label emr-6.2.0-latest --job-driver '{"sparkSubmitJobDriver": {"entryPoint": "s3://<s3 prefix>/thriftscript.py", "sparkSubmitParameters":" --conf spark.executor.instances=3 --conf spark.executor.memory=2G --conf spark.driver.memory=2G --conf spark.executor.cores=1 --conf spark.driver.cores=1 "}}' --configuration-overrides '{"applicationConfiguration": [{"classification": "spark-defaults","properties": {"spark.executor.instances": "2","spark.executor.memory": "2G"}}],"monitoringConfiguration": { "cloudWatchMonitoringConfiguration": { "logGroupName": "`/emr-containers/jobs`", "logStreamNamePrefix": "demo"}, "s3MonitoringConfiguration": { "logUri": "s3://joblogs/" }}}'
```

thriftscript.py: *hive.metastore.uris* config needs to be set to read from external Hive metastore.

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

The above job lists databases from remote Hive Metastore, creates a new table and query it as well.
