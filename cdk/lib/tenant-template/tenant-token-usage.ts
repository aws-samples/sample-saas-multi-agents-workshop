// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Construct } from "constructs";
import * as cdk from "aws-cdk-lib";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";

import * as path from "path";

export interface TenantTokenUsageProps {
  readonly lambdaPowerToolsLayer: lambda.ILayerVersion;
}

export class TenantTokenUsage extends Construct {
  readonly tenantTokenUsageTable: dynamodb.TableV2;
  constructor(scope: Construct, id: string, props: TenantTokenUsageProps) {
    super(scope, id);

    const region = cdk.Stack.of(this).region;
    const accountId = cdk.Stack.of(this).account;

    const partitionKey = {
      name: "TenantId",
      type: dynamodb.AttributeType.STRING,
    };

    // Create the DynamoDB table
    const table = new dynamodb.TableV2(this, "TenantTokenUsage", {
      tableName: "TenantTokenUsage",
      partitionKey: partitionKey,
    });
    this.tenantTokenUsageTable = table;

    const tenantTokenUsageCalculatorLambdaExecRole = new iam.Role(
      this,
      "TenantTokenUsageCalculatorLambdaExecRole",
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

    tenantTokenUsageCalculatorLambdaExecRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["dynamodb:PutItem"],
        resources: [table.tableArn],
      })
    );

    tenantTokenUsageCalculatorLambdaExecRole.addToPolicy(
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

    const tenantTokenUsageCalculatorService = new PythonFunction(
      this,
      "TenantTokenUsageCalculatorService",
      {
        functionName: "TenantTokenUsageCalculatorService",
        entry: path.join(__dirname, "services/tenant-token-usage/"),
        runtime: lambda.Runtime.PYTHON_3_12,
        index: "tenant_token_usage_calculator.py",
        handler: "calculate_daily_tenant_token_usage",
        timeout: cdk.Duration.seconds(60),
        role: tenantTokenUsageCalculatorLambdaExecRole,
        layers: [props.lambdaPowerToolsLayer],
        environment: {
          TENANT_TOKEN_USAGE_DYNAMODB_TABLE: table.tableName,
        },
      }
    );

    const rule = new events.Rule(this, "TenantTokenUsageScheduleRule", {
      schedule: events.Schedule.rate(cdk.Duration.minutes(1)),
    });

    // Add the Lambda function as a target of the rule
    rule.addTarget(
      new targets.LambdaFunction(tenantTokenUsageCalculatorService)
    );
  }
}
