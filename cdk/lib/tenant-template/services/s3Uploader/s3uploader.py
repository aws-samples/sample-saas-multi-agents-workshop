# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
import os

from datetime import datetime
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import (APIGatewayRestResolver, CORSConfig)
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.event_handler.exceptions import (
    InternalServerError,
    NotFoundError,
)

s3_bucket = os.environ['S3_BUCKET_NAME']

tracer = Tracer()
logger = Logger()
cors_config = CORSConfig(allow_origin="*", max_age=300)
app = APIGatewayRestResolver(cors=cors_config)

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    logger.debug(event)
  
    # Retrieve tenantId from event
    tenantId = event['requestContext']['authorizer']['principalId']
    aws_access_key_id = event['requestContext']['authorizer']['aws_access_key_id']
    aws_secret_access_key = event['requestContext']['authorizer']['aws_secret_access_key']
    aws_session_token = event['requestContext']['authorizer']['aws_session_token']

    # Assume S3 prefix is set to tenant_id
    s3_prefix = tenantId
    
    # Extract the notes from the event
    if 'body' in event:
        notes = event['body']
        # Log the body content
        logger.debug("Received notes:", notes)
    else:
        notes = "No notes found"
    
    session = boto3.Session(
        aws_access_key_id = aws_access_key_id,
        aws_secret_access_key = aws_secret_access_key,
        aws_session_token = aws_session_token
    )
    
    # Initialize S3 client
    s3 = session.client('s3')
    
    # Generate a unique file name with current time to avoid duplication
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"meeting_notes_{current_time}.txt"
    
    # Upload the meeting notes to the S3 prefix
    s3_key = f"{s3_prefix}/{file_name}"
    
    try:
        s3.put_object(Bucket=s3_bucket, Key=s3_key, Body=notes)
        logger.info(f"Meeting notes uploaded to S3://{s3_prefix}/{file_name}")
        
        # Return a success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Received your notes',
            })
        }
        
    except s3.exceptions.NoSuchBucket as e:
        logger.error(f"Bucket not found: {e}")
        return {
            'statusCode': 404,
            'body': json.dumps({
                'message': 'Bucket not found'
            })
        }
    except s3.exceptions.ClientError as e:
        logger.error(f"Client error when uploading meeting notes to S3: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({
                'message': 'Client error when uploading to S3',
                'error': str(e)
            })
        }
    except Exception as e:
        logger.error(f"Error uploading meeting notes to S3: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Internal server error',
                'error': str(e)
            })
        }
        
