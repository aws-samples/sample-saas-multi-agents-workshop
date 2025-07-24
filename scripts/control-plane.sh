#!/bin/bash -e

export CDK_PARAM_SYSTEM_ADMIN_EMAIL="$1"

if [[ -z "$CDK_PARAM_SYSTEM_ADMIN_EMAIL" ]]; then
  echo "Please provide system admin email"
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

# Preprovision base infrastructure
cd ../cdk
npm install

npx cdk bootstrap
npx cdk deploy --all --require-approval never --concurrency 10 --asset-parallelism true

CP_API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name ControlPlaneStack --query "Stacks[0].Outputs[?OutputKey=='controlPlaneAPIEndpoint'].OutputValue" --output text)

echo "Control plane api gateway url: $CP_API_GATEWAY_URL"


S3_TENANT_SOURCECODE_BUCKET_URL=$(aws cloudformation describe-stacks --stack-name saas-genai-workshop-bootstrap-template --query "Stacks[0].Outputs[?OutputKey=='TenantSourceCodeS3Bucket'].OutputValue" --output text)
echo "S3 bucket url: $S3_TENANT_SOURCECODE_BUCKET_URL"

# Step 3: Define folder to upload and target S3 bucket
SCRIPT_DIR="$(dirname "$(realpath "$0")")"   # Get the directory of the install.sh script
FOLDER_PATH="$(dirname "$SCRIPT_DIR")"       # Get the parent folder of the script

# Step 4: Upload the folder to the S3 bucket
echo "Uploading folder $FOLDER_PATH to S3 $S3_TENANT_SOURCECODE_BUCKET_URL"
aws s3 cp "$FOLDER_PATH" "s3://$S3_TENANT_SOURCECODE_BUCKET_URL" --recursive --exclude "cdk/cdk.out/*" --exclude "cdk/node_modules/*" --exclude ".git/*" --quiet

echo "Installation completed successfully"