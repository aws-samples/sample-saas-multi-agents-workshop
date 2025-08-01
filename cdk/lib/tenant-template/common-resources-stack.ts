// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { RemovalPolicy, Stack, StackProps, CfnOutput, CfnResource } from "aws-cdk-lib";
import { Construct } from "constructs";
import { AttributeType, BillingMode, Table } from 'aws-cdk-lib/aws-dynamodb';
import { Bucket, ObjectOwnership } from "aws-cdk-lib/aws-s3";
import { Role, ServicePrincipal, PolicyStatement, Effect } from "aws-cdk-lib/aws-iam";
import { bedrock } from '@cdklabs/generative-ai-cdk-constructs';
import * as _bedrock from 'aws-cdk-lib/aws-bedrock';
// import { CoreUtilsTemplateStack } from "../core-utils-template-stack";
import { IdentityProvider } from "./identity-provider";


interface CommonResourcesStackProps extends StackProps {
  // readonly coreUtilsStack: CoreUtilsTemplateStack;
  // readonly controlPlaneApiGwUrl: string;
}

export class CommonResourcesStack extends Stack {
  constructor(
    scope: Construct, 
    id: string, 
    props: CommonResourcesStackProps
  ) {
    super(scope, id, props);

    // Cognito and Identity resources

    const identityProvider = new IdentityProvider(this, "IdentityProvider");
    const app_client_id =
      identityProvider.tenantUserPoolClient.userPoolClientId;
    const userPoolID = identityProvider.tenantUserPool.userPoolId;

    // 1. Create S3 buckets
    const dataBucket = new Bucket(this, "DataBucket", {
      autoDeleteObjects: true,
      removalPolicy: RemovalPolicy.DESTROY,
      // Enable metadata filtering for tenant isolation
      objectOwnership: ObjectOwnership.BUCKET_OWNER_PREFERRED,
    });

    const logsBucket = new Bucket(this, "LogsBucket", {
      autoDeleteObjects: true,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // 2. Create DynamoDB tables for tenant data
    const tenantDataTable = new Table(this, 'TenantDataTable', {
      tableName: "TenantDataTable",
      partitionKey: { name: 'tenantId', type: AttributeType.STRING },
      sortKey: { name: 'dataId', type: AttributeType.STRING },
      readCapacity: 5,
      writeCapacity: 5,
      removalPolicy: RemovalPolicy.DESTROY,
    });

   

    // Create DynamoDB table for technical support issues
    const technicalSupportIssuesTable = new Table(this, 'TechnicalSupportIssuesTable', {
      tableName: 'technical-support-issues-table',
      partitionKey: { name: 'tenantId', type: AttributeType.STRING },
      sortKey: { name: 'issueId', type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // 3. Create IAM role for Bedrock
    const bedrockRole = new Role(this, 'BedrockRole', {
      assumedBy: new ServicePrincipal('bedrock.amazonaws.com'),
    });

    bedrockRole.addToPolicy(
      new PolicyStatement({
        actions: ['s3:GetObject', 's3:ListBucket'],
        resources: [dataBucket.bucketArn, `${dataBucket.bucketArn}/*`],
      })
    );
    
    // Add permissions for tenant mock data
    bedrockRole.addToPolicy(
      new PolicyStatement({
        actions: ['s3:GetObject', 's3:ListBucket'],
        resources: [
          `${dataBucket.bucketArn}/*/logs/*`,
          `${dataBucket.bucketArn}/*/kb/*`,
          `${dataBucket.bucketArn}/*/resolutions/*`,
          `${dataBucket.bucketArn}/*/sops/*`,
          `${dataBucket.bucketArn}/*/meeting-notes.txt`,
          `${dataBucket.bucketArn}/*/*.txt`
        ],
      })
    );

    // 4. Add Bedrock permissions to the role
    bedrockRole.addToPolicy(
      new PolicyStatement({
        actions: [
          "bedrock:CreateKnowledgeBase",
          "bedrock:CreateDataSource",
          "bedrock:InvokeModel",
          "bedrock:ListKnowledgeBases",
          "bedrock:Retrieve",
          "bedrock:RetrieveAndGenerate"
        ],
        effect: Effect.ALLOW,
        resources: ["*"],
      })
    );

    // Create OpenSearch Serverless collection and index
    const indexName =  "saas-workshop-pooled-index";
    const collectionName = "saas-workshop-vector-collection";


    // Create a pooled knowledge base for all tenants with metadata filtering
    const knowledgeBase = new bedrock.VectorKnowledgeBase(this, 'KnowledgeBase', {
      name: 'saas-workshop-pooled-knowledge-base',
      embeddingsModel: bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024,
      instruction: 'Use this knowledge base to answer questions about tenant data. ' +
                  'It contains knowledge base documents, resolution documents, SOPs, and meeting notes for all tenants. ' +
                  'Always filter results by the tenant_id metadata field to ensure tenant isolation.',
    });

    // Create a data source for the pooled knowledge base
    // Note: We're implementing tenant isolation through metadata in the S3 objects
    // and through the lambda function that accesses the knowledge base
    const dataSource = new bedrock.S3DataSource(this, 'S3DataSource', {
      knowledgeBase: knowledgeBase,
      dataSourceName: 'tenant-data-source',
      bucket: dataBucket,
      // Note: In a production environment, we would use a more sophisticated
      // approach to filter by tenant_id metadata, but for this workshop
      // we'll implement the filtering in the lambda function
    });

    const sourceCodeS3Bucket = new Bucket(this, "TenantSourceCodeBucket", {
      autoDeleteObjects: true,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Cost and Usage resources (Commented out for the moment)
        // const curPrefix = "CostUsageReport";
        // const curDatabaseName = "costexplorerdb";
        // // *****************
        // //  Layers
        // // *****************
    
        // // https://docs.powertools.aws.dev/lambda/python/2.31.0/#lambda-layer
        // const lambdaPowerToolsLayerARN = `arn:aws:lambda:${
        //   Stack.of(this).region
        // }:017000801446:layer:AWSLambdaPowertoolsPythonV2:59`;
        // const lambdaPowerToolsLayer = lambda.LayerVersion.fromLayerVersionArn(
        //   this,
        //   "LambdaPowerTools",
        //   lambdaPowerToolsLayerARN
        // );
    
        // const utilsLayer = new python.PythonLayerVersion(this, "UtilsLayer", {
        //   entry: path.join(__dirname, "services/layers/"),
        //   compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
        // });

        // const tenantTokenUsage = new TenantTokenUsage(this, "TenantTokenUsage", {
        //   lambdaPowerToolsLayer: lambdaPowerToolsLayer,
        // });

        // const curS3Bucket = new Bucket(this, "SaaSGenAICURWorkshopBucket", {
        //   autoDeleteObjects: true,
        //   removalPolicy: RemovalPolicy.DESTROY,
        // });

        //     const costPerTenant = new CostPerTenant(this, "CostPerTenant", {
        //       lambdaPowerToolsLayer: lambdaPowerToolsLayer,
        //       utilsLayer: utilsLayer,
        //       modelInvocationLogGroupName: bedrockCustom.modelInvocationLogGroupName,
        //       curDatabaseName: curDatabaseName,
        //       tableName: curPrefix.toLowerCase(),
        //       athenaOutputBucketName: curS3Bucket.bucketName,
        //     });
        
        //     const costUsageReportUpload = new CostUsageReportUpload(
        //       this,
        //       "CostUsageReportUpload",
        //       {
        //         curBucketName: curS3Bucket.bucketName,
        //         folderName: curPrefix,
        //       }
        //     );
        
        //     const curAthena = new CurAthena(this, "CurAthena", {
        //       curBucketName: curS3Bucket.bucketName,
        //       folderName: curPrefix,
        //       databaseName: curDatabaseName,
        //     });
        
        //     curAthena.node.addDependency(costUsageReportUpload);
    
    
    // Add comment explaining the data structure for tenant data in S3
    // Each tenant will have the following structure in S3:
    // tenant-id/
    //   ├── logs/
    //   │   └── microservice-logs.json (not included in knowledge base)
    //   ├── kb/
    //   │   └── [knowledge-base-documents].md (included in knowledge base)
    //   ├── resolutions/
    //   │   └── [resolution-documents].md (included in knowledge base)
    //   ├── sops/
    //   │   └── [sop-documents].md (included in knowledge base)
    //   ├── meeting-notes.txt (included in knowledge base)
    //   └── [tenant]_Error_Codes.txt (included in knowledge base)
    
    // The DynamoDB table will store structured meeting data with the following format:
    // {
    //   "tenantId": "tenant-id",
    //   "dataId": "meeting#meeting-id",
    //   "data": {
    //     "meeting_id": "meeting-id",
    //     "date": "YYYY-MM-DD",
    //     "action_items": [
    //       {
    //         "item_id": "item-id",
    //         "description": "action description",
    //         "owner": "owner name or [OWNER_MISSING]",
    //         "due_date": "YYYY-MM-DD or [DUE_DATE_MISSING]",
    //         "status": "pending|completed|in_progress|delayed",
    //         "context": "relevant discussion context"
    //       }
    //     ]
    //   }
    // }

    // The Technical Support Issues table will store issues with the following format:
    // {
    //   "tenantId": "tenant-id",
    //   "issueId": "issue-id",
    //   "title": "Issue title",
    //   "description": "Issue description",
    //   "status": "Open|In Progress|Resolved",
    //   "errorCode": "ERROR_CODE",
    //   "createdAt": "ISO timestamp",
    //   "updatedAt": "ISO timestamp",
    //   "resolution": {
    //     "steps": ["Step 1", "Step 2", ...],
    //     "resolvedAt": "ISO timestamp",
    //     "resolvedBy": "User or system name"
    //   }
    // }

    // Output the resource ARNs and names for reference
    new CfnOutput(this, "DataBucketName", {
      value: dataBucket.bucketName,
      description: "The name of the S3 bucket for tenant data"
    });

    new CfnOutput(this, "LogsBucketName", {
      value: logsBucket.bucketName,
      description: "The name of the S3 bucket for logs"
    });

    new CfnOutput(this, "TenantDataTableName", {
      value: tenantDataTable.tableName,
      description: "The name of the DynamoDB table for tenant data"
    });

    new CfnOutput(this, "TechnicalSupportIssuesTableName", {
      value: technicalSupportIssuesTable.tableName,
      description: "The name of the DynamoDB table for technical support issues"
    });

    new CfnOutput(this, "TenantSourceCodeS3Bucket", {
      value: sourceCodeS3Bucket.bucketName,
    });

    new CfnOutput(this, "KnowledgeBaseId", {
      value: knowledgeBase.knowledgeBaseId,
      description: "The ID of the Bedrock Knowledge Base"
    });
    
    new CfnOutput(this, "SaaSGenAIWorkshopS3Bucket", {
      value: dataBucket.bucketName,
      description: "The name of the S3 bucket for tenant data"
    });
    
    new CfnOutput(this, "SaaSGenAIWorkshopTriggerIngestionLambdaArn", {
      value: "dummy-value", // This will be replaced with actual Lambda ARN in a real implementation
      description: "The ARN of the Lambda function to trigger ingestion"
    });
    
    new CfnOutput(this, "SaaSGenAIWorkshopOSSCollectionArn", {
      value: "dummy-value", // This will be replaced with actual collection ARN in a real implementation
      description: "The ARN of the OpenSearch Serverless collection"
    });
  }
}