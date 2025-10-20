// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as path from "path";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import { Duration } from "aws-cdk-lib";
import {
  ManagedPolicy,
  Role,
  ServicePrincipal,
  PolicyStatement,
  Effect,
  ArnPrincipal,
} from "aws-cdk-lib/aws-iam";
import { Function, Runtime, Architecture } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { CustomResource } from "aws-cdk-lib";
import { Construct } from "constructs";

export class BedrockCustom extends Construct {
  readonly bedrockLambdaFunc: Function;
  readonly modelInvocationLogGroupName: string;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    /**
     * Creates an IAM role for the Bedrock Customization Lambda function.
     * The role is granted read and write access to the Tenant Details table,
     * and the ability to put events to the Event Manager.
     * The role is also assigned the AWSLambdaBasicExecutionRole,
     * CloudWatchLambdaInsightsExecutionRolePolicy, and AWSXrayWriteOnlyAccess
     * managed policies.
     */
    const bedrockLogGroup = new LogGroup(
      this,
      "SaaSGenAIWorkshopBedrockLogGroup",
      {
        retention: RetentionDays.ONE_WEEK,
      }
    );
    this.modelInvocationLogGroupName = bedrockLogGroup.logGroupName;

    const bedrockLambdaExecRole = new Role(this, "bedrockLambdaExecRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    bedrockLambdaExecRole.addManagedPolicy(
      ManagedPolicy.fromAwsManagedPolicyName(
        "service-role/AWSLambdaBasicExecutionRole"
      )
    );
    bedrockLambdaExecRole.addManagedPolicy(
      ManagedPolicy.fromAwsManagedPolicyName(
        "CloudWatchLambdaInsightsExecutionRolePolicy"
      )
    );
    bedrockLambdaExecRole.addManagedPolicy(
      ManagedPolicy.fromAwsManagedPolicyName("AWSXrayWriteOnlyAccess")
    );

    bedrockLambdaExecRole.addToPolicy(
      new PolicyStatement({
        actions: [
          "bedrock:PutModelInvocationLoggingConfiguration",
          "bedrock:DeleteModelInvocationLoggingConfiguration",
        ],
        effect: Effect.ALLOW,
        resources: ["*"],
      })
    );

    const bedrockLogRole = new Role(this, "bedrockLogRole", {
      assumedBy: new ServicePrincipal("bedrock.amazonaws.com"),
    });

    bedrockLogRole.addToPolicy(
      new PolicyStatement({
        actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
        effect: Effect.ALLOW,
        resources: [bedrockLogGroup.logGroupArn],
      })
    );

    bedrockLambdaExecRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["iam:PassRole"],
        resources: [bedrockLogRole.roleArn],
      })
    );

    /**
     * Creates the Bedrock Customization Lambda function.
     * The function is configured with the necessary environment variables,
     * the Bedrock Customization execution role, and the AWS Lambda Powertools layer.
     */
    const bedrockLambdaFunc = new PythonFunction(
      this,
      "BedrockLambdaFunction",
      {
        entry: path.join(__dirname, "./bedrock-custom"),
        runtime: Runtime.PYTHON_3_12,
        architecture: Architecture.ARM_64,
        index: "bedrock_logs.py",
        handler: "handler",
        timeout: Duration.seconds(60),
        role: bedrockLambdaExecRole,
        environment: {
          LOG_LEVEL: "INFO",
          LOG_GROUP_NAME: bedrockLogGroup.logGroupName,
          BEDROCK_LOG_ROLE: bedrockLogRole.roleArn,
        },
      }
    );

    // this.bedrockLambdaFunc = bedrockLambdaFunc;

    new CustomResource(scope, `bedrockLogsCustomResource-${id}`, {
      serviceToken: bedrockLambdaFunc.functionArn,
      properties: {
        updateToken: Date.now().toString(), // This will force an update on each deployment
      },
    });
  }
}
