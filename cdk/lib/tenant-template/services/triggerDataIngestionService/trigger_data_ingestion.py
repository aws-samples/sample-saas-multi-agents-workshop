# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
import os

from datetime import datetime
from assume_role_layer import assume_role
from aws_lambda_powertools import Logger, Tracer

from aws_lambda_powertools.event_handler import (APIGatewayRestResolver,
                                                CORSConfig)
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.event_handler.exceptions import (
    InternalServerError,
    NotFoundError,
)

tracer = Tracer()
logger = Logger()
cors_config = CORSConfig(allow_origin="*", max_age=300)
app = APIGatewayRestResolver(cors=cors_config)
assume_role_arn = os.environ['ASSUME_ROLE_ARN']

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True)
@tracer.capture_lambda_handler

def lambda_handler(event, context):
    try:
        # Log the entire event object for debugging purposes
        logger.debug(f"Received event: {event}")

        # Extract kb_id,bucket, and key from the event
        
        knowledge_base_id = event['kb_id']
        datasource_id = event['datasource_id']
        bucket = event['bucket']
        key = event['key']
        tenant_id = key.split('/')[0]
        
        # ABAC: create a temporary session using the assume role arn which gives S3 Access to the tenant-specific prefix
        
        logger.info(tenant_id)
        
        request_tags = [("KnowledgeBaseId", knowledge_base_id)]
        session_parameters = assume_role(access_role_arn=assume_role_arn, request_tags = request_tags, duration_sec = 900)

        session = boto3.Session(
            aws_access_key_id=session_parameters.aws_access_key_id,
            aws_secret_access_key=session_parameters.aws_secret_access_key,
            aws_session_token=session_parameters.aws_session_token
        )
        
        client = session.client('bedrock-agent')

        response = client.start_ingestion_job(
            dataSourceId=datasource_id,
            description='data source updated',
            knowledgeBaseId=knowledge_base_id
        )
        logger.info(response)
        
        
    except KeyError as e:
        # Log the error and return a meaningful response
        logger.error(f"KeyError: {e}. Event: {event}")
        return {
            'statusCode': 400,
            'body': json.dumps('Bad Request: Missing required key')
        }
    except Exception as e:
        # Log any other exceptions and return a meaningful response
        logger.error(f"Unhandled exception: {e}. Event: {event}")
        return {
            'statusCode': 500,
            'body': json.dumps('Internal Server Error')
        }

    # Rest of your code
    return {
        'statusCode': 200,
        'body': json.dumps('Success')
    }