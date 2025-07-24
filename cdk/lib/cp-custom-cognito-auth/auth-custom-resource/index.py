# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import botocore
from crhelper import CfnResource
cognito = boto3.client('cognito-idp')
helper = CfnResource()


@helper.create
@helper.update
def do_action(event, _):
    """ Called as part of bootstrap template. 
        Inserts/Updates Settings table based upon the resources deployed inside bootstrap template
        We use these settings inside tenant template

    Args:
            event ([type]): [description]
            _ ([type]): [description]
    """
    # Setting email address as username
    user_name = event['ResourceProperties']['Email']
    email = event['ResourceProperties']['Email']
    user_role = event['ResourceProperties']['Role']
    user_pool_id = event['ResourceProperties']['UserPoolId']

    try:
        create_user_response = cognito.admin_create_user(
            Username=user_name,
            UserPoolId=user_pool_id,
            ForceAliasCreation=True,
            MessageAction='SUPPRESS',
            UserAttributes=[
                {
                    'Name': 'email',
                    'Value': email
                },
                {
                    'Name': 'email_verified',
                    'Value': 'true'
                },
                {
                    'Name': 'custom:userRole',
                    'Value': user_role
                }
            ]
        )
        # Set a default password
        cognito.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=user_name,
            Password='SaaS123!',
            Permanent=True
        )

        print(f'create_user_response: {create_user_response}')
    except cognito.exceptions.UsernameExistsException:
        print(f'user: {user_name} already exists!')
    return user_name


@helper.delete
def do_delete(event, _):
    user_name = event["PhysicalResourceId"]
    user_pool_id = event['ResourceProperties']['UserPoolId']
    try:
        cognito.admin_delete_user(
            UserPoolId=user_pool_id,
            Username=user_name
        )
    except botocore.exceptions.ClientError as e:
        print(f'failed to delete: {e}')


def handler(event, context):
    helper(event, context)
