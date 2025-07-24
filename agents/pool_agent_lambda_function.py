#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import boto3
import uuid
from boto3.dynamodb.conditions import Key
import os

def get_named_parameter(event, name):
    return next(item for item in event['parameters'] if item['name'] == name)['value']


def get_named_property(event, name):
    return next(
        item for item in
        event['requestBody']['content']['application/json']['properties']
        if item['name'] == name)['value']




def create_product(event, productName, productPrice, tenantId):
    print('create product invoked')
    productId=uuid.uuid4().hex
    table = __get_dynamodb_table(event,  'pool-product-table')
    response = table.put_item(
            Item=
                {
                    'tenantId': tenantId,
                    'productId': productId,
                    'productName': productName,
                    'productPrice': productPrice
                }
        )
    return {
        "response": {
            'productId': productId,
            'productName': productName,
            'productPrice': productPrice
        }
    }


def get_products(event, tenantId):
    print('get products invoked')
    get_all_response =[]
    table = __get_dynamodb_table(event,  'pool-product-table')
    
    __get_tenant_data(tenantId,get_all_response, table)
    return {
        "response": get_all_response
    }



def get_product(event, productId, tenantId):
    print('get product invoked')
    table = __get_dynamodb_table(event,  'pool-product-table')
    response =table.get_item(Key={'tenantId': tenantId, 'productId': productId})
    item = response['Item']
    return {
        "response": {
            'productId': item['productId'],  
            'productName': item['productName'],
            'productPrice': item['productPrice']
        }
    }

def create_order(event, product, tenantId, quantity):
    print('create order invoked')
    orderId=uuid.uuid4().hex
    table = __get_dynamodb_table(event,  'pool-order-table')
    response = table.put_item(
            Item=
                {
                    'tenantId': tenantId,
                    'orderId': orderId,
                    'quantity': quantity,
                    'product': product
                }
        )
    return {
        "response": {
            'orderId': orderId,
            'quantity': quantity,
            'product': product
        }
    }

def get_orders(event, tenantId):
    print('get orders invoked')
    get_all_response =[]
    table = __get_dynamodb_table(event, 'pool-order-table')
    
    __get_tenant_data(tenantId,get_all_response, table)
    return {
        "response": get_all_response
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

    if api_path == '/products/create-product':
        productName = get_named_property(event, "productName")
        productPrice = get_named_property(event, "productPrice")
        body = create_product(event, productName, productPrice, tenantId)
    elif api_path == '/products':
        body = get_products(event, tenantId)
    elif api_path == '/products/{productId}':
        productId = get_named_parameter(event, "productId")
        body = get_product(event, productId, tenantId)
    elif api_path == '/orders/create-order':
        product = get_named_property(event, "product")
        quantity = get_named_property(event, "quantity")
        body = create_order(event, product, tenantId,quantity)
    elif api_path == '/orders':
        body = get_orders(event, tenantId)    
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
                aws_access_key_id=event['sessionAttributes']['accessKeyId'],
                aws_secret_access_key=event['sessionAttributes']['secretAccessKey'],
                aws_session_token=event['sessionAttributes']['sessionToken']
                )        
     
    return dynamodb.Table(table_name)    


