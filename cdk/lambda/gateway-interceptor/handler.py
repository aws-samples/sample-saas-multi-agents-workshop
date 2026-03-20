# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Gateway Interceptor Lambda Handler for AgentCore Gateway.

This is a REQUEST interceptor that extracts tenantId from the JWT token
in the Authorization header and injects tenant_id into MCP tool call
arguments before the request reaches the target Lambda.

The gateway's CUSTOM_JWT authorizer has already validated the token.
We decode it here (without verification) only to extract the tenantId claim.
"""

import json
import logging
import base64
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    """
    Decode JWT payload without verification.

    The gateway's CUSTOM_JWT authorizer has already validated the token.
    We only need to read the claims.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")

    payload_b64 = parts[1]
    # Add padding if needed
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding

    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    return json.loads(payload_bytes)


def _extract_tenant_id(headers: Dict[str, str]) -> Optional[str]:
    """Extract tenantId from the Authorization header's JWT claims."""
    auth_header = headers.get("Authorization") or headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "").replace("bearer ", "").strip()
    if not token:
        return None

    try:
        claims = _decode_jwt_payload(token)
        return claims.get("tenantId") or claims.get("custom:tenantId")
    except Exception as e:
        logger.warning(f"Failed to decode JWT: {e}")
        return None


def _inject_tenant_id_into_tool_call(body: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Inject tenant_id into MCP tools/call arguments.

    For tools/call requests, the arguments are in body.params.arguments.
    For other MCP methods (tools/list, initialize, etc.), pass through unchanged.
    """
    method = body.get("method", "")
    if method != "tools/call":
        return body

    params = body.get("params", {})
    arguments = params.get("arguments", {})

    # Inject tenant_id (overwrites any agent-supplied value)
    arguments["tenant_id"] = tenant_id

    # Return modified body
    modified = body.copy()
    modified["params"] = {**params, "arguments": arguments}
    return modified


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AgentCore Gateway REQUEST interceptor.

    Receives the MCP request, extracts tenantId from the JWT in the
    Authorization header, and injects tenant_id into tool call arguments.

    Event format (interceptorInputVersion 1.0):
    {
        "interceptorInputVersion": "1.0",
        "mcp": {
            "gatewayRequest": {
                "body": { "jsonrpc": "2.0", "method": "tools/call", ... },
                "headers": { "Authorization": "Bearer <token>", ... }
            }
        }
    }
    """
    correlation_id = str(uuid.uuid4())

    try:
        mcp_data = event.get("mcp", {})
        gateway_request = mcp_data.get("gatewayRequest", {})
        request_body = gateway_request.get("body", {})
        headers = gateway_request.get("headers", {})

        method = request_body.get("method", "")

        # For non-tools/call methods (initialize, tools/list, etc.),
        # pass through without requiring tenant context.
        # Only tools/call needs tenant_id injection.
        if method != "tools/call":
            logger.info(json.dumps({
                "correlation_id": correlation_id,
                "method": method,
                "action": "pass_through"
            }))
            return {
                "interceptorOutputVersion": "1.0",
                "mcp": {
                    "transformedGatewayRequest": {
                        "body": request_body
                    }
                }
            }

        # Extract tenant ID from JWT in Authorization header
        tenant_id = _extract_tenant_id(headers)

        if not tenant_id:
            logger.error(json.dumps({
                "correlation_id": correlation_id,
                "error": "Missing tenant context",
                "message": "tenantId not found in JWT claims"
            }))
            # Return a 403 response directly, short-circuiting the target call
            return {
                "interceptorOutputVersion": "1.0",
                "mcp": {
                    "transformedGatewayResponse": {
                        "statusCode": 403,
                        "body": {
                            "jsonrpc": "2.0",
                            "id": request_body.get("id"),
                            "error": {
                                "code": -32600,
                                "message": "Missing tenant context"
                            }
                        }
                    }
                }
            }

        # Inject tenant_id into tool call arguments
        modified_body = _inject_tenant_id_into_tool_call(request_body, tenant_id)

        logger.info(json.dumps({
            "correlation_id": correlation_id,
            "tenant_id": tenant_id,
            "method": method,
            "action": "tenant_id_injected"
        }))

        # Pass the modified request through to the target
        return {
            "interceptorOutputVersion": "1.0",
            "mcp": {
                "transformedGatewayRequest": {
                    "body": modified_body
                }
            }
        }

    except Exception as e:
        logger.exception(f"Interceptor error: {e}")
        return {
            "interceptorOutputVersion": "1.0",
            "mcp": {
                "transformedGatewayResponse": {
                    "statusCode": 500,
                    "body": {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "Internal interceptor error"
                        }
                    }
                }
            }
        }
