// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { RemovalPolicy, Stack, StackProps, CfnOutput, CfnResource } from "aws-cdk-lib";
import { Construct } from "constructs";
import { AttributeType, BillingMode, Table } from 'aws-cdk-lib/aws-dynamodb';
import { Bucket } from "aws-cdk-lib/aws-s3";
import { Role, ServicePrincipal, PolicyStatement, Effect } from "aws-cdk-lib/aws-iam";
import { bedrock } from '@cdklabs/generative-ai-cdk-constructs';
import * as _bedrock from 'aws-cdk-lib/aws-bedrock';
import { CoreUtilsTemplateStack } from "../core-utils-template-stack";
import { IdentityProvider } from "./identity-provider";


interface MultiAgentsBootstrapTemplateStackProps extends StackProps {
  readonly coreUtilsStack: CoreUtilsTemplateStack;
  readonly controlPlaneApiGwUrl: string;
}

export class MultiAgentsBootstrapTemplateStack extends Stack {
  constructor(
    scope: Construct, 
    id: string, 
    props: MultiAgentsBootstrapTemplateStackProps
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
    });

    const logsBucket = new Bucket(this, "LogsBucket", {
      autoDeleteObjects: true,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // 2. Create DynamoDB table for tenant data
    const tenantDataTable = new Table(this, 'TenantDataTable', {
      partitionKey: { name: 'tenantId', type: AttributeType.STRING },
      sortKey: { name: 'dataId', type: AttributeType.STRING },
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


    const coreUtilsStack = props.coreUtilsStack;
    // Access the codeBuildProject instance from the coreUtilsStack
    const codeBuildProject = coreUtilsStack.codeBuildProject;

    // Create OpenSearch Serverless collection and index
    const indexName =  "saas-workshop-pooled-index";
    const collectionName = "saas-workshop-vector-collection";


    const knowledgeBase = new bedrock.VectorKnowledgeBase(this, 'KnowledgeBase', {
      name: 'saas-workshop-pooled-knowledge-base',
      embeddingsModel: bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024,
      instruction: 'Use this knowledge base to answer questions about books. ' + 'It contains the full text of novels.',
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
    
    
    // // 6. Create a data source for the knowledge base
    // const dataSource = new bedrock.CfnDataSource(this, 'SimpleDataSource', {
    //   name: 'SimpleS3DataSource',
    //   knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
    //   dataSourceConfiguration: {
    //     type: 'S3',
    //     s3Configuration: {
    //       bucketArn: dataBucket.bucketArn,
    //       inclusionPrefixes: ['tenant-data/']
    //     }
    //   }
    // });

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

    // new CfnOutput(this, "KnowledgeBaseId", {
    //   value: knowledgeBase.attrKnowledgeBaseId,
    //   description: "The ID of the Bedrock Knowledge Base"
    // });
  }
}