# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json
import argparse
import time
import os
import logging
import uuid
import sys
from aws_lambda_powertools import Logger
from error_handling import AppError, ValidationError

# Configure logging
logger = Logger()

# Environment variables
REGION = os.environ['AWS_REGION']
DATA_BUCKET = os.environ['DATA_BUCKET']
LOGS_BUCKET = os.environ['LOGS_BUCKET']
TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN = os.environ['TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN']
TENANT_API_KEY = os.environ['TENANT_API_KEY']
KNOWLEDGE_BASE_ID = os.environ.get('KNOWLEDGE_BASE_ID', '')
DATA_SOURCE_ID = os.environ.get('DATA_SOURCE_ID', '')

# Use the environment variable for the embedding model or fall back to a default
EMBEDDING_MODEL_ARN = os.environ.get(
    'EMBEDDING_MODEL_ARN',
    f'arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0'
)

# Field names for knowledge base
TENANT_KB_METADATA_FIELD = 'tenant-knowledge-base-metadata'
TENANT_KB_TEXT_FIELD = 'tenant-knowledge-base-text'
TENANT_KB_VECTOR_FIELD = 'tenant-knowledge-base-vector'

s3 = boto3.client('s3')
bedrock_agent_client = boto3.client('bedrock-agent')
iam_client = boto3.client('iam')
eventbridge = boto3.client('events')
lambda_client = boto3.client('lambda')

# Initialize AWS clients
s3 = boto3.client('s3')
bedrock_agent_client = boto3.client('bedrock-agent')
iam_client = boto3.client('iam')
eventbridge = boto3.client('events')
lambda_client = boto3.client('lambda')

class TenantProvisioningError(AppError):
    """Error raised when tenant provisioning fails"""
    def __init__(self, message: str, error_code: str = "TENANT_PROVISIONING_ERROR"):
        super().__init__(message, error_code, 500)

def provision_tenant_resources(tenant_id):
    """
    Provision all resources needed for a new tenant
    
    Args:
        tenant_id: The ID of the tenant to provision
        
    Returns:
        0 on success, 1 on failure
    """
    if not tenant_id:
        logger.error("Tenant ID cannot be empty")
        return 1
        
    rule_name = f's3rule-{tenant_id}'

    try:
        # Create S3 tenant prefix and EventBridge rule
        __create_s3_tenant_prefix(tenant_id, rule_name)
        
        # Add API key for tenant
        __api_gw_add_api_key(tenant_id)
        
        logger.info(f"Successfully provisioned resources for tenant: {tenant_id}")
        return 0
    except Exception as e:
        logger.exception(f"Error occurred while provisioning tenant resources: {str(e)}")
        return 1

def __api_gw_add_api_key(tenant_id):
    """
    Add an API key for the tenant to the existing API Gateway usage plan
    
    Args:
        tenant_id: The ID of the tenant
        
    Raises:
        TenantProvisioningError: If the API key creation fails
    """
    try:
        api_key_value = TENANT_API_KEY
        usage_plan_id = os.environ['API_GATEWAY_USAGE_PLAN_ID']
        apigw_client = boto3.client('apigateway')
        
        # Create the API key
        response = apigw_client.create_api_key(
            name=tenant_id,
            description=f'API Key for tenant {tenant_id}',
            enabled=True,
            value=api_key_value
        )
        api_key = response['id']
        
        # Add the API key to the usage plan
        apigw_client.create_usage_plan_key(
            usagePlanId=usage_plan_id,
            keyId=api_key,
            keyType='API_KEY'
        )
        
        logger.info(f'API key {api_key} added to usage plan {usage_plan_id} for tenant {tenant_id}')
    except Exception as e:
        logger.exception(f"Error occurred while adding API key for tenant {tenant_id}")
        raise TenantProvisioningError(f"Failed to create API key for tenant {tenant_id}: {str(e)}")
    
# Note: We're removing the __create_tenant_knowledge_base function since we're using a pooled knowledge base
# The data will be automatically ingested through the S3 event notifications set up in the CDK stack

def __create_tenant_kb_role(tenant_id):
    """
    Create an IAM role for the tenant's knowledge base
    
    Args:
        tenant_id: The ID of the tenant
        
    Returns:
        The ARN of the created role
        
    Raises:
        TenantProvisioningError: If the role creation fails
    """
    try:
        role_name = f'bedrock-kb-role-{tenant_id}'
        
        # Try to create the role, handle case where it already exists
        try:
            response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(__get_kb_trust_policy())
            )
            logger.info(f"Created new IAM role: {role_name}")
        except iam_client.exceptions.EntityAlreadyExistsException:
            logger.info(f"IAM role '{role_name}' already exists, retrieving existing role")
            response = iam_client.get_role(RoleName=role_name)
        
        # Attach or update the policy
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=f'bedrock-kb-policy-{tenant_id}',
            PolicyDocument=json.dumps(__get_kb_policy(tenant_id))
        )
        
        role_arn = response['Role']['Arn']
        logger.info(f"Tenant knowledge base role configured: {role_arn}")
        return role_arn

    except Exception as e:
        logger.exception(f"Error occurred while creating knowledge base role for tenant {tenant_id}")
        raise TenantProvisioningError(f"Failed to create knowledge base role for tenant {tenant_id}: {str(e)}")
    
def __create_s3_tenant_prefix(tenant_id, rule_name):
    """
    Create S3 prefixes for the tenant and set up EventBridge rules
    
    Args:
        tenant_id: The ID of the tenant
        rule_name: The name of the EventBridge rule to create
        
    Returns:
        The name of the created EventBridge rule
        
    Raises:
        TenantProvisioningError: If the prefix creation fails
    """
    try:
        # Create data prefix
        data_prefix = f'{tenant_id}/'
        s3.put_object(Bucket=DATA_BUCKET, Key=data_prefix)
        logger.info(f'S3 data prefix created for tenant {tenant_id} in bucket {DATA_BUCKET}')
        
        # Create logs prefix
        logs_prefix = f'{tenant_id}/'
        s3.put_object(Bucket=LOGS_BUCKET, Key=logs_prefix)
        logger.info(f'S3 logs prefix created for tenant {tenant_id} in bucket {LOGS_BUCKET}')
        
        # Create EventBridge rule for the tenant prefix
        rule_arn = __create_eventbridge_tenant_rule(data_prefix, tenant_id, rule_name)
        __create_trigger_lambda_eventbridge_permissions(rule_arn)
        
        # Add target to the EventBridge rule
        # Use the actual knowledge base ID and data source ID from environment variables
        # If they're not available, fall back to using tenant_id as a placeholder
        kb_id = KNOWLEDGE_BASE_ID
        datasource_id = DATA_SOURCE_ID
        
        __create_eventbridge_tenant_rule_target(tenant_id, kb_id, rule_name, datasource_id)
        logger.info(f'EventBridge rule target added for tenant {tenant_id} with KB ID {kb_id} and datasource ID {datasource_id}')
        
        return rule_name
    
    except Exception as e:
        logger.exception(f"Error occurred while creating S3 prefixes for tenant {tenant_id}")
        raise TenantProvisioningError(f"Failed to create S3 prefixes for tenant {tenant_id}: {str(e)}")
    
def __create_eventbridge_tenant_rule(prefix, tenant_id, rule_name):
    """
    Create an EventBridge rule for the tenant's S3 prefix
    
    Args:
        prefix: The S3 prefix to monitor
        tenant_id: The ID of the tenant
        rule_name: The name of the EventBridge rule
        
    Returns:
        The ARN of the created rule
        
    Raises:
        TenantProvisioningError: If the rule creation fails
    """
    try:
        # Define the event pattern to match S3 object creation events
        event_pattern = {
            "detail": {
                "bucket": {
                    "name": [DATA_BUCKET]
                },
                "object": {
                    "key": [{
                        "prefix": prefix
                    }]
                }
            },
            "detail-type": ["Object Created"],
            "source": ["aws.s3"]
        }

        # Create the rule
        rule = eventbridge.put_rule(
            Name=rule_name,
            Description=f"S3 object creation rule for tenant {tenant_id}",
            EventPattern=json.dumps(event_pattern),
            State='ENABLED'
        )

        logger.info(f'EventBridge rule created for tenant {tenant_id}: {rule_name}')
        return rule['RuleArn']

    except Exception as e:
        logger.exception(f"Error occurred while creating EventBridge rule for tenant {tenant_id}")
        raise TenantProvisioningError(f"Failed to create EventBridge rule for tenant {tenant_id}: {str(e)}")

def __create_trigger_lambda_eventbridge_permissions(rule_arn):
    """
    Add permissions for EventBridge to invoke the ingestion Lambda
    
    Args:
        rule_arn: The ARN of the EventBridge rule
        
    Raises:
        TenantProvisioningError: If the permission creation fails
    """
    try:
        # Generate a unique statement ID
        statement_id = f'bedrock-pipeline-ingestion-{uuid.uuid4()}'
        
        # Add the permission
        lambda_client.add_permission(
            FunctionName=TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN,
            StatementId=statement_id,
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_arn
        )
        
        logger.info(f'Added EventBridge permission to invoke Lambda: {statement_id}')

    except Exception as e:
        # Handle case where permission already exists
        if 'ResourceConflictException' in str(e) and 'already exists' in str(e):
            logger.info('Lambda permission already exists, continuing')
        else:
            logger.exception("Error occurred while creating Lambda permission for EventBridge")
            raise TenantProvisioningError(f"Failed to create Lambda permission: {str(e)}")
    
def __create_eventbridge_tenant_rule_target(tenant_id, kb_id, rule_name, datasource_id):
    """
    Create an EventBridge rule target for the tenant's rule
    
    Args:
        tenant_id: The ID of the tenant
        kb_id: The ID of the knowledge base
        rule_name: The name of the EventBridge rule
        datasource_id: The ID of the data source
        
    Raises:
        TenantProvisioningError: If the target creation fails
    """
    try:
        # Define the input template for the Lambda function
        input_template = {
            "kb_id": kb_id,
            "datasource_id": datasource_id,
            "bucket": "<bucket>",
            "key": "<object-key>"
        }
        
        # Create the input transformer
        input_transformer = {
            'InputPathsMap': {
                "object-key": "$.detail.object.key",
                "bucket": "$.detail.bucket.name"
            },
            "InputTemplate": json.dumps(input_template)
        }

        # Add the target to the rule
        eventbridge.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    'Id': tenant_id,
                    'Arn': TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN,
                    'InputTransformer': input_transformer,
                    'RetryPolicy': {
                        'MaximumRetryAttempts': 2,
                        'MaximumEventAgeInSeconds': 3600
                    }
                }
            ]
        )
        
        logger.info(f'EventBridge rule target created for tenant {tenant_id}')

    except Exception as e:
        logger.exception(f"Error occurred while creating EventBridge rule target for tenant {tenant_id}")
        raise TenantProvisioningError(f"Failed to create EventBridge rule target for tenant {tenant_id}: {str(e)}")
        
def __get_kb_trust_policy():
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service": "bedrock.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }]
    }

def __get_kb_policy(tenant_id):
    return {
        "Version": "2012-10-17",
        "Statement": [
            { #FM model policy
                "Sid": "AmazonBedrockAgentBedrockFoundationModelPolicy",
                "Effect": "Allow",
                "Action": "bedrock:InvokeModel",
                "Resource": [
                    EMBEDDING_MODEL_ARN
                ]
            },
            { # S3 policy
                "Sid": "AllowKBAccessDocuments",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject"
                ],
                "Resource": [f"arn:aws:s3:::{DATA_BUCKET}/{tenant_id}/*"]
            },
            {
                "Sid": "AllowKBAccessBucket",
                "Effect": "Allow",
                "Action": [
                    "s3:ListBucket"
                ],
                "Resource": [
                    f"arn:aws:s3:::{DATA_BUCKET}"
                ],
                "Condition": {
                    "StringLike": {
                        "s3:prefix": [
                            f"{tenant_id}/*"
                        ]
                    }
                }
            }            
        ]
    }

if __name__ == '__main__':
    # Configure logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Provision tenant resources for SaaS application'
    )
    parser.add_argument('--tenantid', type=str, help='Tenant ID to provision', required=True)
    args = parser.parse_args()
    
    # Run the provisioning process
    status = provision_tenant_resources(args.tenantid)
    sys.exit(status)
