# **Self Hosted Spark History Server**

In this section, you will learn how to self host Spark History Server instead of using the Persistent App UI on the AWS Console.

1. In your StartJobRun call for EMR on EKS, set the following conf. to point to an S3 bucket where you would like your event logs to go : `spark.eventLog.dir` and `spark.eventLog.enabled` as such:


        "configurationOverrides": {
          "applicationConfiguration": [{
            "classification": "spark-defaults",
            "properties": {
              "spark.eventLog.enabled": "true",
              "spark.eventLog.dir": "s3://your-bucket-here/some-directory"
        ...


2. Take note of the S3 bucket specified in #1, and use it in the instructions on step #3 wherever you are asked for `path_to_eventlog` and make sure it is prepended with `s3a://`, not `s3://`. An example is `-Dspark.history.fs.logDirectory=s3a://path_to_eventlog`.

3. Follow instructions [here](https://docs.aws.amazon.com/glue/latest/dg/monitor-spark-ui-history.html#monitor-spark-ui-history-local) to launch Spark History Server using a Docker image.

4. After following the above steps, event logs should flow to the specified S3 bucket and the docker container should spin up Spark History Server (which will be available at `127.0.0.1:18080`). This instance of Spark History Server will pick up and parse event logs from the S3 bucket specified.