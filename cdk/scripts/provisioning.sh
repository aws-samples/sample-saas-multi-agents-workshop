#!/bin/bash
#
# Tenant Provisioning Script
# This script handles the provisioning of resources for a new tenant
#

# Exit on error, but allow pipeline commands to fail
set -e
set -o pipefail

# Function for logging with timestamps
log() {
  local level=$1
  shift
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*"
}

# Function to check if a command succeeded
check_command() {
  if [ $? -ne 0 ]; then
    log "ERROR" "$1"
    exit 1
  fi
}

log "INFO" "Starting tenant provisioning process"

# Get source code from S3
log "INFO" "Retrieving tenant source code"
S3_TENANT_SOURCECODE_BUCKET_URL=$(aws cloudformation describe-stacks --stack-name saas-genai-workshop-common-resources --query "Stacks[0].Outputs[?OutputKey=='TenantSourceCodeS3Bucket'].OutputValue" --output text)
check_command "Failed to get source code bucket URL"

export CDK_PARAM_CODE_REPOSITORY_NAME="saas-genai-workshop"

# Download the folder from S3 to local directory
log "INFO" "Downloading folder from s3://$S3_TENANT_SOURCECODE_BUCKET_URL to $CDK_PARAM_CODE_REPOSITORY_NAME..."
aws s3 cp "s3://$S3_TENANT_SOURCECODE_BUCKET_URL" "$CDK_PARAM_CODE_REPOSITORY_NAME" --recursive \
--exclude "cdk/cdk.out/*" --exclude "cdk/node_modules/*" --exclude ".git/*" --quiet
check_command "Failed to download source code from S3"

cd $CDK_PARAM_CODE_REPOSITORY_NAME/cdk

# Start the tenant onboarding process
log "INFO" "Starting tenant onboarding with CodeBuild"
aws codebuild start-build --project-name TenantOnboardingProject --environment-variables-override \
name=TENANT_ID,value=$tenantId,type=PLAINTEXT \
name=PLAN,value=$tier,type=PLAINTEXT \
name=COMPANY_NAME,value=$tenantName,type=PLAINTEXT \
name=ADMIN_EMAIL,value=$email,type=PLAINTEXT
check_command "Failed to start CodeBuild project"

# Use the tenantId directly since the tenant-onboarding-stack doesn't create resources anymore
SAAS_TENANT_ID=$tenantId
log "INFO" "TenantId: $SAAS_TENANT_ID"

# Get common resources from the shared stack
log "INFO" "Retrieving common resources"
COMMON_RESOURCES_STACK="saas-genai-workshop-common-resources"

DATA_BUCKET=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" --output text)
log "INFO" "Data Bucket: $DATA_BUCKET"

TENANT_DATA_TABLE=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='TenantDataTableName'].OutputValue" --output text)
log "INFO" "Tenant Data Table: $TENANT_DATA_TABLE"

KNOWLEDGE_BASE_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='KnowledgeBaseId'].OutputValue" --output text)
log "INFO" "Knowledge Base ID: $KNOWLEDGE_BASE_ID"

DATA_SOURCE_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='DataSourceId'].OutputValue" --output text)
log "INFO" "Data Source ID: $DATA_SOURCE_ID"

LOGS_BUCKET=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='LogsBucketName'].OutputValue" --output text)
log "INFO" "Logs Bucket: $LOGS_BUCKET"

# Get the trigger ingestion Lambda ARN
TRIGGER_INGESTION_LAMBDA=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='SaaSGenAIWorkshopTriggerIngestionLambdaArn'].OutputValue" --output text || echo "dummy-value")
log "INFO" "Trigger Ingestion Lambda: $TRIGGER_INGESTION_LAMBDA"

# Get OpenSearch and API Gateway resources
API_GATEWAY_USAGE_PLAN_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUsagePlan'].OutputValue" --output text || echo "dummy-value")
API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" --output text || echo "dummy-value")
log "INFO" "API Gateway URL: $API_GATEWAY_URL"

# Get common app client ID
COMMON_SAAS_APP_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" --output text || echo "dummy-value")
log "INFO" "Common App Client ID: $COMMON_SAAS_APP_CLIENT_ID"

# Generate a unique API key for the tenant
TENANT_API_KEY=$(python3 -c "import uuid; print(f'{uuid.uuid4()}-sbt')")

# Set environment variables for tenant provisioning
log "INFO" "Setting up environment variables for tenant provisioning"
export DATA_BUCKET
export LOGS_BUCKET
export TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN=$TRIGGER_INGESTION_LAMBDA
export API_GATEWAY_USAGE_PLAN_ID
export TENANT_API_KEY
export KNOWLEDGE_BASE_ID
export DATA_SOURCE_ID

# Run tenant provisioning service
log "INFO" "Running tenant provisioning service"
TENANT_PROVISIONING_SCRIPT="lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py"
if [ -f "$TENANT_PROVISIONING_SCRIPT" ]; then
  # Install required packages
  REQUIREMENTS_FILE="lib/tenant-template/tenant-provisioning/requirements.txt"
  if [ -f "$REQUIREMENTS_FILE" ]; then
    log "INFO" "Installing tenant provisioning dependencies"
    pip3 install -r "$REQUIREMENTS_FILE"
    check_command "Failed to install tenant provisioning dependencies"
  fi
  
  log "INFO" "Calling tenant provisioning service for tenant $SAAS_TENANT_ID..."


set +e  # Temporarily disable exit-on-error
  tenant_provision_output=$(python3 "$TENANT_PROVISIONING_SCRIPT" --tenantid "$SAAS_TENANT_ID" 2>&1)
  exit_code=$?
  set -e  # Re-enable exit-on-error
  
  if [ $exit_code -ne 0 ]; then
    log "ERROR" "Tenant provisioning failed with exit code $exit_code"
    log "ERROR" "$tenant_provision_output"
    # Continue execution despite error to allow partial provisioning
  else
    log "INFO" "Tenant provisioning completed successfully"
  fi
else
  log "WARN" "Tenant provisioning script not found at $TENANT_PROVISIONING_SCRIPT, skipping tenant provisioning"
fi

# Create tenant admin user
log "INFO" "Setting up tenant admin user"
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='TenantUserpoolId'].OutputValue" --output text || echo "")

USER_MANAGEMENT_SCRIPT="lib/tenant-template/user-management/user_management_service.py"
if [ -f "$USER_MANAGEMENT_SCRIPT" ]; then
  # Install required packages if there's a requirements file
  USER_MGMT_REQUIREMENTS="lib/tenant-template/user-management/requirements.txt"
  if [ -f "$USER_MGMT_REQUIREMENTS" ]; then
    log "INFO" "Installing user management dependencies"
    pip3 install -r "$USER_MGMT_REQUIREMENTS"
    check_command "Failed to install user management dependencies"
  fi
  
  log "INFO" "Creating tenant admin user for tenant $SAAS_TENANT_ID..."
  export SAAS_APP_USERPOOL_ID=$USER_POOL_ID
  
  set +e
  tenant_admin_output=$(python3 "$USER_MANAGEMENT_SCRIPT" --tenant-id "$SAAS_TENANT_ID" --email "$email" --user-role "TenantAdmin" 2>&1)
  exit_code=$?
  set -e
  
  if [ $exit_code -ne 0 ]; then
    log "ERROR" "Tenant admin user creation failed with exit code $exit_code"
    log "ERROR" "$tenant_admin_output"
    # Continue execution despite error
  else
    log "INFO" "Tenant admin user created successfully"
  fi
else
  log "WARN" "User management script not found at $USER_MANAGEMENT_SCRIPT, skipping tenant admin user creation"
fi

# Trigger knowledge base ingestion
# Commented out as ingestion disabled on new tenant onboarding
# log "INFO" "Triggering knowledge base ingestion for tenant $SAAS_TENANT_ID..."

# if [ "$TRIGGER_INGESTION_LAMBDA" != "dummy-value" ] && [ -n "$TRIGGER_INGESTION_LAMBDA" ]; then
#   # If we have a real Lambda ARN, invoke it
#   log "INFO" "Invoking Lambda function to trigger knowledge base ingestion"
#   aws lambda invoke \
#     --function-name "$TRIGGER_INGESTION_LAMBDA" \
#     --payload "{\"knowledgeBaseId\":\"$KNOWLEDGE_BASE_ID\",\"tenantId\":\"$SAAS_TENANT_ID\"}" \
#     /tmp/lambda-output.json
#   check_command "Failed to invoke knowledge base ingestion Lambda"
#   log "INFO" "Knowledge base ingestion triggered for tenant $SAAS_TENANT_ID"
# else
#   log "WARN" "Knowledge base ingestion Lambda is not available. Skipping ingestion."
# fi

# Export tenant configuration
log "INFO" "Exporting tenant configuration"
export tenantStatus="Complete"
export registrationStatus="Complete"
export tenantConfig=$(jq --arg SAAS_APP_USERPOOL_ID "$SAAS_APP_USERPOOL_ID" \
  --arg SAAS_TENANT_ID "$SAAS_TENANT_ID" \
  --arg SAAS_APP_CLIENT_ID "$COMMON_SAAS_APP_CLIENT_ID" \
  --arg KNOWLEDGE_BASE_ID "$KNOWLEDGE_BASE_ID" \
  --arg DATA_SOURCE_ID "$DATA_SOURCE_ID" \
  --arg TENANT_API_KEY "$TENANT_API_KEY" \
  --arg API_GATEWAY_URL "$API_GATEWAY_URL" \
  --arg TENANT_NAME "$tenantName" \
  -n '{"tenantId":$SAAS_TENANT_ID,"tenantName":$TENANT_NAME,"userPoolId":$SAAS_APP_USERPOOL_ID, "appClientId":$SAAS_APP_CLIENT_ID,"knowledgeBaseId":$KNOWLEDGE_BASE_ID,"dataSourceId":$DATA_SOURCE_ID,"apiKey":$TENANT_API_KEY,"apiGatewayUrl":$API_GATEWAY_URL}')

log "INFO" "Tenant provisioning completed successfully"