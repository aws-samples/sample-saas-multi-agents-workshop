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

cloudwatch = boto3.client('cloudwatch')
athena = boto3.client('athena')
dynamodb = boto3.resource('dynamodb')
attribution_table = dynamodb.Table(os.getenv("TENANT_COST_DYNAMODB_TABLE"))

ATHENA_S3_OUTPUT = os.getenv("ATHENA_S3_OUTPUT")
CUR_DATABASE_NAME = os.getenv("CUR_DATABASE_NAME")
CUR_TABLE_NAME = os.getenv("CUR_TABLE_NAME")
RETRY_COUNT = 100
SMARTRESOLVE_NAMESPACE = "SmartResolve"

CLAUDE_SONNET_INPUT_TOKENS_LABEL = "USW2-Bedrock-Model-Anthropic-Claude-3-7-Input-Tokens"
CLAUDE_SONNET_OUTPUT_TOKENS_LABEL = "USW2-Bedrock-Model-Anthropic-Claude-3-7-Output-Tokens"

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
        for tenant_id, tenant_attribution_percentage in tenant_attribution_dict.items():
            tenant_attribution_percentage_json = json.loads(tenant_attribution_percentage)
            
            # TODO: Lab3 - Calculate tenant cost for generating final tenant specific response
            # tenant_input_tokens_cost = self.__get_tenant_cost(CLAUDE_SONNET_INPUT_TOKENS_LABEL, total_service_cost_dict, tenant_attribution_percentage_json)
            # tenant_output_tokens_cost = self.__get_tenant_cost(CLAUDE_SONNET_OUTPUT_TOKENS_LABEL, total_service_cost_dict, tenant_attribution_percentage_json)
            tenant_input_tokens_cost = 0
            tenant_output_tokens_cost = 0

            tenant_service_cost = tenant_input_tokens_cost + tenant_output_tokens_cost
            try:
                attribution_table.put_item(
                    Item=
                        {
                            "Date": self.start_date_time,
                            "TenantId#ServiceName": tenant_id + "#" + "AmazonBedrock",
                            "TenantId": tenant_id, 
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

    def __get_tenant_attribution(self, tenant_attribution_dict):
        # Get total tokens across all tenants
        total_input_tokens = Decimal('1')
        total_output_tokens = Decimal('1')

        # TODO: Lab3 - Query CloudWatch Metrics for total input/output tokens across all tenants
        # for metric_name in ['ModelInvocationInputTokens', 'ModelInvocationOutputTokens']:
        #     response = cloudwatch.get_metric_statistics(
        #         Namespace=SMARTRESOLVE_NAMESPACE,
        #         MetricName=metric_name,
        #         StartTime=datetime.fromtimestamp(self.start_date_time),
        #         EndTime=datetime.fromtimestamp(self.end_date_time),
        #         Period=max(60, int(self.end_date_time - self.start_date_time)),
        #         Statistics=['Sum']
        #     )
        #     if response['Datapoints']:
        #         if metric_name == 'ModelInvocationInputTokens':
        #             total_input_tokens = sum(Decimal(str(dp['Sum'])) for dp in response['Datapoints'])
        #         else:
        #             total_output_tokens = sum(Decimal(str(dp['Sum'])) for dp in response['Datapoints'])

        # Get per-tenant metrics
        tenant_ids = self.__get_tenant_ids_from_metrics()

        for tenant_id in tenant_ids:
            tenant_input_tokens = Decimal('0')
            tenant_output_tokens = Decimal('0')

            # TODO: Lab3 - Query CloudWatch Metrics for tenant-specific input/output tokens
            # for metric_name in ['ModelInvocationInputTokens', 'ModelInvocationOutputTokens']:
            #     response = cloudwatch.get_metric_statistics(
            #         Namespace=SMARTRESOLVE_NAMESPACE,
            #         MetricName=metric_name,
            #         Dimensions=[{'Name': 'tenant_id', 'Value': tenant_id}],
            #         StartTime=datetime.fromtimestamp(self.start_date_time),
            #         EndTime=datetime.fromtimestamp(self.end_date_time),
            #         Period=max(60, int(self.end_date_time - self.start_date_time)),
            #         Statistics=['Sum']
            #     )
            #     if response['Datapoints']:
            #         if metric_name == 'ModelInvocationInputTokens':
            #             tenant_input_tokens = sum(Decimal(str(dp['Sum'])) for dp in response['Datapoints'])
            #         else:
            #             tenant_output_tokens = sum(Decimal(str(dp['Sum'])) for dp in response['Datapoints'])

            # TODO: Lab3 - Calculate the percentage of tenant attribution for input and output tokens
            # tenant_attribution_input_tokens_percentage = tenant_input_tokens / total_input_tokens if total_input_tokens > 0 else 0
            # tenant_attribution_output_tokens_percentage = tenant_output_tokens / total_output_tokens if total_output_tokens > 0 else 0
            tenant_attribution_input_tokens_percentage = 0
            tenant_attribution_output_tokens_percentage = 0

            self.__add_or_update_dict(tenant_attribution_dict, tenant_id, CLAUDE_SONNET_INPUT_TOKENS_LABEL, tenant_attribution_input_tokens_percentage)
            self.__add_or_update_dict(tenant_attribution_dict, tenant_id, CLAUDE_SONNET_OUTPUT_TOKENS_LABEL, tenant_attribution_output_tokens_percentage)

    def __get_tenant_ids_from_metrics(self):
        tenant_ids = set()

        paginator = cloudwatch.get_paginator('list_metrics')
        for page in paginator.paginate(Namespace=SMARTRESOLVE_NAMESPACE, MetricName='ModelInvocationInputTokens'):
            for metric in page['Metrics']:
                for dimension in metric.get('Dimensions', []):
                    if dimension['Name'] == 'tenant_id':
                        tenant_ids.add(dimension['Value'])

        return sorted(list(tenant_ids))

    def __add_or_update_dict(self, tenant_attribution_dict, key, new_attribute_name, new_attribute_value):
        if key in tenant_attribution_dict:
            json_obj = json.loads(tenant_attribution_dict[key])
            json_obj[new_attribute_name] = str(new_attribute_value)
            tenant_attribution_dict[key] = json.dumps(json_obj)
        else:
            new_json_obj = {new_attribute_name: str(new_attribute_value)}
            tenant_attribution_dict[key] = json.dumps(new_json_obj)

    def __get_tenant_cost(self, key, total_service_cost, tenant_attribution_percentage_json):
        tenant_attribution_percentage = Decimal(tenant_attribution_percentage_json.get(key, 0))
        total_cost = Decimal(total_service_cost.get(key, 0))
        tenant_cost = tenant_attribution_percentage * total_cost
        return tenant_cost         