from strands import Agent, tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
import logging
import os

import ops_context

log = logging.Logger(__name__)
log.level = logging.DEBUG


@tool(name="query_logs", description="This tool allows you to query tenant application logs using Amazon Athena-compatible queries")
def log_agent_tool(query: str, tenant_id: str) -> str:
    access_token = ops_context.OpsContext.get_gateway_token_ctx()

    # Get gateway URL from environment variable
    log_gateway_url = os.environ.get("LOG_GATEWAY_URL")
    if not log_gateway_url:
        raise ValueError("LOG_GATEWAY_URL environment variable is not set")

    streamable_http_mcp_client = MCPClient(
        lambda: streamablehttp_client(
            log_gateway_url,
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
    )

    with streamable_http_mcp_client:
            system_prompt = f"""You are a log analysis agent that searches tenant application logs using Amazon Athena-compatible SQL queries.

            TENANT_LOGS SCHEMA:
            - timestamp (string): Log timestamp in ISO format
            - level (string): Log level (INFO, ERROR, WARN, DEBUG)
            - tenant (string): Tenant identifier
            - environment (string): Environment name
            - component (string): Application component
            - correlation_id (string): Request correlation ID
            - request_id (string): Unique request ID
            - event (string): Event type/name
            - path (string): Request path
            - job (string): Job identifier
            - status (string): Status code/message
            - entity_id (string): Entity identifier
            - detail (string): Detailed log message

            QUERY EXAMPLES:
            1. Get all logs for tenant: SELECT * FROM tenant_logs WHERE tenant = '{tenant_id}'
            2. Find errors: SELECT * FROM tenant_logs WHERE tenant = '{tenant_id}' AND level = 'ERROR'
            3. Search by time range: SELECT * FROM tenant_logs WHERE tenant = '{tenant_id}' AND timestamp >= '2025-09-22T23:00:00Z'
            4. Find specific events: SELECT * FROM tenant_logs WHERE tenant = '{tenant_id}' AND event = 'python_exception'
            5. Search by correlation ID: SELECT * FROM tenant_logs WHERE tenant = '{tenant_id}' AND correlation_id = 'corr_123'
            6. Count errors by component: SELECT component, COUNT(*) as error_count FROM tenant_logs WHERE tenant = '{tenant_id}' AND level = 'ERROR' GROUP BY component
            7. Recent errors: SELECT * FROM tenant_logs WHERE tenant = '{tenant_id}' AND level = 'ERROR' ORDER BY timestamp DESC LIMIT 10

            Always include tenant filter in queries for security. Focus on finding errors and patterns that help troubleshoot issues."""

            log_agent = Agent(
                name="log_agent",
                system_prompt=system_prompt,
                tools=streamable_http_mcp_client.list_tools_sync(),
                model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            )

            try:
                agent_response = log_agent(f"Execute this log query for tenant {tenant_id}: {query}")
                text_response = str(agent_response)

                if len(text_response) > 0:
                    return text_response

                return "No logs found for this query. Try adjusting the search criteria."
            except Exception as e:
                return f"Error processing log query: {str(e)}"
