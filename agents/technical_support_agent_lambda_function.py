#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import boto3
import uuid
from boto3.dynamodb.conditions import Key
import os
import datetime
import re
from botocore.exceptions import ClientError

def get_named_parameter(event, name):
    return next(item for item in event['parameters'] if item['name'] == name)['value']

def get_named_property(event, name):
    return next(
        item for item in
        event['requestBody']['content']['application/json']['properties']
        if item['name'] == name)['value']

def search_knowledge_base(event, query, category, tenantId):
    """Search the knowledge base for relevant information"""
    print(f'search_knowledge_base invoked with query: {query}, category: {category}, tenantId: {tenantId}')
    
    # Initialize S3 client with tenant credentials
    s3 = boto3.client('s3',
                aws_access_key_id=event['sessionAttributes'].get('accessKeyId'),
                aws_secret_access_key=event['sessionAttributes'].get('secretAccessKey'),
                aws_session_token=event['sessionAttributes'].get('sessionToken')
                )
    
    # Get the S3 bucket name from environment variable or use a default
    bucket_name = os.environ.get('DATA_BUCKET', 'DataBucket')
    
    # List objects in the tenant's prefix
    try:
        # Define the prefix based on category if provided
        prefix = f"{tenantId}/"
        if category:
            if category.lower() == 'sop':
                prefix += "sops/"
            elif category.lower() == 'resolution':
                prefix += "resolutions/"
            elif category.lower() == 'kb':
                prefix += "kb/"
        
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        
        results = []
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                
                # Skip if it's a directory or not a markdown file
                if key.endswith('/') or not (key.endswith('.md') or key.endswith('.txt')):
                    continue
                
                # Get the object
                obj_response = s3.get_object(Bucket=bucket_name, Key=key)
                content = obj_response['Body'].read().decode('utf-8')
                
                # Simple search - check if query is in content
                if query.lower() in content.lower():
                    # Determine category from path
                    if '/kb/' in key:
                        doc_category = 'KB'
                    elif '/sops/' in key:
                        doc_category = 'SOP'
                    elif '/resolutions/' in key:
                        doc_category = 'Resolution'
                    else:
                        doc_category = 'Other'
                    
                    # Extract title from content or filename
                    title = os.path.basename(key).replace('-', ' ').replace('.md', '').replace('.txt', '')
                    title_match = re.search(r'# (.*?)(\n|$)', content)
                    if title_match:
                        title = title_match.group(1)
                    
                    # Get last updated from metadata or file properties
                    last_updated = obj['LastModified'].strftime("%Y-%m-%d")
                    
                    results.append({
                        'title': title,
                        'content': content,
                        'category': doc_category,
                        'lastUpdated': last_updated
                    })
        
        return {
            "response": results
        }
    
    except Exception as e:
        print(f"Error searching knowledge base: {str(e)}")
        return {
            "response": [],
            "error": str(e)
        }

def get_error_code(event, errorCode, tenantId):
    """Get details about a specific error code"""
    print(f'get_error_code invoked with errorCode: {errorCode}, tenantId: {tenantId}')
    
    # Initialize S3 client with tenant credentials
    s3 = boto3.client('s3',
                aws_access_key_id=event['sessionAttributes'].get('accessKeyId'),
                aws_secret_access_key=event['sessionAttributes'].get('secretAccessKey'),
                aws_session_token=event['sessionAttributes'].get('sessionToken')
                )
    
    # Get the S3 bucket name from environment variable or use a default
    bucket_name = os.environ.get('DATA_BUCKET', 'DataBucket')
    
    try:
        # Check for tenant-specific error codes document
        key = f"{tenantId}/ClearPay_Error_Codes.txt" if "clearpay" in tenantId.lower() else f"{tenantId}/MediOps_Error_Codes.txt"
        
        try:
            obj_response = s3.get_object(Bucket=bucket_name, Key=key)
            content = obj_response['Body'].read().decode('utf-8')
            
            # Parse the content to find the error code
            error_section_pattern = re.compile(f"### {errorCode}[^\n]*\n(.*?)(?=###|\Z)", re.DOTALL)
            match = error_section_pattern.search(content)
            
            if match:
                error_section = match.group(1).strip()
                
                # Extract details
                name_match = re.search(r"### [^\n]*: ([^\n]*)", error_section) or re.search(r"### ([^\n]*)", error_section)
                name = name_match.group(1) if name_match else ""
                
                description_match = re.search(r"\*\*Description\*\*: ([^\n]*)", error_section)
                description = description_match.group(1) if description_match else ""
                
                resolution_match = re.search(r"\*\*Resolution\*\*: ([^\n]*)", error_section)
                resolution = resolution_match.group(1) if resolution_match else ""
                
                return {
                    "response": {
                        "code": errorCode,
                        "name": name,
                        "description": description,
                        "resolution": resolution
                    }
                }
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchKey':
                raise
        
        # If not found or error, return a generic response
        return {
            "response": {
                "code": errorCode,
                "name": "Unknown Error",
                "description": f"No information found for error code {errorCode}",
                "resolution": "Please contact technical support for assistance with this error code."
            }
        }
    
    except Exception as e:
        print(f"Error getting error code: {str(e)}")
        return {
            "response": {
                "code": errorCode,
                "name": "Error",
                "description": "An error occurred while retrieving error code information.",
                "resolution": "Please try again later or contact system administrator."
            },
            "error": str(e)
        }

def search_logs(event, query, startTime=None, endTime=None, logLevel=None, service=None, transactionId=None, tenantId=None):
    """Search logs for specific patterns or time periods"""
    print(f'search_logs invoked with query: {query}, tenantId: {tenantId}')
    
    # Initialize S3 client with tenant credentials
    s3 = boto3.client('s3',
                aws_access_key_id=event['sessionAttributes'].get('accessKeyId'),
                aws_secret_access_key=event['sessionAttributes'].get('secretAccessKey'),
                aws_session_token=event['sessionAttributes'].get('sessionToken')
                )
    
    # Get the S3 bucket name from environment variable or use a default
    bucket_name = os.environ.get('DATA_BUCKET', 'DataBucket')
    
    try:
        # Get the logs file
        key = f"{tenantId}/logs/microservice-logs.json"
        obj_response = s3.get_object(Bucket=bucket_name, Key=key)
        logs_content = obj_response['Body'].read().decode('utf-8')
        logs = json.loads(logs_content)
        
        # Filter logs based on criteria
        filtered_logs = []
        for log in logs:
            # Check if query is in message
            if query.lower() not in log.get('message', '').lower():
                continue
            
            # Filter by log level if specified
            if logLevel and log.get('level') != logLevel:
                continue
            
            # Filter by service if specified
            if service and log.get('service') != service:
                continue
            
            # Filter by transaction ID if specified
            if transactionId and log.get('transaction_id') != transactionId:
                continue
            
            # Filter by time range if specified
            if startTime or endTime:
                log_time = datetime.datetime.strptime(log.get('timestamp'), "%Y-%m-%d %H:%M:%S")
                
                if startTime:
                    start = datetime.datetime.fromisoformat(startTime.replace('Z', '+00:00'))
                    if log_time < start:
                        continue
                
                if endTime:
                    end = datetime.datetime.fromisoformat(endTime.replace('Z', '+00:00'))
                    if log_time > end:
                        continue
            
            filtered_logs.append(log)
        
        return {
            "response": filtered_logs
        }
    
    except Exception as e:
        print(f"Error searching logs: {str(e)}")
        return {
            "response": [],
            "error": str(e)
        }

def get_issues(event, tenantId):
    """Get a list of all issues"""
    print(f'get_issues invoked with tenantId: {tenantId}')
    
    table = __get_dynamodb_table(event, 'technical-support-issues-table')
    
    try:
        response = table.query(KeyConditionExpression=Key('tenantId').eq(tenantId))
        issues = response.get('Items', [])
        
        return {
            "response": issues
        }
    except Exception as e:
        print(f"Error getting issues: {str(e)}")
        return {
            "response": [],
            "error": str(e)
        }

def create_issue(event, title, description, errorCode, tenantId):
    """Create a new issue in the system"""
    print(f'create_issue invoked with title: {title}, tenantId: {tenantId}')
    
    table = __get_dynamodb_table(event, 'technical-support-issues-table')
    
    try:
        issue_id = str(uuid.uuid4())
        now = datetime.datetime.now().isoformat()
        
        item = {
            'tenantId': tenantId,
            'issueId': issue_id,
            'title': title,
            'description': description,
            'status': 'Open',
            'errorCode': errorCode if errorCode else 'UNKNOWN',
            'createdAt': now,
            'updatedAt': now
        }
        
        table.put_item(Item=item)
        
        return {
            "response": item
        }
    except Exception as e:
        print(f"Error creating issue: {str(e)}")
        return {
            "response": {},
            "error": str(e)
        }

def get_issue(event, issueId, tenantId):
    """Get details about a specific issue"""
    print(f'get_issue invoked with issueId: {issueId}, tenantId: {tenantId}')
    
    table = __get_dynamodb_table(event, 'technical-support-issues-table')
    
    try:
        response = table.get_item(Key={'tenantId': tenantId, 'issueId': issueId})
        
        if 'Item' in response:
            return {
                "response": response['Item']
            }
        else:
            return {
                "response": {},
                "error": "Issue not found"
            }
    except Exception as e:
        print(f"Error getting issue: {str(e)}")
        return {
            "response": {},
            "error": str(e)
        }

def resolve_issue(event, issueId, steps, resolvedBy, tenantId):
    """Mark an issue as resolved with resolution steps"""
    print(f'resolve_issue invoked with issueId: {issueId}, tenantId: {tenantId}')
    
    table = __get_dynamodb_table(event, 'technical-support-issues-table')
    
    try:
        # First, check if the issue exists
        response = table.get_item(Key={'tenantId': tenantId, 'issueId': issueId})
        
        if 'Item' not in response:
            return {
                "response": {},
                "error": "Issue not found"
            }
        
        # Update the issue
        now = datetime.datetime.now().isoformat()
        
        update_response = table.update_item(
            Key={'tenantId': tenantId, 'issueId': issueId},
            UpdateExpression="set #status = :status, #updatedAt = :updatedAt, #resolution = :resolution",
            ExpressionAttributeNames={
                '#status': 'status',
                '#updatedAt': 'updatedAt',
                '#resolution': 'resolution'
            },
            ExpressionAttributeValues={
                ':status': 'Resolved',
                ':updatedAt': now,
                ':resolution': {
                    'steps': steps,
                    'resolvedAt': now,
                    'resolvedBy': resolvedBy if resolvedBy else 'System'
                }
            },
            ReturnValues="ALL_NEW"
        )
        
        return {
            "response": {
                "issueId": issueId,
                "steps": steps,
                "resolvedAt": now,
                "resolvedBy": resolvedBy if resolvedBy else 'System'
            }
        }
    except Exception as e:
        print(f"Error resolving issue: {str(e)}")
        return {
            "response": {},
            "error": str(e)
        }

def __get_tenant_data(tenant_id, get_all_response, table):    
    response = table.query(KeyConditionExpression=Key('tenantId').eq(tenant_id))    
    if (len(response['Items']) > 0):
        for item in response['Items']:
            get_all_response.append(item)

def lambda_handler(event, context):
    action = event['actionGroup']
    api_path = event['apiPath']
    tenantId = event['sessionAttributes']['tenantId']

    if api_path == '/kb/search':
        query = get_named_property(event, "query")
        category = get_named_property(event, "category") if "category" in [p["name"] for p in event['requestBody']['content']['application/json']['properties']] else None
        body = search_knowledge_base(event, query, category, tenantId)
    elif api_path == '/error-codes/{errorCode}':
        errorCode = get_named_parameter(event, "errorCode")
        body = get_error_code(event, errorCode, tenantId)
    elif api_path == '/logs/search':
        query = get_named_property(event, "query")
        
        # Get optional parameters if they exist
        properties = [p["name"] for p in event['requestBody']['content']['application/json']['properties']]
        startTime = get_named_property(event, "startTime") if "startTime" in properties else None
        endTime = get_named_property(event, "endTime") if "endTime" in properties else None
        logLevel = get_named_property(event, "logLevel") if "logLevel" in properties else None
        service = get_named_property(event, "service") if "service" in properties else None
        transactionId = get_named_property(event, "transactionId") if "transactionId" in properties else None
        
        body = search_logs(event, query, startTime, endTime, logLevel, service, transactionId, tenantId)
    elif api_path == '/issues' and event['httpMethod'] == 'GET':
        body = get_issues(event, tenantId)
    elif api_path == '/issues' and event['httpMethod'] == 'POST':
        title = get_named_property(event, "title")
        description = get_named_property(event, "description")
        
        # Get optional parameters if they exist
        properties = [p["name"] for p in event['requestBody']['content']['application/json']['properties']]
        errorCode = get_named_property(event, "errorCode") if "errorCode" in properties else None
        
        body = create_issue(event, title, description, errorCode, tenantId)
    elif api_path == '/issues/{issueId}':
        issueId = get_named_parameter(event, "issueId")
        body = get_issue(event, issueId, tenantId)
    elif api_path == '/issues/{issueId}/resolve':
        issueId = get_named_parameter(event, "issueId")
        steps = get_named_property(event, "steps")
        
        # Get optional parameters if they exist
        properties = [p["name"] for p in event['requestBody']['content']['application/json']['properties']]
        resolvedBy = get_named_property(event, "resolvedBy") if "resolvedBy" in properties else None
        
        body = resolve_issue(event, issueId, steps, resolvedBy, tenantId)
    else:
        body = {"{}::{} is not a valid api, try another one.".format(action, api_path)}

    response_body = {
        'application/json': {
            'body': str(body)
        }
    }

    action_response = {
        'actionGroup': event['actionGroup'],
        'apiPath': event['apiPath'],
        'httpMethod': event['httpMethod'],
        'httpStatusCode': 200,
        'responseBody': response_body
    }

    response = {'response': action_response}
    return response
    
def __get_dynamodb_table(event, table_name):
    dynamodb = boto3.resource('dynamodb',
                aws_access_key_id=event['sessionAttributes'].get('accessKeyId'),
                aws_secret_access_key=event['sessionAttributes'].get('secretAccessKey'),
                aws_session_token=event['sessionAttributes'].get('sessionToken')
                )        
     
    return dynamodb.Table(table_name)