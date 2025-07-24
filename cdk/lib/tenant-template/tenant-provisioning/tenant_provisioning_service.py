# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json
import argparse
import time
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
import os
import logging
import uuid
import sys


# HOST=os.environ['OPENSEARCH_SERVERLESS_ENDPOINT']
REGION=os.environ['AWS_REGION']
S3_BUCKET=os.environ['S3_BUCKET']
TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN=os.environ['TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN']
OPENSEARCH_SERVERLESS_COLLECTION_ARN=os.environ['OPENSEARCH_SERVERLESS_COLLECTION_ARN']
TENANT_API_KEY=os.environ['TENANT_API_KEY']
EMBEDDING_MODEL_ARN = f'arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v1'
TENANT_KB_METADATA_FIELD = 'tenant-knowledge-base-metadata'
TENANT_KB_TEXT_FIELD = 'tenant-knowledge-base-text'
TENANT_KB_VECTOR_FIELD = 'tenant-knowledge-base-vector'

aoss_client = boto3.client('opensearchserverless')
s3 = boto3.client('s3')
bedrock_agent_client = boto3.client('bedrock-agent')
iam_client = boto3.client('iam')
eventbridge = boto3.client('events')
lambda_client = boto3.client('lambda')

def provision_tenant_resources(tenant_id):

    kb_collection = __get_opensearch_serverless_collection_details()
    kb_collection_name = kb_collection['name']
    kb_collection_endpoint = kb_collection['collectionEndpoint']
    kb_collection_endpoint_domain=kb_collection_endpoint.split("//")[-1]
    rule_name=f's3rule-{tenant_id}'

    try:
        # TODO: Lab1 - Add provision tenant resources
        
        __api_gw_add_api_key(tenant_id)
        return 0
    except Exception as e:
        logging.error('Error occured while provisioning tenant resources', e) 
        return 1

# Function adding api key to existing api gateway usage plan
def __api_gw_add_api_key(tenant_id):
    try:
        api_key_value = TENANT_API_KEY
        usage_plan_id = os.environ['API_GATEWAY_USAGE_PLAN_ID']
        apigw_client = boto3.client('apigateway')
        response = apigw_client.create_api_key(
            name=tenant_id,
            description='Tenant API Key',
            enabled=True,
            value=api_key_value
        )
        api_key = response['id']
        apigw_client.create_usage_plan_key(
            usagePlanId=usage_plan_id,
            keyId=api_key,
            keyType='API_KEY'
        )
        logging.info(f'API key {api_key} added to usage plan {usage_plan_id}')
        return 0
    except Exception as e:
        logging.error('Error occured while adding api key to api gateway usage plan', e)
        return 1
    
def __get_opensearch_serverless_collection_details():
    try:
        kb_collection_id = OPENSEARCH_SERVERLESS_COLLECTION_ARN.split('/')[-1]
        kb_collection = aoss_client.batch_get_collection(
            ids=[kb_collection_id]
        )
        
        logging.info(f'OpenSearch serverless collection details: {kb_collection}')
        return kb_collection['collectionDetails'][0]
    except Exception as e:
        logging.error('Error occured while getting OpenSearch serverless collection details', e)
        raise Exception('Error occured while getting OpenSearch serverless collection details') from e
    
def __create_tenant_knowledge_base(tenant_id, kb_collection_name, rule_name):
    try:
        tenant_kb_role_arn = __create_tenant_kb_role(tenant_id)

        storage_configuration = {
            'opensearchServerlessConfiguration': {
                'collectionArn': OPENSEARCH_SERVERLESS_COLLECTION_ARN, 
                'fieldMapping': {
                    'metadataField': TENANT_KB_METADATA_FIELD,
                    'textField': TENANT_KB_TEXT_FIELD,
                    'vectorField': TENANT_KB_VECTOR_FIELD
                },
                'vectorIndexName': tenant_id
            },
            'type': 'OPENSEARCH_SERVERLESS'
        }

        
        __add_data_access_policy(tenant_id, tenant_kb_role_arn, kb_collection_name)
        
        # Wait for the IAM role to be created
        logging.info(f'Waiting for IAM role "bedrock-kb-role-{tenant_id}" to be created...')
        time.sleep(10)

        # Retries to handle delay in indexes or Data Access Policies to be available. Indexes and Data Access Policy could take few seconds to be available to Bedrock KB.
        num_retries = 0
        max_retries = 10
        while num_retries < max_retries:
            try:
                response = bedrock_agent_client.create_knowledge_base(
                    name=tenant_id,
                    description=f'Knowledge base for tenant {tenant_id}',
                    roleArn=tenant_kb_role_arn,
                    knowledgeBaseConfiguration={
                        'type': 'VECTOR',
                        'vectorKnowledgeBaseConfiguration': {
                            'embeddingModelArn': EMBEDDING_MODEL_ARN
                        },
                    },
                    storageConfiguration=storage_configuration
                );
                logging.info(f'Tenant knowledge base created: {response}')
            except bedrock_agent_client.exceptions.ValidationException as e:
                error_message = e.response['Error']['Message']
                logging.error(f'{error_message}. Retrying in 5 seconds')
                time.sleep(5)
                num_retries += 1
            except bedrock_agent_client.exceptions.ConflictException:
                logging.info(f"Knowledge base '{tenant_id}' already exists, skipping creation.")
                break
            except Exception as e:
                logging.error('Error occurred while creating tenant knowledge base', e)
                raise Exception('Error occurred while creating tenant knowledge base') from e
        else:
            logging.error('Maximum number of retries reached, giving up.')
            raise Exception('Error occurred while creating tenant knowledge base: Maximum number of retries reached')
        knowledge_base_id = response['knowledgeBase']['knowledgeBaseId']
        logging.info(knowledge_base_id)
        datasource_id = __create_tenant_data_source(tenant_id, knowledge_base_id)
        __create_eventbridge_tenant_rule_target(tenant_id, knowledge_base_id, rule_name, datasource_id)

    except Exception as e:
        logging.error('Error occured while creating tenant knowledge base', e)
        raise Exception('Error occured while creating tenant knowledge base') from e

# Create Data Source in S3 per Tenant
def __create_tenant_data_source(tenant_id, knowledge_base_id):
    s3_bucket_arn=f'arn:aws:s3:::{S3_BUCKET}'
    response = bedrock_agent_client.create_data_source(
        name=tenant_id,
        description=f'Data source for tenant {tenant_id}',
        dataSourceConfiguration={
            's3Configuration':{
                'bucketArn':s3_bucket_arn,
                'inclusionPrefixes': [f'{tenant_id}/']
            },
            'type': 'S3'
        },
        knowledgeBaseId=knowledge_base_id
    )

    return response['dataSource']['dataSourceId']
    

def __create_tenant_kb_role(tenant_id):
    try:
        try:
            response = iam_client.create_role(
                RoleName=f'bedrock-kb-role-{tenant_id}',
                AssumeRolePolicyDocument=json.dumps(__get_kb_trust_policy()))
        except Exception as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                logging.info (f"IAM role 'bedrock-kb-role-{tenant_id}' already exists, skipping creation.")
                response = iam_client.get_role(
                    RoleName=f'bedrock-kb-role-{tenant_id}')
        
        iam_client.put_role_policy(
            RoleName=f'bedrock-kb-role-{tenant_id}',
            PolicyName=f'bedrock-kb-policy-{tenant_id}',
            PolicyDocument=json.dumps(__get_kb_policy(tenant_id))
        )
        logging.info(f"Tenant knowledge base role created: {response['Role']['Arn']}")
        return response['Role']['Arn']

    except Exception as e:
        logging.error('Error occured while creating tenant knowledge base role', e)
        raise Exception('Error occured while creating tenant knowledge base role') from e
    
# Function creating a Data Access Policy per tenant
def __add_data_access_policy(tenant_id, tenant_kb_role_arn, kb_collection_name):

    # Trimming tenant id to accomodate the polic name 32 characters limit
    # Shortening tenant id to 25 characters to fit the policy name
    trimmed_tenant_id = tenant_id[:25]

    try:

        response=aoss_client.create_access_policy(
            name=f'policy-{trimmed_tenant_id}',
            description=f'Data Access Policy for tenant {tenant_id}',
            policy=json.dumps(__generate_data_access_policy(tenant_id, tenant_kb_role_arn, kb_collection_name)),
            type='data')

        logging.info(f'Tenant data access policy created: {response}')
        
    except Exception as e: 
        logging.error('Error occured while adding data access policy', e)
        raise Exception('Error occured while adding data access policy') from e    

def __create_s3_tenant_prefix(tenant_id, rule_name):
    try:
        prefix = ''.join([tenant_id, '/'])
        s3.put_object(Bucket=S3_BUCKET, Key=prefix)
        rule_arn=__create_eventbridge_tenant_rule(prefix, tenant_id, rule_name)
        __create_trigger_lambda_eventbridge_permissions(rule_arn)
        logging.info(f'S3 tenant prefix created for tenant {tenant_id}')
        return rule_name
    
    except Exception as e:
        logging.error('Error occured while creating S3 tenant prefix', e)
        raise Exception('Error occured while creating S3 tenant prefix') from e     
    
def __create_eventbridge_tenant_rule(prefix, tenant_id, rule_name):
    try:
        event_pattern = {
            "detail": {
                "bucket": {
                    "name": [S3_BUCKET]
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

        rule = eventbridge.put_rule(
            Name=rule_name,
            EventPattern=json.dumps(event_pattern),
            State='ENABLED'
        )

        logging.info(f'Eventbridge Rule Created for tenant {tenant_id}')

        return rule['RuleArn']

    except Exception as e:
        logging.error('Error occured while creating eventbridge rule', e)
        raise Exception('Error occured while creating eventbridge rule', e) 

def __create_trigger_lambda_eventbridge_permissions(rule_arn):
    try:
        lambda_client.add_permission(
            FunctionName=TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN,
            StatementId=f'bedrock-pipeline-ingestion-{uuid.uuid4()}',
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_arn
        )
        logging.info(f'Trigger Lambda EventBridge permissions created')

    except Exception as e:
        logging.error('Error occured while creating trigger lambda eventbridge permissions', e)
        raise Exception('Error occured while creating trigger lambda eventbridge permissions', e)
    
def __create_eventbridge_tenant_rule_target(tenant_id, kb_id, rule_name, datasource_id):
    try:
        # input_template=f'{{"kb_id": "{kb_id}", "datasource_id": "{datasource_id}", "bucket": <bucket>, "key": <object-key>}}'
        input_template = {
            "kb_id": kb_id,
            "datasource_id": datasource_id,
            "bucket": "<bucket>",
            "key": "<object-key>"
        }
        input_transformer = {
            'InputPathsMap': {
                "object-key": "$.detail.object.key",
                "bucket": "$.detail.bucket.name"
            },
            "InputTemplate": json.dumps(input_template)
        }

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
        logging.info(f'Eventbridge rule target created for tenant {tenant_id}')

    except Exception as e:
        logging.error('Error occured while creating eventbridge rule', e)
        raise Exception('Error occured while creating eventbridge rule') from e 
        
def __create_opensearch_serverless_tenant_index(tenantId, kb_collection_endpoint):
    try:
        # Get AWS credentials
        credentials = boto3.Session().get_credentials()

        # Create the AWS Signature Version 4 signer for OpenSearch Serverless
        auth = AWSV4SignerAuth(credentials, REGION, 'aoss')

        # Create the OpenSearch client
        client = OpenSearch(
            hosts=[{'host': kb_collection_endpoint, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20
        )

        index_body = {
            "settings": {
                "index.knn": True,
                "number_of_shards": 1,
                "knn.algo_param.ef_search": 512,
                "number_of_replicas": 0,
            },
            "mappings": {
                "properties": {}
            }
        }

        index_body["mappings"]["properties"][TENANT_KB_VECTOR_FIELD] = {
            "type": "knn_vector",
            "dimension": 1536,
            "method": {
                "name": "hnsw",
                "engine": "faiss"
            },
        }

        index_body["mappings"]["properties"][TENANT_KB_TEXT_FIELD] = {
            "type": "text"
        }

        index_body["mappings"]["properties"][TENANT_KB_METADATA_FIELD] = {
            "type": "text"
        }

        # Create the index
        try:
            response = client.indices.create(index=tenantId, body=index_body)
            logging.info(f'Tenant open search serverless index created: {response}')
        except Exception as e:
            if 'resource_already_exists_exception' in str(e).lower():
                logging.info(f'Tenant open search serverless index {tenantId} already exists, skipping creation.')
            else:
                logging.error('Error occurred while creating opensearch serverless tenant index', e)
                raise Exception('Error occurred while creating opensearch serverless tenant index') from e
    except Exception as e:
        logging.error('Error occured while creating opensearch serverless tenant prefix', e)
        raise Exception('Error occured while creating opensearch serverless tenant prefix') from e   
    


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
            { #AOSS policy
                "Effect": "Allow",
                "Action": "aoss:APIAccessAll",
                "Resource": [OPENSEARCH_SERVERLESS_COLLECTION_ARN]
            },
            { # S3 policy
                "Sid": "AllowKBAccessDocuments",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject"
                ],
                "Resource": [f"arn:aws:s3:::{S3_BUCKET}/{tenant_id}/*"]
            },
            {
                "Sid": "AllowKBAccessBucket",
                "Effect": "Allow",
                "Action": [
                    "s3:ListBucket"
                ],
                "Resource": [
                    f"arn:aws:s3:::{S3_BUCKET}"
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

# Generating a Data Access Policy per tenant
def __generate_data_access_policy(tenant_id, tenant_kb_role_arn, kb_collection_name):
    return [
        {
            "Rules": [
            {
                "Resource": [
                f"index/{kb_collection_name}/{tenant_id}"
                ],
                "Permission": [
                    "aoss:CreateIndex",
                    "aoss:DeleteIndex",
                    "aoss:UpdateIndex",
                    "aoss:DescribeIndex",
                    "aoss:ReadDocument",
                    "aoss:WriteDocument"
                ],
                "ResourceType": "index"
            }
            ],
            "Principal": [tenant_kb_role_arn],
        }
    ]



if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Provisioning tenant resources')
    parser.add_argument('--tenantid', type=str, help='tenantid', required=True)
    args = parser.parse_args()
    # tenantId=args.tenantid.strip('"')

    # provision_tenant_resources(**vars(args))
    status = provision_tenant_resources(args.tenantid)
    sys.exit(status)
