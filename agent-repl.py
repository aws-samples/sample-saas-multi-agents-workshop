#!/usr/bin/env python3

import os
import sys
import json
import uuid
import urllib.parse
import requests
import boto3
import getpass
import argparse
import logging
import time

logger = logging.getLogger(__name__)


def get_stack_outputs():
    logger.debug("Getting CloudFormation stack outputs")
    cf = boto3.client("cloudformation")
    response = cf.describe_stacks(StackName="AgentCoreStack")
    outputs = response["Stacks"][0]["Outputs"]
    result = {output["OutputKey"]: output["OutputValue"] for output in outputs}
    logger.debug(f"Stack outputs: {list(result.keys())}")
    return result


def get_agent_arn():
    logger.debug("Looking for ops_agent runtime")
    try:
        agentcore = boto3.client("bedrock-agentcore-control")
        runtimes = agentcore.list_agent_runtimes()["agentRuntimes"]
        for runtime in runtimes:
            if "ops_agent" in runtime["agentRuntimeArn"]:
                logger.debug(f"Found agent: {runtime['agentRuntimeArn']}")
                return runtime["agentRuntimeArn"]
    except Exception as e:
        logger.debug(f"Error finding agent: {e}")
    return None


def get_access_token():
    stack_outputs = get_stack_outputs()
    user_pool_id = stack_outputs["UserPoolId"]
    user_client_id = stack_outputs["UserClientId"]
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    logger.debug(f"Using user pool: {user_pool_id}")
    logger.debug(f"Using client: {user_client_id}")

    # Prompt for credentials
    username = input("Username (testuser): ").strip() or "testuser"
    password = getpass.getpass("Password (TempPassword123!): ") or "TempPassword123!"

    logger.debug("Authenticating with Cognito")

    try:
        cognito = boto3.client("cognito-idp", region_name=region)

        # Initial authentication
        response = cognito.initiate_auth(
            ClientId=user_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )

        logger.debug(f"Auth result keys: {list(response.keys())}")

        if "AuthenticationResult" in response:
            logger.debug("Authentication successful")
            return response["AuthenticationResult"]["AccessToken"]
        elif response.get("ChallengeName") == "NEW_PASSWORD_REQUIRED":
            logger.debug("New password required")
            print("New password required. Please set a new password.")
            new_password = getpass.getpass("New password: ")

            # Respond to auth challenge
            challenge_response = cognito.respond_to_auth_challenge(
                ClientId=user_client_id,
                ChallengeName="NEW_PASSWORD_REQUIRED",
                Session=response["Session"],
                ChallengeResponses={"USERNAME": username, "NEW_PASSWORD": new_password},
            )

            if "AuthenticationResult" in challenge_response:
                logger.debug("Password change successful")
                return challenge_response["AuthenticationResult"]["AccessToken"]
            else:
                logger.debug(f"Password change failed: {challenge_response}")
        else:
            logger.debug(f"Unexpected auth response: {response}")

    except Exception as e:
        logger.debug(f"Authentication error: {e}")

    return None


def get_recent_logs(agent_arn):
    """Get recent CloudWatch logs for the agent from multiple streams"""
    try:

        # Extract agent ID from ARN
        agent_id = agent_arn.split("/")[-1]
        log_group = f"/aws/bedrock-agentcore/runtimes/{agent_id}-DEFAULT"

        logs_client = boto3.client("logs")

        # Get logs from last 5 minutes across all streams
        end_time = int(time.time() * 1000)
        start_time = end_time - (5 * 60 * 1000)  # 5 minutes ago

        events_response = logs_client.filter_log_events(
            logGroupName=log_group, startTime=start_time, endTime=end_time, limit=50
        )

        if events_response["events"]:
            recent_logs = []
            for event in events_response["events"][-20:]:  # Last 20 events
                message = event["message"]
                recent_logs.append(message)
            return "\n".join(recent_logs)
        else:
            return "No recent log events found in the last 5 minutes"

    except Exception as e:
        return f"Error retrieving logs: {e}"


def invoke_agent_with_streaming(
    prompt: str, agent_arn: str, token: str, *, runtime_session_id=None
):
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    # URL encode the agent ARN
    escaped_agent_arn = urllib.parse.quote(agent_arn, safe="")

    # Construct the URL
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{escaped_agent_arn}/invocations?qualifier=DEFAULT"
    logger.debug(f"Invoking: {url}")

    # Set up headers
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": runtime_session_id
        or str(uuid.uuid4()),
    }
    logger.debug(
        f"Headers: {dict((k, v[:20] + '...' if k == 'Authorization' else v) for k, v in headers.items())}"
    )

    # Use with context manager for the request
    with requests.post(
        url, headers=headers, data=json.dumps({"prompt": prompt}), stream=True
    ) as response:

        logger.debug(f"Response status: {response.status_code}")

        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            logger.debug(f"Content-Type: {content_type}")

            # Handle streaming response
            if "text/event-stream" in content_type:
                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            if data.strip() and data != "[DONE]":
                                # Remove quotes and convert \n to actual newlines
                                clean_data = data.strip().strip('"').replace('\\n', '\n')
                                print(clean_data, end="", flush=True)
                print()  # Final newline

            else:
                # Handle non-streaming response
                try:
                    response_data = response.json()
                    print(json.dumps(response_data, indent=2))
                except Exception as e:
                    print(f"Error parsing response: {e}")
                    print(f"Raw response: {response.text}")

        else:
            print(f"Error: {response.status_code}")
            try:
                error_data = response.json()
                print(json.dumps(error_data, indent=2))

                # Check for runtime errors and show logs
                if (
                    response.status_code == 424
                    and "runtime" in error_data.get("message", "").lower()
                ):
                    print("\nRecent CloudWatch logs:")
                    print("=" * 50)
                    logs = get_recent_logs(agent_arn)
                    print(logs)
                    print("=" * 50)
            except:
                print(response.text)


def main():
    parser = argparse.ArgumentParser(description="AgentCore REPL")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")

    # Keep boto3/botocore at INFO level even in verbose mode
    logging.getLogger("boto3").setLevel(logging.INFO)
    logging.getLogger("botocore").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)

    print("AgentCore REPL - Getting agent information...")

    agent_arn = get_agent_arn()
    if not agent_arn:
        print("Error: No ops_agent runtime found")
        sys.exit(1)

    token = get_access_token()
    if not token:
        print("Error: Could not get access token")
        sys.exit(1)

    print(f"Connected to agent: {agent_arn}")
    print("Type 'quit' or 'exit' to quit\n")

    session_id = str(uuid.uuid4())
    logger.debug(f"Session ID: {session_id}")

    while True:
        try:
            prompt = input(">>> ").strip()

            if prompt.lower() in ["/quit", "/exit"]:
                break

            if not prompt:
                continue

            logger.debug(f"User prompt: {prompt}")
            invoke_agent_with_streaming(
                prompt, agent_arn, token, runtime_session_id=session_id
            )
            print()

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
