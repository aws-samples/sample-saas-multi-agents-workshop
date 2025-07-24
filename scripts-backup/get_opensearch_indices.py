import boto3
import json
import time
import os
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# Constants
PORT = 443
STACK_NAME = "saas-genai-workshop-bootstrap-template"
OSSC_ARN_PARAM_NAME = "SaaSGenAIWorkshopOSSCollectionArn"

# AWS configuration
region = os.environ.get('AWS_REGION', 'us-west-2')
service = 'aoss'
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)


def get_collection_arn():
    # OpenSearch Serverless configuration
    cf_client = boto3.Session(region_name=region).client('cloudformation')
    # Get the ARN using list comprehension
    oass_collection_arn = next(
        (output['OutputValue'] 
        for output in cf_client.describe_stacks(StackName=STACK_NAME)['Stacks'][0]['Outputs'] 
        if output['OutputKey'] == OSSC_ARN_PARAM_NAME),
        None
    )
    return (oass_collection_arn)

aoss_client = boto3.Session(region_name=region).client('opensearchserverless')

def __get_current_role():
    # Get the full STS ARN
    sts_arn = boto3.client('sts').get_caller_identity()['Arn']

    # Extract the role name using string operations
    role_name = sts_arn.split('/')[1]  # Get the middle part between first and last '/'

    # Format it as IAM role ARN
    account_id = sts_arn.split(':')[4]  # Get the AWS account ID
    iam_role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    return(iam_role_arn)

# Function creating a Data Access Policy per tenant
def __add_data_access_policy(kb_collection):
    kb_collection_name=kb_collection['name']
    iam_role_arn = __get_current_role()
    try:
        response = aoss_client.create_access_policy(
            name=f'participantpolicy',
            description=f'Data access policy for participant for collection: {kb_collection_name}',
            policy=json.dumps(__generate_data_access_policy(iam_role_arn, kb_collection_name)),
            type='data')

        print(f'Participant data access policy created')
    except boto3.exceptions.botocore.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ConflictException':
            print(f'Policy with name "participantpolicy" and type "data" already exists. Skipping creation.')
        else:
            print('Error occurred while adding data access policy', e)
            raise Exception('Error occurred while adding data access policy') from e

# Generating a Data Access Policy per tenant
def __generate_data_access_policy(iam_role_arn, kb_collection_name):
    return [
        {
            "Rules": [
            {
                "Resource": [
                f"index/{kb_collection_name}/*"
                ],
                "Permission": [
                    "aoss:DescribeIndex"
                ],
                "ResourceType": "index"
            }
            ],
            "Principal": [iam_role_arn],
        }
    ]

def __get_opensearch_serverless_collection_details(collection_arn):
    try:
        kb_collection_id = collection_arn.split('/')[-1]
        kb_collection = aoss_client.batch_get_collection(
            ids=[kb_collection_id]
        )

        kb_collection_endpoint = kb_collection['collectionDetails'][0]['collectionEndpoint']
        return kb_collection['collectionDetails'][0]
    except Exception as e:
        print('Error occured while getting OpenSearch serverless collection details', e)
        raise Exception('Error occured while getting OpenSearch serverless collection details') from e

def get_index_sizes(kb_collection):
    kb_collection_endpoint=kb_collection['collectionEndpoint']
    kb_collection_endpoint_domain= kb_collection_endpoint.split("//")[-1]
    # Create the OpenSearch client
    client = OpenSearch(
        hosts=[{'host': kb_collection_endpoint_domain, 'port': PORT}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )

    # Get all indexes in the collection
    indices = client.cat.indices(format='json')

    ## Print index name and data size
    for index in indices:
        index_name = index['index']
        store_size = index['store.size']
        print(f"Index: {index_name}, Data Size: {store_size}")

if __name__ == "__main__":
    collection_arn=get_collection_arn()
    kb_collection=__get_opensearch_serverless_collection_details(collection_arn)
    __add_data_access_policy(kb_collection)
    time.sleep(10)
    get_index_sizes(kb_collection)