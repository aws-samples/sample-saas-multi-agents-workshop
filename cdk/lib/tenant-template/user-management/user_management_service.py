# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import os
import argparse

SAAS_APP_USERPOOL_ID=os.environ['SAAS_APP_USERPOOL_ID']

cognito = boto3.client('cognito-idp')

def create_user(tenant_id, email, user_role):
    username=email
    admin_user_exists = __admin_user_exists(SAAS_APP_USERPOOL_ID,username)
    if not admin_user_exists:
        temporary_password = "SaaS123!"  
        response = cognito.admin_create_user(
                Username=username,
                UserPoolId=SAAS_APP_USERPOOL_ID,
                ForceAliasCreation=True,
                TemporaryPassword=temporary_password,
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
                        'Name': 'custom:tenantId',
                        'Value': tenant_id 
                    },
                    {
                        'Name': 'custom:userRole',
                        'Value': user_role 
                    }
                ],
            )
            
        
        __set_user_password(SAAS_APP_USERPOOL_ID, username, temporary_password)
    else:
        response = cognito.admin_update_user_attributes(
                UserPoolId=SAAS_APP_USERPOOL_ID,
                Username=username,
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
                        'Name': 'custom:tenantId',
                        'Value': tenant_id 
                    },
                    {
                        'Name': 'custom:userRole',
                        'Value': user_role 
                    }
                ]
            )
    group_exists = __user_group_exists(SAAS_APP_USERPOOL_ID, tenant_id)
    if not group_exists:
        __create_user_group(SAAS_APP_USERPOOL_ID, tenant_id)

    __add_user_to_group(SAAS_APP_USERPOOL_ID, username, tenant_id)
    return response

def __admin_user_exists(SAAS_APP_USERPOOL_ID,username):
    try:
        response=cognito.admin_get_user(
            UserPoolId=SAAS_APP_USERPOOL_ID,
            Username=username)
        return True
    except Exception as e:
        return False

def __set_user_password(user_pool_id, username, password):
    response = cognito.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=username,
        Password=password,
        Permanent=True
    )
    return response

def __create_user_group(user_pool_id, group_name):
        response = cognito.create_group(
            GroupName=group_name,
            UserPoolId=user_pool_id,
            Precedence=0
        )
        return response


def __add_user_to_group(user_pool_id, user_name, group_name):
        response = cognito.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=user_name,
            GroupName=group_name
        )
        return response

def __user_group_exists(user_pool_id, group_name):        
        try:
            response=cognito.get_group(
                UserPoolId=user_pool_id, 
                GroupName=group_name)
            return True
        except Exception as e:
            return False
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Managing tenant users')
    parser.add_argument('--tenant-id', type=str, help='tenant-id', required=True)
    parser.add_argument('--email', type=str, help='email', required=True)
    parser.add_argument('--user-role', type=str, help='user role', required=True)
    
    args = parser.parse_args()
    create_user(**vars(args))
