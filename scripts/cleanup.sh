#!/bin/bash -e

# Cleanup Script for SaaS Multi-Agent Workshop
# This script handles the complete cleanup of all CloudFormation stacks and resources
#
# Usage:
#   ./scripts/cleanup.sh <system_admin_email>
#
# This script can be run independently or called from install.sh with the delete operation.
# It will clean up:
#   - TenantStack-* stacks (CloudFormation stacks created by CodeBuild)
#   - InstallWorkshopStack-* projects (CodeBuild projects)
#   - AgentCore resources
#   - S3 buckets and contents
#   - All CDK-managed stacks
#
# Example:
#   ./scripts/cleanup.sh admin@example.com

shopt -s expand_aliases
source ~/.bashrc

export CDK_PARAM_SYSTEM_ADMIN_EMAIL="$1"

if [[ -z "$CDK_PARAM_SYSTEM_ADMIN_EMAIL" ]]; then
  echo "Cleanup Script for SaaS Multi-Agent Workshop"
  echo ""
  echo "Usage: $0 <system_admin_email>"
  echo ""
  echo "This script performs comprehensive cleanup of all workshop resources including:"
  echo "  - TenantStack-* stacks (CloudFormation stacks created by CodeBuild)"
  echo "  - InstallWorkshopStack-* projects (CodeBuild projects)"
  echo "  - AgentCore resources"
  echo "  - S3 buckets and contents"
  echo "  - All CDK-managed stacks"
  echo ""
  echo "Example:"
  echo "  $0 admin@example.com"
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
SCRIPT_DIR="$(dirname "$(realpath "$0")")"   # Get the directory of the cleanup.sh script
FOLDER_PATH="$(dirname "$SCRIPT_DIR")"       # Get the parent folder of the script

echo "Performing comprehensive cleanup operation..."

# Function to delete stacks with a given prefix
delete_stacks_with_prefix() {
    local prefix="$1"
    echo "Looking for stacks with prefix: $prefix"
    
    # Get all stacks with the specified prefix
    local stacks=$(aws cloudformation list-stacks \
        --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE \
        --query "StackSummaries[?starts_with(StackName, '$prefix')].StackName" \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$stacks" && "$stacks" != "None" ]]; then
        echo "Found stacks to delete: $stacks"
        for stack in $stacks; do
            echo "Deleting stack: $stack"
            aws cloudformation delete-stack --stack-name "$stack"
            if [ $? -eq 0 ]; then
                echo "Successfully initiated deletion of stack: $stack"
            else
                echo "Warning: Failed to initiate deletion of stack: $stack"
            fi
        done
        
        # Wait for stack deletions to complete
        echo "Waiting for stack deletions to complete..."
        for stack in $stacks; do
            echo "Waiting for stack deletion: $stack"
            aws cloudformation wait stack-delete-complete --stack-name "$stack" 2>/dev/null || echo "Warning: Stack $stack deletion wait failed or timed out"
        done
    else
        echo "No stacks found with prefix: $prefix"
    fi
}

# Function to delete CodeBuild projects with a given prefix
delete_codebuild_projects_with_prefix() {
    local prefix="$1"
    echo "Looking for CodeBuild projects with prefix: $prefix"
    
    # Get all CodeBuild projects with the specified prefix
    local projects=$(aws codebuild list-projects \
        --query "projects[?starts_with(@, '$prefix')]" \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$projects" && "$projects" != "None" ]]; then
        echo "Found CodeBuild projects to delete: $projects"
        for project in $projects; do
            echo "Deleting CodeBuild project: $project"
            aws codebuild delete-project --name "$project"
            if [ $? -eq 0 ]; then
                echo "Successfully deleted CodeBuild project: $project"
            else
                echo "Warning: Failed to delete CodeBuild project: $project"
            fi
        done
    else
        echo "No CodeBuild projects found with prefix: $prefix"
    fi
}

# Clean up CodeBuild-created resources
echo "Cleaning up CodeBuild-created resources..."

# Delete TenantStack-* stacks (CloudFormation stacks)
delete_stacks_with_prefix "TenantStack-"

# Delete InstallWorkshopStack-* projects (CodeBuild projects)
delete_codebuild_projects_with_prefix "InstallWorkshopStack-"

# Clean up AgentCore resources
echo "Cleaning up AgentCore resources..."
cd "$SCRIPT_DIR"

AGENTCORE_PROVISIONING_SCRIPT="agentcore-provisioning/deploy-agentcore.py"
REQUIREMENTS_FILE="agentcore-provisioning/requirements.txt"

# Install required packages if requirements file exists
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip3 install -r "$REQUIREMENTS_FILE"
fi

# Run AgentCore cleanup
python3 "$AGENTCORE_PROVISIONING_SCRIPT" --destroy

if [ $? -eq 0 ]; then
    echo "AgentCore cleanup completed successfully"
else
    echo "Warning: AgentCore cleanup failed, but continuing with stack deletion"
fi

# Return to cdk directory for stack operations
cd "$FOLDER_PATH/cdk"

# Install CDK dependencies
npm install

# Get S3 bucket URL before deleting stacks
S3_TENANT_SOURCECODE_BUCKET_URL=$(aws cloudformation describe-stacks --stack-name saas-genai-workshop-common-resources --query "Stacks[0].Outputs[?OutputKey=='TenantSourceCodeS3Bucket'].OutputValue" --output text 2>/dev/null || echo "")

if [[ -n "$S3_TENANT_SOURCECODE_BUCKET_URL" ]]; then
    echo "Emptying S3 bucket: $S3_TENANT_SOURCECODE_BUCKET_URL"
    aws s3 rm "s3://$S3_TENANT_SOURCECODE_BUCKET_URL" --recursive
fi

# Destroy all CDK-managed stacks
echo "Destroying CDK-managed stacks..."
npx cdk destroy --all --force

# Final cleanup: Check for any remaining stacks and CodeBuild projects
echo "Performing final cleanup check..."

# Check for remaining CloudFormation stacks
remaining_tenant_stacks=$(aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE \
    --query "StackSummaries[?starts_with(StackName, 'TenantStack-')].StackName" \
    --output text 2>/dev/null || echo "")

# Check for remaining CodeBuild projects
remaining_workshop_projects=$(aws codebuild list-projects \
    --query "projects[?starts_with(@, 'InstallWorkshopStack-')]" \
    --output text 2>/dev/null || echo "")

if [[ -n "$remaining_tenant_stacks" && "$remaining_tenant_stacks" != "None" ]]; then
    echo "Warning: Some TenantStack stacks may still exist: $remaining_tenant_stacks"
    echo "You may need to delete them manually if they are in a failed state"
fi

if [[ -n "$remaining_workshop_projects" && "$remaining_workshop_projects" != "None" ]]; then
    echo "Warning: Some InstallWorkshopStack CodeBuild projects may still exist: $remaining_workshop_projects"
    echo "You may need to delete them manually if they are in a failed state"
fi

echo "Cleanup operation completed successfully"
echo ""
echo "All workshop resources have been cleaned up."
echo "Please verify in the AWS Console that all stacks have been deleted."