// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Construct } from "constructs";
import * as path from "path";
import * as python from "@aws-cdk/aws-lambda-python-alpha";
import {
  Architecture,
  Code,
  Runtime,
  LayerVersion,
  Function,
  ILayerVersion,
} from "aws-cdk-lib/aws-lambda";
import { Duration, Stack, Arn } from "aws-cdk-lib";
import { Bucket } from "aws-cdk-lib/aws-s3";
import {
  Role,
  ServicePrincipal,
  PolicyStatement,
  Effect,
  ArnPrincipal,
  ManagedPolicy,
  PolicyDocument,
} from "aws-cdk-lib/aws-iam";
import {
  RestApi,
  LambdaIntegration,
  AuthorizationType,
} from "aws-cdk-lib/aws-apigateway";
import * as apigw from "aws-cdk-lib/aws-apigateway";
import { Asset } from "aws-cdk-lib/aws-s3-assets";
import { TableV2 } from "aws-cdk-lib/aws-dynamodb";

export interface ServicesProps {
  readonly appClientID: string;
  readonly userPoolID: string;
  readonly s3Bucket: Bucket;
  readonly tenantTokenUsageTable?: TableV2; // Made optional
  readonly restApi: RestApi;
  readonly controlPlaneApiGwUrl: string;
  readonly lambdaPowerToolsLayer: ILayerVersion;
  readonly utilsLayer: ILayerVersion;
}

export class Services extends Construct {
  public readonly ragService: Function;
  public readonly s3UploaderService: Function;
  public readonly triggerDataIngestionService: Function;
  public readonly getJWTTokenService: Function;
  public readonly authorizerService: Function;

  constructor(scope: Construct, id: string, props: ServicesProps) {
    super(scope, id);

    const region = Stack.of(this).region;
    const accountId = Stack.of(this).account;

    const invoke = props.restApi.root.addResource("invoke");
    const s3Upload = props.restApi.root.addResource("upload");

    // *****************
    // Authorizer Lambda
    // *****************

    const authorizerLambdaExecRole = new Role(
      this,
      "authorizerLambdaExecRole",
      {
        assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
        managedPolicies: [
          ManagedPolicy.fromAwsManagedPolicyName(
            "CloudWatchLambdaInsightsExecutionRolePolicy"
          ),
          ManagedPolicy.fromAwsManagedPolicyName(
            "service-role/AWSLambdaBasicExecutionRole"
          ),
        ],
      }
    );

    authorizerLambdaExecRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["cognito-idp:InitiateAuth"],
        resources: [
          `arn:aws:cognito-idp:${region}:${accountId}:userpool/${props.userPoolID}`,
        ],
      })
    );

    // Create role only if tenantTokenUsageTable is provided
    const tenantTokenUsageTableAccessRole = props.tenantTokenUsageTable ? new Role(
      this,
      "TenantTokenUsageTableAccessRole",
      {
        assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
        inlinePolicies: {
          DynamoDBPolicy: new PolicyDocument({
            statements: [
              new PolicyStatement({
                effect: Effect.ALLOW,
                actions: ["dynamodb:GetItem"],
                resources: [props.tenantTokenUsageTable.tableArn],
                conditions: {
                  "ForAllValues:StringEquals": {
                    "dynamodb:LeadingKeys": ["${aws:PrincipalTag/TenantId}"],
                  },
                },
              }),
            ],
          }),
        },
      }
    ) : undefined;

    // Only add statements if the role exists
    if (tenantTokenUsageTableAccessRole) {
      tenantTokenUsageTableAccessRole.assumeRolePolicy?.addStatements(
        new PolicyStatement({
          actions: ["sts:AssumeRole", "sts:TagSession"],
          effect: Effect.ALLOW,
          principals: [new ArnPrincipal(authorizerLambdaExecRole.roleArn)],
          conditions: {
            StringLike: {
              "aws:RequestTag/TenantId": "*",
            },
          },
        })
      );
    }

    // *********************
    //  Combined ABAC Role
    // *********************

    const abacExecRole = new Role(this, "AbacExecRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        ManagedPolicy.fromAwsManagedPolicyName(
          "CloudWatchLambdaInsightsExecutionRolePolicy"
        ),
        ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
      inlinePolicies: {
        ABACPolicy: new PolicyDocument({
          statements: [
            new PolicyStatement({
              effect: Effect.ALLOW,
              actions: ["bedrock:ListKnowledgeBases"],
              resources: ["*"],
            }),
            new PolicyStatement({
              effect: Effect.ALLOW,
              actions: ["bedrock:InvokeModel"],
              resources: [
                "arn:aws:bedrock:*::foundation-model/amazon.titan-text-lite-v1",
              ],
            }),
            new PolicyStatement({
              effect: Effect.ALLOW,
              actions: [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject",
              ],
              resources: [
                `arn:aws:s3:::${props.s3Bucket.bucketName}` +
                  "/${aws:PrincipalTag/TenantId}/*",
              ],
            }),
            new PolicyStatement({
              effect: Effect.ALLOW,
              actions: ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
              resources: [
                Arn.format(
                  {
                    service: "bedrock",
                    resource: "knowledge-base",
                    // TODO: Lab2 - Add principalTag in ABAC policy
                    resourceName: "*",
                    account: accountId,
                    region: region,
                  },
                  Stack.of(this)
                ),
              ],
            }),
          ],
        }),
      },
    });

    abacExecRole.assumeRolePolicy?.addStatements(
      new PolicyStatement({
        actions: ["sts:AssumeRole", "sts:TagSession"],
        effect: Effect.ALLOW,
        principals: [new ArnPrincipal(authorizerLambdaExecRole.roleArn)],
        conditions: {
          StringLike: {
            "aws:RequestTag/TenantId": "*",
            "aws:RequestTag/KnowledgeBaseId": "*",
          },
        },
      })
    );

    const authorizerService = new python.PythonFunction(
      this,
      "AuthorizerService",
      {
        functionName: "authorizerService",
        entry: path.join(__dirname, "services/authorizerService/"),
        runtime: Runtime.PYTHON_3_12,
        architecture: Architecture.ARM_64,
        index: "tenant_authorizer.py",
        handler: "lambda_handler",
        timeout: Duration.seconds(60),
        role: authorizerLambdaExecRole,
        layers: [props.lambdaPowerToolsLayer, props.utilsLayer],
        bundling: {
          platform: "linux/arm64",
        },
        environment: {
          APP_CLIENT_ID: props.appClientID,
          USER_POOL_ID: props.userPoolID,
          ASSUME_ROLE_ARN: abacExecRole.roleArn,
          CP_API_GW_URL: props.controlPlaneApiGwUrl,
          ...(props.tenantTokenUsageTable && {
            TENANT_TOKEN_USAGE_DYNAMODB_TABLE: props.tenantTokenUsageTable.tableName,
            TENANT_TOKEN_USAGE_ROLE_ARN: tenantTokenUsageTableAccessRole?.roleArn || '',
          }),
        },
      }
    );

    const authorizer = new apigw.RequestAuthorizer(
      this,
      "apiRequestAuthorizer",
      {
        handler: authorizerService,
        identitySources: [apigw.IdentitySource.header("authorization")],
        resultsCacheTtl: Duration.seconds(0),
      }
    );

    // RAG lambda
    const raglambdaExecRole = new Role(this, "RaglambdaExecRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        ManagedPolicy.fromAwsManagedPolicyName(
          "CloudWatchLambdaInsightsExecutionRolePolicy"
        ),
        ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    });

    const ragService = new python.PythonFunction(this, "RagService", {
      functionName: "ragService",
      entry: path.join(__dirname, "services/ragService/"),
      runtime: Runtime.PYTHON_3_12,
      architecture: Architecture.ARM_64,
      index: "rag_service.py",
      handler: "lambda_handler",
      timeout: Duration.seconds(60),
      memorySize: 256,
      role: raglambdaExecRole,
      layers: [props.lambdaPowerToolsLayer, props.utilsLayer],
      bundling: {
        platform: "linux/arm64",
      },
      environment: {
        POWERTOOLS_SERVICE_NAME: "RagService",
        POWERTOOLS_METRICS_NAMESPACE: "SaaSRAGGenAI",
      },
    });

    this.ragService = ragService;
    invoke.addMethod(
      "POST",
      new LambdaIntegration(this.ragService, { proxy: true }),
      {
        authorizer: authorizer,
        authorizationType: apigw.AuthorizationType.CUSTOM,
        apiKeyRequired: true,
      }
    );

    // S3 Uploader lambda
    const s3UploaderExecRole = new Role(this, "S3UploaderExecRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        ManagedPolicy.fromAwsManagedPolicyName(
          "CloudWatchLambdaInsightsExecutionRolePolicy"
        ),
        ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    });

    const s3Uploader = new python.PythonFunction(this, "S3Uploader", {
      functionName: "s3Uploader",
      entry: path.join(__dirname, "services/s3Uploader/"),
      runtime: Runtime.PYTHON_3_12,
      architecture: Architecture.ARM_64,
      index: "s3uploader.py",
      handler: "lambda_handler",
      timeout: Duration.seconds(60),
      role: s3UploaderExecRole,
      layers: [props.lambdaPowerToolsLayer],
      bundling: {
        platform: "linux/arm64",
      },
      environment: {
        S3_BUCKET_NAME: props.s3Bucket.bucketName,
      },
    });

    this.s3UploaderService = s3Uploader;
    s3Upload.addMethod(
      "POST",
      new LambdaIntegration(this.s3UploaderService, { proxy: true }),
      {
        authorizer: authorizer,
        authorizationType: apigw.AuthorizationType.CUSTOM,
      }
    );

    // Trigger data ingestion lambda
    const triggerDataIngestionExecRole = new Role(
      this,
      "TriggerDataIngestionExecRole",
      {
        assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
        managedPolicies: [
          ManagedPolicy.fromAwsManagedPolicyName(
            "CloudWatchLambdaInsightsExecutionRolePolicy"
          ),
          ManagedPolicy.fromAwsManagedPolicyName(
            "service-role/AWSLambdaBasicExecutionRole"
          ),
        ],
      }
    );

    // ABAC role which will be assumed by the Data Ingestion  lambda
    const triggerDataIngestionServiceAssumeRole = new Role(
      this,
      "TriggerDataIngestionServiceAssumeRole",
      {
        assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
      }
    );

    triggerDataIngestionServiceAssumeRole.assumeRolePolicy?.addStatements(
      new PolicyStatement({
        actions: ["sts:AssumeRole", "sts:TagSession"],
        effect: Effect.ALLOW,
        principals: [new ArnPrincipal(triggerDataIngestionExecRole.roleArn)],
      })
    );

    triggerDataIngestionServiceAssumeRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["bedrock:StartIngestionJob", "bedrock:GetIngestionJob"],
        resources: [
          Arn.format(
            {
              service: "bedrock",
              resource: "knowledge-base",
              resourceName: "${aws:PrincipalTag/KnowledgeBaseId}",
              account: accountId,
              region: region,
            },
            Stack.of(this)
          ),
        ],
      })
    );

    const triggerDataIngestionService = new python.PythonFunction(
      this,
      "TriggerDataIngestionService",
      {
        functionName: "triggerDataIngestionService",
        entry: path.join(__dirname, "services/triggerDataIngestionService/"),
        runtime: Runtime.PYTHON_3_12,
        architecture: Architecture.ARM_64,
        index: "trigger_data_ingestion.py",
        handler: "lambda_handler",
        timeout: Duration.seconds(60),
        role: triggerDataIngestionExecRole,
        layers: [props.lambdaPowerToolsLayer],
        bundling: {
          platform: "linux/arm64",
        },
        environment: {
          ASSUME_ROLE_ARN: triggerDataIngestionServiceAssumeRole.roleArn,
        },
      }
    );

    this.triggerDataIngestionService = triggerDataIngestionService;

    // Add permission for eventbrige to trigger data ingestion service
    const eventBusRuleArn = Arn.format(
      {
        service: "events",
        resource: "rule/*",
        account: accountId,
        region: region,
      },
      Stack.of(this)
    );
    triggerDataIngestionService.addPermission(
      "EventBusTriggerDataIngestionPermission",
      {
        principal: new ServicePrincipal("events.amazonaws.com"),
        action: "lambda:InvokeFunction",
        sourceArn: eventBusRuleArn,
      }
    );
  }
}
