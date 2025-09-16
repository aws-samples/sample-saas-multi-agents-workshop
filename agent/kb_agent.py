from strands import Agent, tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
import logging
import os

import ops_context

log = logging.Logger(__name__)
log.level = logging.DEBUG


@tool(name="query_kb", description="This tool allows you to query a knowledgebase")
def kb_agent_tool(query: str) -> str:
    """Use this tool to make up logs in JSON format for debugging purposes."""
    access_token = ops_context.OpsContext.get_gateway_token_ctx()

    # Get gateway URL from environment variable
    log_gateway_url = os.environ.get("KB_GATEWAY_URL")
    if not log_gateway_url:
        raise ValueError("KB_GATEWAY_URL environment variable is not set")

    streamable_http_mcp_client = MCPClient(
        lambda: streamablehttp_client(
            log_gateway_url,
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
    )

    with streamable_http_mcp_client:
        kb_agent = Agent(
            name="kb_agent",
            system_prompt=f"You are an agent that searches a Knowledgebase for ops-related code.",
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        )

        try:
            agent_response = kb_agent(f"Please fetch KB entries for {query}.")
            text_response = str(agent_response)

            if len(text_response) > 0:
                return text_response

            return "I apologize, but I couldn't find any KB entires for this query. Please try rephrasing it."
        except Exception as e:
            # Return specific error message for math processing
            return f"Error processing your KB query: {str(e)}"
