import json
import os
import re
import uuid
from strands import Agent, tool
from log_agent import log_agent_tool
from kb_agent import kb_agent_tool
from bedrock_agentcore.tools.code_interpreter_client import code_session
import asyncio
from mcp.client.streamable_http import streamablehttp_client
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.tools.mcp import MCPClient
import re
from metrics_manager import record_metric
import boto3  

# Define and configure the code interpreter tool
@tool(name="executePython", description="Execute Python code")
def execute_python(code: str, description: str = "") -> str:
    """Execute Python code"""

    if description:
        code = f"# {description}\n{code}"

    # Print code to be executed
    print(f"\n Code: {code}")

    # Call the Invoke method and execute the generated code, within the initialized code interpreter session
    with code_session("us-east-1") as code_client:
        response = code_client.invoke(
            "executeCode", {"code": code, "language": "python", "clearContext": False}
        )

    for event in response["stream"]:
        return json.dumps(event["result"])


class CustomConversationManager(SlidingWindowConversationManager):
    def __scrub_tenant_id(self, messages, uuid_pattern=r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}'):
        def scrub_value(value):
            if isinstance(value, str):
                return re.sub(uuid_pattern, '<tenant_id_scrubbed>', value)
            elif isinstance(value, list):
                return [scrub_value(v) for v in value]
            elif isinstance(value, dict):
                return {k: scrub_value(v) for k, v in value.items()}
            else:
                return value

        for i, msg in enumerate(messages):
            messages[i] = scrub_value(msg)
    
    def apply_management(self, messages):
        self.__scrub_tenant_id(messages=messages)
        return super().apply_management(messages)


class OrchestratorAgent:
    def __init__(self, bearer_token: str, mcp_server_url: str = None) -> None:
        if mcp_server_url:
            # Use MCP client when server URL is provided
            self.mcp_client = MCPClient(lambda: streamablehttp_client(mcp_server_url))
            with self.mcp_client:
                self.agent = Agent(
                    name="orchestrator",
                    system_prompt="""You are the Orchestrator Agent for SmartResolve, a GenAI-powered autonomous intelligent resolution engine that revolutionizes technical support for organizations. This SaaS platform serves as a virtual agent, empowering on-call and technical teams to quickly identify, diagnose, and resolve complex technical issues by leveraging LLMs to analyze incidents, suggest troubleshooting steps, and provide actionable solutions in real time.

            You orchestrate a collaborative system of three specialized subagents:
            1. Knowledge Base Agent - investigates static technical documents using RAG powered by Amazon Bedrock Knowledge Bases
            2. Log Agent - analyzes dynamic, real-time application and system logs stored in Amazon S3
            3. Coder Agent (executePython) - generates and tests appropriate code fixes

            Your responsibilities:
            - Extract tenant_id from queries (company names like 'clearpay', 'mediops', or tenant codes, such as uuid or similar)
            - Determine optimal resolution strategy to minimize downtime and reduce resolution time
            - Delegate tasks while maintaining tenant isolation

            Optimized Workflow:
            1. ALWAYS identify tenant_id from the query (explicit or implied)
            2. Search knowledge base using kb_agent with tenant_id
            3. IF knowledge base provides credible, complete answer - STOP and return that solution (saves time/resources)
            4. IF no solution found, query logs using log_agent with tenant_id (filter for recent errors)
            5. Generate Python code solutions and test with executePython
            6. ALWAYS pass tenant_id to kb_agent and log_agent (skip for executePython)

            Prioritize knowledge base answers as they are assumed credible and complete.""",
                    tools=self.mcp_client.list_tools_sync(),
                    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                    conversation_manager=CustomConversationManager()
                )
        else:
            # Fallback to original implementation
            self.mcp_client = None
            self.agent = Agent(
                name="orchestrator",
                system_prompt="""You are the Orchestrator Agent for SmartResolve, a GenAI-powered autonomous intelligent resolution engine that revolutionizes technical support for organizations. This SaaS platform serves as a virtual agent, empowering on-call and technical teams to quickly identify, diagnose, and resolve complex technical issues by leveraging LLMs to analyze incidents, suggest troubleshooting steps, and provide actionable solutions in real time.

            You orchestrate a collaborative system of three specialized subagents:
            1. Knowledge Base Agent - investigates static technical documents using RAG powered by Amazon Bedrock Knowledge Bases
            2. Log Agent - analyzes dynamic, real-time application and system logs stored in Amazon S3
            3. Coder Agent (executePython) - generates and tests appropriate code fixes

            Your responsibilities:
            - Extract tenant_id from queries (company names like 'clearpay', 'mediops', or tenant codes)
            - Determine optimal resolution strategy to minimize downtime and reduce resolution time
            - Delegate tasks while maintaining tenant isolation

            Optimized Workflow:
            1. ALWAYS identify tenant_id from the query (explicit or implied)
            2. Search knowledge base using kb_agent with tenant_id
            3. IF knowledge base provides credible, complete answer - STOP and return that solution (saves time/resources)
            4. IF no solution found, query logs using log_agent with tenant_id (filter for recent errors)
            5. Generate Python code solutions and test with executePython
            6. ALWAYS pass tenant_id to kb_agent and log_agent (skip for executePython)

            Prioritize knowledge base answers as they are assumed credible and complete.""",
                tools=[log_agent_tool, kb_agent_tool, execute_python],
                model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            )

    def _extract_tenant_id(self, user_query: str, explicit_tenant_id: str = None) -> str:
        """Extract tenant_id from query using Bedrock Claude model"""
        if explicit_tenant_id:
            return explicit_tenant_id
        
        try:
            bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
            
            prompt = f"""Extract the tenant ID from this query. Look for:
                - Company names: clearpay, mediops
                - Explicit tenant IDs or UUIDs
                - Any tenant identifiers

                Query: {user_query}

                Return ONLY the tenant ID (no explanation). If none found, return 'unknown'."""
            
            response = bedrock.invoke_model(
                modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 50,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            
            result = json.loads(response['body'].read())
            return result['content'][0]['text'].strip()
            
        except Exception:
            return "unknown"

    def invoke(self, user_query: str, tenant_id: str = None):
        try:
            # Extract tenant_id from query if not explicitly provided
            resolved_tenant_id = self._extract_tenant_id(user_query, tenant_id)
            
            if tenant_id:
                input_text_with_context = f'{user_query} for tenant id {tenant_id}'
            else:
                input_text_with_context = user_query
            
            # Get the full AgentResult object
            result = self.agent(input_text_with_context)
            
            # Log input and output tokens using the documented structure
            if hasattr(result, 'metrics') and hasattr(result.metrics, 'accumulated_usage'):
                accumulated_usage = result.metrics.accumulated_usage
                
                # Log input tokens
                if 'inputTokens' in accumulated_usage:
                    record_metric(resolved_tenant_id, "ModelInvocationInputTokens", "Count", accumulated_usage['inputTokens'])
                
                # Log output tokens  
                if 'outputTokens' in accumulated_usage:
                    record_metric(resolved_tenant_id, "ModelInvocationOutputTokens", "Count", accumulated_usage['outputTokens'])
            
            # Return the response as string
            return str(result)
            
        except Exception as e:
            return f"Error invoking agent: {e}"

    async def stream(self, user_query: str, tenant_id: str = None):
        try:
            # Extract tenant_id from query if not explicitly provided
            resolved_tenant_id = self._extract_tenant_id(user_query, tenant_id)
            
            if tenant_id:
                input_text_with_context = f'{user_query} for tenant id {tenant_id}'
            else:
                input_text_with_context = user_query
                
            # For streaming, collect the final result to log metrics
            final_result = None
            
            async for event in self.agent.stream_async(input_text_with_context):
                if "data" in event:
                    yield event["data"]
                # Capture the final result when streaming completes
                if "result" in event:
                    final_result = event["result"]
            
            # Log metrics after streaming completes
            if final_result and hasattr(final_result, 'metrics') and hasattr(final_result.metrics, 'accumulated_usage'):
                accumulated_usage = final_result.metrics.accumulated_usage
                
                # Log input tokens
                if 'inputTokens' in accumulated_usage:
                    record_metric(resolved_tenant_id, "ModelInvocationInputTokens", "Count", accumulated_usage['inputTokens'])
                
                # Log output tokens  
                if 'outputTokens' in accumulated_usage:
                    record_metric(resolved_tenant_id, "ModelInvocationOutputTokens", "Count", accumulated_usage['outputTokens'])
                
        except Exception as e:
            yield f"We are unable to process your request at the moment. Error: {e}"
