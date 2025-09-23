from strands import Agent, tool
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
import logging
import os

import ops_context

log = logging.Logger(__name__)
log.level = logging.DEBUG


@tool(name="query_kb", description="This tool searches Amazon Bedrock Knowledge base for SaaS application errors with tenant isolation. Performs RAG search limited to specific tenant data.")
def kb_agent_tool(query: str, tenant_id: str, top_k: int = 5) -> str:
    access_token = ops_context.OpsContext.get_gateway_token_ctx()

    # Get gateway URL from environment variable
    kb_gateway_url = os.environ.get("KB_GATEWAY_URL")
    if not kb_gateway_url:
        raise ValueError("KB_GATEWAY_URL environment variable is not set")

    streamable_http_mcp_client = MCPClient(
        lambda: streamablehttp_client(
            kb_gateway_url,
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
    )

    with streamable_http_mcp_client:
        kb_agent = Agent(
            name="kb_agent",
            system_prompt=f"You are a tenant-aware knowledge base agent that searches Amazon Bedrock Knowledge base for solutions to application errors for a SaaS application (multi-tenant). You must only query knowledge base using tenant_id: {tenant_id}. If there is no tenant_id, refuse to respond.",
            tools=streamable_http_mcp_client.list_tools_sync(),
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        )

        try:
            agent_response = kb_agent(f"Search knowledge base for tenant {tenant_id} with query: {query}. Specify the number of results to return in top {top_k} (optional). Ensure tenant isolation.")
            text_response = str(agent_response)

            if len(text_response) > 0:
                return text_response

            return "I apologize, but I couldn't find any KB entires for this query. Please try rephrasing it."
        except Exception as e:
            # Return specific error message for math processing
            return f"Error processing your KB query: {str(e)}"
