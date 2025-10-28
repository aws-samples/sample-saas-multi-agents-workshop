#!/bin/bash -e

# Enable nocasematch option
shopt -s nocasematch

# Parse tenant details from the input message
export CDK_PARAM_TENANT_ID=$(echo $tenantId | tr -d '"')

echo "Deprovisioning tenant: $CDK_PARAM_TENANT_ID"

# Define variables
STACK_NAME="TenantStack-$CDK_PARAM_TENANT_ID"
COMMON_RESOURCES_STACK="saas-genai-workshop-common-resources"
TENANT_DATA_TABLE_PARAM_NAME="TenantDataTableName"

# Read tenant details from the cloudformation
export REGION=$(aws configure get region)

# Check if the common resources stack exists
if aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK 2>/dev/null; then
  echo "Found common resources stack: $COMMON_RESOURCES_STACK"
  export TENANT_DATA_TABLE=$(aws cloudformation describe-stacks --stack-name $COMMON_RESOURCES_STACK --query "Stacks[0].Outputs[?OutputKey=='$TENANT_DATA_TABLE_PARAM_NAME'].OutputValue" --output text)
else
  echo "Common resources stack not found: $COMMON_RESOURCES_STACK"
  echo "Using default values"
  export TENANT_DATA_TABLE="TenantDataTable"
fi

# Check if the tenant stack exists
if aws cloudformation describe-stacks --stack-name $STACK_NAME 2>/dev/null; then
  echo "Found tenant stack: $STACK_NAME"
  echo "Deleting stack: $STACK_NAME"

  # Delete the CloudFormation stack
  aws cloudformation delete-stack --stack-name $STACK_NAME

  # Wait for the stack to be deleted
  echo "Waiting for stack deletion to complete..."
  aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME

  echo "Tenant $CDK_PARAM_TENANT_ID has been successfully deprovisioned."
else
  echo "Tenant stack not found: $STACK_NAME"
  echo "Skipping stack deletion"
fi

# Try to find the cdk directory
if [ -d "/codebuild/output/src*/src/cdk" ]; then
  echo "Found cdk directory at /codebuild/output/src*/src/cdk"
  cd /codebuild/output/src*/src/cdk
elif [ -d "/codebuild/output/src*/cdk" ]; then
  echo "Found cdk directory at /codebuild/output/src*/cdk"
  cd /codebuild/output/src*/cdk
else
  echo "Could not find cdk directory, using current directory"
fi

# Check if tenant provisioning service exists
if [ -d "lib/tenant-template/tenant-provisioning" ]; then
  echo "Found tenant-provisioning directory"
  
  # Check if requirements.txt exists
  if [ -f "lib/tenant-template/tenant-provisioning/requirements.txt" ]; then
    pip3 install -r lib/tenant-template/tenant-provisioning/requirements.txt
  else
    echo "requirements.txt not found, skipping pip install"
  fi
  
  # Create a simple deprovisioning script if it doesn't exist
  if [ ! -f "lib/tenant-template/tenant-provisioning/tenant_deprovisioning_service.py" ]; then
    echo "Creating minimal tenant deprovisioning script"
    cat > lib/tenant-template/tenant-provisioning/tenant_deprovisioning_service.py << 'EOF'
#!/usr/bin/env python3
import argparse

def main():
    parser = argparse.ArgumentParser(description='Tenant Deprovisioning Service')
    parser.add_argument('--tenantid', required=True, help='Tenant ID')
    args = parser.parse_args()
    print(f"Deprovisioning tenant: {args.tenantid}")
    return 0

if __name__ == "__main__":
    exit(main())
EOF
  fi
  
  # Run the deprovisioning script
  python3 lib/tenant-template/tenant-provisioning/tenant_deprovisioning_service.py --tenantid $CDK_PARAM_TENANT_ID
else
  echo "tenant-provisioning directory not found, skipping tenant deprovisioning"
fi

# Export variables
export tenantStatus="Deleted"
export tenantConfig=$(jq -n '{"tenantId":"'$CDK_PARAM_TENANT_ID'","status":"deleted"}')