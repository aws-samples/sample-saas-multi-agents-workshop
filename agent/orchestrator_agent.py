import json
import os
from strands import Agent, tool
import ops_context
from log_agent import log_agent_tool
from kb_agent import kb_agent_tool
from bedrock_agentcore.tools.code_interpreter_client import code_session
import asyncio
import jwt
from botocore.config import Config as BotocoreConfig
from strands.models import BedrockModel

from metrics_manager import record_metric

boto_cfg = BotocoreConfig(
    retries={"total_max_attempts": 10, "mode": "standard"}  # exponential backoff
)

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
    
class OrchestratorAgent:
    #def __init__(self) -> None:
    def __init__(self, bearer_token: str) -> None:
        decoded = ops_context.decode_jwt_claims(bearer_token)
        self.tenant_id = decoded.get("tenantId")

        self.agent = Agent(
            name="orchestrator",
            system_prompt="""You are the Orchestrator Agent for SmartResolve, a GenAI-powered autonomous intelligent resolution engine that revolutionizes technical support for organizations. This SaaS platform serves as a virtual agent, empowering on-call and technical teams to quickly identify, diagnose, and resolve complex technical issues by leveraging LLMs to analyze incidents, suggest troubleshooting steps, and provide actionable solutions in real time.

            You orchestrate a collaborative system of three specialized subagents:
            1. Knowledge Base Agent - investigates static technical documents using RAG powered by Amazon Bedrock Knowledge Bases
            2. Log Agent - analyzes dynamic, real-time application and system logs stored in Amazon S3
            3. Coder Agent (executePython) - generates and tests appropriate code fixes

            Your responsibilities:
            - Determine optimal resolution strategy to minimize downtime and reduce resolution time
            - Delegate tasks while maintaining tenant isolation

            Optimized Workflow:
            1. Search knowledge base using kb_agent
            2. IF knowledge base provides an answer - STOP and return that solution (saves time/resources)
            3. ONLY IF no solution found, query logs using log_agent
            4. Generate Python code solutions and test with executePython (Python code execution environment)

            Prioritize knowledge base answers as they are assumed credible and complete.
            Return raw logs if requested by the user.""",

            tools=[log_agent_tool, kb_agent_tool, execute_python],
            #model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            #model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0"
            model=BedrockModel(
                model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                boto_client_config=boto_cfg,
            )
        )

    def invoke(self, user_query: str):
        try:
            response = str(self.agent(user_query))

            # Log input and output tokens using the documented structure
            if hasattr(response, 'metrics') and hasattr(response.metrics, 'accumulated_usage'):
                accumulated_usage = response.metrics.accumulated_usage
                
                # Log input tokens
                if 'inputTokens' in accumulated_usage:
                    record_metric(self.tenant_id, "ModelInvocationInputTokens", "Count", accumulated_usage['inputTokens'])
                
                # Log output tokens  
                if 'outputTokens' in accumulated_usage:
                    record_metric(self.tenant_id, "ModelInvocationOutputTokens", "Count", accumulated_usage['outputTokens'])

        except Exception as e:
            return f"Error invoking agent: {e}"
        return response
    
    async def stream(self, user_query: str):
        try:
            # Decode JWT and yield claims as string representation
            # header = ops_context.OpsContext.get_authorization_header_ctx()
            # if not header:
            #     raise Exception("Authorization header not found")
            # claims = decode_jwt_claims(header)
            # yield f"JWT Claims: {json.dumps(claims)}\n\n"
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    # Only stream text chunks to the client
                    yield event["data"]

            # Log metrics after streaming completes
            if event and hasattr(event, 'metrics') and hasattr(event.metrics, 'accumulated_usage'):
                accumulated_usage = event.metrics.accumulated_usage
                
                # Log input tokens
                if 'inputTokens' in accumulated_usage:
                    record_metric(self.tenant_id, "ModelInvocationInputTokens", "Count", accumulated_usage['inputTokens'])
                
                # Log output tokens  
                if 'outputTokens' in accumulated_usage:
                    record_metric(self.tenant_id, "ModelInvocationOutputTokens", "Count", accumulated_usage['outputTokens'])

        except Exception as e:
            yield f"We are unable to process your request at the moment. Error: {e}"
