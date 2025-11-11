# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from datetime import datetime, timedelta
from aws_lambda_powertools import Tracer, Logger
import boto3
import os
import time
from decimal import Decimal
tracer = Tracer()
logger = Logger()


RAG_SERVICE_CLOUDWATCH_LOGS= "/aws/lambda/ragResolutionService"
logs = boto3.client('logs')
athena = boto3.client('athena')
dynamodb = boto3.resource('dynamodb')
tenant_token_usage_table = dynamodb.Table(os.getenv("TENANT_TOKEN_USAGE_DYNAMODB_TABLE"))


@tracer.capture_lambda_handler
def calculate_daily_tenant_token_usage(event, context):
    log_group_names = [RAG_SERVICE_CLOUDWATCH_LOGS]

    tenant_token_usage_query = "filter @message like /ModelInvocationInputTokens|ModelInvocationOutputTokens/ \
                            | fields tenant_id as TenantId, ModelInvocationInputTokens.0 as ModelInvocationInputTokens, ModelInvocationOutputTokens.0 as ModelInvocationOutputTokens \
                            | stats sum(ModelInvocationInputTokens) as TotalInputTokens, sum(ModelInvocationOutputTokens) as TotalOutputTokens by TenantId, dateceil(@timestamp, 1d) as timestamp"

    tenant_token_usage_resultset = __query_cloudwatch_logs(log_group_names, tenant_token_usage_query)

    logger.info(f'Returned tenant token usage result set of size: {len(tenant_token_usage_resultset['results'])}')

    if len(tenant_token_usage_resultset['results']) > 0:
        for row in tenant_token_usage_resultset['results']:
            for field in row:
                if 'TenantId' in field['field']:
                    tenant_id = field['value']
                if 'TotalInputTokens' in field['field']:
                    total_input_tokens = Decimal(field['value'])
                if 'TotalOutputTokens' in field['field']:
                    total_output_tokens = Decimal(field['value'])


            tenant_token_usage_table.put_item(
                Item={
                    'TenantId': tenant_id,
                    'TotalInputTokens': total_input_tokens,
                    'TotalOutputTokens': total_output_tokens,
                    'StartDate': __get_start_date_time(),
                    'EndDate': __get_end_date_time()
                }
            )




def __get_start_date_time():
    time_zone = datetime.now().astimezone().tzinfo
    start_date_time = int(datetime.now(tz=time_zone).date().strftime('%s')) #current day epoch
    return start_date_time

def __get_end_date_time():
    time_zone = datetime.now().astimezone().tzinfo    
    end_date_time =  int((datetime.now(tz=time_zone) + timedelta(days=1)).date().strftime('%s')) #next day epoch
    return end_date_time


def __query_cloudwatch_logs(log_group_names, query_string):
        query = logs.start_query(logGroupNames=log_group_names,
        startTime=__get_start_date_time(),
        endTime=__get_end_date_time(),
        queryString=query_string)

        query_results = logs.get_query_results(queryId=query["queryId"])

        while query_results['status']=='Running' or query_results['status']=='Scheduled':
            time.sleep(5)
            query_results = logs.get_query_results(queryId=query["queryId"])

        return query_results
