#!/bin/bash -e

# Deprovision tenant.
STACK_NAME="TenantStack-$tenantId"

echo "Deprovisioning tenant: $tenantId"
echo "Deleting stack: $STACK_NAME"

# Delete the CloudFormation stack
aws cloudformation delete-stack --stack-name $STACK_NAME

# Wait for the stack to be deleted
echo "Waiting for stack deletion to complete..."
aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME

echo "Tenant $tenantId has been successfully deprovisioned."

# Export variables
export tenantStatus="Deleted"
export tenantConfig=$(jq -n '{"tenantId":"'$tenantId'","status":"deleted"}')