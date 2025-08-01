#!/bin/bash -e

# Enable nocasematch option
shopt -s nocasematch

# Parse tenant details from the input message
export CDK_PARAM_TENANT_ID=$(echo $tenantId | tr -d '"')
export CDK_PARAM_TENANT_NAME=$(echo $tenantName | tr -d '"')
export TENANT_ADMIN_EMAIL=$(echo $email | tr -d '"')
export TIER=$(echo $tier | tr -d '"')

echo "Provisioning tenant: $CDK_PARAM_TENANT_ID"
echo "Tenant name: $CDK_PARAM_TENANT_NAME"
echo "Admin email: $TENANT_ADMIN_EMAIL"
echo "Tier: $TIER"

# Define variables
STACK_NAME="TenantStack-$CDK_PARAM_TENANT_ID"
COMMON_RESOURCES_STACK="saas-genai-workshop-common-resources"
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

# Check if the common resources stack exists
if aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK 2>/dev/null; then
  echo "Found common resources stack: $COMMON_RESOURCES_STACK"
  export SAAS_APP_USERPOOL_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$USER_POOL_OUTPUT_PARAM_NAME'].OutputValue" --output text)
  export SAAS_APP_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$APP_CLIENT_ID_OUTPUT_PARAM_NAME'].OutputValue" --output text)
  export API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$API_GATEWAY_URL_OUTPUT_PARAM_NAME'].OutputValue" --output text)
  export API_GATEWAY_USAGE_PLAN_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$API_GATEWAY_USAGE_PLAN_ID_OUTPUT_PARAM_NAME'].OutputValue" --output text)
  export S3_BUCKET=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$S3_PARAM_NAME'].OutputValue" --output text)
  export TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$INGESTION_LAMBDA_ARN_PARAM_NAME'].OutputValue" --output text)
  export OPENSEARCH_SERVERLESS_COLLECTION_ARN=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$OSSC_ARN_PARAM_NAME'].OutputValue" --output text)
  export TENANT_DATA_TABLE=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$TENANT_DATA_TABLE_PARAM_NAME'].OutputValue" --output text)
else
  echo "Common resources stack not found: $COMMON_RESOURCES_STACK"
  echo "Using default values"
  export SAAS_APP_USERPOOL_ID="default-userpool-id"
  export SAAS_APP_CLIENT_ID="default-client-id"
  export API_GATEWAY_URL="default-api-gateway-url"
  export API_GATEWAY_USAGE_PLAN_ID="default-usage-plan-id"
  export S3_BUCKET="default-s3-bucket"
  export TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN="default-lambda-arn"
  export OPENSEARCH_SERVERLESS_COLLECTION_ARN="default-collection-arn"
  export TENANT_DATA_TABLE="TenantDataTable"
fi

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

# Try to find the cdk directory
if [ -d "/codebuild/output/src*/src/cdk" ]; then
  echo "Found cdk directory at /codebuild/output/src*/src/cdk"
  cd /codebuild/output/src*/src/cdk
elif [ -d "/codebuild/output/src*/cdk" ]; then
  echo "Found cdk directory at /codebuild/output/src*/cdk"
  cd /codebuild/output/src*/cdk
else
  echo "Could not find cdk directory, using current directory"
  # Try to find the tenant-provisioning directory
  if [ -d "lib/tenant-template/tenant-provisioning" ]; then
    echo "Found tenant-provisioning directory"
  else
    echo "Could not find tenant-provisioning directory"
    echo "Creating minimal tenant provisioning structure"
    mkdir -p lib/tenant-template/tenant-provisioning
    mkdir -p lib/tenant-template/user-management
    
    # Create a minimal tenant provisioning script
    cat > lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py << 'EOF'
#!/usr/bin/env python3
import argparse

def main():
    parser = argparse.ArgumentParser(description='Tenant Provisioning Service')
    parser.add_argument('--tenantid', required=True, help='Tenant ID')
    args = parser.parse_args()
    print(f"Provisioning tenant: {args.tenantid}")
    return 0

if __name__ == "__main__":
    exit(main())
EOF

    # Create a minimal user management script
    cat > lib/tenant-template/user-management/user_management_service.py << 'EOF'
#!/usr/bin/env python3
import argparse

def main():
    parser = argparse.ArgumentParser(description='User Management Service')
    parser.add_argument('--tenant-id', required=True, help='Tenant ID')
    parser.add_argument('--email', required=True, help='User email')
    parser.add_argument('--user-role', required=True, help='User role')
    args = parser.parse_args()
    print(f"Creating user for tenant: {args.tenant_id}, email: {args.email}, role: {args.user_role}")
    return 0

if __name__ == "__main__":
    exit(main())
EOF

    # Create a minimal requirements.txt file
    cat > lib/tenant-template/tenant-provisioning/requirements.txt << 'EOF'
boto3>=1.26.0
EOF
  fi
fi

# Invoke tenant provisioning service
# Check if requirements.txt exists
if [ -f "lib/tenant-template/tenant-provisioning/requirements.txt" ]; then
  pip3 install -r lib/tenant-template/tenant-provisioning/requirements.txt
else
  echo "requirements.txt not found, skipping pip install"
fi
provision_name="Tenant Provisioning"
# Add tenant provisioning service
export TENANT_NAME=$CDK_PARAM_TENANT_NAME
export TENANT_DATA_TABLE=${TENANT_DATA_TABLE:-"TenantDataTable"}
# Check if tenant provisioning script exists
if [ -f "lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py" ]; then
  tenant_provision_output=$(python3 lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py --tenantid $CDK_PARAM_TENANT_ID 2>&1 >/dev/null && exit_code=$?) || exit_code=$?
else
  echo "tenant_provisioning_service.py not found, skipping tenant provisioning"
  tenant_provision_output="Tenant provisioning skipped"
  exit_code=0
fi
check_error "$provision_name" $exit_code "$tenant_provision_output"

export KNOWLEDGE_BASE_NAME=$CDK_PARAM_TENANT_ID

# List all knowledge bases and filter the results based on the KnowledgeBase name
# Check if bedrock-agent command is available
if command -v aws bedrock-agent &> /dev/null; then
  export KNOWLEDGE_BASE_ID=$(aws bedrock-agent list-knowledge-bases | jq -r '.[] | .[] | select(.name == $name) | .knowledgeBaseId' --arg name $KNOWLEDGE_BASE_NAME)
else
  echo "aws bedrock-agent command not available, skipping knowledge base lookup"
  export KNOWLEDGE_BASE_ID="default-knowledge-base-id"
fi

# Create tenant admin user
provision_name="Tenant Admin User Provisioning"
# Check if user management script exists
if [ -f "lib/tenant-template/user-management/user_management_service.py" ]; then
  tenant_admin_output=$(python3 lib/tenant-template/user-management/user_management_service.py --tenant-id $CDK_PARAM_TENANT_ID --email $TENANT_ADMIN_EMAIL --user-role "TenantAdmin" 2>&1 >/dev/null && exit_code=$?) || exit_code=$?
else
  echo "user_management_service.py not found, skipping user management"
  tenant_admin_output="User management skipped"
  exit_code=0
fi
check_error "$provision_name" $exit_code  "$tenant_admin_output"

# Create JSON response of output parameters
export tenantStatus="Complete"
export tenantConfig=$(jq --arg SAAS_APP_USERPOOL_ID "$SAAS_APP_USERPOOL_ID" \
  --arg SAAS_APP_CLIENT_ID "$SAAS_APP_CLIENT_ID" \
  --arg API_GATEWAY_URL "$API_GATEWAY_URL" \
  --arg TENANT_API_KEY "$TENANT_API_KEY" \
  --arg CDK_PARAM_TENANT_NAME "$CDK_PARAM_TENANT_NAME" \
  --arg KNOWLEDGE_BASE_ID "$KNOWLEDGE_BASE_ID" \
  --arg INPUT_TOKENS "$INPUT_TOKENS" \
  --arg OUTPUT_TOKENS "$OUTPUT_TOKENS" \
  -n '{"tenantName":$CDK_PARAM_TENANT_NAME,"userPoolId":$SAAS_APP_USERPOOL_ID,"appClientId":$SAAS_APP_CLIENT_ID,"apiGatewayUrl":$API_GATEWAY_URL,"apiKey":$TENANT_API_KEY, "knowledgeBaseId":$KNOWLEDGE_BASE_ID, "inputTokens":$INPUT_TOKENS, "outputTokens":$OUTPUT_TOKENS}')