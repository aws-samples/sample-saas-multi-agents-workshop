# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import (APIGatewayRestResolver, CORSConfig)
from aws_lambda_powertools.logging import correlation_paths
import metrics_manager
from error_handling import handle_error, ValidationError, ResourceNotFoundError

import boto3
import json
import os
import time
import random
from botocore.client import Config


tracer = Tracer()
logger = Logger()
cors_config = CORSConfig(allow_origin="*", max_age=300)
app = APIGatewayRestResolver(cors=cors_config)

region_id = os.environ['AWS_REGION']

def create_short_trace_id():
    """Create a shorter trace ID (12-16 characters total)"""
    timestamp = hex(int(time.time()))[2:][-6:]  # Last 6 chars of timestamp
    random_part = hex(random.getrandbits(16))[2:].zfill(4)  # 4 random chars
    return f"{timestamp}-{random_part}"

def invoke_agentcore_runtime(session, query, tenant_id, event=None):
    """
    Invoke the AgentCore Runtime with boto3
    
    Args:
        session: The boto3 session
        query: The query to send to the agent
        tenant_id: The tenant ID to include in the parameters
        event: The original event for metrics recording
    """
    start_time = time.time()
    
    # Create agentcore client with config
    bedrock_config = Config(connect_timeout=120, read_timeout=120, retries={'max_attempts': 0})
    agentcore_client = session.client('bedrock-agentcore', config=bedrock_config)
    
    # Prepare payload with tenant ID
    payload = {
        "prompt": query,
        "stream": True,
        "tenant_id": tenant_id
    }
    
    # Get agent runtime ARN from environment variable
    agent_runtime_arn = os.environ.get('AGENT_RUNTIME_ARN')
    if not agent_runtime_arn:
        raise ResourceNotFoundError("Agent runtime ARN not configured")
    
    trace_id = create_short_trace_id()
    
    logger.info(f"Invoking agent runtime with trace ID: {trace_id}")
    
    # Invoke the agent runtime
    boto3_response = agentcore_client.invoke_agent_runtime(
        agentRuntimeArn=agent_runtime_arn,
        qualifier="DEFAULT",
        payload=json.dumps(payload),
        traceId=trace_id
    )
    
    logger.info(f"Content Type: {boto3_response.get('contentType', 'unknown')}")
    
    # Process the response
    if "text/event-stream" in boto3_response.get("contentType", ""):
        content = []
        for line in boto3_response["response"].iter_lines(chunk_size=1):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                    logger.info(line)
                    content.append(line)
        result = "\n".join(content)
    else:
        try:
            events = []
            for event in boto3_response.get("response", []):
                events.append(event)
        except Exception as e:
            events = [f"Error reading EventStream: {e}"]
        result = "".join([e.decode("utf-8") for e in events])

    # Handle double-encoded JSON from bedrock agent
    try:
        # First parse
        first_parse = json.loads(result)
        
        # If it's still a string, parse again (double-encoded)
        if isinstance(first_parse, str):
            parsed_result = json.loads(first_parse)
        else:
            parsed_result = first_parse
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return {
            'error': 'Failed to parse response from bedrock agent'
        }
    
    # Record metrics if event is provided
    if event is not None:
        end_time = time.time()
        duration_ms = int((end_time - start_time) * 1000)
        metrics_manager.record_metric(event, "AgentCoreInvocationDuration", "Milliseconds", duration_ms)
        metrics_manager.record_metric(event, "AgentCoreInvocation", "Count", 1)
      
    return parsed_result

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True)
@tracer.capture_lambda_handler
@handle_error
def lambda_handler(event, context):
    # Extract and validate required fields from the authorizer
    if 'requestContext' not in event or 'authorizer' not in event['requestContext']:
        raise ValidationError('Missing authorization context')
        
    authorizer = event['requestContext']['authorizer']
    required_fields = ['aws_access_key_id', 'aws_secret_access_key', 'aws_session_token',
                      'knowledge_base_id', 'tenant_name']
    
    for field in required_fields:
        if field not in authorizer:
            raise ValidationError(f'Missing required field: {field}')
    
    aws_access_key_id = authorizer['aws_access_key_id']
    aws_secret_access_key = authorizer['aws_secret_access_key']
    aws_session_token = authorizer['aws_session_token']
    knowledge_base_id = authorizer['knowledge_base_id']
    tenant_name = authorizer['tenant_name']
    tenant_id = authorizer.get('tenant_id', tenant_name)

    logger.info(f"input tenant name: {tenant_name} and its tenant_id: {tenant_id}")
    # TODO: Lab2 - uncomment below and hardcode a tenant id
    # tenant_id = "<hardcode tenant id>"
    # logger.info(f"hard coded tenant id: {c}")
    
    logger.info(f"Processing request for tenant: {tenant_name}, tenant_id: {tenant_id}")
    
    # Validate the request body
    if 'body' not in event:
        raise ValidationError('No query provided')
        
    # Extract the query from the event
    query = event['body']
    
    # Log the body content
    logger.debug("Received query:", query)
    
    session = boto3.Session(
        aws_access_key_id = aws_access_key_id,
        aws_secret_access_key = aws_secret_access_key,
        aws_session_token = aws_session_token
    )
    
    # Initialize the Bedrock config
    bedrock_config = Config(connect_timeout=120, read_timeout=120, retries={'max_attempts': 0})
    
    # Use agentcore runtime instead of retrieveAndGenerate
    logger.info(f"Invoking agentcore runtime with tenant_id: {tenant_id}")
    response = invoke_agentcore_runtime(session, query, tenant_id, event)
    
    logger.info(f"AgentCore runtime response for tenant {tenant_id}: {response}")
    
    # Return the results
    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }
    
    # The handle_error decorator will catch any exceptions and format the response