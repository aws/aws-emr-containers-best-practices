from pyspark.sql import SparkSession
from pyspark.sql.functions import to_json, struct
import boto3,sys
from botocore.exceptions import ClientError

def main():
    print("=== Starting Spark Session ===")
    S3_FILE=sys.argv[1]
    SQS_URL=sys.argv[2]

    spark = SparkSession.builder.appName("irsa-poc").getOrCreate()

    # 1. Read data from S3
    try:
        df = spark.read.parquet(S3_FILE)
    except Exception as e:
        print(f"Error reading S3 data: {e}")
        spark.stop()
        return

    # 2. Convert each row to JSON string
    print("Converting rows to JSON...")
    json_df = df.select(to_json(struct("*")).alias("value"))    

    print("=== Sample JSON Output ===")
    json_df.show(5, truncate=False)

    # 3. Send to SQS
    def send_partition(partition):
        print(f"\nInitializing SQS client for partition...")
        try:
            sqs = boto3.client('sqs', region_name='us-east-1')        
            
            results = []
            results.append(f"Caller Identity: {boto3.client('sts').get_caller_identity()}")
            for i, row in enumerate(partition, 1): 
                try:
                    response=sqs.send_message(
                        QueueUrl=SQS_URL,
                        MessageBody=row.value
                    )
                    results.append(f"Sent message {i} - MessageId: {response['MessageId']}")
                
                except ClientError as e:
                    results.append(f"Failed: {e} | Message: {row.value}")
            return results
        except Exception as e:
            return [f"Partition failed: {str(e)}"]

    print("\n=== Starting boto3 connection ===")
    results = json_df.rdd.mapPartitions(send_partition).collect()
    for msg in results:
        print(msg)
    print("\n=== Job Completed ===")


if __name__ == "__main__":
    print("Script started")
    main()
    print("Script finished")