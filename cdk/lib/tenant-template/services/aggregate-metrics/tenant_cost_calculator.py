# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from datetime import datetime, timedelta
from invoke_model_tenant_cost import InvokeModelTenantCost
from aws_lambda_powertools import Tracer, Logger

tracer = Tracer()
logger = Logger()

@tracer.capture_lambda_handler
def calculate_cost_per_tenant(event, context):

    invoke_model_tenant_cost = InvokeModelTenantCost(__get_start_date_time(), 
                                                      __get_end_date_time())
    
    total_service_cost_dict = invoke_model_tenant_cost.total_service_cost()
    metrics_dict = invoke_model_tenant_cost.query_metrics()
    invoke_model_tenant_cost.calculate_tenant_cost(total_service_cost_dict, metrics_dict)


def __get_start_date_time():
    time_zone = datetime.now().astimezone().tzinfo
    start_date_time = int(datetime.now(tz=time_zone).date().strftime('%s')) #current day epoch
    return start_date_time

def __get_end_date_time():
    time_zone = datetime.now().astimezone().tzinfo    
    end_date_time =  int((datetime.now(tz=time_zone) + timedelta(days=1)).date().strftime('%s')) #next day epoch
    return end_date_time