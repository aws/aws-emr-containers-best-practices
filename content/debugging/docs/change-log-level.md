# Change Log level for Spark application on EMR on EKS

Spark application developer would want to change log level to different levels depending on their requirement. spark uses apache log4j for logging.

### Change log level to DEBUG for spark application submitted to EMR-Containers

1.**Using EMR classification:**
Log level of spark applications can be changed using the [EMR spark-log4j configuration classification.](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-spark-configure.html)
Request

```
cat > Spark-Python-in-s3-debug-log.json << EOF
{
  "name": "spark-python-in-s3-debug-log", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count-repartition-fsx.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.driver.extraJavaOptions":"-Dlog4j.configuration=file:///var/data/log4j-debug.properties",
          "spark.executor.extraJavaOptions":"-Dlog4j.configuration=file:///var/data/log4j-debug.properties",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.options.claimName":"fsx-claim",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.mount.path":"/var/data/",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.mount.readOnly":"false",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.options.claimName":"fsx-claim",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.mount.path":"/var/data/",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.mount.readOnly":"false"
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

aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-debug-log.json


```

The above request will print DEBUG logs in the spark driver and executor logs stored in S3 and  Cloudwatch logs as configured.

2. **Custom log4j properties:**
Download log4j properties from [here](https://github.com/apache/spark/blob/master/conf/log4j.properties.template). Edit log4j.properties with log level as required. Save the edited log4j.properties in a mounted volume. In this example log4j.properties is placed in a s3 bucket that is mapped to a FSx for Lustre filesystem. 

Request

```
cat > Spark-Python-in-s3-debug-log.json << EOF
{
  "name": "spark-python-in-s3-debug-log", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/trip-count-repartition-fsx.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=5 --conf spark.executor.memory=20G --conf spark.driver.memory=15G --conf spark.executor.cores=6"
    }
  }, 
  "configurationOverrides": {
    "applicationConfiguration": [
      {
        "classification": "spark-defaults", 
        "properties": {
          "spark.driver.extraJavaOptions":"-Dlog4j.configuration=file:///var/data/log4j-debug.properties",
          "spark.executor.extraJavaOptions":"-Dlog4j.configuration=file:///var/data/log4j-debug.properties",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.options.claimName":"fsx-claim",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.mount.path":"/var/data/",
          "spark.kubernetes.driver.volumes.persistentVolumeClaim.sparkdata.mount.readOnly":"false",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.options.claimName":"fsx-claim",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.mount.path":"/var/data/",
          "spark.kubernetes.executor.volumes.persistentVolumeClaim.sparkdata.mount.readOnly":"false"
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

aws emr-containers start-job-run --cli-input-json file:///Spark-Python-in-s3-debug-log.json

```

Configurations of interest: Below configuration makes spark driver and executor to pickup the log4j configuration file from /var/data/ folder mounted to the driver and executor containers. For guide to mount FSx for Lustre to driver and executor containers - refer to [EMR Containers integration with FSx for Lustre](../../storage/docs/spark/fsx-lustre.md)

```
"spark.driver.extraJavaOptions":"-Dlog4j.configuration=file:///var/data/log4j-debug.properties",
"spark.executor.extraJavaOptions":"-Dlog4j.configuration=file:///var/data/log4j-debug.properties",


```

