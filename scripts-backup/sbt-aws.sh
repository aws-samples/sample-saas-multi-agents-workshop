#!/bin/bash

set -e

# Config values
CONFIG_FILE="${HOME}/.sbt-aws-config"

# Functions
help() {
  echo "Usage: $0 [--debug] <operation> [additional args]"
  echo "Operations:"
  echo "  configure <control_plane_stack> <admin_user_name>"
  echo "  refresh-tokens"
  echo "  create-tenant <tenant_name>"
  echo "  get-tenant <tenant_id>"
  echo "  get-all-tenants"
  echo "  get-knowledge-base-id <tenant_name>"
  echo "  delete-tenant <tenant_id>"
  echo "  update-tenant <tenant_id> <key> <value>"
  echo "  update-token-limit <tenant_name> <input_tokens> <output_tokens>"
  echo "  create-user"
  echo "  get-user <user_name>"
  echo "  delete-user <user_name>"
  echo "  invoke <user_name> <password> <query> <requests>"
  echo "  upload-file <user_name> <password> <file_location>"
  echo "  execute-query <user_name> <password> <knowledge_base_query>"
  echo "  help"
}

generate_credentials() {
  if $DEBUG; then
    echo "Generating credentials..."
  fi

  CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $CONTROL_PLANE_STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='ControlPlaneIdpClientId'].OutputValue"| jq -r '.[0]')
  USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name $CONTROL_PLANE_STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='ControlPlaneIdpUserPoolId'].OutputValue"| jq -r '.[0]')
  USER="$2"
  PASSWORD="$1"

  if $DEBUG; then
    echo "CLIENT_ID: $CLIENT_ID"
    echo "USER_POOL_ID: $USER_POOL_ID"
    echo "USER: $USER"
  fi

  # required in order to initiate-auth
  aws cognito-idp update-user-pool-client \
    --user-pool-id "$USER_POOL_ID" \
    --client-id "$CLIENT_ID" \
    --explicit-auth-flows USER_PASSWORD_AUTH \
    --output text >/dev/null

  if $DEBUG; then
    echo "Updated user pool client for USER_PASSWORD_AUTH"
  fi

  # remove need for password reset
  aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username "$USER" \
    --password "$PASSWORD" \
    --permanent \
    --output text >/dev/null

  if $DEBUG; then
    echo "Set user password for $USER"
  fi

  # get credentials for user
  AUTHENTICATION_RESULT=$(aws cognito-idp initiate-auth \
    --auth-flow USER_PASSWORD_AUTH \
    --client-id "${CLIENT_ID}" \
    --auth-parameters "USERNAME='${USER}',PASSWORD='${PASSWORD}'" \
    --query 'AuthenticationResult')


  ACCESS_TOKEN=$(echo "$AUTHENTICATION_RESULT" | jq -r '.AccessToken')
  ID_TOKEN=$(echo "$AUTHENTICATION_RESULT" | jq -r '.IdToken')

  if $DEBUG; then
    echo "ACCESS_TOKEN: $ACCESS_TOKEN"
    echo "ID_TOKEN: $ID_TOKEN"
  fi

  export ACCESS_TOKEN
  export ID_TOKEN
}


configure() {
  CONTROL_PLANE_STACK_NAME="$1"
  ADMIN_USER_NAME="$2"

  if $DEBUG; then
    echo "Configuring with:"
    echo "CONTROL_PLANE_STACK_NAME: $CONTROL_PLANE_STACK_NAME"
    echo "ADMIN_USER_NAME: $ADMIN_USER_NAME"
  fi

  read -r -s -p "Enter admin password: " ADMIN_USER_PASSWORD
  echo

  generate_credentials "$ADMIN_USER_PASSWORD" "$ADMIN_USER_NAME"
  CONTROL_PLANE_API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$CONTROL_PLANE_STACK_NAME" \
    --query "Stacks[0].Outputs[?contains(OutputKey,'controlPlaneAPIEndpoint')].OutputValue" \
    --output text)

  if $DEBUG; then
    echo "CONTROL_PLANE_API_ENDPOINT: $CONTROL_PLANE_API_ENDPOINT"
  fi

  printf "CONTROL_PLANE_STACK_NAME=%s\nCONTROL_PLANE_API_ENDPOINT=%s\nADMIN_USER_PASSWORD=\'%s\'\nADMIN_USER_NAME=%s\nACCESS_TOKEN=%s\nID_TOKEN=%s\n" \
    "$CONTROL_PLANE_STACK_NAME" "$CONTROL_PLANE_API_ENDPOINT" "$ADMIN_USER_PASSWORD" "$ADMIN_USER_NAME" "$ACCESS_TOKEN" "$ID_TOKEN" > "$CONFIG_FILE"

  if $DEBUG; then
    echo "Configuration saved to $CONFIG_FILE"
  fi
  echo "Successfully configured SaaS admin credentials"
}

refresh_tokens() {
  source_config

  if $DEBUG; then
    echo "Refreshing tokens..."
  fi

  generate_credentials "$ADMIN_USER_PASSWORD" "$ADMIN_USER_NAME"
  CONTROL_PLANE_API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$CONTROL_PLANE_STACK_NAME" \
    --query "Stacks[0].Outputs[?contains(OutputKey,'controlPlaneAPIEndpoint')].OutputValue" \
    --output text)

  printf "CONTROL_PLANE_STACK_NAME=%s\nCONTROL_PLANE_API_ENDPOINT=%s\nADMIN_USER_PASSWORD=\'%s\'\nADMIN_USER_NAME=%s\nACCESS_TOKEN=%s\nID_TOKEN=%s\n" \
    "$CONTROL_PLANE_STACK_NAME" "$CONTROL_PLANE_API_ENDPOINT" "$ADMIN_USER_PASSWORD" "$ADMIN_USER_NAME" "$ACCESS_TOKEN" "$ID_TOKEN"  >"$CONFIG_FILE"

  if $DEBUG; then
    echo "Tokens refreshed and saved to $CONFIG_FILE"
  fi
}

source_config() {
  source "$CONFIG_FILE"
}

create_tenant() {
  TENANT_NAME="$1"
  TENANT_EMAIL="$TENANT_NAME@example.com"
  source_config
  
  if $DEBUG; then
    echo "Creating tenant with:"
    echo "TENANT_NAME: $TENANT_NAME"
    echo "TENANT_EMAIL: $TENANT_EMAIL"
  fi

  DATA=$(jq --null-input \
    --arg tenantName "$TENANT_NAME" \
    --arg tenantEmail "$TENANT_EMAIL" \
    '{
      "tenantName": $tenantName,
      "email": $tenantEmail,
      "tier": "basic",
      "tenantStatus": "In progress"
    }')

  RESPONSE=$(curl --request POST \
    --url "${CONTROL_PLANE_API_ENDPOINT}tenants" \
    --header "Authorization: Bearer ${ID_TOKEN}" \
    --header 'content-type: application/json' \
    --data "$DATA" \
    --silent)

  if $DEBUG; then
    echo "Response: $RESPONSE"
  else
    echo "$RESPONSE"
  fi
}

get_tenant() {
  source_config
  TENANT_ID="$1"

  if $DEBUG; then
    echo "Getting tenant with ID: $TENANT_ID"
  fi

  RESPONSE=$(curl --request GET \
    --url "${CONTROL_PLANE_API_ENDPOINT}tenants/$TENANT_ID" \
    --header "Authorization: Bearer $ID_TOKEN" \
    --silent)

  if $DEBUG; then
    echo "Response: $RESPONSE"
  else
    echo "$RESPONSE"
  fi
}

get_all_tenants() {
  source_config

  if $DEBUG; then
    echo "Getting all tenants"
  fi

  RESPONSE=$(curl --request GET \
    --url "${CONTROL_PLANE_API_ENDPOINT}tenants" \
    --header "Authorization: Bearer $ID_TOKEN" \
    --silent  | jq)

  if $DEBUG; then
    echo "Response: $RESPONSE"
  else
    echo "$RESPONSE"
  fi
}

get_knowledge_base_id() {
  TENANT_NAME="$1"

  if [ -z "$TENANT_NAME" ]; then
    echo "Error: Tenant name not provided"
    return 1
  fi

  if $DEBUG; then
    echo "Getting Knowledge Base ID per tenant name"
  fi

  # Get all tenants
  tenants=$(get_all_tenants)
  # Extract the knowledgeBaseId for the given tenantName
  KB_ID=$(echo "$tenants" | jq -r ".data[] | select(.tenantName==\"$TENANT_NAME\") | .tenantConfig | fromjson | .knowledgeBaseId")
  
  if [ -z "$KB_ID" ]; then
    echo "Error: Tenant with name '$tenant_name' not found"
    return 1
  fi

  echo "Knowledge Base id for $TENANT_NAME is: $KB_ID"
}

delete_tenant() {
  source_config
  TENANT_ID="$1"

  if $DEBUG; then
    echo "Deleting tenant with ID: $TENANT_ID"
  fi

  RESPONSE=$(curl --request DELETE \
    --url "${CONTROL_PLANE_API_ENDPOINT}tenants/$TENANT_ID" \
    --header "Authorization: Bearer $ID_TOKEN" \
    --header 'content-type: application/json' \
    --silent)

  if $DEBUG; then
    echo "Response: $RESPONSE"
  else
    echo "$RESPONSE"
  fi
}

create_user() {
  source_config
  USER_NAME="user$RANDOM"
  USER_EMAIL="${EMAIL_USERNAME}+${USER_NAME}@${EMAIL_DOMAIN}"

  if $DEBUG; then
    echo "Creating user with:"
    echo "USER_NAME: $USER_NAME"
    echo "USER_EMAIL: $USER_EMAIL"
  fi

  DATA=$(jq --null-input \
    --arg userName "$USER_NAME" \
    --arg email "$USER_EMAIL" \
    '{
      "userName": $userName,
      "email": $email,
      "userRole": "basicUser"
    }')

  RESPONSE=$(curl --request POST \
    --url "${CONTROL_PLANE_API_ENDPOINT}users" \
    --header "Authorization: Bearer $ID_TOKEN" \
    --header 'content-type: application/json' \
    --data "$DATA" \
    --silent)

  if $DEBUG; then
    echo "Response: $RESPONSE"
  else
    echo "$RESPONSE"
  fi
}

get_user() {
  source_config
  USER_NAME="$1"

  if $DEBUG; then
    echo "Getting user with name: $USER_NAME"
  fi

  RESPONSE=$(curl --request GET \
    --url "${CONTROL_PLANE_API_ENDPOINT}users/$USER_NAME" \
    --header "Authorization: Bearer $ID_TOKEN" \
    --silent)

  if $DEBUG; then
    echo "Response: $RESPONSE"
  else
    echo "$RESPONSE"
  fi
}

delete_user() {
  source_config
  USER_NAME="$1"

  if $DEBUG; then
    echo "Deleting user with name: $USER_NAME"
  fi

  RESPONSE=$(curl --request DELETE \
    --url "${CONTROL_PLANE_API_ENDPOINT}users/$USER_NAME" \
    --header "Authorization: Bearer $ID_TOKEN" \
    --silent)

  if $DEBUG; then
    echo "Response: $RESPONSE"
  else
    echo "$RESPONSE"
  fi
}

update_token_limit() {
  source_config

  TENANT_NAME="$1"
  INPUT_TOKENS="$2"
  OUTPUT_TOKENS="$3"

  tenants=$(get_all_tenants)

  # Extract the tenantId for the matching tenantName
  TENANT_ID=$(echo "$tenants" | jq -r ".data[] | select(.tenantName==\"$TENANT_NAME\") | .tenantId")

  if [ -z "$TENANT_ID" ] || [ "$TENANT_ID" = "null" ]; then
    echo "Error: Could not find tenant ID for tenant name: $TENANT_NAME" >&2
    return 1
  fi

  # Fetch the current tenantConfig
  CURRENT_CONFIG=$(curl --silent --request GET \
    --url "${CONTROL_PLANE_API_ENDPOINT}tenants/$TENANT_ID" \
    --header "Authorization: Bearer $ID_TOKEN" | jq -r '.data.tenantConfig')

  # Update only the tokens while preserving other fields
  UPDATED_CONFIG=$(echo $CURRENT_CONFIG | jq \
    --arg inputTokens "$INPUT_TOKENS" \
    --arg outputTokens "$OUTPUT_TOKENS" \
    '.inputTokens = $inputTokens | .outputTokens = $outputTokens')

  # Construct the full update payload
  DATA=$(jq --null-input \
    --arg tenantConfig "$UPDATED_CONFIG" \
    '{"tenantConfig": $tenantConfig}')

  if $DEBUG; then
    echo "CURRENT CONFIG: $CURRENT_CONFIG"
    echo "UPDATED CONFIG: $UPDATED_CONFIG"
  fi

  # Send the PUT request
  RESPONSE=$(curl --request PUT \
    --url "${CONTROL_PLANE_API_ENDPOINT}tenants/$TENANT_ID" \
    --header "Authorization: Bearer $ID_TOKEN" \
    --header 'content-type: application/json' \
    --data "$DATA" \
    --write-out '%{http_code}' \
    --silent \
    --output /dev/null)

  if [ "$RESPONSE" -eq 200 ]; then
    echo "Tenant $TENANT_NAME updated to $INPUT_TOKENS input tokens and $OUTPUT_TOKENS output tokens"
  else
    echo "Error updating tenant $TENANT_NAME: HTTP status code $RESPONSE" >&2
  fi
}

update_tenant() {
  echo "PUT ${CONTROL_PLANE_API_ENDPOINT}tenants/$TENANT_ID only supports AWS_IAM auth"
  # source_config
  # TENANT_ID="$1"
  # KEY="$2"
  # VALUE="$3"

  # DATA=$(jq --null-input \
  #   --arg key "$KEY" \
  #   --arg value "$VALUE" \
  #   '{($key): $value}')

  # curl --request PUT \
  #   --url "${CONTROL_PLANE_API_ENDPOINT}tenants/$TENANT_ID" \
  #   --header "Authorization: Bearer $ID_TOKEN" \
  #   --header 'content-type: application/json' \
  #   --data "$DATA" \
  #   --silent
}

upload_file() {
  
  USER="$1"
  PASSWORD="$2"
  FILE_LOCATION="$3"

  STACK_NAME="saas-genai-workshop-bootstrap-template"
  APP_CLIENT_ID_OUTPUT_PARAM_NAME="UserPoolClientId"
  API_GATEWAY_URL_OUTPUT_PARAM_NAME="ApiGatewayUrl"

  export SAAS_APP_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$APP_CLIENT_ID_OUTPUT_PARAM_NAME'].OutputValue" --output text)
  export API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$API_GATEWAY_URL_OUTPUT_PARAM_NAME'].OutputValue" --output text)

  AUTHENTICATION_RESULT=$(aws cognito-idp initiate-auth \
    --auth-flow USER_PASSWORD_AUTH \
    --client-id "${SAAS_APP_CLIENT_ID}" \
    --auth-parameters "USERNAME='${USER}',PASSWORD='${PASSWORD}'" \
    --query 'AuthenticationResult')

  ACCESS_TOKEN=$(echo "$AUTHENTICATION_RESULT" | jq -r '.AccessToken')
  ID_TOKEN=$(echo "$AUTHENTICATION_RESULT" | jq -r '.IdToken')

  TENANT_DATA=$(jq -n --arg content "$(cat "$FILE_LOCATION")" '{"fileContent": $content}')

  RESPONSE=$(curl --request POST \
    --url "${API_GATEWAY_URL}upload" \
    --header "Authorization: Bearer ${ID_TOKEN}" \
    --header 'content-type: application/json' \
    --data "$TENANT_DATA" \
    --silent)

  echo $RESPONSE

}

invoke() {
  
  USER="$1"
  PASSWORD="$2"
  QUERY="$3"
  REQUESTS="$4"

  STACK_NAME="saas-genai-workshop-bootstrap-template"
  APP_CLIENT_ID_OUTPUT_PARAM_NAME="UserPoolClientId"
  API_GATEWAY_URL_OUTPUT_PARAM_NAME="ApiGatewayUrl"
  

  export SAAS_APP_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$APP_CLIENT_ID_OUTPUT_PARAM_NAME'].OutputValue" --output text)
  export API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$API_GATEWAY_URL_OUTPUT_PARAM_NAME'].OutputValue" --output text)

  AUTHENTICATION_RESULT=$(aws cognito-idp initiate-auth \
    --auth-flow USER_PASSWORD_AUTH \
    --client-id "${SAAS_APP_CLIENT_ID}" \
    --auth-parameters "USERNAME='${USER}',PASSWORD='${PASSWORD}'" \
    --query 'AuthenticationResult')

  ACCESS_TOKEN=$(echo "$AUTHENTICATION_RESULT" | jq -r '.AccessToken')
  ID_TOKEN=$(echo "$AUTHENTICATION_RESULT" | jq -r '.IdToken')

  if $DEBUG; then
    echo "Creating tenant with:"
    echo "API GATEWAY URL: $API_GATEWAY_URL"
    echo "TENANT_EMAIL: $TENANT_EMAIL"
  fi

  echo "Sending request and waiting for response..."

  for i in $(seq 1 ${REQUESTS})
    do
      RESPONSE=$(curl -s -w '\n%{http_code}' -X POST \
      -H "Authorization: Bearer ${ID_TOKEN}" \
      -H "Content-Type: application/json" \
      --data "$QUERY" \
      "${API_GATEWAY_URL}invoke")

      BODY=$(echo "$RESPONSE" | sed '$d')
      HTTP_STATUS_CODE=$(echo "$RESPONSE" | tail -n1)
      echo "Request $i - HTTP Status Code: $HTTP_STATUS_CODE, Output Text: $BODY" &
      sleep 12
    done
    wait
    echo "All done"

}

execute_query() {
  USER="$1"
  PASSWORD="$2"
  QUERY="$3"

  STACK_NAME="saas-genai-workshop-bootstrap-template"
  APP_CLIENT_ID_OUTPUT_PARAM_NAME="UserPoolClientId"
  API_GATEWAY_URL_OUTPUT_PARAM_NAME="ApiGatewayUrl"

  export SAAS_APP_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$APP_CLIENT_ID_OUTPUT_PARAM_NAME'].OutputValue" --output text)
  export API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$API_GATEWAY_URL_OUTPUT_PARAM_NAME'].OutputValue" --output text)

  AUTHENTICATION_RESULT=$(aws cognito-idp initiate-auth \
    --auth-flow USER_PASSWORD_AUTH \
    --client-id "${SAAS_APP_CLIENT_ID}" \
    --auth-parameters "USERNAME='${USER}',PASSWORD='${PASSWORD}'" \
    --query 'AuthenticationResult')

  ACCESS_TOKEN=$(echo "$AUTHENTICATION_RESULT" | jq -r '.AccessToken')
  ID_TOKEN=$(echo "$AUTHENTICATION_RESULT" | jq -r '.IdToken')

  echo "Sending request and waiting for response..."

  RESPONSE=$(curl --request POST \
    --url "${API_GATEWAY_URL}invoke" \
    --header "Authorization: Bearer ${ID_TOKEN}" \
    --header 'content-type: application/json' \
    --data "$QUERY" \
    --silent)

  echo -e "$RESPONSE" | tr '\n' '\n'

}


# Main
DEBUG=false
if [ "$1" = "--debug" ]; then
  DEBUG=true
  shift
fi

if [ $# -eq 0 ]; then
  help
  exit 1
fi

case "$1" in
"configure")
  shift
  configure "$@"
  ;;

"refresh-tokens")
  refresh_tokens
  ;;

"create-tenant")
  if [ $# -ne 2 ]; then
    echo "Error: create-tenant requires tenant name"
    exit 1
  fi
  create_tenant "$2"
  ;;

"get-tenant")
  if [ $# -ne 2 ]; then
    echo "Error: delete-tenant requires tenant id"
    exit 1
  fi
  get_tenant "$2"
  ;;

"get-all-tenants")
  get_all_tenants
  ;;

"get-knowledge-base-id")
  if [ $# -ne 2 ]; then
    echo "Error: get-knowledge-base-id requires tenant name"
    exit 1
  fi
  get_knowledge_base_id "$2"
  ;;

"delete-tenant")
  if [ $# -ne 2 ]; then
    echo "Error: delete-tenant requires tenant id"
    exit 1
  fi
  delete_tenant "$2"
  ;;

"update-tenant")
  if [ $# -ne 4 ]; then
    echo "Error: update-tenant requires tenant id, key, and value"
    exit 1
  fi
  update_tenant "$2" "$3" "$4"
  ;;

"update-token-limit")
  if [ $# -ne 4 ]; then
    echo "Error: update-tenant requires tenant name, input tokens, and output tokens"
    exit 1
  fi
  update_token_limit "$2" "$3" "$4"
  ;;

"upload-file")
  if [ $# -ne 4 ]; then
    echo "Error: update-file requires tenant username, password, and data"
    exit 1
  fi
  upload_file "$2" "$3" "$4"
  ;;

"invoke")
  if [ $# -ne 5 ]; then
    echo "Error: invoke requires tenant username, password, query, number of requests"
    exit 1
  fi
  invoke "$2" "$3" "$4" "$5"
  ;;

"execute-query")
  if [ $# -ne 4 ]; then
    echo "Error: execute-query requires tenant username, password, and query"
    exit 1
  fi
  execute_query "$2" "$3" "$4"
  ;;

"create-user")
  create_user
  ;;

"get-user")
  if [ $# -ne 2 ]; then
    echo "Error: get-user requires user name"
    exit 1
  fi
  get_user "$2"
  ;;

"delete-user")
  if [ $# -ne 2 ]; then
    echo "Error: delete-user requires user name"
    exit 1
  fi
  delete_user "$2"
  ;;

"help")
  help
  ;;

*)
  echo "Invalid operation: $1"
  help
  exit 1
  ;;
esac