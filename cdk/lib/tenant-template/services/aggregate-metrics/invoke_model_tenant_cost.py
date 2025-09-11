# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import time
import os
import json
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from decimal import *
from aws_lambda_powertools import Tracer, Logger

tracer = Tracer()
logger = Logger()

cloudformation = boto3.client('cloudformation')
logs = boto3.client('logs')
athena = boto3.client('athena')
dynamodb = boto3.resource('dynamodb')
# attribution_table = dynamodb.Table("TenantCostAndUsageAttribution")
attribution_table = dynamodb.Table(os.getenv("TENANT_COST_DYNAMODB_TABLE"))

ATHENA_S3_OUTPUT = os.getenv("ATHENA_S3_OUTPUT")
CUR_DATABASE_NAME = os.getenv("CUR_DATABASE_NAME")
CUR_TABLE_NAME = os.getenv("CUR_TABLE_NAME")
RETRY_COUNT = 100
EMBEDDING_TITAN_INPUT_TOKENS_LABEL="USW2-TitanEmbeddingsG1-Text-input-tokens"
TEXTLITE_INPUT_TOKENS_LABEL="USW2-TitanTextG1-Lite-input-tokens"
TEXTLITE_OUTPUT_TOKENS_LABEL="USW2-TitanTextG1-Lite-output-tokens"
MODEL_INVOCATION_LOG_GROUPNAME= os.getenv("MODEL_INVOCATION_LOG_GROUPNAME")

class InvokeModelTenantCost():

    
    def __init__(self, start_date_time, end_date_time):
        self.start_date_time = start_date_time
        self.end_date_time = end_date_time

    def total_service_cost(self):

        # We need to add more filters for day, month, year, resource ids etc. Below query is because we are just using a sample cur file
        #Ignoting startTime and endTime filter for now since we have a static/sample cur file

        query = f"SELECT line_item_usage_type, CAST(sum(line_item_blended_cost) AS DECIMAL(10, 6)) AS cost FROM {CUR_DATABASE_NAME}.{CUR_TABLE_NAME} WHERE line_item_product_code='AmazonBedrock' group by 1"

        # Execution
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={
                'Database': CUR_DATABASE_NAME
            },
            ResultConfiguration={
                'OutputLocation': "s3://" + ATHENA_S3_OUTPUT,
            }
        )

        # get query execution id
        query_execution_id = response['QueryExecutionId']
        logger.info(query_execution_id)

        # get execution status
        for i in range(1, 1 + RETRY_COUNT):

            # get query execution
            query_status = athena.get_query_execution(QueryExecutionId=query_execution_id)
            print (query_status)
            query_execution_status = query_status['QueryExecution']['Status']['State']

            if query_execution_status == 'SUCCEEDED':
                print("STATUS:" + query_execution_status)
                break

            if query_execution_status == 'FAILED':
                raise Exception("STATUS:" + query_execution_status)

            else:
                print("STATUS:" + query_execution_status)
                time.sleep(i)
        else:
            athena.stop_query_execution(QueryExecutionId=query_execution_id)
            raise Exception('TIME OVER')

        # get query results
        result = athena.get_query_results(QueryExecutionId=query_execution_id)
        
        logger.info (result)
        

        
        total_service_cost_dict = {}
        for row in result['ResultSet']['Rows'][1:]:
            line_item = row['Data'][0]['VarCharValue']
            cost = Decimal(row['Data'][1]['VarCharValue'])
            # TODO: Lab3 - Get total input and output tokens cost
            
            
            
            
        logger.info(total_service_cost_dict)

        
        # total_service_cost_dict = {"USE1-TitanEmbeddingsG1-Text-input-tokens": 5000, "USE1-TitanTextLite-input-tokens": 4000, "USE1-TitanTextLite-output-tokens": 6000}
        return total_service_cost_dict

    def query_metrics(self):
        # This dictionary stores the data in format
        #  {'TenantId': '{"USE1-TitanEmbeddingsG1-Text-input-tokens":0.2, 
        # "USE1-TitanTextLite-input-tokens": 0.4, "USE1-TitanTextLite-output-tokens": 0.6}'}
        tenant_attribution_dict = {}
        log_group_names = self.__get_list_of_log_group_names()

        self.__get_tenant_kb_attribution(log_group_names, tenant_attribution_dict)

        self.__get_tenant_converse_attribution(log_group_names, tenant_attribution_dict)
                            
        return tenant_attribution_dict    



    def calculate_tenant_cost(self, total_service_cost_dict, tenant_attribution_dict):

        for tenant_id, tenant_attribution_percentage in tenant_attribution_dict.items():

            tenant_attribution_percentage_json = json.loads(tenant_attribution_percentage)

            # TODO: Lab4 - Calculate tenant cost for ingesting & retrieving tenant data to/from Amazon Bedrock Knowledge Base
            tenant_kb_input_tokens_cost = 0
            
            # TODO: Lab4 - Calculate tenant cost for generating final tenant specific response
            tenant_input_tokens_cost = 0
            tenant_output_tokens_cost = 0

            tenant_service_cost = tenant_kb_input_tokens_cost + tenant_input_tokens_cost + tenant_output_tokens_cost    
            try:
                response = attribution_table.put_item(
                    Item=
                        {
                            "Date": self.start_date_time,
                            "TenantId#ServiceName": tenant_id+"#"+"AmazonBedrock",
                            "TenantId": tenant_id, 
                            "TenantKnowledgeBaseInputTokensCost": tenant_kb_input_tokens_cost,
                            "TenantInputTokensCost": tenant_input_tokens_cost,
                            "TenantOutputTokensCost": tenant_output_tokens_cost,
                            "TenantAttributionPercentage": tenant_attribution_percentage,
                            "TenantServiceCost": tenant_service_cost,
                            "TotalServiceCost": total_service_cost_dict
                        }
                )
            except ClientError as e:
                print(e.response['Error']['Message'])
                raise Exception('Error', e)
            else:
                print("PutItem succeeded:")

    def __is_log_group_exists(self, log_group_name):
        logs_paginator = logs.get_paginator('describe_log_groups')
        response_iterator = logs_paginator.paginate(logGroupNamePrefix=log_group_name)
        for log_groups_list in response_iterator:
            if not log_groups_list["logGroups"]:
                return False
            else:
                return True       

    def __add_log_group_name(self, log_group_name, log_group_names_list):
        if self.__is_log_group_exists(log_group_name):
            log_group_names_list.append(log_group_name)


    def __get_list_of_log_group_names(self):
        log_group_names = []
        # Adding bedrock model invocation cloudwatch log group
        self.__add_log_group_name(MODEL_INVOCATION_LOG_GROUPNAME, log_group_names)

        # Adding RagService lambda cloudwatch log group
        log_group_prefix = '/aws/lambda/'
        cloudformation_paginator = cloudformation.get_paginator('list_stack_resources')
        response_iterator = cloudformation_paginator.paginate(StackName='saas-genai-workshop-bootstrap-template')
        for stack_resources in response_iterator:
            for resource in stack_resources['StackResourceSummaries']:
                if ("RagService" in resource["LogicalResourceId"]
                    and resource["ResourceType"] == "AWS::Lambda::Function"):
                    self.__add_log_group_name(''.join([log_group_prefix,resource["PhysicalResourceId"]]), 
                    log_group_names)
                    continue    

        logger.info(log_group_names)
        return log_group_names
    
    def __query_cloudwatch_logs(self, log_group_names, query_string):
        query = logs.start_query(logGroupNames=log_group_names,
        startTime=self.start_date_time,
        endTime=self.end_date_time,
        queryString=query_string)

        query_results = logs.get_query_results(queryId=query["queryId"])

        while query_results['status']=='Running' or query_results['status']=='Scheduled':
            time.sleep(5)
            query_results = logs.get_query_results(queryId=query["queryId"])

        return query_results
    
    def __get_tenant_kb_attribution(self, log_group_names, tenant_attribution_dict):

        #TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get knowledge base input tokens
        knowledgebase_input_tokens_query = ""
        
        
        knowledgebase_input_tokens_resultset = self.__query_cloudwatch_logs(log_group_names, knowledgebase_input_tokens_query)


        # TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get total knowledge base input tokens
        total_knowledgebase_input_tokens_query = ""
        
        total_knowledgebase_input_tokens_resultset = self.__query_cloudwatch_logs(log_group_names, total_knowledgebase_input_tokens_query)
        
        # We configure knowledgebase to use Amazon Titan Text Embeddings V2 model to generate embeddings
        # When generating embeddings you are only charged for input tokens.
        # Here we are calculating the tenant percentage of embedding input tokens 
        # when interacting with Amazon Titan Text Embeddings V2 model through knowledgebase
        if len(total_knowledgebase_input_tokens_resultset['results']) > 0:
            total_knowledgebase_input_tokens = Decimal('1')
            for row in total_knowledgebase_input_tokens_resultset['results'][0]:
                if 'TotalInputTokens' in row['field']:
                    total_knowledgebase_input_tokens = Decimal(row['value'])

            for row in knowledgebase_input_tokens_resultset['results']:
                for field in row:
                    if 'tenantId' in field['field']:
                        tenant_id = field['value']
                    if 'TotalInputTokens' in field['field']:
                        input_tokens = Decimal(field['value'])

                # TODO: Lab4 - Calculate the percentage of tenant attribution for knowledge base input tokens
                tenant_kb_input_tokens_attribution_percentage = 0
                self.__add_or_update_dict(tenant_attribution_dict, tenant_id,EMBEDDING_TITAN_INPUT_TOKENS_LABEL, tenant_kb_input_tokens_attribution_percentage)

    
    def __get_tenant_converse_attribution(self, log_group_names, tenant_attribution_dict):
        
        # TODO: Lab4 - Add Amazon CloudWatch logs insights queries for converse input output tokens
        converse_input_output_tokens_query = ""
        
        converse_input_output_tokens = self.__query_cloudwatch_logs(log_group_names, converse_input_output_tokens_query)

        # TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get total converse input output tokens
        total_converse_input_output_tokens_query = ""
        
        total_converse_input_output_tokens = self.__query_cloudwatch_logs(log_group_names, total_converse_input_output_tokens_query)

        if (len(total_converse_input_output_tokens['results']) > 0):    
            total_input_tokens = Decimal('1')
            total_output_tokens = Decimal('1')

            for row in total_converse_input_output_tokens['results'][0]:
                if 'TotalInputTokens' in row['field']:
                    total_input_tokens = Decimal(row['value'])
                if 'TotalOutputTokens' in row['field']:
                    total_output_tokens = Decimal(row['value'])

            total_input_output_tokens = total_input_tokens + total_output_tokens        

            if ( total_input_output_tokens > 0):

                for row in converse_input_output_tokens['results']:
                    for field in row:
                        if 'TenantId' in field['field']:
                            tenant_id = field['value']
                        if 'TotalInputTokens' in field['field']:
                            tenant_input_tokens = Decimal(field['value'])
                        if 'TotalOutputTokens' in field['field']:
                            tenant_output_tokens = Decimal(field['value'])

                    # TODO: Lab4 - Calculate the percentage of tenant attribution for converse input and output tokens
                    tenant_attribution_input_tokens_percentage = 0
                    tenant_attribution_output_tokens_percentage = 0
                    
                    self.__add_or_update_dict(tenant_attribution_dict, tenant_id,TEXTLITE_INPUT_TOKENS_LABEL, tenant_attribution_input_tokens_percentage)
                    self.__add_or_update_dict(tenant_attribution_dict, tenant_id,TEXTLITE_OUTPUT_TOKENS_LABEL, tenant_attribution_output_tokens_percentage)

                    

    def __add_or_update_dict(self, tenant_attribution_dict, key, new_attribute_name, new_attribute_value):
        if key in tenant_attribution_dict:
            # Key exists, so load the JSON string into a Python object
            json_obj = json.loads(tenant_attribution_dict[key])
            
            # Add the new attribute to the Python object
            json_obj[new_attribute_name] = str(new_attribute_value)
            
            tenant_attribution_dict[key] = json.dumps(json_obj)
        else:
            # Key does not exist, create a new Python object with the new attribute
            new_json_obj = {new_attribute_name: str(new_attribute_value)}
            
            tenant_attribution_dict[key] = json.dumps(new_json_obj)           


    def __get_tenant_cost(self, key, total_service_cost, tenant_attribution_percentage_json):
        tenant_data = tenant_attribution_percentage_json.get(key, 0)
        # Bedrock service cost is charged per 1000 tokens
        tenant_cost = Decimal(tenant_data) * Decimal(total_service_cost[key])/1000
        return tenant_cost         