# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient
from strands import Agent, tool
from botocore.config import Config as BotocoreConfig
from strands.models import BedrockModel

import logging
import ops_context
import wrapped_tool
import constants
from metrics_manager import record_metric

log = logging.Logger(__name__)
log.level = logging.DEBUG

boto_cfg = BotocoreConfig(
    retries={"total_max_attempts": 10, "mode": "standard"}  # exponential backoff
)

@tool(name="query_logs", description="This tool allows you to query tenant application logs using Amazon Athena-compatible queries")
def log_agent_tool(query: str) -> str:
    access_token = ops_context.OpsContext.get_authorization_header_ctx()
    if not access_token:
        raise ValueError("Authorization header is not set")

    # Workaround for AgentCore Runtime Bug
    log_gateway_url = constants.LOG_MCP_SERVER_URL
    if not log_gateway_url:
        raise ValueError("LOG_GATEWAY_URL environment variable is not set")

    streamable_http_mcp_client = MCPClient(
        lambda: streamablehttp_client(
            log_gateway_url,
            headers={
                "Authorization": f"{access_token}",
            },
        )
    )

    decoded = ops_context.decode_jwt_claims(access_token)
    tenant_id = decoded.get("tenantId")

    with streamable_http_mcp_client:
        tools = []

        for t in streamable_http_mcp_client.list_tools_sync():
            if t.tool_name != "x_amz_bedrock_agentcore_search":
                tool = wrapped_tool.WrappedTool(t)
                tool.bind_param("tenant_id", tenant_id)

                tools.append(tool)
            else:
                tools.append(t)
            
        system_prompt = """You are a log analysis agent that searches tenant application logs using Amazon Athena-compatible SQL queries.

        TENANT_LOGS SCHEMA:
        - timestamp (string): Log timestamp in ISO format
        - level (string): Log level (INFO, ERROR, WARN, DEBUG)
        - environment (string): Environment name
        - component (string): Application component
        - correlation_id (string): Request correlation ID
        - request_id (string): Unique request ID
        - event (string): Event type/name
        - path (string): Request path
        - job (string): Job identifier
        - tenant_id (string): tenant_id
        - status (string): Status code/message
        - detail (string): Detailed log message

        QUERY EXAMPLES:
        1. Get all logs: SELECT * FROM tenant_logs
        2. Find errors: SELECT * FROM tenant_logs WHERE level = 'ERROR'
        3. Search by time range: SELECT * FROM tenant_logs WHERE timestamp >= '2025-09-22T23:00:00Z'
        4. Count errors by component: SELECT component, COUNT(*) as error_count FROM tenant_logs WHERE level = 'ERROR' GROUP BY component
        5. Recent errors: SELECT * FROM tenant_logs WHERE level = 'ERROR' ORDER BY timestamp DESC LIMIT 10

        IF REQUESTED TO RETURN EXACT LOG ENTRIES - RETURN THEM TO THE CALLER.
        """

        log_agent = Agent(
            name="log_agent",
            system_prompt=system_prompt,
            tools=tools,
            #model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            #model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0"
            model=BedrockModel(
                model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                boto_client_config=boto_cfg,
            )
        )

        try:
            agent_response = log_agent(f"Execute this log query: {query}")
            
            usage = agent_response.metrics.accumulated_usage or {}
            input_tokens = int(usage.get("inputTokens", 0))
            output_tokens = int(usage.get("outputTokens", 0))
            total_tokens = int(usage.get("totalTokens", input_tokens + output_tokens))
            
            agent_name = log_agent.name
            record_metric(tenant_id, "ModelInvocationInputTokens", "Count", input_tokens, agent_name)
            record_metric(tenant_id, "ModelInvocationOutputTokens", "Count", output_tokens, agent_name)
            record_metric(tenant_id, "ModelInvocationTotalTokens", "Count", total_tokens, agent_name)
            
            text_response = str(agent_response)

            if len(text_response) > 0:
                return text_response

            return "No logs found for this query. Try adjusting the search criteria."
        except Exception as e:
            return f"Error processing log query: {str(e)}"
