from strands import Agent, tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
import logging
import os

import ops_context

log = logging.Logger(__name__)
log.level = logging.DEBUG


@tool(name="query_logs", description="This tool allows you to query logs")
def log_agent_tool(query: str) -> str:
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
        log_agent = Agent(
            name="log_agent",
            system_prompt=f"You are an agent that can access a customer's cloud logs using its tools.",
            tools=streamable_http_mcp_client.list_tools_sync(),
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        )

        try:
            agent_response = log_agent(f"Please fetch the logs for {query}.")
            text_response = str(agent_response)

            if len(text_response) > 0:
                return text_response

            return "I apologize, but I couldn't find any logs for this query. Please try rephrasing it."
        except Exception as e:
            # Return specific error message for math processing
            return f"Error processing your log query: {str(e)}"
