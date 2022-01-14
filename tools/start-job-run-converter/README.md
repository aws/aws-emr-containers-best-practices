# start-job-run converter
This tool can be used to migrate spark-submit commands in a script to **aws emr-containers start-job-run**
and save the result to a new file with _converted suffix.

Supported arguments:
```
  -h, --help            show this help message and exit
  --file FILE           the input spark-submit script file
  --name NAME           The name of the job run
  --virtual-cluster-id VIRTUAL_CLUSTER_ID
                        The virtual cluster ID for which the job run request is submitted
  --client-token CLIENT_TOKEN
                        The client idempotency token of the job run request
  --execution-role-arn EXECUTION_ROLE_ARN
                        The execution role ARN for the job run
  --release-label RELEASE_LABEL
                        The Amazon EMR release version to use for the job run
  --configuration-overrides CONFIGURATION_OVERRIDES
                        The configuration overrides for the job run
  --tags TAGS           The tags assigned to job runs
```

##Run the tool

```
startJobRunConverter.py \
--file ./submit_script.sh \
--virtual-cluster-id <virtual-cluster-id> \
--name emreks-test-job \
--execution-role-arn <execution-role-arn> \
--release-label emr-6.4.0-latest \
--tags KeyName1=string \
--configuration-overrides '{
  "monitoringConfiguration": {
    "cloudWatchMonitoringConfiguration": {
      "logGroupName": "emrekstest",
      "logStreamNamePrefix": "emreks_log_stream"
    },
    "s3MonitoringConfiguration": {
       "logUri": "s3://<s3 log bucket>"
    }
  }
}'
```

###Example 1
Below spark-submit command in submit_script.sh
```
spark-submit --deploy-mode cluster \
--conf spark.executor.instances=2 \
--conf spark.executor.memory=2G \
--conf spark.executor.cores=2 \
--conf spark.driver.cores=1 \
--conf "spark.executor.extraJavaOptions=-XX:+PrintGCDetails -XX:+PrintGCTimeStamps" \
--verbose \
s3://<s3 bucket>/health_violations.py \
--data_source s3://<s3 bucket>/food_establishment_data.csv \
--output_uri s3://<s3 bucket>/myOutputFolder
```

is converted to below in submit_script.sh_converted

```
#spark-submit --deploy-mode cluster \
#--conf spark.executor.instances=2 \
#--conf spark.executor.memory=2G \
#--conf spark.executor.cores=2 \
#--conf spark.driver.cores=1 \
#--conf "spark.executor.extraJavaOptions=-XX:+PrintGCDetails -XX:+PrintGCTimeStamps" \
#--verbose \
#s3://<s3 bucket>/health_violations.py \
#--data_source s3://<s3 bucket>/food_establishment_data.csv \
#--output_uri s3://<s3 bucket>/myOutputFolder

# ----- Auto converted by startJobRunConverter.py -----
aws emr-containers start-job-run \
--name emreks-test-job \
--virtual-cluster-id <virtual-cluster-id> \
--execution-role-arn <execution-role-arn> \
--release-label emr-6.4.0-latest \
--configuration-overrides '{
  "monitoringConfiguration": {
    "cloudWatchMonitoringConfiguration": {
      "logGroupName": "emrekstest",
      "logStreamNamePrefix": "emreks_log_stream"
    },
    "s3MonitoringConfiguration": {
       "logUri": "s3://<s3 log bucket>"
    }
  }
}' \
--tags KeyName1=string \
--job-driver '{
    "sparkSubmitJobDriver": {
        "entryPoint": "s3://<s3 bucket>/health_violations.py",
        "entryPointArguments": [
            "--data_source",
            "s3://<s3 bucket>/food_establishment_data.csv",
            "--output_uri",
            "s3://<s3 bucket>/myOutputFolder"
        ],
        "sparkSubmitParameters": "--deploy-mode cluster --conf spark.executor.instances=2 --conf spark.executor.memory=2G --conf spark.executor.cores=2 --conf spark.driver.cores=1 --conf \"spark.executor.extraJavaOptions=-XX:+PrintGCDetails -XX:+PrintGCTimeStamps\" --verbose"
    }
}'
```
>As you can see in the example, the original spark-submit command is kept as comments

###Example 2
```
EXECMEM=2G
EXEC_INST=2
REGION=us-east-2
spark-submit --deploy-mode cluster \
--conf spark.executor.instances=$EXEC_INST --conf spark.executor.memory=$EXECMEM --conf spark.executor.cores=2 --conf spark.driver.cores=1 \
s3://<s3 bucket>/wordcount.py s3://<s3 bucket>/wordcount_output $REGION
```

is converted to below in submit_script.sh_converted

```

EXECMEM=2G
EXEC_INST=2
REGION=us-east-2
#spark-submit --deploy-mode cluster \
#--conf spark.executor.instances=$EXEC_INST --conf spark.executor.memory=$EXECMEM --conf spark.executor.cores=2 --conf spark.driver.cores=1 \
#s3://<s3 bucket>/wordcount.py s3://<s3 bucket>/wordcount_output $REGION

# ----- Auto converted by startJobRunConverter.py -----
aws emr-containers start-job-run \
--name emreks-test-job \
--virtual-cluster-id <virtual-cluster-id> \
--execution-role-arn <execution-role-arn> \
--release-label emr-6.4.0-latest \
--configuration-overrides '{
  "monitoringConfiguration": {
    "cloudWatchMonitoringConfiguration": {
      "logGroupName": "emrekstest",
      "logStreamNamePrefix": "emreks_log_stream"
    },
    "s3MonitoringConfiguration": {
       "logUri": "s3://<s3 log bucket>"
    }
  }
}' \
--tags KeyName1=string \
--job-driver '{
    "sparkSubmitJobDriver": {
        "entryPoint": "s3://<s3 bucket>/wordcount.py",
        "entryPointArguments": [
            "s3://<s3 bucket>/wordcount_output",
            "'"$REGION"'"
        ],
        "sparkSubmitParameters": "--deploy-mode cluster --conf spark.executor.instances='"$EXEC_INST"' --conf spark.executor.memory='"$EXECMEM"' --conf spark.executor.cores=2 --conf spark.driver.cores=1"
    }
}'
```
>In bash shell, single quote won't expand variables. The tool can correctly handle the variables using double quote.

##Wait for completion
One difference between spark-submit and start-job-run is that spark-submit is waiting for the spark job to complete 
but start-job-run is async. A wait_for_completion() bash shell function can be manually appended to the converted 
command if needed.

```
function wait_for_completion() {
    cat < /dev/stdin|jq -r '[.id, .virtualClusterId]|join(" ")'| { read id virtualClusterId; echo id=$id; echo virtualClusterId=$virtualClusterId;    while [ true ]
	    do
	       sleep 10
	       state=$(aws emr-containers describe-job-run --id $id --virtual-cluster-id $virtualClusterId|jq -r '.jobRun.state')
	       echo "$(date) job run state: $state"
	       if [ "$state" = "COMPLETED" ]; then
	            echo "job run id: $id completed"
	            break
	        elif [ "$state" = "FAILED" ]; then
	            echo "job run id: $id failed. Exiting..."
	            exit 1
	        fi
	    done; }
}
```
>jq tool is required for json parsing.

To use it, append wait_for_completion to the end of the command. 
```
# ----- Auto converted by startJobRunConverter.py -----
aws emr-containers start-job-run \
--name emreks-test-job \
--virtual-cluster-id <virtual-cluster-id> \
--execution-role-arn <execution-role-arn> \
--release-label emr-6.4.0-latest \
--configuration-overrides '{
  "monitoringConfiguration": {
    "cloudWatchMonitoringConfiguration": {
      "logGroupName": "emrekstest",
      "logStreamNamePrefix": "emreks_log_stream"
    },
    "s3MonitoringConfiguration": {
       "logUri": "s3://<s3 log bucket>"
    }
  }
}' \
--tags KeyName1=string,k2=v2 \
--job-driver '{
    "sparkSubmitJobDriver": {
        "entryPoint": "s3://<s3 bucket>/wordcount.py",
        "entryPointArguments": [
            "s3://<s3 bucket>/wordcount_output",
            "'"$REGION"'"
        ],
        "sparkSubmitParameters": "--deploy-mode cluster --conf spark.executor.instances='"$EXEC_INST"' --conf spark.executor.memory='"$EXECMEM"' --conf spark.executor.cores=2 --conf spark.driver.cores=1"
    }
}'|wait_for_completion
```
