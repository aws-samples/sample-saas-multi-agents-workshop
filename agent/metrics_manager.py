# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
from datetime import datetime

logs_client = boto3.client('logs')
LOG_GROUP_NAME = "/smartresolve/log-group"
log_stream_tokens = {}

def record_metric(tenant_id, metric_name, metric_unit, metric_value, agent_name=None):
    """ Record the metric in CloudWatch Logs
    Args:
        tenant_id (str): The tenant identifier
        metric_name (str): Name of the metric
        metric_unit (str): Unit of measurement
        metric_value (int/float): Value to record
        agent_name (str): Name of the agent (optional)
    """
    log_event = {
        "timestamp": datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
        "agent_name": agent_name,
        "metric_name": metric_name,
        "metric_unit": metric_unit,
        "metric_value": metric_value,
        metric_name: [metric_value]  # For CloudWatch Insights queries
    }
    
    log_stream_name = f"metrics-{datetime.utcnow().strftime('%Y-%m-%d')}"
    
    try:
        put_args = {
            'logGroupName': LOG_GROUP_NAME,
            'logStreamName': log_stream_name,
            'logEvents': [{
                'timestamp': int(datetime.utcnow().timestamp() * 1000),
                'message': json.dumps(log_event)
            }]
        }
        
        if log_stream_name in log_stream_tokens:
            put_args['sequenceToken'] = log_stream_tokens[log_stream_name]
        
        response = logs_client.put_log_events(**put_args)
        log_stream_tokens[log_stream_name] = response.get('nextSequenceToken')
        
    except logs_client.exceptions.ResourceNotFoundException:
        try:
            logs_client.create_log_group(logGroupName=LOG_GROUP_NAME)
        except logs_client.exceptions.ResourceAlreadyExistsException:
            pass
        
        try:
            logs_client.create_log_stream(
                logGroupName=LOG_GROUP_NAME,
                logStreamName=log_stream_name
            )
        except logs_client.exceptions.ResourceAlreadyExistsException:
            pass
        
        response = logs_client.put_log_events(
            logGroupName=LOG_GROUP_NAME,
            logStreamName=log_stream_name,
            logEvents=[{
                'timestamp': int(datetime.utcnow().timestamp() * 1000),
                'message': json.dumps(log_event)
            }]
        )
        log_stream_tokens[log_stream_name] = response.get('nextSequenceToken')
        
    except logs_client.exceptions.InvalidSequenceTokenException as e:
        expected_token = e.response['Error']['Message'].split('sequenceToken: ')[-1]
        response = logs_client.put_log_events(
            logGroupName=LOG_GROUP_NAME,
            logStreamName=log_stream_name,
            sequenceToken=expected_token,
            logEvents=[{
                'timestamp': int(datetime.utcnow().timestamp() * 1000),
                'message': json.dumps(log_event)
            }]
        )
        log_stream_tokens[log_stream_name] = response.get('nextSequenceToken')
        
    except Exception as e:
        print(f"Error logging metric: {e}")
    
    # Still print for debugging
    print(json.dumps(log_event))