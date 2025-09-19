#!/usr/bin/env python3

import os
import sys
import boto3
import logging
import argparse
import yaml
import random
import time
from contextlib import contextmanager
from bedrock_agentcore.services.identity import IdentityClient
from bedrock_agentcore_starter_toolkit import Runtime

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Set specific format for this script's logger
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.handlers = [handler]
logger.propagate = False


def get_stack_outputs():
    """
    Get stack outputs from environment variables passed by parent script.
    Falls back to CloudFormation API if environment variables are not set.
    """
    # Try to get from environment variables first (preferred approach)
    env_outputs = {
        "UserPoolId": os.environ.get("USER_POOL_ID"),
        "UserClientId": os.environ.get("USER_CLIENT_ID"),
        "M2MClientId": os.environ.get("M2M_CLIENT_ID"),
        "M2MClientSecret": os.environ.get("M2M_CLIENT_SECRET"),
        "AgentCoreRoleArn": os.environ.get("AGENT_CORE_ROLE_ARN"),
        "LogMcpLambdaArn": os.environ.get("LOG_MCP_LAMBDA_ARN"),
        "KbMcpLambdaArn": os.environ.get("KB_MCP_LAMBDA_ARN"),
    }
    
    # Check if all required environment variables are set
    if all(value is not None for value in env_outputs.values()):
        logger.info("Using parameters from environment variables")
        return env_outputs
    
    # Fallback to CloudFormation API - try the nested stack first
    logger.info("Environment variables not set, falling back to CloudFormation API")
    cf = boto3.client("cloudformation")
    
    try:
        # Try to get from the common resources stack first (new approach)
        response = cf.describe_stacks(StackName="saas-genai-workshop-common-resources")
        outputs = response["Stacks"][0]["Outputs"]
        stack_outputs = {output["OutputKey"]: output["OutputValue"] for output in outputs}
        
        # Map the outputs to the expected keys
        mapped_outputs = {}
        for key, value in env_outputs.items():
            # Try to find matching output key (may have different naming)
            if key == "UserPoolId" and "TenantUserpoolId" in stack_outputs:
                mapped_outputs[key] = stack_outputs["TenantUserpoolId"]
            elif key == "UserClientId" and "UserPoolClientId" in stack_outputs:
                mapped_outputs[key] = stack_outputs["UserPoolClientId"]
            elif key in stack_outputs:
                mapped_outputs[key] = stack_outputs[key]
        
        # Check if we got all required outputs
        if len(mapped_outputs) == len(env_outputs):
            logger.info("Using parameters from common resources stack")
            return mapped_outputs
            
    except Exception as e:
        logger.warning(f"Could not get outputs from common resources stack: {e}")
    
    try:
        # Fallback to original AgentCoreStack (legacy approach)
        response = cf.describe_stacks(StackName="AgentCoreStack")
        outputs = response["Stacks"][0]["Outputs"]
        logger.info("Using parameters from AgentCoreStack (legacy)")
        return {output["OutputKey"]: output["OutputValue"] for output in outputs}
    except Exception as e:
        logger.error(f"Could not get outputs from any stack: {e}")
        raise


def destroy_gateway(name):
    logger.info(f"Destroying gateway: {name}")
    agentcore = boto3.client("bedrock-agentcore-control")

    gateways = agentcore.list_gateways()["items"]
    gateway = next((g for g in gateways if g["name"] == name), None)

    if gateway:
        gateway_id = gateway["gatewayId"]

        # Delete all targets first
        targets = agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
        for target in targets:
            agentcore.delete_gateway_target(
                gatewayIdentifier=gateway_id, targetId=target["targetId"]
            )

        # Delete gateway
        agentcore.delete_gateway(gatewayIdentifier=gateway_id)


def destroy_oauth_provider():
    logger.info("Destroying OAuth2 credential provider")
    try:
        agentcore = boto3.client("bedrock-agentcore-control")
        providers = agentcore.list_oauth2_credential_providers()

        for provider in providers.get("credentialProviders"):
            if provider["name"] == "cognito-m2m-provider":
                logger.info(f"Deleting provider by name: {provider['name']}")
                agentcore.delete_oauth2_credential_provider(name=provider["name"])
                return

        logger.info("No cognito-m2m-provider found (may not have been created)")

    except Exception as e:
        logger.error(f"Error destroying OAuth2 credential provider: {e}")


def destroy_agentcore_runtime():
    logger.info("Destroying AgentCore Runtime")
    try:
        agentcore = boto3.client("bedrock-agentcore-control")
        runtimes = agentcore.list_agent_runtimes()["agentRuntimes"]
        for runtime in runtimes:
            if "ops_agent" in runtime["agentRuntimeArn"]:
                # Extract ID from ARN and handle URL decoding
                arn_parts = runtime["agentRuntimeArn"].split("/")
                if len(arn_parts) >= 2:
                    runtime_id = arn_parts[-1]  # Get the last part after the last slash
                    agentcore.delete_agent_runtime(agentRuntimeId=runtime_id)
    except Exception as e:
        logger.error(f"Error destroying AgentCore runtime: {e}")


def create_log_mcp_server(
    role_arn,
    user_pool_id,
    user_client_id,
    m2m_client_id,
    region,
    log_lambda_arn,
    recreate=False,
):
    logger.info("1.1: Creating Log MCP Server")
    agentcore = boto3.client("bedrock-agentcore-control")

    if recreate:
        destroy_gateway("LogGateway")

    gateways = agentcore.list_gateways()["items"]
    gateway_id = next(
        (g["gatewayId"] for g in gateways if g["name"] == "LogGateway"), None
    )

    if not gateway_id:
        discovery_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration"
        response = agentcore.create_gateway(
            name="LogGateway",
            roleArn=role_arn,
            protocolType="MCP",
            protocolConfiguration={"mcp": {"searchType": "SEMANTIC"}},
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration={
                "customJWTAuthorizer": {
                    "discoveryUrl": discovery_url,
                    "allowedClients": [user_client_id, m2m_client_id],
                }
            },
            exceptionLevel="DEBUG",
        )
        gateway_id = response["gatewayId"]

    targets = agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
    if not next((t for t in targets if t["name"] == "LogSearchTarget"), None):
        agentcore.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name="LogSearchTarget",
            description="Searches cloud logs using free text queries",
            targetConfiguration={
                "mcp": {
                    "lambda": {
                        "lambdaArn": log_lambda_arn,
                        "toolSchema": {
                            "inlinePayload": [
                                {
                                    "name": "search_logs",
                                    "description": "Search logs using natural language queries",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "query": {
                                                "type": "string",
                                                "description": "Free text search query",
                                            },
                                            "timeRange": {
                                                "type": "object",
                                                "properties": {
                                                    "start": {"type": "string"},
                                                    "end": {"type": "string"},
                                                },
                                                "required": ["start", "end"],
                                            },
                                        },
                                        "required": ["query"],
                                    },
                                }
                            ]
                        },
                    }
                }
            },
            credentialProviderConfigurations=[
                {"credentialProviderType": "GATEWAY_IAM_ROLE"}
            ],
        )

    return gateway_id


def create_kb_mcp_server(
    role_arn,
    user_pool_id,
    user_client_id,
    m2m_client_id,
    region,
    kb_lambda_arn,
    recreate=False,
):
    logger.info("1.2: Creating KB MCP Server")
    agentcore = boto3.client("bedrock-agentcore-control")

    if recreate:
        destroy_gateway("KnowledgeBaseGateway")

    gateways = agentcore.list_gateways()["items"]
    gateway_id = next(
        (g["gatewayId"] for g in gateways if g["name"] == "KnowledgeBaseGateway"), None
    )

    if not gateway_id:
        discovery_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration"
        response = agentcore.create_gateway(
            name="KnowledgeBaseGateway",
            roleArn=role_arn,
            protocolType="MCP",
            protocolConfiguration={"mcp": {"searchType": "SEMANTIC"}},
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration={
                "customJWTAuthorizer": {
                    "discoveryUrl": discovery_url,
                    "allowedClients": [user_client_id, m2m_client_id],
                }
            },
            exceptionLevel="DEBUG",
        )
        gateway_id = response["gatewayId"]

    targets = agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
    if not next((t for t in targets if t["name"] == "KBSearchTarget"), None):
        agentcore.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name="KBSearchTarget",
            description="Searches knowledge base using natural language queries",
            targetConfiguration={
                "mcp": {
                    "lambda": {
                        "lambdaArn": kb_lambda_arn,
                        "toolSchema": {
                            "inlinePayload": [
                                {
                                    "name": "search_kb",
                                    "description": "Search knowledge base using natural language queries",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "query": {
                                                "type": "string",
                                                "description": "Free text search query",
                                            },
                                            "maxResults": {
                                                "type": "integer",
                                                "description": "Maximum number of results to return",
                                            },
                                        },
                                        "required": ["query"],
                                    },
                                }
                            ]
                        },
                    }
                }
            },
            credentialProviderConfigurations=[
                {"credentialProviderType": "GATEWAY_IAM_ROLE"}
            ],
        )

    return gateway_id


def update_access_token_file(provider_name):
    """Update access_token.py with the new provider name"""
    access_token_file = "../agent/access_token.py"
    
    with open(access_token_file, "r") as f:
        content = f.read()
    
    # Replace the provider name in the decorator
    updated_content = content.replace(
        'provider_name="cognito-m2m-provider"',
        f'provider_name="{provider_name}"'
    )
    
    with open(access_token_file, "w") as f:
        f.write(updated_content)
    
    logger.info(f"Updated access_token.py with provider name: {provider_name}")


def create_m2m_outbound_identity(
    m2m_client_id, m2m_client_secret, discovery_url, region, recreate=False
):
    logger.info("2.1: Creating M2M Outbound Identity")

    if recreate:
        destroy_oauth_provider()

    try:
        identity_client = IdentityClient(region=region)
        random_suffix = ''.join([str(random.randint(0, 9)) for _ in range(5)])
        provider_name = f"cognito-m2m{random_suffix}-provider"
        
        identity_client.create_oauth2_credential_provider(
            req={
                "name": provider_name,
                "credentialProviderVendor": "CustomOauth2",
                "oauth2ProviderConfigInput": {
                    "customOauth2ProviderConfig": {
                        "clientId": m2m_client_id,
                        "clientSecret": m2m_client_secret,
                        "oauthDiscovery": {"discoveryUrl": discovery_url},
                    }
                },
            }
        )
        
        # Update access_token.py with the new provider name
        update_access_token_file(provider_name)
        
        return provider_name
    except Exception as e:
        if "already exists" not in str(e):
            raise


def update_agent_runtime_with_gateways(log_gateway_id, kb_gateway_id, region, role_arn):
    logger.info("Updating agent runtime with gateway URLs")
    try:
        # Get agent runtime info
        agentcore = boto3.client("bedrock-agentcore-control")
        runtimes = agentcore.list_agent_runtimes()["agentRuntimes"]

        agent_runtime = None
        for runtime in runtimes:
            if "ops_agent" in runtime["agentRuntimeArn"]:
                agent_runtime = runtime
                break

        if not agent_runtime:
            logger.error("No ops_agent runtime found to update")
            return

        runtime_id = agent_runtime["agentRuntimeArn"].split("/")[-1]

        # Get current runtime details
        runtime_details = agentcore.get_agent_runtime(agentRuntimeId=runtime_id)

        # Construct gateway URLs
        log_gateway_url = f"https://{log_gateway_id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp"
        kb_gateway_url = f"https://{kb_gateway_id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp"

        # Update with environment variables
        agentcore.update_agent_runtime(
            agentRuntimeId=runtime_id,
            agentRuntimeArtifact=runtime_details["agentRuntimeArtifact"],
            roleArn=role_arn,
            networkConfiguration=runtime_details["networkConfiguration"],
            protocolConfiguration=runtime_details.get("protocolConfiguration"),
            authorizerConfiguration=runtime_details.get("authorizerConfiguration"),
            environmentVariables={
                "LOG_GATEWAY_URL": log_gateway_url,
                "KB_GATEWAY_URL": kb_gateway_url,
            },
        )

        logger.info(f"Updated agent runtime with gateway URLs")
        logger.info(f"LOG_GATEWAY_URL: {log_gateway_url}")
        logger.info(f"KB_GATEWAY_URL: {kb_gateway_url}")

    except Exception as e:
        logger.error(f"Error updating agent runtime: {e}")


def create_agentcore_runtime(
    discovery_url,
    user_client_id,
    m2m_client_id,
    log_gateway_id,
    kb_gateway_id,
    region,
    role_arn,
    recreate=False,
):
    logger.info("3: Creating AgentCore Runtime")

    if recreate:
        destroy_agentcore_runtime()
        # Clear agent-specific config to force fresh creation
        config_file = "../agent/.bedrock_agentcore.yaml"
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)

            # Null out agent-specific fields
            if "agents" in config and "ops_agent" in config["agents"]:
                config["agents"]["ops_agent"]["bedrock_agentcore"] = {
                    "agent_id": None,
                    "agent_arn": None,
                    "agent_session_id": None,
                }

            with open(config_file, "w") as f:
                yaml.safe_dump(config, f)

    agentcore_runtime = Runtime()

    with change_dir("../agent/"):
        agentcore_runtime.configure(
            entrypoint="main.py",
            auto_create_execution_role=True,
            auto_create_ecr=True,
            requirements_file="./requirements.txt",
            region=region,
            agent_name="ops_agent",
            protocol="HTTP",
            authorizer_configuration={
                "customJWTAuthorizer": {
                    "discoveryUrl": discovery_url,
                    "allowedClients": [user_client_id, m2m_client_id],
                }
            },
        )

        launch_result = agentcore_runtime.launch()
        logger.info(f"Agent ARN: {launch_result.agent_arn}")

        # Update runtime with gateway URLs
        update_agent_runtime_with_gateways(log_gateway_id, kb_gateway_id, region, role_arn)


@contextmanager
def change_dir(new_dir):
    prev_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(prev_dir)


def destroy_all():
    logger.info("Destroying all AgentCore resources")
    destroy_agentcore_runtime()
    destroy_oauth_provider()
    destroy_gateway("LogGateway")
    destroy_gateway("KnowledgeBaseGateway")


def main():
    parser = argparse.ArgumentParser(
        description="Deploy or destroy AgentCore resources"
    )
    parser.add_argument(
        "--destroy", action="store_true", help="Destroy all AgentCore resources"
    )
    args = parser.parse_args()

    if args.destroy:
        destroy_all()
        return

    stack_outputs = get_stack_outputs()

    user_pool_id = stack_outputs["UserPoolId"]
    user_client_id = stack_outputs["UserClientId"]
    m2m_client_id = stack_outputs["M2MClientId"]
    m2m_client_secret = stack_outputs["M2MClientSecret"]
    role_arn = stack_outputs["AgentCoreRoleArn"]
    log_lambda_arn = stack_outputs["LogMcpLambdaArn"]
    kb_lambda_arn = stack_outputs["KbMcpLambdaArn"]
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    discovery_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration"

    # Check if resources exist and recreate if needed
    agentcore = boto3.client("bedrock-agentcore-control")
    gateways = agentcore.list_gateways()["items"]
    log_exists = any(g["name"] == "LogGateway" for g in gateways)
    kb_exists = any(g["name"] == "KnowledgeBaseGateway" for g in gateways)

    logger.info("1: Creating MCP servers")
    log_gateway_id = create_log_mcp_server(
        role_arn,
        user_pool_id,
        user_client_id,
        m2m_client_id,
        region,
        log_lambda_arn,
        log_exists,
    )
    kb_gateway_id = create_kb_mcp_server(
        role_arn,
        user_pool_id,
        user_client_id,
        m2m_client_id,
        region,
        kb_lambda_arn,
        kb_exists,
    )

    logger.info("2: Creating AgentCore Outbound Identity")
    create_m2m_outbound_identity(
        m2m_client_id, m2m_client_secret, discovery_url, region, True
    )

    create_agentcore_runtime(
        discovery_url,
        user_client_id,
        m2m_client_id,
        log_gateway_id,
        kb_gateway_id,
        region,
        role_arn,
        True,
    )


if __name__ == "__main__":
    main()
