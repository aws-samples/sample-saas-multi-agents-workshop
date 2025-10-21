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

        print(self.tenant_id)

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
            result = self.agent(user_query)  # result is an AgentResult
            usage = result.metrics.accumulated_usage or {}
            input_tokens = int(usage.get("inputTokens", 0))
            output_tokens = int(usage.get("outputTokens", 0))
            total_tokens = int(usage.get("totalTokens", input_tokens + output_tokens))

            # record metrics per your tenant
            agent_name = self.agent.name
            record_metric(self.tenant_id, "ModelInvocationInputTokens", "Count", input_tokens, agent_name)
            record_metric(self.tenant_id, "ModelInvocationOutputTokens", "Count", output_tokens, agent_name)
            record_metric(self.tenant_id, "ModelInvocationTotalTokens", "Count", total_tokens, agent_name)

            return str(result.message) if hasattr(result, "message") else str(result)
        except Exception as e:
            return f"Error invoking agent: {e}"

    async def stream(self, user_query: str):
        try:
            final_result = None
            async for event in self.agent.stream_async(user_query):
                # Intermediate chunks
                if isinstance(event, dict) and "data" in event:
                    yield event["data"]
                
                # Capture the final event (last one will have "result")
                if isinstance(event, dict) and "result" in event:
                    final_result = event["result"]  # This is the AgentResult object

            # After loop, extract metrics from AgentResult
            if final_result is not None:
                usage = final_result.metrics.accumulated_usage  # Dict with keys: inputTokens, outputTokens, totalTokens
                input_tokens = int(usage.get("inputTokens", 0))
                output_tokens = int(usage.get("outputTokens", 0))
                total_tokens = int(usage.get("totalTokens", input_tokens + output_tokens))

                agent_name = self.agent.name
                record_metric(self.tenant_id, "ModelInvocationInputTokens", "Count", input_tokens, agent_name)
                record_metric(self.tenant_id, "ModelInvocationOutputTokens", "Count", output_tokens, agent_name)
                record_metric(self.tenant_id, "ModelInvocationTotalTokens", "Count", total_tokens, agent_name)

        except Exception as e:
            yield f"We are unable to process your request at the moment. Error: {e}"   