// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { RemovalPolicy, Stack, StackProps, CfnOutput, CfnResource, Duration } from "aws-cdk-lib";
import { Construct } from "constructs";
import { AttributeType, BillingMode, Table } from 'aws-cdk-lib/aws-dynamodb';
import { Bucket, ObjectOwnership } from "aws-cdk-lib/aws-s3";
import { Role, ServicePrincipal, PolicyStatement, Effect } from "aws-cdk-lib/aws-iam";
// import { bedrock } from '@cdklabs/generative-ai-cdk-constructs';
import { ApiGateway } from "./api-gateway";
import { Services } from "./services";
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as python from '@aws-cdk/aws-lambda-python-alpha';
import * as path from 'path';
// import { CoreUtilsTemplateStack } from "../core-utils-template-stack";
import { IdentityProvider } from "./identity-provider";
import { TenantTokenUsage } from "./tenant-token-usage";
import { S3VectorBucketResource } from './s3-vector-bucket-resource';
import { BedrockKnowledgeBaseResource } from './bedrock-knowledge-base-resource';


interface CommonResourcesStackProps extends StackProps {
  // readonly coreUtilsStack: CoreUtilsTemplateStack;
  readonly controlPlaneApiGwUrl: string;
  readonly crossRegionReferences?: boolean;
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

    // *****************
    //  Layers
    // *****************

    // https://docs.powertools.aws.dev/lambda/python/2.31.0/#lambda-layer
    const lambdaPowerToolsLayerARN = `arn:aws:lambda:${
      Stack.of(this).region
    }:017000801446:layer:AWSLambdaPowertoolsPythonV2:59`;

    const lambdaPowerToolsLayer = lambda.LayerVersion.fromLayerVersionArn(
      this,
      "LambdaPowerTools",
      lambdaPowerToolsLayerARN
    );

    // 1. Create S3 buckets
    const dataBucket = new Bucket(this, "DataBucket", {
      bucketName: `saas-ws-kb-data-${this.account}`,
      autoDeleteObjects: true,
      removalPolicy: RemovalPolicy.DESTROY,
      // Enable metadata filtering for tenant isolation
      objectOwnership: ObjectOwnership.BUCKET_OWNER_PREFERRED,
    });

    // Create S3 Vector bucket
    const vectorBucket = new S3VectorBucketResource(this, 'VectorBucket', {
      bucketName: `saas-ws-kb-vectors-${this.account}`,
      sseType: 'AES256',
      indexName: `kb-embeddings-index-${this.account}`,
      dimension: 1024,
      distanceMetric: 'cosine',
      dataType: 'float32',
      lambdaLayer: lambdaPowerToolsLayer,
    });

    const logsBucket = new Bucket(this, "LogsBucket", {
      bucketName: `saas-ws-logs-bucket-${this.account}`,
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
      description: 'Role for Bedrock to access resources',
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

    bedrockRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          's3vectors:QueryVectors',
          's3vectors:GetVectors',
          's3vectors:GetIndex',
          's3vectors:ListIndices',
          's3vectors:DescribeVectorBucket',
          's3vectors:PutVectors',
          's3vectors:DeleteVectors',
        ],
        resources: ['*'],
      })
    );


    // Create a pooled knowledge base for all tenants with metadata filtering
    // const knowledgeBase = new bedrock.VectorKnowledgeBase(this, 'KnowledgeBase', {
    //   name: 'saas-workshop-pooled-knowledge-base',
    //   embeddingsModel: bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024,
    //   instruction: 'Use this knowledge base to answer questions about tenant data. ' +
    //               'It contains knowledge base documents, resolution documents, SOPs, and meeting notes for all tenants. ' +
    //               'Always filter results by the tenant_id metadata field to ensure tenant isolation.',
    // });

    // Create a data source for the pooled knowledge base
    // Note: We're implementing tenant isolation through metadata in the S3 objects
    // and through the lambda function that accesses the knowledge base



    // Create Bedrock Knowledge Base
    const knowledgeBase = new BedrockKnowledgeBaseResource(this, 'BedrockKnowledgeBase', {
      knowledgeName: `${this.stackName.toLowerCase()}-saas-ws-data-kb`, 
      description: 'Knowledge base for custom data source',
      roleArn: bedrockRole.roleArn,
      embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
      indexArn: `arn:aws:s3vectors:${this.region}:${this.account}:bucket/kb-vectors-${this.account}/index/kb-embeddings-index-${this.account}`,
      lambdaLayer: lambdaPowerToolsLayer,
    });

    const knowledgeBaseId = knowledgeBase.knowledgeBaseId;
    const knowledgeBaseArn = knowledgeBase.knowledgeBaseArn;

    const dataSource = new bedrock.CfnDataSource(this, 'S3DataSource', {
      knowledgeBaseId: knowledgeBaseId,
      name: `${this.stackName.toLowerCase()}-kb-data-source`,
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: {
            bucketArn: dataBucket.bucketArn
          },
      },
      // Note: In a production environment, we would use a more sophisticated
      // approach to filter by tenant_id metadata, but for this workshop
      // we'll implement the filtering in the lambda function
    });

    knowledgeBase.node.addDependency(vectorBucket);
    knowledgeBase.bedrockKb.node.addDependency(vectorBucket.s3VectorBucket);

    dataSource.node.addDependency(knowledgeBase);

    const sourceCodeS3Bucket = new Bucket(this, "TenantSourceCodeBucket", {
      autoDeleteObjects: true,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Cost and Usage resources
    const curPrefix = "CostUsageReport";
    const curDatabaseName = "costexplorerdb";


    const utilsLayer = new python.PythonLayerVersion(this, "UtilsLayer", {
      entry: path.join(__dirname, "services/layers/"),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      compatibleArchitectures: [lambda.Architecture.ARM_64],
      bundling: {
        platform: "linux/arm64",
      },
    });


    const tenantTokenUsage = new TenantTokenUsage(this, "TenantTokenUsage", {
      lambdaPowerToolsLayer: lambdaPowerToolsLayer,
    });

    const api = new ApiGateway(this, "SaaSGenAIWorkshopRestApi", {});

    const services = new Services(this, "SaaSGenAIWorkshopServices", {
      appClientID: app_client_id,
      userPoolID: userPoolID,
      s3Bucket: dataBucket,
      tenantTokenUsageTable: tenantTokenUsage.tenantTokenUsageTable,
      restApi: api.restApi,
      controlPlaneApiGwUrl: props.controlPlaneApiGwUrl,
      lambdaPowerToolsLayer: lambdaPowerToolsLayer,
      utilsLayer: utilsLayer,
    });

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

    new CfnOutput(this, "TenantUserpoolId", {
      value: identityProvider.tenantUserPool.userPoolId,
    });

    new CfnOutput(this, "UserPoolClientId", {
      value: identityProvider.tenantUserPoolClient.userPoolClientId,
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

    new CfnOutput(this, "ApiGatewayUrl", {
      value: api.restApi.url,
    });

    new CfnOutput(this, "ApiGatewayUsagePlan", {
      value: api.usagePlanBasicTier.usagePlanId,
    });
    
    new CfnOutput(this, "SaaSGenAIWorkshopTriggerIngestionLambdaArn", {
      value: "dummy-value", // This will be replaced with actual Lambda ARN in a real implementation
      description: "The ARN of the Lambda function to trigger ingestion"
    });
    
  }
}