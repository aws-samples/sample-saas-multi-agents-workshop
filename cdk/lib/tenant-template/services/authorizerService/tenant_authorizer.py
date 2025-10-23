# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import urllib.request
import json
import os
import boto3
import time
import re
import authorizer_layer
import requests
from urllib.parse import urlparse

from jose import jwk, jwt
from jose.utils import base64url_decode
from aws_lambda_powertools import Logger, Tracer
from collections import namedtuple
from assume_role_layer import assume_role


region = os.environ['AWS_REGION']
userpool_id = os.environ['USER_POOL_ID']
appclient_id = os.environ['APP_CLIENT_ID']
assume_role_arn = os.environ['ASSUME_ROLE_ARN']
control_plane_gw_url = os.environ['CP_API_GW_URL']

tenant_token_usage_role_arn = os.environ["TENANT_TOKEN_USAGE_ROLE_ARN"]
tenant_token_usage_table = os.environ["TENANT_TOKEN_USAGE_DYNAMODB_TABLE"]

logger = Logger()

def is_safe_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ['http', 'https']

def lambda_handler(event, context):
    method_arn = event["methodArn"]

    # get JWT token after Bearer from authorization
    # Check if authorizationToken is present in the headers
    if 'authorizationToken' in event:
        token_str = event['authorizationToken']
    elif 'Authorization' in event['headers']:
        token_str = event['headers']['Authorization']
    else:
        raise Exception('Authorization token is missing')

    token = token_str.split(" ")
    if (token[0] != 'Bearer'):
        raise Exception('Authorization header should have a format Bearer <JWT> Token')
    jwt_bearer_token = token[1]

    # only to get tenant id to get user pool info
    unauthorized_claims = jwt.get_unverified_claims(jwt_bearer_token)
    logger.info(unauthorized_claims)

    # get keys for tenant user pool to validate
    keys_url = 'https://cognito-idp.{}.amazonaws.com/{}/.well-known/jwks.json'.format(region, userpool_id)
    if is_safe_url(keys_url):
        response = requests.get(keys_url, timeout=10).content
    else:
        logger.error(f"Unsafe URL scheme detected: {keys_url}")
        raise ValueError("URL scheme not allowed")
    keys = json.loads(response.decode('utf-8'))['keys']

    # authenticate against cognito user pool using the key
    response = authorizer_layer.validateJWT(jwt_bearer_token, appclient_id, keys)
    logger.info(response)
    
    # get authenticated claims
    if (response == False):
        logger.error('Unauthorized')
        return authorizer_layer.create_auth_denied_policy(method_arn)
    else:
        tenant_id = response["custom:tenantId"]
        response_url = control_plane_gw_url + f'tenant-config?tenantId={tenant_id}'
        if is_safe_url(response_url):
            response_data = requests.get(response_url, timeout=10).content
        else:
            logger.error(f"Unsafe URL scheme detected: {response_url}")
            raise ValueError("URL scheme not allowed")
        try:    
            response_text = response_data.decode('utf-8')
            response_json = json.loads(response_text)
            api_key = response_json['apiKey']
            tenant_name=response_json['tenantName']
            knowledge_base_id = response_json["knowledgeBaseId"]
            input_tokens = response_json["inputTokens"]
            output_tokens = response_json["outputTokens"]
        except UnicodeDecodeError:
            print('Unable to decode response data')
        except KeyError:
            print('API Key not found in response')
        
        # TODO: Lab3 - Enable tenant token usage 
        
        # assume role
        # ABAC: create a temporary session using the assume role arn 
        # which gives S3 Access to the tenant-specific prefix and specific knowledge base
        
        request_tags = [("KnowledgeBaseId", knowledge_base_id), ("TenantID", tenant_id)]
        session_parameters = assume_role(access_role_arn = assume_role_arn, request_tags = request_tags, duration_sec = 900)
        
        print("Role Assumed!")

        authorization_success_policy = authorizer_layer.create_auth_success_policy(method_arn, 
            tenant_id,
            tenant_name, 
            knowledge_base_id, 
            session_parameters.aws_access_key_id,
            session_parameters.aws_secret_access_key,
            session_parameters.aws_session_token,
            api_key
        )
        
        logger.debug(authorization_success_policy)
        logger.info("Authorization succeeded")
        return authorization_success_policy
    

def __is_tenant_token_limit_exceeded(tenant_id, input_tokens, output_tokens):
    # check if tenant has enough tokens
    try:
        input_tokens=int(input_tokens)
        output_tokens=int(output_tokens)
        table = __get_dynamodb_table(tenant_id)
        response = table.get_item(
            Key={
                'TenantId': tenant_id
            }
        )
        if 'Item' in response:
            current_input_tokens = response['Item']['TotalInputTokens']
            current_output_tokens = response['Item']['TotalOutputTokens']
        else:
            current_input_tokens = 0
            current_output_tokens = 0

        if (current_input_tokens > input_tokens ) or (current_output_tokens > output_tokens ):
            logger.error('Tenant token limit exceeded')
            return True

    except Exception as e:
        logger.error(f"Error validating tenant token usage limit: {e}")
        return True    
    
    return False

def __get_dynamodb_table(tenant_id):
    request_tags = [("TenantID", tenant_id)]
    session_parameters = assume_role(access_role_arn=tenant_token_usage_role_arn, request_tags = request_tags, duration_sec=900)
    dynamodb = boto3.resource('dynamodb', aws_access_key_id=session_parameters.aws_access_key_id,
            aws_secret_access_key=session_parameters.aws_secret_access_key,
            aws_session_token=session_parameters.aws_session_token)
    return dynamodb.Table(tenant_token_usage_table)