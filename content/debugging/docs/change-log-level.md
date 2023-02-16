# **Change Log level for Spark application on EMR on EKS**

To obtain more detail about their application or job submission, Spark application developers can change the log level of their job to different levels depending on their requirements. Spark uses apache log4j for logging.

### Change log level to DEBUG 

####**Using EMR classification**
Log level of spark applications can be changed using the [EMR spark-log4j configuration classification.](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-spark-configure.html)

**Request**  
The `pi.py` application script is from the [spark examples](https://github.com/apache/spark/blob/master/examples/src/main/python/pi.py). EMR on EKS has included the example located at`/usr/lib/spark/examples/src/main` for you to try.

`spark-log4j` classification can be used to configure values in [log4j.properties](https://github.com/apache/spark/blob/branch-3.2/conf/log4j.properties.template) for EMR releases 6.7.0 or lower , and [log4j2.properties](https://github.com/apache/spark/blob/master/conf/log4j2.properties.template) for EMR releases 6.8.0+ .
```
cat > Spark-Python-in-s3-debug-log.json << EOF
{
  "name": "spark-python-in-s3-debug-log-classification", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "local:///usr/lib/spark/examples/src/main/python/pi.py",
      "entryPointArguments": [ "200" ],
       "sparkSubmitParameters": "--conf spark.executor.memory=2G --conf spark.executor.cores=2 --conf spark.driver.memory=2G --conf spark.executor.instances=2"
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
        "classification": "spark-log4j", 
        "properties": {
          "log4j.rootCategory":"DEBUG, console"
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

The above request will print DEBUG logs in the spark driver and executor containers. The generated logs will be pushed to S3 and AWS Cloudwatch logs as configured in the request.

Starting from the version 3.3.0, Spark has been [migrated from log4j1 to log4j2](https://issues.apache.org/jira/browse/SPARK-37814). EMR on EKS allows you still write the log4j properties to the same `"classification": "spark-log4j"`, however it now needs to be log4j2.properties, such as 
```
      {
        "classification": "spark-log4j",
        "properties": {
          "rootLogger.level" : "DEBUG"
          }
      }

```

####**Custom log4j properties**  
Download log4j properties from [here](https://github.com/apache/spark/blob/master/conf/log4j.properties.template). Edit log4j.properties with log level as required. Save the edited log4j.properties in a mounted volume. In this example log4j.properties is placed in a s3 bucket that is mapped to a [FSx for Lustre filesystem](https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html). 

**Request**  
pi.py used in the below request payload is from [spark examples](https://github.com/apache/spark/blob/master/examples/src/main/python/pi.py)
```
cat > Spark-Python-in-s3-debug-log.json << EOF
{
  "name": "spark-python-in-s3-debug-log", 
  "virtualClusterId": "<virtual-cluster-id>", 
  "executionRoleArn": "<execution-role-arn>", 
  "releaseLabel": "emr-6.2.0-latest", 
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://<s3 prefix>/pi.py", 
       "sparkSubmitParameters": "--conf spark.driver.cores=2 --conf spark.executor.memory=2G --conf spark.driver.memory=2G --conf spark.executor.cores=2"
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

**Configurations of interest:**   
Below configuration enables spark driver and executor to pickup the log4j configuration file from ``/var/data/`` folder mounted to the driver and executor containers. For guide to mount FSx for Lustre to driver and executor containers - refer to [EMR Containers integration with FSx for Lustre](../../storage/docs/spark/fsx-lustre.md)

```
"spark.driver.extraJavaOptions":"-Dlog4j.configuration=file:///var/data/log4j-debug.properties",
"spark.executor.extraJavaOptions":"-Dlog4j.configuration=file:///var/data/log4j-debug.properties",


```

