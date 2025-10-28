# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import time
import os
import json
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal
from aws_lambda_powertools import Tracer, Logger

tracer = Tracer()
logger = Logger()

cloudwatch_logs = boto3.client('logs')
athena = boto3.client('athena')
dynamodb = boto3.resource('dynamodb')
attribution_table = dynamodb.Table(os.getenv("TENANT_COST_DYNAMODB_TABLE"))

ATHENA_S3_OUTPUT = os.getenv("ATHENA_S3_OUTPUT")
CUR_DATABASE_NAME = os.getenv("CUR_DATABASE_NAME")
CUR_TABLE_NAME = os.getenv("CUR_TABLE_NAME")
RETRY_COUNT = 100
SMARTRESOLVE_LOG_GROUP = "/smartresolve/log-group"

CLAUDE_SONNET_INPUT_TOKENS_LABEL = "USE1-Bedrock-Model-Anthropic-Claude-3-7-Input-Tokens"
CLAUDE_SONNET_OUTPUT_TOKENS_LABEL = "USE1-Bedrock-Model-Anthropic-Claude-3-7-Output-Tokens"

class InvokeModelTenantCost():
    def __init__(self, start_date_time, end_date_time):
        self.start_date_time = start_date_time
        self.end_date_time = end_date_time

    def total_service_cost(self):
        # Additional filters (day, month, year, resource IDs) should be added in production.
        # Currently using a static CUR file, so startTime and endTime filters are omitted.

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
        logger.info(result)

        total_service_cost_dict = {}
        for row in result['ResultSet']['Rows'][1:]:
            line_item = row['Data'][0]['VarCharValue']
            cost = Decimal(row['Data'][1]['VarCharValue'])

            # TODO: Lab3 - Get total input and output tokens cost
            # if line_item in (CLAUDE_SONNET_INPUT_TOKENS_LABEL, CLAUDE_SONNET_OUTPUT_TOKENS_LABEL):
            #     total_service_cost_dict[line_item] = cost

        logger.info(total_service_cost_dict)
        return total_service_cost_dict

    def query_metrics(self):
        tenant_attribution_dict = {}
        self.__get_tenant_attribution(tenant_attribution_dict)
        return tenant_attribution_dict

    def calculate_tenant_cost(self, total_service_cost_dict, tenant_attribution_dict):
        logger.info(f"Total service cost dict: {total_service_cost_dict}")
        logger.info(f"Tenant attribution dict: {tenant_attribution_dict}")
        
        total_service_cost = total_service_cost_dict.get(CLAUDE_SONNET_INPUT_TOKENS_LABEL, Decimal('0')) + total_service_cost_dict.get(CLAUDE_SONNET_OUTPUT_TOKENS_LABEL, Decimal('0'))
        logger.info(f"Total service cost: {total_service_cost}")
        
        for tenant_id, tenant_attribution_percentage in tenant_attribution_dict.items():
            logger.info(f"Calculating cost for tenant: {tenant_id}")
            tenant_attribution_percentage_json = json.loads(tenant_attribution_percentage)
            logger.info(f"Attribution percentages: {tenant_attribution_percentage_json}")
            
            # TODO: Lab3 - Calculate tenant cost for generating final tenant specific response
            # tenant_input_tokens_cost = self.__get_tenant_cost(CLAUDE_SONNET_INPUT_TOKENS_LABEL, total_service_cost_dict, tenant_attribution_percentage_json)
            # tenant_output_tokens_cost = self.__get_tenant_cost(CLAUDE_SONNET_OUTPUT_TOKENS_LABEL, total_service_cost_dict, tenant_attribution_percentage_json)
            # logger.info(f"Tenant {tenant_id} costs - Input: {tenant_input_tokens_cost}, Output: {tenant_output_tokens_cost}")
            tenant_input_tokens_cost = 0
            tenant_output_tokens_cost = 0

            tenant_service_cost = tenant_input_tokens_cost + tenant_output_tokens_cost
            tenant_attribution_percentage_value = tenant_service_cost / total_service_cost if total_service_cost > 0 else Decimal('0')
            logger.info(f"Tenant {tenant_id} attribution percentage: {tenant_attribution_percentage_value}")
            
            try:
                attribution_table.put_item(
                    Item=
                        {
                            "Date": self.start_date_time,
                            "TenantId#ServiceName": tenant_id + "#" + "AmazonBedrock",
                            "TenantId": tenant_id, 
                            "TenantInputTokensCost": tenant_input_tokens_cost,
                            "TenantOutputTokensCost": tenant_output_tokens_cost,
                            "TenantAttributionPercentage": tenant_attribution_percentage_value,
                            "TenantServiceCost": tenant_service_cost,
                            "TotalServiceCost": total_service_cost
                        }
                )
            except ClientError as e:
                print(e.response['Error']['Message'])
                raise Exception('Error', e)
            else:
                print("PutItem succeeded:")

    def __get_tenant_attribution(self, tenant_attribution_dict):
        logger.info("Starting __get_tenant_attribution")
        total_input_tokens = Decimal('1')
        total_output_tokens = Decimal('1')

        # TODO: Lab3 - Query CloudWatch Logs for total input/output tokens across all tenants
        # query = "filter metric_name in ['ModelInvocationInputTokens', 'ModelInvocationOutputTokens'] | stats sum(metric_value) as total by metric_name"
        # total_input_tokens, total_output_tokens = self.__query_cloudwatch_logs(query, Decimal('1'))
        # logger.info(f"Total tokens - Input: {total_input_tokens}, Output: {total_output_tokens}")

        tenant_ids = self.__get_tenant_ids_from_logs()
        logger.info(f"Found tenant IDs: {tenant_ids}")

        for tenant_id in tenant_ids:
            logger.info(f"Processing tenant: {tenant_id}")
            tenant_input_tokens = Decimal('0')
            tenant_output_tokens = Decimal('0')

            # TODO: Lab3 - Query CloudWatch Logs for tenant-specific input/output tokens
            # query = f"filter metric_name in ['ModelInvocationInputTokens', 'ModelInvocationOutputTokens'] and tenant_id = '{tenant_id}' | stats sum(metric_value) as total by metric_name"
            # tenant_input_tokens, tenant_output_tokens = self.__query_cloudwatch_logs(query, Decimal('0'))
            # logger.info(f"Tenant {tenant_id} tokens - Input: {tenant_input_tokens}, Output: {tenant_output_tokens}")

            # TODO: Lab3 - Calculate the percentage of tenant attribution for input and output tokens
            # tenant_attribution_input_tokens_percentage = tenant_input_tokens / total_input_tokens if total_input_tokens > 0 else 0
            # tenant_attribution_output_tokens_percentage = tenant_output_tokens / total_output_tokens if total_output_tokens > 0 else 0
            # logger.info(f"Tenant {tenant_id} percentages - Input: {tenant_attribution_input_tokens_percentage}, Output: {tenant_attribution_output_tokens_percentage}")
            tenant_attribution_input_tokens_percentage = 0
            tenant_attribution_output_tokens_percentage = 0

            self.__add_or_update_dict(tenant_attribution_dict, tenant_id, CLAUDE_SONNET_INPUT_TOKENS_LABEL, tenant_attribution_input_tokens_percentage)
            self.__add_or_update_dict(tenant_attribution_dict, tenant_id, CLAUDE_SONNET_OUTPUT_TOKENS_LABEL, tenant_attribution_output_tokens_percentage)
            logger.info(f"Tenant {tenant_id} attribution dict: {tenant_attribution_dict[tenant_id]}")

    def __query_cloudwatch_logs(self, query, default_value=Decimal('0')):
        logger.info(f"Query: {query}")
        logger.info(f"Default value: {default_value}")
        
        response = cloudwatch_logs.start_query(
            logGroupName=SMARTRESOLVE_LOG_GROUP,
            startTime=int(self.start_date_time),
            endTime=int(self.end_date_time),
            queryString=query
        )
        
        result = self.__wait_for_query_completion(response['queryId'])
        logger.info(f"Query results: {result}")
        
        input_tokens = default_value
        output_tokens = default_value
        
        if result and result['results']:
            logger.info(f"Processing {len(result['results'])} rows")
            for row in result['results']:
                logger.info(f"Row: {row}")
                metric_name = next((f['value'] for f in row if f['field'] == 'metric_name'), None)
                total_value = next((f['value'] for f in row if f['field'] == 'total'), None)
                logger.info(f"Metric name: {metric_name}, Total value: {total_value}")
                
                if metric_name == 'ModelInvocationInputTokens' and total_value:
                    input_tokens = Decimal(total_value)
                    logger.info(f"Set input_tokens to: {input_tokens}")
                elif metric_name == 'ModelInvocationOutputTokens' and total_value:
                    output_tokens = Decimal(total_value)
                    logger.info(f"Set output_tokens to: {output_tokens}")
        
        logger.info(f"Returning input_tokens={input_tokens}, output_tokens={output_tokens}")
        return input_tokens, output_tokens

    def __get_tenant_ids_from_logs(self):
        query = "filter @message like /tenant_id/ | fields tenant_id | stats count() by tenant_id"
        
        response = cloudwatch_logs.start_query(
            logGroupName=SMARTRESOLVE_LOG_GROUP,
            startTime=int(self.start_date_time),
            endTime=int(self.end_date_time),
            queryString=query
        )
        
        query_id = response['queryId']
        result = self.__wait_for_query_completion(query_id)
        
        if result and result['results']:
            tenant_ids = set()
            for row in result['results']:
                for field in row:
                    if field['field'] == 'tenant_id' and field['value']:
                        tenant_ids.add(field['value'])
                        break
            return sorted(list(tenant_ids))
        
        return []

    def __add_or_update_dict(self, tenant_attribution_dict, key, new_attribute_name, new_attribute_value):
        if key in tenant_attribution_dict:
            json_obj = json.loads(tenant_attribution_dict[key])
            json_obj[new_attribute_name] = str(new_attribute_value)
            tenant_attribution_dict[key] = json.dumps(json_obj)
        else:
            new_json_obj = {new_attribute_name: str(new_attribute_value)}
            tenant_attribution_dict[key] = json.dumps(new_json_obj)

    def __wait_for_query_completion(self, query_id):
        for _ in range(RETRY_COUNT):
            response = cloudwatch_logs.get_query_results(queryId=query_id)
            if response['status'] == 'Complete':
                return response
            elif response['status'] == 'Failed':
                raise Exception(f"Query failed: {response.get('statistics', {})}")
            time.sleep(1)
        raise Exception('Query timeout')

    def __get_tenant_cost(self, key, total_service_cost, tenant_attribution_percentage_json):
        tenant_attribution_percentage = Decimal(tenant_attribution_percentage_json.get(key, '0'))
        total_cost = total_service_cost.get(key, Decimal('0'))
        tenant_cost = tenant_attribution_percentage * total_cost
        logger.info(f"__get_tenant_cost - key: {key}, percentage: {tenant_attribution_percentage}, total_cost: {total_cost}, result: {tenant_cost}")
        return tenant_cost         