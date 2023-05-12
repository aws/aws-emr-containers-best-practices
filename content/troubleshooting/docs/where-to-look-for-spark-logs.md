# **Spark Driver and Executor Logs**

The status of the spark jobs can be monitored via [EMR on EKS describe-job-run API](https://docs.aws.amazon.com/cli/latest/reference/emr-containers/describe-job-run.html).

To be able to monitor the job progress and to troubleshoot failures, you must configure your jobs to send log information to Amazon S3, Amazon CloudWatch Logs, or both

### Send Spark Logs to S3

####**Update the IAM role with S3 write access**
Configure the IAM Role passed in StartJobRun input `executionRoleArn` with access to S3 buckets.
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::my_s3_log_location",
                "arn:aws:s3:::my_s3_log_location/*",
            ]
        }
    ]
}
```

####**Configure the StartJobRun API with S3 buckets**
Configure the `monitoringConfiguration` with `s3MonitoringConfiguration`, and configure the S3 location where the logs would be synced.

```json
{
  "name": "<job_name>", 
  "virtualClusterId": "<vc_id>",  
  "executionRoleArn": "<iam_role_name_for_job_execution>", 
  "releaseLabel": "<emr_release_label>", 
  "jobDriver": {
    
  }, 
  "configurationOverrides": {
    "monitoringConfiguration": {
      "persistentAppUI": "ENABLED",
      "s3MonitoringConfiguration": {
        "logUri": "s3://my_s3_log_location"
      }
    }
  }
}
```

####**Log location of JobRunner, Driver, Executor in S3**
The JobRunner (pod that does spark-submit), Spark Driver, and Spark Executor logs would be found in the following S3 locations.
```text
JobRunner/Spark-Submit/Controller Logs - s3://my_s3_log_location/${virtual-cluster-id}/jobs/${job-id}/containers/${job-runner-pod-id}/(stderr.gz/stdout.gz)

Driver Logs - s3://my_s3_log_location/${virtual-cluster-id}/jobs/${job-id}/containers/${spark-application-id}/${spark-job-id-driver-pod-name}/(stderr.gz/stdout.gz)

Executor Logs - s3://my_s3_log_location/${virtual-cluster-id}/jobs/${job-id}/containers/${spark-application-id}/${spark-job-id-driver-executor-id}/(stderr.gz/stdout.gz)
```


### Send Spark Logs to CloudWatch

####**Update the IAM role with CloudWatch access**
Configure the IAM Role passed in StartJobRun input `executionRoleArn` with access to CloudWatch Streams.
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ],
      "Resource": [
        "arn:aws:logs:*:*:*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:PutLogEvents"
      ],
      "Resource": [
        "arn:aws:logs:*:*:log-group:my_log_group_name:log-stream:my_log_stream_prefix/*"
      ]
    }
  ]
}
```

####**Configure StartJobRun API with CloudWatch**
Configure the `monitoringConfiguration` with `cloudWatchMonitoringConfiguration`, and configure the CloudWatch `logGroupName` and `logStreamNamePrefix` where the logs should be pushed.

```json
{
  "name": "<job_name>", 
  "virtualClusterId": "<vc_id>",  
  "executionRoleArn": "<iam_role_name_for_job_execution>", 
  "releaseLabel": "<emr_release_label>", 
  "jobDriver": {
    
  }, 
  "configurationOverrides": {
    "monitoringConfiguration": {
      "persistentAppUI": "ENABLED",
      "cloudWatchMonitoringConfiguration": {
        "logGroupName": "my_log_group_name",
        "logStreamNamePrefix": "my_log_stream_prefix"
      }
    }
  }
}
```

####**Log location of JobRunner, Driver, Executor**
The JobRunner (pod that does spark-submit), Spark Driver, and Spark Executor logs would be found in the following AWS CloudWatch locations.

```text
JobRunner/Spark-Submit/Controller Logs - ${my_log_group_name}/${my_log_stream_prefix}/${virtual-cluster-id}/jobs/${job-id}/containers/${job-runner-pod-id}/(stderr.gz/stdout.gz)

Driver Logs - ${my_log_group_name}/${my_log_stream_prefix}/${virtual-cluster-id}/jobs/${job-id}/containers/${spark-application-id}/${spark-job-id-driver-pod-name}/(stderr.gz/stdout.gz)

Executor Logs - ${my_log_group_name}/${my_log_stream_prefix}/${virtual-cluster-id}/jobs/${job-id}/containers/${spark-application-id}/${spark-job-id-driver-executor-id}/(stderr.gz/stdout.gz)
```

