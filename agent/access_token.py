from bedrock_agentcore.identity.auth import requires_access_token
from ops_context import OpsContext
import constants
async def on_auth_url(url: str):
    response_queue = OpsContext.get_response_queue_ctx()
    if response_queue is None:
        raise RuntimeError("Response queue is None")
    print(
        f"=============================\n\n\n\n\nPlease authorize using this url: {url}\n\n\n\n\n============================="
    )
    await response_queue.put(f"Please authenticate using {url}.\n")
@requires_access_token(
    provider_name=constants.ACCESS_TOKEN_PROVIDER_NAME,
    scopes=["AgentCore-Gateway/invoke"],
    auth_flow="M2M",
    on_auth_url=on_auth_url,  # prints authorization URL to console
    force_authentication=False,
    into="access_token",  # injects the access token into the function
)
async def get_token(*, access_token: str):
    print("Access token:", access_token)
    return access_token
# @requires_access_token(
#     provider_name="cognito-provider",
#     scopes=["agentcore_gateway/invoke"],
#     auth_flow="USER_FEDERATION",
#     on_auth_url=on_auth_url,  # prints authorization URL to console
#     force_authentication=False,
#     into="access_token",  # injects the access token into the function
# )
# async def get_token(*, access_token: str):
#     print("Access token:", access_token)
#     return access_token
