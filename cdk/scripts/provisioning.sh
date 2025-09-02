#!/bin/bash -e

# Install/update the AWS CLI.
# sudo yum remove awscli

# curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
# unzip awscliv2.zip
# sudo ./aws/install

S3_TENANT_SOURCECODE_BUCKET_URL=$(aws cloudformation describe-stacks --stack-name saas-genai-workshop-common-resources --query "Stacks[0].Outputs[?OutputKey=='TenantSourceCodeS3Bucket'].OutputValue" --output text)
export CDK_PARAM_CODE_REPOSITORY_NAME="saas-genai-workshop"

# Download the folder from S3 to local directory
echo "Downloading folder from s3://$S3_TENANT_SOURCECODE_BUCKET_URL to $CDK_PARAM_CODE_REPOSITORY_NAME..."
aws s3 cp "s3://$S3_TENANT_SOURCECODE_BUCKET_URL" "$CDK_PARAM_CODE_REPOSITORY_NAME" --recursive \
--exclude "cdk/cdk.out/*" --exclude "cdk/node_modules/*" --exclude ".git/*" --quiet
cd $CDK_PARAM_CODE_REPOSITORY_NAME/cdk

aws codebuild start-build --project-name TenantOnboardingProject --environment-variables-override \
name=TENANT_ID,value=$tenantId,type=PLAINTEXT \
name=PLAN,value=$tier,type=PLAINTEXT \
name=COMPANY_NAME,value=$tenantName,type=PLAINTEXT \
name=ADMIN_EMAIL,value=$email,type=PLAINTEXT

STACK_NAME="TenantStack-$tenantId"

echo Waiting
aws cloudformation wait stack-exists --stack-name $STACK_NAME
echo Waiting
aws cloudformation wait stack-exists --stack-name $STACK_NAME

aws cloudformation wait stack-create-complete --stack-name $STACK_NAME
STACKS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME)
echo "Stacks: $STACKS"
SAAS_TENANT_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='TenantId'].OutputValue" --output text)
echo "TenantId: $SAAS_TENANT_ID"
SAAS_APP_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='ClientId'].OutputValue" --output text)
echo "ClientId: $SAAS_APP_CLIENT_ID"
SAAS_AUTH_SERVER=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='AuthServer'].OutputValue" --output text)
echo "AuthServer: $SAAS_AUTH_SERVER"
SAAS_REDIRECT_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='RedirectUri'].OutputValue" --output text)
echo "RedirectUri: $SAAS_REDIRECT_URL"

# Get the S3 bucket name from the common resources stack
COMMON_RESOURCES_STACK="saas-genai-workshop-common-resources"
DATA_BUCKET=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" --output text)
echo "Data Bucket: $DATA_BUCKET"

TENANT_DATA_TABLE=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='TenantDataTableName'].OutputValue" --output text)
echo "Tenant Data Table: $TENANT_DATA_TABLE"

KNOWLEDGE_BASE_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='KnowledgeBaseId'].OutputValue" --output text)
echo "Knowledge Base ID: $KNOWLEDGE_BASE_ID"

# Create tenant prefix folders in S3 buckets
echo "Creating tenant prefix folders for tenant $SAAS_TENANT_ID..."

# Set environment variables for tenant provisioning
export DATA_BUCKET=$DATA_BUCKET
export LOGS_BUCKET=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='LogsBucketName'].OutputValue" --output text)
echo "Logs Bucket: $LOGS_BUCKET"
export TRIGGER_PIPELINE_INGESTION_LAMBDA_ARN=$TRIGGER_INGESTION_LAMBDA
export OPENSEARCH_SERVERLESS_COLLECTION_ARN=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='SaaSGenAIWorkshopOSSCollectionArn'].OutputValue" --output text || echo "dummy-value")
export API_GATEWAY_USAGE_PLAN_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUsagePlan'].OutputValue" --output text || echo "dummy-value")
export TENANT_API_KEY=$(python3 -c "import uuid; print(f'{uuid.uuid4()}-sbt')")

# Call tenant provisioning service
if [ -f "lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py" ]; then
  # Install required packages
  if [ -f "lib/tenant-template/tenant-provisioning/requirements.txt" ]; then
    pip3 install -r lib/tenant-template/tenant-provisioning/requirements.txt
  fi
  
  echo "Calling tenant provisioning service for tenant $SAAS_TENANT_ID..."
  tenant_provision_output=$(python3 lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py --tenantid $SAAS_TENANT_ID 2>&1)
  exit_code=$?
  
  if [ $exit_code -ne 0 ]; then
    echo "ERROR: Tenant provisioning failed with exit code $exit_code"
    echo "$tenant_provision_output"
  else
    echo "Tenant provisioning completed successfully"
  fi
else
  echo "tenant_provisioning_service.py not found, skipping tenant provisioning"
fi

# Get the user pool ID from the common resources stack
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='TenantUserpoolId'].OutputValue" --output text || echo "")

# Create tenant admin user if user management service exists
if [ -f "lib/tenant-template/user-management/user_management_service.py" ]; then
  # Install required packages if there's a requirements file
  if [ -f "lib/tenant-template/user-management/requirements.txt" ]; then
    pip3 install -r lib/tenant-template/user-management/requirements.txt
  fi
  
  echo "Creating tenant admin user for tenant $SAAS_TENANT_ID..."
  export SAAS_APP_USERPOOL_ID=$USER_POOL_ID
  
  tenant_admin_output=$(python3 lib/tenant-template/user-management/user_management_service.py --tenant-id $SAAS_TENANT_ID --email $email --user-role "TenantAdmin" 2>&1)
  exit_code=$?
  
  if [ $exit_code -ne 0 ]; then
    echo "ERROR: Tenant admin user creation failed with exit code $exit_code"
    echo "$tenant_admin_output"
  else
    echo "Tenant admin user created successfully"
  fi
else
  echo "user_management_service.py not found, skipping tenant admin user creation"
fi

# Trigger knowledge base ingestion
echo "Triggering knowledge base ingestion for tenant $SAAS_TENANT_ID..."
TRIGGER_INGESTION_LAMBDA=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='SaaSGenAIWorkshopTriggerIngestionLambdaArn'].OutputValue" --output text)

if [ "$TRIGGER_INGESTION_LAMBDA" != "dummy-value" ]; then
  # If we have a real Lambda ARN, invoke it
  aws lambda invoke --function-name $TRIGGER_INGESTION_LAMBDA --payload "{\"knowledgeBaseId\":\"$KNOWLEDGE_BASE_ID\",\"tenantId\":\"$SAAS_TENANT_ID\"}" /tmp/lambda-output.json
  echo "Knowledge base ingestion triggered for tenant $SAAS_TENANT_ID"
else
  echo "Knowledge base ingestion Lambda is not available (dummy value). Skipping ingestion."
fi

#Export variables
export tenantStatus="Complete"
export tenantConfig=$(jq --arg SAAS_TENANT_ID "$SAAS_TENANT_ID" \
  --arg SAAS_APP_CLIENT_ID "$SAAS_APP_CLIENT_ID" \
  --arg SAAS_AUTH_SERVER "$SAAS_AUTH_SERVER" \
  --arg SAAS_REDIRECT_URL "$SAAS_REDIRECT_URL" \
  --arg USER_POOL_ID "$USER_POOL_ID" \
  -n '{"tenantId":$SAAS_TENANT_ID,"appClientId":$SAAS_APP_CLIENT_ID,"authServer":$SAAS_AUTH_SERVER,"redirectUrl":$SAAS_REDIRECT_URL,"userPoolId":$USER_POOL_ID}')