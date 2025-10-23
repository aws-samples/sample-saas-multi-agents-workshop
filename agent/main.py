# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import contextvars

from bedrock_agentcore import BedrockAgentCoreApp
import logging
import asyncio

from ops_context import OpsContext
from orchestrator_agent import OrchestratorAgent
from access_token import get_token
from streaming_queue import StreamingQueue

# logging.basicConfig(level=logging.DEBUG)
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
app = BedrockAgentCoreApp(debug=True)


async def agent_task(user_message: str, session_id: str):
    agent = OpsContext.get_agent_ctx()

    response_queue = OpsContext.get_response_queue_ctx()
    gateway_access_token = OpsContext.get_gateway_token_ctx()

    if not response_queue:
        raise RuntimeError("Response queue is None")

    if not gateway_access_token:
        raise RuntimeError("Access token is None")

    try:
        if agent is None:
            # memory_hook = MemoryHook(
            #     memory_client=memory_client,
            #     memory_id=get_ssm_parameter("/app/customersupport/agentcore/memory_id"),
            #     actor_id=actor_id,
            #     session_id=session_id,
            # )

            #agent = OrchestratorAgent()
            agent = OrchestratorAgent(
                bearer_token=gateway_access_token,
                # memory_hook=memory_hook,
                # tools=[get_calendar_events_today, create_calendar_event],
            )
            OpsContext.set_agent_ctx(agent)

        async for chunk in agent.stream(user_query=user_message):
            await response_queue.put(chunk)

    except Exception as e:
        logger.exception("Agent execution failed.")
        await response_queue.put(f"Error: {str(e)}")
    finally:
        await response_queue.finish()


REQUEST_HEADERS: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "REQUEST_HEADERS", default={}
)


class CaptureHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        REQUEST_HEADERS.set(dict(request.headers))
        return await call_next(request)


app.add_middleware(CaptureHeadersMiddleware)


@app.entrypoint
async def agent_invocation(payload, context):
    # auth_header = context.request_headers.get("Authorization")

    headers = REQUEST_HEADERS.get({})
    auth_header = headers.get("authorization")  # Headers accessible here

    if not auth_header:
        print(f"==========################### Headers ###################==========")
        for key, value in headers:
            print(f"\t\t\t{key}: {value}")

        raise Exception("Authorization header not found")

    if not OpsContext.get_response_queue_ctx():
        OpsContext.set_response_queue_ctx(StreamingQueue())

    # if not OpsContext.get_gateway_token_ctx():
    #     OpsContext.set_gateway_token_ctx("Foobar")
    #     # OpsContext.set_gateway_token_ctx(await get_token(access_token=""))

    if not OpsContext.get_gateway_token_ctx():
        OpsContext.set_gateway_token_ctx(auth_header)    

    if not OpsContext.get_authorization_header_ctx():
        print(
            f"==========################### Auth header is {auth_header} ###################=========="
        )
        OpsContext.set_authorization_header_ctx(auth_header)

    user_message = payload["prompt"]
    # actor_id = payload["actor_id"]

    session_id = context.session_id
    if not session_id:
        raise Exception("Context session_id is not set")

    task = asyncio.create_task(
        agent_task(
            user_message=user_message,
            session_id=session_id,
            # actor_id=actor_id,
        )
    )

    response_queue = OpsContext.get_response_queue_ctx()
    if response_queue is None:
        raise RuntimeError("Response queue is None")

    async def stream_output():
        async for item in response_queue.stream():
            yield item
        await task  # Ensure task completion

    return stream_output()


if __name__ == "__main__":
    app.run()
