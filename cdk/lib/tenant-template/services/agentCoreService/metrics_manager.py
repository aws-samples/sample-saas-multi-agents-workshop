# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import boto3
from aws_lambda_powertools import Logger

logger = Logger()

def record_metric(event, metric_name, unit, value):
    """
    Record a custom metric to CloudWatch Metrics
    
    Args:
        event: The Lambda event that triggered the function
        metric_name: The name of the metric to record
        unit: The unit of the metric (Count, Milliseconds, etc.)
        value: The value of the metric
    """
    try:
        # Extract tenant information from the event if available
        tenant_id = None
        tenant_name = None
        
        if event and 'requestContext' in event and 'authorizer' in event['requestContext']:
            authorizer = event['requestContext']['authorizer']
            tenant_id = authorizer.get('tenant_id')
            tenant_name = authorizer.get('tenant_name')
        
        # Create dimensions for the metric
        dimensions = [
            {
                'Name': 'Service',
                'Value': 'AgentCoreService'
            }
        ]
        
        # Add tenant dimensions if available
        if tenant_id:
            dimensions.append({
                'Name': 'TenantId',
                'Value': tenant_id
            })
        
        if tenant_name:
            dimensions.append({
                'Name': 'TenantName',
                'Value': tenant_name
            })
        
        # Get the CloudWatch client
        cloudwatch = boto3.client('cloudwatch')
        
        # Put the metric data
        cloudwatch.put_metric_data(
            Namespace='SaaS/AgentCore',
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Dimensions': dimensions,
                    'Unit': unit,
                    'Value': value
                }
            ]
        )
        
        logger.debug(f"Recorded metric {metric_name}: {value} {unit}")
    except Exception as e:
        # Log the error but don't fail the main function
        logger.error(f"Failed to record metric {metric_name}: {str(e)}")