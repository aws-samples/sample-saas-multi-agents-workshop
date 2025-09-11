import json
import os
import boto3
import uuid
from aws_lambda_powertools import Logger

logger = Logger()
s3_client = boto3.client('s3')
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']

@logger.inject_lambda_context
def lambda_handler(event, context):
    logger.info("Received event: " + json.dumps(event))
    
    try:
        # Extract tenant ID from requestContext
        tenant_id = event['requestContext']['authorizer']['tenantId']
        
        # Parse the request body
        body = json.loads(event['body'])
        file_content = body.get('fileContent')
        
        if not file_content:
            return {
                'statusCode': 400,
                'body': json.dumps({'message': 'Missing fileContent in request body'})
            }
        
        # Generate a unique file name
        file_name = f"{uuid.uuid4()}.log"
        
        # Define the S3 key (path) - organize logs by tenant
        s3_key = f"{tenant_id}/logs/{file_name}"
        
        # Upload the file to S3
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=file_content
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Log file uploaded successfully',
                'bucket': S3_BUCKET_NAME,
                'key': s3_key
            })
        }
        
    except Exception as e:
        logger.error(f"Error uploading log file: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'message': f'Error uploading log file: {str(e)}'})
        }