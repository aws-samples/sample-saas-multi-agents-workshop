// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { RemovalPolicy, Stack, StackProps, CfnOutput, CfnResource, Duration } from "aws-cdk-lib";
import { Construct } from "constructs";
import { AttributeType, BillingMode, Table } from 'aws-cdk-lib/aws-dynamodb';
import { Bucket, ObjectOwnership } from "aws-cdk-lib/aws-s3";
import { Role, ServicePrincipal, PolicyStatement, Effect } from "aws-cdk-lib/aws-iam";
import { ApiGateway } from "./api-gateway";
import { Services } from "./services";
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as python from '@aws-cdk/aws-lambda-python-alpha';
import * as path from 'path';
import { IdentityProvider } from "./identity-provider";
import { TenantTokenUsage } from "./tenant-token-usage";
import { BucketFactory } from '../constructs/bucket-factory';
import { Config } from '../config';
import { ResourceNaming } from '../naming';
import { BedrockKnowledgeBase } from '../constructs/bedrock-kb';

interface CommonResourcesStackProps extends StackProps {
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

    // Get Lambda Powertools layer using Config
    const lambdaPowerToolsLayer = lambda.LayerVersion.fromLayerVersionArn(
      this,
      "LambdaPowerTools",
      Config.getPowerToolsLayerArn(this.region)
    );

    // Create a resource naming helper
    const naming = new ResourceNaming(this);
    
    // 1. Create S3 buckets using BucketFactory
    const dataBucket = BucketFactory.createDataBucket(this, "DataBucket",
      naming.bucketName('kb-data')
    );

    const logsBucket = BucketFactory.createLogsBucket(this, "LogsBucket",
      naming.bucketName('logs')
    );

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

    // Create Bedrock Knowledge Base (handles dependencies internally)
    const knowledgeBase = new BedrockKnowledgeBase(this, 'BedrockKnowledgeBase', {
      knowledgeBaseName: naming.knowledgeBaseName('data'),
      description: 'Knowledge base for custom data source',
      roleArn: bedrockRole.roleArn,
      dataBucket: dataBucket,
      lambdaLayer: lambdaPowerToolsLayer,
      vectorBucketName: naming.bucketName('kb-vectors'),
      vectorIndexName: `kb-embeddings-index-${this.account}`,
    });
    
    const knowledgeBaseId = knowledgeBase.knowledgeBaseId;
    const knowledgeBaseArn = knowledgeBase.knowledgeBaseArn;

    const sourceCodeS3Bucket = BucketFactory.createStandardBucket(
      this,
      "TenantSourceCodeBucket"
    );

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

    const api = new ApiGateway(this, "SaaSKnowledgeServiceRestApi", {});

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
    
    new CfnOutput(this, "DataSourceId", {
      value: knowledgeBase.dataSource.attrDataSourceId,
      description: "The ID of the Bedrock Knowledge Base Data Source"
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
      value: services.triggerDataIngestionService.functionArn,
      description: "The ARN of the Lambda function to trigger ingestion"
    });
    
  }
}