import json
import uuid

def lambda_handler(event, context):
    # Extract the gateway request 
    mcp_data = event.get('mcp', {})
    gateway_request = mcp_data.get('gatewayRequest', {})
    headers = gateway_request.get('headers', {})
    body = gateway_request.get('body', {})
    extended_body = body
    
    auth_header = headers.get('authorization', '') or headers.get('Authorization', '')
    
    # Extract Tenant Id from custom header for propagation
    tenant_id = headers.get('X-Tenant-ID', '')
    
    if "params" in extended_body and "arguments" in extended_body["params"]:
        # Add custom header to arguments for downstream processing
        extended_body["params"]["arguments"]["tenant_id"] = tenant_id
    
    # Return transformed request without passing the original authorization header
    response = {
        "interceptorOutputVersion": "1.0",
        "mcp": {
            "transformedGatewayRequest": {
                "headers": {
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                "body": extended_body
            }
        }
    }
    return response