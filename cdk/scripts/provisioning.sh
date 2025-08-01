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

# Generate and upload mock data for the tenant
echo "Generating mock data for tenant $SAAS_TENANT_ID..."
ls
python3 scripts/generate_tenant_mock_data.py --tenant-id $SAAS_TENANT_ID --tenant-name "$tenantName" --bucket $DATA_BUCKET --table $TENANT_DATA_TABLE

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
  -n '{"tenantId":$SAAS_TENANT_ID,"appClientId":$SAAS_APP_CLIENT_ID,"authServer":$SAAS_AUTH_SERVER,"redirectUrl":$SAAS_REDIRECT_URL}')