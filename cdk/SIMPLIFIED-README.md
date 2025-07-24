# Simplified SaaS Multi-Agents Workshop CDK

This is a simplified version of the SaaS Multi-Agents Workshop CDK that creates only the essential resources:

1. DynamoDB table to store tenant data
2. Amazon Bedrock Knowledge Base
3. S3 buckets for data and logs

## Resources Created

### DynamoDB Table
- **Name**: TenantDataTable
- **Partition Key**: tenantId (String)
- **Sort Key**: dataId (String)
- **Billing Mode**: Pay-per-request (on-demand)

### S3 Buckets
- **Data Bucket**: For storing tenant data
- **Logs Bucket**: For storing logs

### Amazon Bedrock
- **Knowledge Base**: For storing and retrieving vector embeddings
- **Data Source**: S3 data source connected to the Knowledge Base

### IAM Roles
- **Bedrock Role**: With permissions to access S3 and Bedrock services

## How to Deploy

To deploy only this simplified stack, run:

```bash
cd saas-multi-agents-workshop/cdk
npm run deploy:simplified
```

This will deploy only the simplified stack without deploying the full workshop infrastructure.

## How to Use

After deployment, you can use the resources as follows:

### Store Tenant Data in DynamoDB

```javascript
// Example using AWS SDK v3
import { DynamoDBClient, PutItemCommand } from "@aws-sdk/client-dynamodb";
import { marshall } from "@aws-sdk/util-dynamodb";

const client = new DynamoDBClient({ region: "us-east-1" });

const params = {
  TableName: "SimplifiedStack-TenantDataTable12345", // Replace with actual table name from output
  Item: marshall({
    tenantId: "tenant1",
    dataId: "config",
    name: "Example Tenant",
    tier: "basic",
    createdAt: new Date().toISOString()
  })
};

await client.send(new PutItemCommand(params));
```

### Upload Data to S3

```javascript
// Example using AWS SDK v3
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";

const s3Client = new S3Client({ region: "us-east-1" });

const params = {
  Bucket: "simplifiedstack-databucket12345", // Replace with actual bucket name from output
  Key: "tenant-data/tenant1/document.txt",
  Body: "This is a sample document for tenant1"
};

await s3Client.send(new PutObjectCommand(params));
```

### Use Amazon Bedrock Knowledge Base

The Bedrock Knowledge Base can be used to store and search vector embeddings:

```javascript
// Example using AWS SDK v3
import { BedrockAgentClient, RetrieveCommand } from "@aws-sdk/client-bedrock-agent";

const client = new BedrockAgentClient({ region: "us-east-1" });

const params = {
  knowledgeBaseId: "your-knowledge-base-id", // From stack output
  retrievalQuery: {
    text: "What is the pricing for the basic tier?"
  },
  retrievalConfiguration: {
    vectorSearchConfiguration: {
      numberOfResults: 5
    }
  }
};

const response = await client.send(new RetrieveCommand(params));
console.log(response.retrievalResults);
```

## Clean Up

To delete all resources created by this stack, run:

```bash
cd saas-multi-agents-workshop/cdk
cdk destroy --app "npx ts-node --prefer-ts-exts bin/simplified-app.ts"
```

This will delete all resources created by the simplified stack.