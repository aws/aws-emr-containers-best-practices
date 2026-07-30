# **Self Hosted Spark History Server**

In this section, you will learn how to send Spark event logs to your own S3 bucket and self host Spark History Server. You no longer have to choose between the Persistent App UI on the AWS Console and having event logs in your own bucket: both can be used together.

## Send event logs to your own S3 bucket

EMR on EKS supports delivering Spark event logs to a custom S3 location with the `logging.eventLog.dir` property under the `emr-containers-defaults` classification. In your StartJobRun call, set:

        "configurationOverrides": {
          "applicationConfiguration": [
            {
              "classification": "emr-containers-defaults",
              "properties": {
                "logging.eventLog.dir": "s3://your-bucket-here/some-directory"
              }
            }
          ]
        }

This is compatible with and can be used alongside the Persistent App UI:

        "monitoringConfiguration": {
          "persistentAppUI": "ENABLED"
        }

!!! warning
    Do **not** set the `spark.eventLog.dir` Spark property (under the `spark-defaults` classification) when using `logging.eventLog.dir`. Setting `spark.eventLog.dir` interferes with fluentd's forwarding of the event logs and can break event log delivery. Earlier versions of this page recommended setting `spark.eventLog.enabled` and `spark.eventLog.dir` directly; that guidance is superseded by `logging.eventLog.dir`.

## Self host Spark History Server from the S3 event logs

1. Take note of the S3 path specified in `logging.eventLog.dir`, and use it in the instructions on step #2 wherever you are asked for `path_to_eventlog`. Make sure it is prepended with `s3a://`, not `s3://`. An example is `-Dspark.history.fs.logDirectory=s3a://path_to_eventlog`.

2. Follow instructions [here](https://docs.aws.amazon.com/glue/latest/dg/monitor-spark-ui-history.html#monitor-spark-ui-history-local) to launch Spark History Server using a Docker image.

3. After following the above steps, event logs flow to the specified S3 bucket and the docker container spins up Spark History Server (available at `127.0.0.1:18080`), which will pick up and parse event logs from the S3 bucket specified.
