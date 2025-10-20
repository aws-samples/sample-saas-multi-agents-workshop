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

region = os.environ.get("AWS_REGION", "AWS_DEFAULT_REGION")

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
    cf = boto3.client("cloudformation",region_name=region)
    
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
            elif key == "M2MClientId" and "AgentCoreM2MClientId" in stack_outputs:
                mapped_outputs[key] = stack_outputs["AgentCoreM2MClientId"]
            elif key == "M2MClientSecret" and "AgentCoreM2MClientSecret" in stack_outputs:
                mapped_outputs[key] = stack_outputs["AgentCoreM2MClientSecret"]
            elif key == "LogMcpLambdaArn" and "AgentCoreLogMcpLambdaArn" in stack_outputs:
                mapped_outputs[key] = stack_outputs["AgentCoreLogMcpLambdaArn"]
            elif key == "KbMcpLambdaArn" and "AgentCoreKbMcpLambdaArn" in stack_outputs:
                mapped_outputs[key] = stack_outputs["AgentCoreKbMcpLambdaArn"]
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
    agentcore = boto3.client("bedrock-agentcore-control",region_name=region)

    try:
        gateways = agentcore.list_gateways()["items"]
        gateway = next((g for g in gateways if g["name"] == name), None)

        if gateway:
            gateway_id = gateway["gatewayId"]
            logger.info(f"Found gateway {name} with ID: {gateway_id}")

            # Delete all targets first
            try:
                targets = agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
                for target in targets:
                    logger.info(f"Deleting target: {target['name']}")
                    agentcore.delete_gateway_target(
                        gatewayIdentifier=gateway_id, targetId=target["targetId"]
                    )
                
                # Wait for all targets to be deleted before deleting gateway
                if targets:
                    wait_for_targets_deleted(agentcore, gateway_id, max_wait_time=300)
                    
            except Exception as e:
                logger.warning(f"Error deleting targets for gateway {name}: {e}")

            # Delete gateway
            try:
                agentcore.delete_gateway(gatewayIdentifier=gateway_id)
                logger.info(f"Gateway {name} deletion initiated")
            except Exception as e:
                logger.error(f"Error deleting gateway {name}: {e}")
        else:
            logger.info(f"Gateway {name} not found, skipping deletion")
    except Exception as e:
        logger.error(f"Error during gateway {name} destruction: {e}")


def destroy_oauth_provider():
    logger.info("Destroying OAuth2 credential provider")
    try:
        agentcore = boto3.client("bedrock-agentcore-control",region_name=region)
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
    agentcore = boto3.client("bedrock-agentcore-control",region_name=region)
    
    while True:
        try:
            runtimes = agentcore.list_agent_runtimes()["agentRuntimes"]
            runtime_to_delete = None
            
            for runtime in runtimes:
                if "ops_agent" in runtime["agentRuntimeArn"]:
                    runtime_to_delete = runtime
                    break
            
            if not runtime_to_delete:
                logger.info("No ops_agent runtime found to delete")
                break
                
            # Extract ID from ARN
            arn_parts = runtime_to_delete["agentRuntimeArn"].split("/")
            if len(arn_parts) >= 2:
                runtime_id = arn_parts[-1]
                agentcore.delete_agent_runtime(agentRuntimeId=runtime_id)
                logger.info("Agent runtime deletion initiated, waiting for completion...")
                
        except Exception as e:
            if "DELETING" in str(e):
                logger.info("Agent runtime is still deleting, waiting 5 seconds...")
                time.sleep(5)
                continue
            else:
                logger.error(f"Error destroying AgentCore runtime: {e}")
                break
        
        # Wait and check if deletion completed
        time.sleep(5)



def wait_for_gateway_active(agentcore, gateway_id, max_wait_time=300):
    """Wait for gateway to be in READY status before proceeding"""
    logger.info(f"Waiting for gateway {gateway_id} to be READY...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = agentcore.get_gateway(gatewayIdentifier=gateway_id)
            status = response.get("status", "UNKNOWN")
            logger.info(f"Gateway {gateway_id} status: {status}")
            
            if status == "READY":
                logger.info(f"Gateway {gateway_id} is now READY")
                return True
            elif status in ["FAILED", "DELETED"]:
                logger.error(f"Gateway {gateway_id} is in failed state: {status}")
                return False
            
            # Wait before checking again
            time.sleep(10)
            
        except Exception as e:
            logger.warning(f"Error checking gateway status: {e}")
            time.sleep(10)
    
    logger.error(f"Gateway {gateway_id} did not become READY within {max_wait_time} seconds")
    return False


def wait_for_targets_deleted(agentcore, gateway_id, max_wait_time=300):
    """Wait for all gateway targets to be deleted before proceeding with gateway deletion"""
    logger.info(f"Waiting for all targets to be deleted from gateway {gateway_id}...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            targets = agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
            
            if not targets:
                logger.info(f"All targets have been deleted from gateway {gateway_id}")
                return True
            
            logger.info(f"Gateway {gateway_id} still has {len(targets)} targets, waiting...")
            
            # Wait before checking again
            time.sleep(10)
            
        except Exception as e:
            # If we can't list targets, it might mean the gateway is already being deleted
            # or there's a temporary issue - log and continue waiting
            logger.warning(f"Error checking gateway targets: {e}")
            time.sleep(10)
    
    logger.error(f"Gateway {gateway_id} targets were not deleted within {max_wait_time} seconds")
    return False


def create_gateway_target_with_retry(agentcore, gateway_id, target_name, target_config, max_retries=5):
    """Create gateway target with exponential backoff retry logic"""
    for attempt in range(max_retries):
        try:
            logger.info(f"Creating {target_name} (attempt {attempt + 1}/{max_retries})...")
            agentcore.create_gateway_target(**target_config)
            logger.info(f"{target_name} created successfully")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Attempt {attempt + 1} failed for {target_name}: {error_msg}")
            
            if "CREATING" in error_msg or "ValidationException" in error_msg:
                # Gateway is still creating or in invalid state, wait with exponential backoff
                wait_time = min(30, 5 * (2 ** attempt))  # Cap at 30 seconds
                logger.warning(f"Gateway not ready, waiting {wait_time} seconds before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
                
                # Check gateway status again
                if not wait_for_gateway_active(agentcore, gateway_id, max_wait_time=60):
                    logger.error(f"Gateway {gateway_id} failed to become READY during retry")
                    if attempt == max_retries - 1:
                        raise Exception(f"Gateway {gateway_id} never became READY after {max_retries} attempts")
                    continue
            elif "already exists" in error_msg.lower():
                # Target already exists, this is actually success
                logger.info(f"{target_name} already exists, continuing...")
                return True
            else:
                # Different error, log and potentially retry
                logger.error(f"Failed to create {target_name}: {error_msg}")
                if attempt == max_retries - 1:
                    raise
                # Short wait before retry for other errors
                time.sleep(5)
    
    raise Exception(f"Failed to create {target_name} after {max_retries} attempts")


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
    agentcore = boto3.client("bedrock-agentcore-control",region_name=region)

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
        
        # Wait for gateway to be ready before creating targets
        if not wait_for_gateway_active(agentcore, gateway_id):
            raise Exception(f"Gateway {gateway_id} failed to become READY")
    else:
        # Even if gateway exists, make sure it's ready
        if not wait_for_gateway_active(agentcore, gateway_id):
            raise Exception(f"Existing gateway {gateway_id} is not in READY state")

    targets = agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
    if not next((t for t in targets if t["name"] == "LogSearchTarget"), None):
        target_config = {
            "gatewayIdentifier": gateway_id,
            "name": "LogSearchTarget",
            "description": "Searches tenant application logs using Amazon Athena-compatible queries",
            "targetConfiguration": {
                "mcp": {
                    "lambda": {
                        "lambdaArn": log_lambda_arn,
                        "toolSchema": {
                            "inlinePayload": [
                                {
                                    "name": "search_logs",
                                    "description": "Search logs using Amazon Athena-compatible queries",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "query": {
                                                "type": "string",
                                                "description": "Amazon Athena-compatible search query",
                                            },
                                            "tenant_id": {
                                                "type": "string",
                                                "description": "Tenant identifier for multi-tenant log isolation",
                                            },
                                        },
                                        "required": ["query", "tenant_id"],
                                    },
                                }
                            ]
                        },
                    }
                }
            },
            "credentialProviderConfigurations": [
                {"credentialProviderType": "GATEWAY_IAM_ROLE"}
            ],
        }
        create_gateway_target_with_retry(agentcore, gateway_id, "LogSearchTarget", target_config)

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
    agentcore = boto3.client("bedrock-agentcore-control",region_name=region)

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
        
        # Wait for gateway to be ready before creating targets
        if not wait_for_gateway_active(agentcore, gateway_id):
            raise Exception(f"Gateway {gateway_id} failed to become READY")
    else:
        # Even if gateway exists, make sure it's ready
        if not wait_for_gateway_active(agentcore, gateway_id):
            raise Exception(f"Existing gateway {gateway_id} is not in READY state")

    targets = agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
    if not next((t for t in targets if t["name"] == "KBSearchTarget"), None):
        target_config = {
            "gatewayIdentifier": gateway_id,
            "name": "KBSearchTarget",
            "description": "Searches knowledge base using natural language queries",
            "targetConfiguration": {
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
                                            "tenant_id": {
                                                "type": "string",
                                                "description": "Tenant identifier for multi-tenant knowledge base isolation",
                                            },
                                            "top_k": {
                                                "type": "integer",
                                                "description": "Maximum number of results to return",
                                            },
                                        },
                                        "required": ["query", "tenant_id"],
                                    },
                                }
                            ]
                        },
                    }
                }
            },
            "credentialProviderConfigurations": [
                {"credentialProviderType": "GATEWAY_IAM_ROLE"}
            ],
        }
        create_gateway_target_with_retry(agentcore, gateway_id, "KBSearchTarget", target_config)
    return gateway_id


def update_constants_file(provider_name, log_gateway_url, kb_gateway_url):
    """Update constants.py with the new values"""
    # Get the absolute path to the constants file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    constants_file = os.path.join(script_dir, "..", "..", "agent", "constants.py")

    # Write the entire file content
    content = f"""# ========= AUTO-GENERATED FILE =========
# WARNING: This file is auto-generated by the deploy script and will be overwritten.
# Do not edit manually - your changes will be lost on next deployment.

# ========= WORKAROUND =========
# We really should be using environment variables here.
# However, right now, there seems to be a bug with env variables
# and getting the authorization header, which is why we set
# the constants here.

ACCESS_TOKEN_PROVIDER_NAME = "{provider_name}"
LOG_MCP_SERVER_URL = "{log_gateway_url}"
KB_MCP_SERVER_URL = "{kb_gateway_url}"
"""

    with open(constants_file, "w") as f:
        f.write(content)

    logger.info(
        f"Updated constants.py with provider: {provider_name}, log URL: {log_gateway_url}, kb URL: {kb_gateway_url}"
    )



def create_m2m_outbound_identity(
    m2m_client_id, m2m_client_secret, discovery_url, region, recreate=False
):
    logger.info("2.1: Creating M2M Outbound Identity")

    if recreate:
        destroy_oauth_provider()

    try:
        identity_client = IdentityClient(region=region)

        # Check if a provider already exists
        agentcore = boto3.client("bedrock-agentcore-control",region_name=region)
        providers = agentcore.list_oauth2_credential_providers()

        existing_provider = None
        for provider in providers.get("credentialProviders", []):
            if provider["name"].startswith("cognito-m2m") and provider["name"].endswith(
                "-provider"
            ):
                existing_provider = provider["name"]
                logger.info(f"Found existing provider: {existing_provider}")
                break

        if existing_provider:
            provider_name = existing_provider
        else:
            # Create new provider
            random_suffix = "".join([str(random.randint(0, 9)) for _ in range(5)])
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
            logger.info(f"Created new provider: {provider_name}")

        return provider_name
    except Exception as e:
        if "already exists" not in str(e):
            raise


def create_agentcore_runtime(
    discovery_url,
    user_client_id,
    m2m_client_id,
    region,
    role_arn,
    recreate=False,
):
    if recreate:
        destroy_agentcore_runtime()
        # Clear agent-specific config to force fresh creation
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(script_dir, "..", "..", "agent", ".bedrock_agentcore.yaml")
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

    # Get the absolute path to the agent directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    agent_dir = os.path.join(script_dir, "..", "..", "agent")
    
    with change_dir(agent_dir):
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

        launch_result = agentcore_runtime.launch(
            auto_update_on_conflict=True,
        )
        logger.info(f"Agent ARN: {launch_result.agent_arn}")

    agentcore = boto3.client("bedrock-agentcore-control",region_name=region)
    runtime_details = agentcore.get_agent_runtime(agentRuntimeId=launch_result.agent_id)

    agentcore.update_agent_runtime(
        agentRuntimeId=launch_result.agent_id,
        agentRuntimeArtifact=runtime_details["agentRuntimeArtifact"],
        roleArn=role_arn,
        networkConfiguration=runtime_details["networkConfiguration"],
        protocolConfiguration=runtime_details.get("protocolConfiguration"),
        authorizerConfiguration=runtime_details.get("authorizerConfiguration"),
        # DISABLED DUE TO THE WEIRD ISSUE WITH THE RUNTIME, HOPEFULLY WE CAN RE:ENABLE THIS SOON
        # environmentVariables={
        #     "LOG_GATEWAY_URL": log_gateway_url,
        #     "KB_GATEWAY_URL": kb_gateway_url,
        # },
        requestHeaderConfiguration={"requestHeaderAllowlist": ["Authorization"]},
    )


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
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate resources instead of skipping creation.",
    )

    args = parser.parse_args()

    if args.destroy:
        destroy_all()
        return

    stack_outputs = get_stack_outputs()

    print("Stack outputs:")
    print(stack_outputs)

    user_pool_id = stack_outputs["UserPoolId"]
    user_client_id = stack_outputs["UserClientId"]
    m2m_client_id = stack_outputs["M2MClientId"]
    m2m_client_secret = stack_outputs["M2MClientSecret"]
    role_arn = stack_outputs["AgentCoreRoleArn"]
    log_lambda_arn = stack_outputs["LogMcpLambdaArn"]
    kb_lambda_arn = stack_outputs["KbMcpLambdaArn"]
    discovery_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration"

    # Check if resources exist and recreate if needed
    agentcore = boto3.client("bedrock-agentcore-control",region_name=region)
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
        log_exists and args.recreate,
    )
    kb_gateway_id = create_kb_mcp_server(
        role_arn,
        user_pool_id,
        user_client_id,
        m2m_client_id,
        region,
        kb_lambda_arn,
        kb_exists and args.recreate,
    )

    logger.info("2: Creating AgentCore Outbound Identity")
    m2m_provider_name = create_m2m_outbound_identity(
        m2m_client_id, m2m_client_secret, discovery_url, region, args.recreate
    )

    logger.info("3: Creating AgentCore Runtime")
    logger.info("3.1: Writing constants file")

    # Update constants.py with the new values
    log_gateway_url = (
        f"https://{log_gateway_id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp"
    )
    kb_gateway_url = (
        f"https://{kb_gateway_id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp"
    )
    update_constants_file(m2m_provider_name, log_gateway_url, kb_gateway_url)

    logger.info("3.2: Creating AgentCore Runtime")
    create_agentcore_runtime(
        discovery_url,
        user_client_id,
        m2m_client_id,
        # log_gateway_id,
        # kb_gateway_id,
        region,
        role_arn,
        args.recreate,
    )


if __name__ == "__main__":
    main()
