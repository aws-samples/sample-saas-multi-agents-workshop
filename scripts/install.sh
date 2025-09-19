#!/bin/bash -e

shopt -s expand_aliases
source ~/.bashrc

# Get operation and convert to lowercase for case-insensitive comparison
STACK_OPERATION_ORIG=${1:-"create"}
STACK_OPERATION=$(echo "$STACK_OPERATION_ORIG" | tr '[:upper:]' '[:lower:]')
export CDK_PARAM_SYSTEM_ADMIN_EMAIL="$2"

if [[ -z "$CDK_PARAM_SYSTEM_ADMIN_EMAIL" ]]; then
  echo "Usage: $0 [Create|Update|Delete] <system_admin_email>"
  exit 1
fi


# Check if running on EC2 by looking for the AWS_REGION environment variable
if [[ -n "$AWS_REGION" ]]; then
  REGION="$AWS_REGION"
else
  # If not on EC2, try to get the region from aws configure
  REGION=$(aws configure get region)
  if [[ -z "$REGION" ]]; then
    echo "Unable to determine AWS region. Please set AWS_REGION environment variable or configure AWS CLI."
    exit 1
  fi
fi

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
echo "Using AWS Account ID: $AWS_ACCOUNT_ID"
echo "Using AWS Region: $REGION"

# Get script directory before changing directories
SCRIPT_DIR="$(dirname "$(realpath "$0")")"   # Get the directory of the install.sh script
FOLDER_PATH="$(dirname "$SCRIPT_DIR")"       # Get the parent folder of the script

# Preprovision base infrastructure
cd ../cdk
npm install

if [[ "$STACK_OPERATION" == "create" || "$STACK_OPERATION" == "update" ]]; then
    echo "Performing $STACK_OPERATION operation..."
    
    # Bootstrap CDK if creating
    if [[ "$STACK_OPERATION" == "create" ]]; then
        echo "Bootstrapping CDK with account $AWS_ACCOUNT_ID and region $REGION"
        npx cdk bootstrap
    fi
    
    # Deploy all stacks
    npx cdk deploy --all --require-approval never --concurrency 10 --asset-parallelism true
    
    # Get API Gateway URL
    CP_API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name ControlPlaneStack --query "Stacks[0].Outputs[?OutputKey=='controlPlaneAPIEndpoint'].OutputValue" --output text)
    echo "Control plane api gateway url: $CP_API_GATEWAY_URL"
    
    # Get S3 bucket URL
    S3_TENANT_SOURCECODE_BUCKET_URL=$(aws cloudformation describe-stacks --stack-name saas-genai-workshop-common-resources --query "Stacks[0].Outputs[?OutputKey=='TenantSourceCodeS3Bucket'].OutputValue" --output text)
    echo "S3 bucket url: $S3_TENANT_SOURCECODE_BUCKET_URL"
    
    # Upload the folder to the S3 bucket
    echo "Uploading folder $FOLDER_PATH to S3 $S3_TENANT_SOURCECODE_BUCKET_URL"
    aws s3 cp "$FOLDER_PATH" "s3://$S3_TENANT_SOURCECODE_BUCKET_URL" --recursive --exclude "cdk/cdk.out/*" --exclude "cdk/node_modules/*" --exclude ".git/*" --quiet
    
    # Deploy AgentCore resources
    echo "Deploying AgentCore resources..."
    
    # Get AgentCore stack outputs from the common resources stack
    # AgentCoreStack is now a substack within CommonResourcesStack
    COMMON_RESOURCES_STACK="saas-genai-workshop-common-resources"
    
    # Extract all AgentCore parameters from CommonResourcesStack outputs
    USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='TenantUserpoolId'].OutputValue" --output text 2>/dev/null || echo "")
    USER_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" --output text 2>/dev/null || echo "")
    M2M_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='AgentCoreM2MClientId'].OutputValue" --output text 2>/dev/null || echo "")
    M2M_CLIENT_SECRET=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='AgentCoreM2MClientSecret'].OutputValue" --output text 2>/dev/null || echo "")
    AGENT_CORE_ROLE_ARN=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='AgentCoreRoleArn'].OutputValue" --output text 2>/dev/null || echo "")
    LOG_MCP_LAMBDA_ARN=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='AgentCoreLogMcpLambdaArn'].OutputValue" --output text 2>/dev/null || echo "")
    KB_MCP_LAMBDA_ARN=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='AgentCoreKbMcpLambdaArn'].OutputValue" --output text 2>/dev/null || echo "")
    
    # Export environment variables for deploy-agentcore.py
    export USER_POOL_ID
    export USER_CLIENT_ID
    export M2M_CLIENT_ID
    export M2M_CLIENT_SECRET
    export AGENT_CORE_ROLE_ARN
    export LOG_MCP_LAMBDA_ARN
    export KB_MCP_LAMBDA_ARN
    export AWS_DEFAULT_REGION="$REGION"
    
    # Check if we have the required parameters
    if [[ -n "$USER_POOL_ID" && -n "$USER_CLIENT_ID" ]]; then
        echo "Found AgentCore parameters, deploying AgentCore resources..."
        echo "User Pool ID: $USER_POOL_ID"
        echo "User Client ID: $USER_CLIENT_ID"
        
        # Navigate to scripts directory and run deploy-agentcore.py
        cd "$SCRIPT_DIR"

        python3 --version

        AGENTCORE_PROVISIONING_SCRIPT="agentcore-provisioning/deploy-agentcore.py"
        # Install required packages
        REQUIREMENTS_FILE="agentcore-provisioning/requirements.txt"
        if [ -f "$REQUIREMENTS_FILE" ]; then
            pip3 install -r "$REQUIREMENTS_FILE"
        fi

        python3 "$AGENTCORE_PROVISIONING_SCRIPT"
        
        if [ $? -eq 0 ]; then
            echo "AgentCore deployment completed successfully"
        else
            echo "Warning: AgentCore deployment failed, but continuing with main deployment"
        fi
        
        # Return to cdk directory
        cd "$FOLDER_PATH/cdk"
    else
        echo "Warning: Could not find all required AgentCore parameters, skipping AgentCore deployment"
        echo "This might be expected if AgentCore stack is not yet deployed or outputs are not available"
    fi
    
    echo "$STACK_OPERATION operation completed successfully"
    
elif [[ "$STACK_OPERATION" == "delete" ]]; then
    echo "Performing delete operation..."
    
    # Get S3 bucket URL before deleting stacks
    S3_TENANT_SOURCECODE_BUCKET_URL=$(aws cloudformation describe-stacks --stack-name saas-genai-workshop-common-resources --query "Stacks[0].Outputs[?OutputKey=='TenantSourceCodeS3Bucket'].OutputValue" --output text 2>/dev/null || echo "")
    
    if [[ -n "$S3_TENANT_SOURCECODE_BUCKET_URL" ]]; then
        echo "Emptying S3 bucket: $S3_TENANT_SOURCECODE_BUCKET_URL"
        aws s3 rm "s3://$S3_TENANT_SOURCECODE_BUCKET_URL" --recursive
    fi
    
    # Destroy all stacks
    npx cdk destroy --all --force
    
    echo "Delete operation completed successfully"
    
else
    echo "Invalid stack operation: $STACK_OPERATION_ORIG"
    echo "Usage: $0 [Create|Update|Delete] <system_admin_email>"
    exit 1
fi