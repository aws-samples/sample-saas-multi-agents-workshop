# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import os
from crhelper import CfnResource

log_group = os.environ['LOG_GROUP_NAME']
log_role= os.environ['BEDROCK_LOG_ROLE']

# Create Bedrock client
bedrock_client = boto3.client('bedrock')
helper = CfnResource()

@helper.create
@helper.update
def do_action(event, _):
    # Set up logging configuration
    logging_config = {
        'cloudWatchConfig': {
            'logGroupName': log_group,
            'roleArn': log_role 
        }
  
    }

    print(logging_config)

    # Enable model invocation logging
    try:
        bedrock_client.put_model_invocation_logging_configuration(
            loggingConfig=logging_config
        )
        print('Model invocation logging enabled successfully.')
    except Exception as e:
        print(f'Error enabling model invocation logging: {e}')

    return log_group

@helper.delete
def do_delete(event, _):
    # Disable model invocation logging
    try:
        bedrock_client.delete_model_invocation_logging_configuration()
        print('Model invocation logging disabled successfully.')
    except Exception as e:
        print(f'Error disabling model invocation logging: {e}')

def handler(event, context):
    helper(event, context)

