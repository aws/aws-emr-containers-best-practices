import boto3,json,sys

def list_s3_bucket_contents(bucket_name, prefix):
    s3 = boto3.client('s3', region_name='us-west-2')
    objects = []
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        if 'Contents' in response:
            print(f"Files in bucket '{bucket_name}':")
            for obj in response['Contents']:
                print(f"- {obj['Key']} (Size: {obj['Size']} bytes)")
                objects.append(obj['Key'])
        else:
            print(f"No objects found with prefix '{prefix}'")
    except Exception as e:
        print(f"Error accessing S3 bucket: {e}")
    return objects

def send_s3_references_to_sqs(bucket_name, object_keys, sqs_queue_url):
    sqs = boto3.client('sqs', region_name='us-west-2')
    for key in object_keys:
        try:
            print(f"Sending S3 reference: {key}")
            message_body = json.dumps({
                's3_bucket': bucket_name,
                's3_key': key,
                'message_type': 's3_reference'
            })
            response = sqs.send_message(
                QueueUrl=sqs_queue_url,
                MessageBody=message_body,
                MessageAttributes={
                    'Source': {'StringValue': 's3-reference-sender', 'DataType': 'String'},
                    'FileType': {'StringValue': 'parquet', 'DataType': 'String'}
                }
            )
            print(f"Message sent with ID: {response['MessageId']}")
        except Exception as e:
            print(f"ERROR processing {key}: {str(e)[:200]}...")
            continue

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python script.py <bucket_name> <prefix> <sqs_queue_url>")
        sys.exit(1)
        
    BUCKET_NAME = sys.argv[1]
    PREFIX_FILE_PATH = sys.argv[2]
    SQS_QUEUE_URL = sys.argv[3]
    
    s3_objects = list_s3_bucket_contents(BUCKET_NAME, PREFIX_FILE_PATH)
    print(f"Found {len(s3_objects)} objects to process")
    if s3_objects:
        send_s3_references_to_sqs(BUCKET_NAME, s3_objects, SQS_QUEUE_URL)
    else:
        print("No objects to process")