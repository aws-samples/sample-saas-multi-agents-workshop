# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import (APIGatewayRestResolver, CORSConfig)
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.event_handler.exceptions import (
    InternalServerError,
    NotFoundError,
)
from langchain_aws.chat_models import ChatBedrockConverse
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.retrievers import AmazonKnowledgeBasesRetriever
from langchain.chains import RetrievalQA
from langchain_core.runnables import RunnablePassthrough
import metrics_manager

import boto3
import json
import os
from botocore.client import Config


tracer = Tracer()
logger = Logger()
cors_config = CORSConfig(allow_origin="*", max_age=300)
app = APIGatewayRestResolver(cors=cors_config)

region_id = os.environ['AWS_REGION']
MODEL_ID = 'us.amazon.nova-micro-v1:0'

def retrieveAndGenerate(bedrock_agent_client, bedrock_client, input, knowledge_base_id, event):
    vector_retrieval_config={"vectorSearchConfiguration": {
            "numberOfResults": 4,

        }}
    
    retriever = AmazonKnowledgeBasesRetriever(
        knowledge_base_id=knowledge_base_id,
        retrieval_config=vector_retrieval_config,
        client=bedrock_agent_client
    )

    # template = """Answer the question based only on the following context:
    # {context}
    # Question: {question}
    # """
    # chat_prompt_template = ChatPromptTemplate.from_template(template)

    chat_prompt_template = ChatPromptTemplate.from_messages(
        [
            
            ("human", """Answer the question based only on the following context: 
             {context}
             Question: {question}
             Skip a line for each result
             """),
            
         ]
        )

    
    # Get account ID to construct the inference profile ARN
    sts_client = boto3.client('sts')
    account_id = sts_client.get_caller_identity()["Account"]
    inference_profile_arn = f'arn:aws:bedrock:{region_id}:{account_id}:inference-profile/{MODEL_ID}'
    
    llm = ChatBedrockConverse(model=inference_profile_arn, temperature=0, client=bedrock_client)

    rag_chain = (
        {"context": retriever , "question": RunnablePassthrough()}
        | chat_prompt_template
        | llm
    )

    response = rag_chain.invoke(input)

    # Publish metrics

    metrics_manager.record_metric(event, "ModelInvocationInputTokens", "Count", response.usage_metadata['input_tokens'])
    metrics_manager.record_metric(event, "ModelInvocationOutputTokens", "Count", response.usage_metadata['output_tokens'])


    return response.content


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST, log_event=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    try:
        aws_access_key_id = event['requestContext']['authorizer']['aws_access_key_id']
        aws_secret_access_key = event['requestContext']['authorizer']['aws_secret_access_key']
        aws_session_token = event['requestContext']['authorizer']['aws_session_token']    
        knowledge_base_id = event['requestContext']['authorizer']['knowledge_base_id']
        tenant_name = event['requestContext']['authorizer']['tenant_name']
        logger.info(f"input tenant name: {tenant_name} and its knowledge_base_id: {knowledge_base_id}")
    	# TODO: Lab2 - uncomment below and hardcode an knowledge base id
        # knowledge_base_id = "<hardcode knowledge base id>"
        # logger.info(f"hard coded knowledge base id: {knowledge_base_id}")
        
        
        if 'body' not in event:
            raise ValueError('No query provided')
        
        # Extract the query from the event
        query = event['body']
        
        # Log the body content
        logger.debug("Received query:", query)
        
        session = boto3.Session(
            aws_access_key_id = aws_access_key_id,
            aws_secret_access_key = aws_secret_access_key,
            aws_session_token = aws_session_token
        )    
        
        # Initialize the Bedrock client
        bedrock_config = Config(connect_timeout=120, read_timeout=120, retries={'max_attempts': 0})
        bedrock_agent_client = session.client('bedrock-agent-runtime', config=bedrock_config)
        bedrock_client = session.client('bedrock-runtime', config=bedrock_config)
        
        response = retrieveAndGenerate(bedrock_agent_client, bedrock_client, query, knowledge_base_id, event)
        
        logger.info(f"Used the knowledge_base_id: {knowledge_base_id} to generate this response: {response}")
        
	    # Return the results
        return {
            'statusCode': 200,
            'body': json.dumps(response)
        }
    
    except Exception as e:
        logger.exception("An error occurred during execution")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'An error occurred during execution'
            })
        }