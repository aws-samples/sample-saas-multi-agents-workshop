import json
import boto3
import time
import datetime
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

logger = Logger()
tracer = Tracer()
metrics = Metrics()

@tracer.capture_lambda_handler
@logger.inject_lambda_context
@metrics.log_metrics
def handler(event, context):
    logger.info("Received event", extra={"event": event})
    
    request_type = event.get('RequestType', '')
    physical_id = event.get('PhysicalResourceId', 'bedrock-kb-default')
    
    properties = event.get('ResourceProperties', {})
    kb_name = properties.get('KnowledgeName', '')
    kb_description = properties.get('Description', '')
    role_arn = properties.get('RoleArn', '')
    embedding_model_arn = properties.get('EmbeddingModelArn', '')
    index_arn = properties.get('IndexArn', '')
    
    try:
        bedrock_agent = boto3.client('bedrock-agent')
        s3vectors = boto3.client('s3vectors')
        
        if request_type == 'Create':
            logger.info(f"Creating Bedrock Knowledge Base: {kb_name}")
            response = create_knowledge_base(bedrock_agent, s3vectors, kb_name, kb_description, role_arn, embedding_model_arn, index_arn)
            kb_id = response['knowledgeBase']['knowledgeBaseId']
            
            logger.info(f"Knowledge Base ID: {kb_id}")
            wait_for_kb_creation(bedrock_agent, kb_id)
            
            data = {
                'KnowledgeBaseId': kb_id,
                'KnowledgeBaseArn': response['knowledgeBase']['knowledgeBaseArn']
            }
            
            metrics.add_metric(name="KnowledgeBaseCreated", unit=MetricUnit.Count, value=1)
            
            return {
                'Status': 'SUCCESS',
                'PhysicalResourceId': kb_id,
                'Data': data
            }
            
        elif request_type == 'Update':
            logger.info(f"Updating Bedrock Knowledge Base: {physical_id}")
            return {
                'Status': 'SUCCESS',
                'PhysicalResourceId': physical_id
            }
            
        elif request_type == 'Delete':
            # Use PhysicalResourceId as the Knowledge Base ID for deletion
            kb_id_to_delete = physical_id
            
            if kb_id_to_delete and kb_id_to_delete != 'bedrock-kb-default':
                logger.info(f"Deleting Bedrock Knowledge Base: {kb_id_to_delete}")
                delete_knowledge_base(bedrock_agent, kb_id_to_delete)
                metrics.add_metric(name="KnowledgeBaseDeleted", unit=MetricUnit.Count, value=1)
            else:
                logger.info("No valid Knowledge Base ID found to delete")
                
            return {
                'Status': 'SUCCESS',
                'PhysicalResourceId': physical_id
            }
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        metrics.add_metric(name="KnowledgeBaseError", unit=MetricUnit.Count, value=1)
        return {
            'Status': 'FAILED',
            'PhysicalResourceId': physical_id,
            'Reason': str(e)
        }

def verify_s3_vector_index(s3vectors_client, index_arn):
    try:
        parts = index_arn.split('/')
        if len(parts) < 4:
            logger.error(f"Invalid index ARN format: {index_arn}")
            return False
            
        bucket_name = parts[-3]
        index_name = parts[-1]
        
        logger.info(f"Verifying S3 vector index: {index_name} in bucket: {bucket_name}")
        
        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                response = s3vectors_client.get_index(
                    vectorBucketName=bucket_name,
                    indexName=index_name
                )
                
                sanitized_response = sanitize_for_json(response)
                logger.info(f"Index details: {json.dumps(sanitized_response)}")
                
                dimension = response.get('dimension')
                if dimension != 1024:
                    logger.warning(f"Index dimension is {dimension}, but Titan embedding model uses 1024 dimensions")
                
                logger.info(f"Successfully verified index {index_name} in bucket {bucket_name}")
                return True
            except Exception as e:
                if 'AccessDeniedException' in str(e):
                    logger.warning(f"Access denied when verifying index: {str(e)}")
                    return True
                elif 'ResourceNotFoundException' in str(e) and attempt < max_attempts - 1:
                    logger.info(f"Index not found yet, waiting... (attempt {attempt+1}/{max_attempts})")
                    time.sleep(5)
                else:
                    if attempt == max_attempts - 1:
                        logger.error(f"Error getting index details: {str(e)}")
                        return False
                    else:
                        logger.info(f"Retrying index verification... (attempt {attempt+1}/{max_attempts})")
                        time.sleep(5)
        
        logger.error(f"Failed to verify index after {max_attempts} attempts")
        return False
    except Exception as e:
        logger.error(f"Error verifying S3 vector index: {str(e)}")
        return False

def create_knowledge_base(bedrock_agent, s3vectors_client, name, description, role_arn, embedding_model_arn, index_arn):
    logger.info(f"Creating knowledge base with S3 Vectors configuration using index ARN: {index_arn}")
    
    try:
        verify_s3_vector_index(s3vectors_client, index_arn)
    except Exception as e:
        logger.warning(f"Index verification failed but continuing: {str(e)}")
    
    try:
        try:
            existing_kb = find_knowledge_base_by_name(bedrock_agent, name)
            if existing_kb:
                logger.info(f"Knowledge base with name '{name}' already exists")
                kb_id = existing_kb['knowledgeBaseId']
                return {
                    'Status': 'SUCCESS',
                    'PhysicalResourceId': kb_id,
                    'Data': {
                        'KnowledgeBaseId': kb_id,
                        'KnowledgeBaseArn': existing_kb['knowledgeBaseArn']
                    }
                }
        except Exception as find_error:
            logger.warning(f"Error checking for existing knowledge base: {str(find_error)}")
        
        kb_params = {
            'name': name,
            'description': description,
            'roleArn': role_arn,
            'knowledgeBaseConfiguration': {
                'type': 'VECTOR',
                'vectorKnowledgeBaseConfiguration': {
                    'embeddingModelArn': embedding_model_arn,
                    "embeddingModelConfiguration": {
                        "bedrockEmbeddingModelConfiguration": {
                            "dimensions": 1024,
                            "embeddingDataType": "FLOAT32"
                        }
                    }
                }
            },
            'storageConfiguration': {
                'type': 'S3_VECTORS',
                's3VectorsConfiguration': {
                    'indexArn': index_arn
                }
            }
        }
        
        response = bedrock_agent.create_knowledge_base(**kb_params)
        logger.info(f"Successfully created knowledge base: {response}")
        return response
    except Exception as e:
        if 'ConflictException' in str(e) and 'already exists' in str(e):
            try:
                existing_kb = find_knowledge_base_by_name(bedrock_agent, name)
                if existing_kb:
                    logger.info(f"Found existing knowledge base with name '{name}'")
                    kb_id = existing_kb['knowledgeBaseId']
                    return {
                        'Status': 'SUCCESS',
                        'PhysicalResourceId': kb_id,
                        'Data': {
                            'KnowledgeBaseId': kb_id,
                            'KnowledgeBaseArn': existing_kb['knowledgeBaseArn']
                        }
                    }
            except Exception as find_error:
                logger.error(f"Error finding existing knowledge base: {str(find_error)}")
        
        logger.error(f"Error creating knowledge base: {str(e)}")
        if hasattr(e, 'response') and 'Error' in e.response:
            logger.error(f"Error details: {e.response['Error']}")
        raise e

def delete_knowledge_base(bedrock_agent, kb_id):
    try:
        bedrock_agent.delete_knowledge_base(knowledgeBaseId=kb_id)
    except Exception as e:
        logger.info(f"Error deleting Knowledge Base {kb_id}: {str(e)}")

def wait_for_kb_creation(bedrock_agent, kb_id, max_attempts=30, delay=10):
    for attempt in range(max_attempts):
        try:
            response = bedrock_agent.get_knowledge_base(knowledgeBaseId=kb_id)
            status = response['knowledgeBase']['status']
            
            if status == 'ACTIVE':
                logger.info(f"Knowledge Base {kb_id} is now available")
                return True
            elif status in ['FAILED', 'DELETING', 'DELETED']:
                logger.error(f"Knowledge Base creation failed with status: {status}")
                return False
                
            logger.info(f"Knowledge Base status: {status}, waiting... (attempt {attempt+1}/{max_attempts})")
            time.sleep(delay)
            
        except Exception as e:
            logger.error(f"Error checking knowledge base status: {str(e)}")
            time.sleep(delay)
    
    logger.error(f"Timed out waiting for Knowledge Base {kb_id}")
    return False

def find_knowledge_base_by_name(bedrock_agent, name):
    try:
        paginator = bedrock_agent.get_paginator('list_knowledge_bases')
        for page in paginator.paginate():
            for kb in page.get('knowledgeBaseItems', []):
                if kb.get('name') == name:
                    kb_details = bedrock_agent.get_knowledge_base(
                        knowledgeBaseId=kb['knowledgeBaseId']
                    )['knowledgeBase']
                    return kb_details
        return None
    except Exception as e:
        logger.error(f"Error listing knowledge bases: {str(e)}")
        raise e

def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    else:
        return obj
