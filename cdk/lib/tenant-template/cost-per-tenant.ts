// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";

import * as path from "path";

export interface CostPerTenantProps {
  readonly lambdaPowerToolsLayer: lambda.ILayerVersion;
  readonly utilsLayer: lambda.ILayerVersion;
  readonly modelInvocationLogGroupName: string;
  readonly curDatabaseName: string;
  readonly tableName: string;
  readonly athenaOutputBucketName: string;
}

export class CostPerTenant extends Construct {
  constructor(scope: Construct, id: string, props: CostPerTenantProps) {
    super(scope, id);

    const region = cdk.Stack.of(this).region;
    const accountId = cdk.Stack.of(this).account;
    const athenaOutputPath = `${props.athenaOutputBucketName}/athenaoutput`;

    // TODO: Athena setup

    const partitionKey = { name: "Date", type: dynamodb.AttributeType.NUMBER };
    const sortKey = {
      name: "TenantId#ServiceName",
      type: dynamodb.AttributeType.STRING,
    };

    // Create the DynamoDB table
    const table = new dynamodb.TableV2(this, "TenantCostAndUsageAttribution", {
      tableName: "TenantCostAndUsageAttribution",
      partitionKey: partitionKey,
      sortKey: sortKey,
    });

    const tenantCostCalculatorLambdaExecRole = new iam.Role(
      this,
      "tenantCostCalculatorLambdaExecRole",
      {
        assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
        managedPolicies: [
          iam.ManagedPolicy.fromAwsManagedPolicyName(
            "CloudWatchLambdaInsightsExecutionRolePolicy"
          ),
          iam.ManagedPolicy.fromAwsManagedPolicyName(
            "service-role/AWSLambdaBasicExecutionRole"
          ),
        ],
      }
    );

    tenantCostCalculatorLambdaExecRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["dynamodb:PutItem"],
        resources: [table.tableArn],
      })
    );

    tenantCostCalculatorLambdaExecRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "logs:GetQueryResults",
          "logs:StartQuery",
          "logs:StopQuery",
          "logs:FilterLogEvents",
          "logs:DescribeLogGroups",
        ],
        resources: [`arn:aws:logs:${region}:${accountId}:log-group:*`],
      })
    );

    tenantCostCalculatorLambdaExecRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "cloudwatch:ListMetrics",
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
        ],
        resources: ["*"],
      })
    );

    tenantCostCalculatorLambdaExecRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["cloudformation:ListStackResources"],
        resources: [`arn:aws:cloudformation:${region}:${accountId}:stack/*/*`],
      })
    );

    tenantCostCalculatorLambdaExecRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "athena:StartQueryExecution",
          "athena:StopQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
        ],
        resources: [`arn:aws:athena:${region}:${accountId}:workgroup/*`],
      })
    );

    tenantCostCalculatorLambdaExecRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "s3:PutObject",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts",
          "s3:ListBucketMultipartUploads",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ],
        resources: [
          `arn:aws:s3:::${props.athenaOutputBucketName}`,
          `arn:aws:s3:::${props.athenaOutputBucketName}/*`,
        ],
      })
    );

    tenantCostCalculatorLambdaExecRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions"],
        resources: [`*`],
      })
    );

    const tenantCostCalculatorService = new PythonFunction(
      this,
      "TenantCostCalculatorService",
      {
        functionName: "TenantCostCalculatorService",
        entry: path.join(__dirname, "services/aggregate-metrics/"),
        runtime: lambda.Runtime.PYTHON_3_12,
        architecture: lambda.Architecture.ARM_64,
        index: "tenant_cost_calculator.py",
        handler: "calculate_cost_per_tenant",
        timeout: cdk.Duration.seconds(60),
        role: tenantCostCalculatorLambdaExecRole,
        layers: [props.lambdaPowerToolsLayer, props.utilsLayer],
        environment: {
          ATHENA_S3_OUTPUT: athenaOutputPath,
          TENANT_COST_DYNAMODB_TABLE: table.tableName,
          MODEL_INVOCATION_LOG_GROUPNAME: props.modelInvocationLogGroupName,
          CUR_DATABASE_NAME: props.curDatabaseName,
          CUR_TABLE_NAME: props.tableName,
        },
      }
    );

    const rule = new events.Rule(this, "ScheduleRule", {
      schedule: events.Schedule.rate(cdk.Duration.minutes(5)),
    });

    // Add the Lambda function as a target of the rule
    rule.addTarget(new targets.LambdaFunction(tenantCostCalculatorService));
  }
}
