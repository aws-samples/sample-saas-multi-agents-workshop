import json
import boto3
import time
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
    
    request_type = event['RequestType']
    bucket_name = event['ResourceProperties']['BucketName']
    index_name = event['ResourceProperties'].get('IndexName', 'default-index')
    dimension = int(event['ResourceProperties'].get('Dimension', '1024'))
    distance_metric = event['ResourceProperties'].get('DistanceMetric', 'cosine')
    data_type = event['ResourceProperties'].get('DataType', 'float32')
    
    physical_id = event.get('PhysicalResourceId', bucket_name)
    
    try:
        s3vectors_client = boto3.client('s3vectors')
        
        if request_type == 'Create' or request_type == 'Update':
            encryption_config = {
                'sseType': event['ResourceProperties']['SSEType']
            }
            
            if encryption_config['sseType'] != 'AES256':
                logger.warning(f"Invalid sseType: {encryption_config['sseType']}, defaulting to AES256")
                encryption_config['sseType'] = 'AES256'
            
            logger.info(f"Creating vector bucket: {bucket_name}")
            
            try:
                s3vectors_client.create_vector_bucket(
                    vectorBucketName=bucket_name,
                    encryptionConfiguration=encryption_config
                )
                logger.info(f"Created vector bucket: {bucket_name}")
                metrics.add_metric(name="VectorBucketCreated", unit=MetricUnit.Count, value=1)
            except Exception as e:
                error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', '')
                if error_code not in ['ConflictException', 'ResourceAlreadyExistsException']:
                    logger.error(f"Error creating bucket: {str(e)}")
                    raise
                logger.info(f"Bucket {bucket_name} already exists")
            
            time.sleep(2)
            
            try:
                logger.info(f"Creating vector index: {index_name}")
                s3vectors_client.create_index(
                    vectorBucketName=bucket_name,
                    indexName=index_name,
                    dimension=dimension,
                    distanceMetric=distance_metric,
                    dataType=data_type,
                    metadataConfiguration={"nonFilterableMetadataKeys": ["AMAZON_BEDROCK_METADATA", "AMAZON_BEDROCK_TEXT"]}
                )
                logger.info(f"Created vector index: {index_name}")
                metrics.add_metric(name="VectorIndexCreated", unit=MetricUnit.Count, value=1)
                
                # Wait for index to be available
                max_attempts = 10
                for attempt in range(max_attempts):
                    try:
                        index_info = s3vectors_client.get_index(
                            vectorBucketName=bucket_name,
                            indexName=index_name
                        )
                        logger.info(f"Index {index_name} is available")
                        break
                    except Exception as e:
                        if attempt < max_attempts - 1:
                            logger.info(f"Index not yet available, waiting... (attempt {attempt+1}/{max_attempts})")
                            time.sleep(5)
                        else:
                            logger.error(f"Error getting index details: {str(e)}")
            except Exception as e:
                error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', '')
                if error_code not in ['ConflictException', 'ResourceAlreadyExistsException']:
                    logger.error(f"Error creating index: {str(e)}")
                    raise
                logger.info(f"Index {index_name} already exists")
            
            return {
                'Status': 'SUCCESS',
                'PhysicalResourceId': physical_id,
                'Data': {
                    'BucketName': bucket_name,
                    'IndexName': index_name
                }
            }
            
        elif request_type == 'Delete':
            try:
                s3vectors_client.delete_index(
                    vectorBucketName=bucket_name,
                    indexName=index_name
                )
                logger.info(f"Deleted vector index: {index_name}")
                time.sleep(2)
            except Exception as e:
                logger.info(f"Error deleting index: {str(e)}")
                
            try:
                s3vectors_client.delete_vector_bucket(vectorBucketName=bucket_name)
                logger.info(f"Deleted vector bucket: {bucket_name}")
                metrics.add_metric(name="VectorBucketDeleted", unit=MetricUnit.Count, value=1)
            except Exception as e:
                logger.info(f"Error deleting bucket: {str(e)}")
            
            return {
                'Status': 'SUCCESS',
                'PhysicalResourceId': physical_id
            }
        
        return {
            'Status': 'SUCCESS',
            'PhysicalResourceId': physical_id
        }
    
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        metrics.add_metric(name="VectorBucketError", unit=MetricUnit.Count, value=1)
        return {
            'Status': 'FAILED',
            'PhysicalResourceId': physical_id,
            'Reason': str(e)
        }
