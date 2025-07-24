#!/bin/bash -e

export CDK_PARAM_SYSTEM_ADMIN_EMAIL="$1"

if [[ -z "$CDK_PARAM_SYSTEM_ADMIN_EMAIL" ]]; then
  echo "Please provide system admin email"
  exit 1
fi

echo "$(date) emptying out buckets..."
for i in $(aws s3 ls | awk '{print $3}' | grep -E "^saas-genai-workshop-*"); do
    echo "$(date) emptying out s3 bucket with name s3://${i}..."
    aws s3 rm --recursive "s3://${i}"
done

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if required tools are installed
if ! command_exists aws; then
    echo "Error: AWS CLI is not installed. Please install it and configure your credentials."
    exit 1
fi

if ! command_exists cdk; then
    echo "Error: AWS CDK is not installed. Please install it using 'npm install -g aws-cdk'."
    exit 1
fi

# Navigate to the directory containing the CDK app
# Replace 'path/to/cdk/app' with the actual path to your CDK application
cd ../cdk

echo "Starting cleanup process..."

# Destroy the CDK stacks
echo "Destroying CDK stacks..."
cdk destroy --all --force

# Remove the CDK context file
echo "Removing CDK context file..."
rm -f cdk.context.json

# Remove the CDK output directory
echo "Removing CDK output directory..."
rm -rf cdk.out

# Optionally, remove node_modules if you want to clean up dependencies
# echo "Removing node_modules..."
# rm -rf node_modules

# Clean up any DynamoDB tables
echo "Cleaning up DynamoDB tables..."
tables=$(aws dynamodb list-tables --query 'TableNames[?contains(@, `TenantCostAndUsageAttribution`)]' --output text)

for table in $tables; do
    echo "Deleting DynamoDB table: $table"
    aws dynamodb delete-table --table-name $table --no-cli-pager
done

# Clean up any Lambda functions
# echo "Cleaning up Lambda functions..."
# functions=$(aws lambda list-functions --query 'Functions[?contains(FunctionName, `YourProjectPrefix`)].FunctionName' --output text)

# for func in $functions; do
#     echo "Deleting Lambda function: $func"
#     aws lambda delete-function --function-name $func
# done

# Clean up CodeCommit repository
echo "Cleaning up CodeCommit repository..."
export CDK_PARAM_CODE_COMMIT_REPOSITORY_NAME="saas-genai-workshop"

if aws codecommit get-repository --repository-name $CDK_PARAM_CODE_COMMIT_REPOSITORY_NAME >/dev/null 2>&1; then
  echo "Deleting CodeCommit repository: $CDK_PARAM_CODE_COMMIT_REPOSITORY_NAME"
  aws codecommit delete-repository --repository-name $CDK_PARAM_CODE_COMMIT_REPOSITORY_NAME --no-cli-pager
  echo "CodeCommit repository deleted successfully."
else
  echo "CodeCommit repository $CDK_PARAM_CODE_COMMIT_REPOSITORY_NAME does not exist. Skipping deletion."
fi

echo "$(date) cleaning up log groups..."
next_token=""
while true; do
    if [[ "${next_token}" == "" ]]; then
        response=$(aws logs describe-log-groups)
    else
        response=$(aws logs describe-log-groups --starting-token "$next_token")
    fi

    log_groups=$(echo "$response" | jq -r '.logGroups[].logGroupName | select(. | test("^/aws/lambda/ControlPlaneStack-*|saas-genai-workshop-*|provisioningJobRunner*|^/aws/lambda/TenantCostCalculatorService|^/aws/bedrock/SaaSGenAIWorkshopBedrockLogGroup"))')
    for i in $log_groups; do
        if [[ -z "${skip_flag}" ]]; then
            read -p "Delete log group with name $i [Y/n] " -n 1 -r
        fi

        if [[ $REPLY =~ ^[n]$ ]]; then
            echo "$(date) NOT deleting log group $i."
        else
            echo "$(date) deleting log group with name $i..."
            aws logs delete-log-group --log-group-name "$i"
        fi
    done

    next_token=$(echo "$response" | jq '.NextToken')
    if [[ "${next_token}" == "null" ]]; then
        # no more results left. Exit loop...
        break
    fi
done

echo "$(date) cleaning up user pools..."
next_token=""
while true; do
    if [[ "${next_token}" == "" ]]; then
        response=$( aws cognito-idp list-user-pools --max-results 10)
    else
        # using next-token instead of starting-token. See: https://github.com/aws/aws-cli/issues/7661
        response=$( aws cognito-idp list-user-pools --max-results 10 --next-token "$next_token")
    fi

    pool_ids=$(echo "$response" | jq -r '.UserPools[] | select(.Name | test("^IdentityProvidertenantUserPool|^CognitoAuthUserPool")) |.Id')
    for i in $pool_ids; do
        echo "$(date) deleting user pool with name $i..."
        echo "getting pool domain..."
        pool_domain=$(aws cognito-idp describe-user-pool --user-pool-id "$i" | jq -r '.UserPool.Domain')

        # Delete the pool domain if it exists
        if [[ "$pool_domain" != "null" && -n "$pool_domain" ]]; then
          echo "deleting pool domain $pool_domain..."
          aws cognito-idp delete-user-pool-domain \
            --user-pool-id "$i" \
            --domain "$pool_domain"
        else
          echo "No domain associated with this user pool or unable to retrieve domain."
        fi

        echo "deleting pool $i..."
        aws cognito-idp delete-user-pool --user-pool-id "$i" --no-cli-pager
    done

    next_token=$(echo "$response" | jq -r '.NextToken')
    if [[ "${next_token}" == "null" ]]; then
        # no more results left. Exit loop...
        break
    fi
done

echo "Cleanup process completed."
