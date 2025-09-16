import json
import os
from strands import Agent, tool
from log_agent import log_agent_tool
from kb_agent import kb_agent_tool


class OrchestratorAgent:
    def __init__(self, bearer_token: str) -> None:
        self.agent = Agent(
            name="orchestrator",
            system_prompt="""You are an orchestrator agent that coordinates between logging and knowledge base operations. Use the log_agent for logging tasks and kb_agent for knowledge base queries.""",
            tools=[log_agent_tool, kb_agent_tool],
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        )

    def invoke(self, user_query: str):
        try:
            response = str(self.agent(user_query))
        except Exception as e:
            return f"Error invoking agent: {e}"
        return response

    async def stream(self, user_query: str):
        try:
            async for event in self.agent.stream_async(user_query):
                if "data" in event:
                    # Only stream text chunks to the client
                    yield event["data"]

        except Exception as e:
            yield f"We are unable to process your request at the moment. Error: {e}"
