from strands import Agent, tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
import logging
import os

import wrapped_tool
import ops_context
import constants

import ops_context

log = logging.Logger(__name__)
log.level = logging.DEBUG


@tool(name="query_kb", description="This tool searches Amazon Bedrock Knowledge base.")
def kb_agent_tool(query: str, top_k: int = 5) -> str:
    access_token = ops_context.OpsContext.get_authorization_header_ctx()
    if not access_token:
        raise ValueError("Authorization header is not set")

    # Get gateway URL from environment variable
    kb_gateway_url = constants.KB_MCP_SERVER_URL
    if not kb_gateway_url:
        raise ValueError("KB_GATEWAY_URL environment variable is not set")

    streamable_http_mcp_client = MCPClient(
        lambda: streamablehttp_client(
            kb_gateway_url,
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

        kb_agent = Agent(
            name="kb_agent",
            system_prompt=f"""You are a knowledge base agent that searches Amazon Bedrock Knowledge base for solutions to application errors.""",
            tools=tools,
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        )

        try:
            agent_response = kb_agent(f"Search knowledge base with query: {query}. Specify the number of results to return in top {top_k} (optional).")
            text_response = str(agent_response)

            if len(text_response) > 0:
                return text_response

            return "I apologize, but I couldn't find any KB entires for this query. Please try rephrasing it."
        except Exception as e:
            # Return specific error message for math processing
            return f"Error processing your KB query: {str(e)}"
