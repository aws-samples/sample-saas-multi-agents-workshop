#!/bin/bash -e

# Enable nocasematch option
shopt -s nocasematch

S3_TENANT_SOURCECODE_BUCKET_URL=$(aws cloudformation describe-stacks --stack-name saas-genai-workshop-bootstrap-template --query "Stacks[0].Outputs[?OutputKey=='TenantSourceCodeS3Bucket'].OutputValue" --output text)
export CDK_PARAM_CODE_REPOSITORY_NAME="saas-genai-workshop"

# Download the folder from S3 to local directory
echo "Downloading folder from s3://$S3_TENANT_SOURCECODE_BUCKET_URL to $CDK_PARAM_CODE_REPOSITORY_NAME..."
aws s3 cp "s3://$S3_TENANT_SOURCECODE_BUCKET_URL" "$CDK_PARAM_CODE_REPOSITORY_NAME" --recursive \
--exclude "cdk/cdk.out/*" --exclude "cdk/node_modules/*" --exclude ".git/*" --quiet
cd $CDK_PARAM_CODE_REPOSITORY_NAME/cdk

# Parse tenant details from the input message from step function
export CDK_PARAM_TENANT_ID=$(echo $tenantId | tr -d '"')
export CDK_PARAM_TENANT_NAME=$(echo $tenantName | tr -d '"')
export TENANT_ADMIN_EMAIL=$(echo $email | tr -d '"')

# Define variables
STACK_NAME="saas-genai-workshop-bootstrap-template"
USER_POOL_OUTPUT_PARAM_NAME="TenantUserpoolId"
APP_CLIENT_ID_OUTPUT_PARAM_NAME="UserPoolClientId"
API_GATEWAY_URL_OUTPUT_PARAM_NAME="ApiGatewayUrl"
API_GATEWAY_USAGE_PLAN_ID_OUTPUT_PARAM_NAME="ApiGatewayUsagePlan"
S3_PARAM_NAME="SaaSGenAIWorkshopS3Bucket"
INGESTION_LAMBDA_ARN_PARAM_NAME="SaaSGenAIWorkshopTriggerIngestionLambdaArn"
OSSC_ARN_PARAM_NAME="SaaSGenAIWorkshopOSSCollectionArn"
TENANT_DATA_TABLE_PARAM_NAME="TenantDataTableName"
INPUT_TOKENS="10000"
OUTPUT_TOKENS="500"


# Read tenant details from the cloudformation
export REGION=$(aws configure get region)
export SAAS_APP_USERPOOL_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$USER_POOL_OUTPUT_PARAM_NAME'].OutputValue" --output text)
export SAAS_APP_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$APP_CLIENT_ID_OUTPUT_PARAM_NAME'].OutputValue" --output text)
export API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$API_GATEWAY_URL_OUTPUT_PARAM_NAME'].OutputValue" --output text)
export API_GATEWAY_USAGE_PLAN_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$API_GATEWAY_USAGE_PLAN_ID_OUTPUT_PARAM_NAME'].OutputValue" --output text)
export S3_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$S3_PARAM_NAME'].OutputValue" --output text)
export TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$INGESTION_LAMBDA_ARN_PARAM_NAME'].OutputValue" --output text)
export OPENSEARCH_SERVERLESS_COLLECTION_ARN=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$OSSC_ARN_PARAM_NAME'].OutputValue" --output text)
export TENANT_DATA_TABLE=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='$TENANT_DATA_TABLE_PARAM_NAME'].OutputValue" --output text)

# Create Tenant API Key
generate_api_key() {
    local suffix=${1:-sbt}
    local uuid=$(python3 -c "import uuid; print(uuid.uuid4())")
    echo "${uuid}-${suffix}"
}

TENANT_API_KEY=$(generate_api_key)

# Error handling function
check_error() {
    provision_script_name=$1
    exit_code=$2
    provision_output=$3
    if [[ "$exit_code" -ne 0 ]]; then
        echo "$provision_output"
        echo "ERROR: $provision_script_name failed. Exiting"
        exit 1
    fi
        echo "$provision_script_name completed successfully"
}

# Invoke tenant provisioning service
pip3 install -r lib/tenant-template/tenant-provisioning/requirements.txt
provision_name="Tenant Provisioning"
# Add tenant provisioning service
export TENANT_NAME=$CDK_PARAM_TENANT_NAME
export TENANT_DATA_TABLE=${TENANT_DATA_TABLE:-"TenantDataTable"}
tenant_provision_output=$(python3 lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py --tenantid $CDK_PARAM_TENANT_ID 2>&1 >/dev/null && exit_code=$?) || exit_code=$?
check_error "$provision_name" $exit_code "$tenant_provision_output"



export KNOWLEDGE_BASE_NAME=$CDK_PARAM_TENANT_ID

# List all knowledge bases and filter the results based on the KnowledgeBase name
export KNOWLEDGE_BASE_ID=$(aws bedrock-agent list-knowledge-bases | jq -r '.[] | .[] | select(.name == $name) | .knowledgeBaseId' --arg name $KNOWLEDGE_BASE_NAME)

# Create tenant admin user
provision_name="Tenant Admin User Provisioning"
# TODO: Lab1 - Uncomment below lines - user management service
tenant_admin_output=$(python3 lib/tenant-template/user-management/user_management_service.py --tenant-id $CDK_PARAM_TENANT_ID --email $TENANT_ADMIN_EMAIL --user-role "TenantAdmin" 2>&1 >/dev/null && exit_code=$?) || exit_code=$?
check_error "$provision_name" $exit_code  "$tenant_admin_output" 

# Create JSON response of output parameters
export tenantConfig=$(jq --arg SAAS_APP_USERPOOL_ID "$SAAS_APP_USERPOOL_ID" \
  --arg SAAS_APP_CLIENT_ID "$SAAS_APP_CLIENT_ID" \
  --arg API_GATEWAY_URL "$API_GATEWAY_URL" \
  --arg TENANT_API_KEY "$TENANT_API_KEY" \
  --arg CDK_PARAM_TENANT_NAME "$CDK_PARAM_TENANT_NAME" \
  --arg KNOWLEDGE_BASE_ID "$KNOWLEDGE_BASE_ID" \
  --arg INPUT_TOKENS "$INPUT_TOKENS" \
  --arg OUTPUT_TOKENS "$OUTPUT_TOKENS" \
  -n '{"tenantName":$CDK_PARAM_TENANT_NAME,"userPoolId":$SAAS_APP_USERPOOL_ID,"appClientId":$SAAS_APP_CLIENT_ID,"apiGatewayUrl":$API_GATEWAY_URL,"apiKey":$TENANT_API_KEY, "knowledgeBaseId":$KNOWLEDGE_BASE_ID, "inputTokens":$INPUT_TOKENS, "outputTokens":$OUTPUT_TOKENS}')
export tenantStatus="Complete"
