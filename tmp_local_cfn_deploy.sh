#!/bin/bash
set -e

# Step 1: Sync the workshop folder to S3 bucket
# echo "Syncing workshop folder to S3 bucket..."
# cd "$(dirname "$0")/../.."
aws s3 sync "." "s3://assets-test-bucket-blumron" --delete --exclude "cdk/cdk.out/*" --exclude "cdk/node_modules/*" --exclude ".git/*" --profile blumron+orgsandbox3-Admin


# cd saas-multi-agents-workshop
# pwd 
# # Step 2: Deploy the CloudFormation stack
# echo "Deploying CloudFormation stack..."
# aws cloudformation deploy \
#   --template-file saas-bedrock-multi-agent-workshop/static/cfn/WorkshopStack.yaml \
#   --stack-name SaasWorkshopStack \
#   --parameter-overrides \
#     RepoUrl=https://github.com/aws-samples/saas-multi-agents-workshop.git \
#     AssetsBucketName=assets-test-bucket-blumron \
#     AssetsBucketPrefix="" \
#   --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
#   --profile blumron+orgsandbox3-Admin \
#   --region us-west-2

echo "Deployment complete! Now connect to Virtual VS Code, sync S3 and deploy the solution (./install.sh Create admin@example.com)"