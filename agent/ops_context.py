# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from contextvars import ContextVar
from typing import Optional
import asyncio
import jwt

from streaming_queue import StreamingQueue
from orchestrator_agent import OrchestratorAgent


def decode_jwt_claims(token: str) -> dict:
    """Decode JWT token and return all claims as a dict"""
    try:
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        # Decode without verification (for development/testing)
        claims = jwt.decode(token, options={"verify_signature": False})
        return claims
    except Exception as e:
        return {"error": f"Failed to decode JWT: {str(e)}"}

class OpsContext:
    """Context Manager for Customer Support Assistant"""

    # Global state for tokens that persist across agent calls
    _gateway_token: Optional[str] = None
    _response_queue: Optional[StreamingQueue] = None
    _agent: Optional[OrchestratorAgent] = None
    _authorization_header: Optional[str] = None    

    _gateway_token_ctx: ContextVar[Optional[str]] = ContextVar(
        "gateway_token", default=None
    )
    _response_queue_ctx: ContextVar[Optional[StreamingQueue]] = ContextVar(
        "response_queue", default=None
    )
    _agent_ctx: ContextVar[Optional[OrchestratorAgent]] = ContextVar(
        "agent", default=None
    )
    _authorization_header_ctx: ContextVar[Optional[str]] = ContextVar(
        "authorization_header", default=None
    )

    @classmethod
    def get_response_queue_ctx(
        cls,
    ) -> Optional[StreamingQueue]:
        # First try to get from global state for persistence across calls
        if cls._response_queue:
            return cls._response_queue
        try:
            return cls._response_queue_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_response_queue_ctx(cls, queue: StreamingQueue) -> None:
        # Set both global state and context variable
        cls._response_queue = queue
        cls._response_queue_ctx.set(queue)

    @classmethod
    def get_gateway_token_ctx(
        cls,
    ) -> Optional[str]:
        # First try to get from global state for persistence across calls
        if cls._gateway_token:
            return cls._gateway_token
        try:
            return cls._gateway_token_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_gateway_token_ctx(cls, token: str) -> None:
        # Set both global state and context variable
        cls._gateway_token = token
        cls._gateway_token_ctx.set(token)

    @classmethod
    def get_agent_ctx(
        cls,
    ) -> Optional[OrchestratorAgent]:
        # First try to get from global state for persistence across calls
        if cls._agent:
            return cls._agent
        try:
            return cls._agent_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_agent_ctx(cls, agent: OrchestratorAgent) -> None:
        # Set both global state and context variable
        cls._agent = agent
        cls._agent_ctx.set(agent)

    @classmethod
    def get_authorization_header_ctx(cls) -> Optional[str]:
        if cls._authorization_header:
            return cls._authorization_header
        try:
            return cls._authorization_header_ctx.get()
        except LookupError:
            return None

    @classmethod
    def set_authorization_header_ctx(cls, header: str) -> None:
        cls._authorization_header = header
        cls._authorization_header_ctx.set(header)

