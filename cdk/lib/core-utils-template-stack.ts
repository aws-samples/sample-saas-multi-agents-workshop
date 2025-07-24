// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";
import { PolicyDocument } from "aws-cdk-lib/aws-iam";
import { Project } from "aws-cdk-lib/aws-codebuild";
import {
  CoreApplicationPlane,
  EventManager,
  ControlPlane,
  ScriptJobProps,
  ScriptJob,
  EventDefinition,
  EnvironmentVariablesToOutgoingEventProps
} from "@cdklabs/sbt-aws";
import * as fs from "fs";

interface CoreUtilsTemplateStackProps extends StackProps {
  readonly controlPlane: ControlPlane;
}

export class CoreUtilsTemplateStack extends Stack {
  public readonly codeBuildProject: Project;

  constructor(
    scope: Construct,
    id: string,
    props: CoreUtilsTemplateStackProps
  ) {
    super(scope, id, props);

    const provisioningJobRunnerProps: ScriptJobProps = {
      jobIdentifierKey: "tenantId",
      jobFailureStatus: { "tenantStatus": "FAILED" },
      permissions: PolicyDocument.fromJson(
        JSON.parse(`
        {
          "Version": "2012-10-17",
          "Statement": [
              {
                  "Effect": "Allow",
                  "Action": [
                      "cloudformation:DescribeStacks",
                      "cognito-idp:AdminCreateUser",
                      "cognito-idp:AdminSetUserPassword",
                      "cognito-idp:AdminUpdateUserAttributes",
                      "cognito-idp:AdminGetUser",
                      "cognito-idp:CreateGroup",
                      "cognito-idp:AdminAddUserToGroup",
                      "cognito-idp:GetGroup",
                      "s3:PutObject",
                      "s3:GetObject",
                      "s3:ListBucket",
                      "lambda:AddPermission",
                      "events:PutRule",
                      "events:PutTargets",
                      "iam:CreateRole",
                      "iam:GetRole",
                      "iam:PutRolePolicy",
                      "iam:PassRole",
                      "bedrock:CreateKnowledgeBase",
                      "bedrock:CreateDataSource",
                      "bedrock:CreateKnowledgeBase",
                      "bedrock:InvokeModel",
                      "bedrock:ListKnowledgeBases",
                      "aoss:CreateAccessPolicy",
                      "aoss:BatchGetCollection",
                      "aoss:APIAccessAll",
                      "codecommit:GetRepository",
                      "codecommit:GitPull",
                      "apigateway:*"
                  ],
                  "Resource": "*"
              }
          ]
      }
  `)
      ),
      script: fs.readFileSync("../scripts/provision-tenant.sh", "utf8"),
      environmentJSONVariablesFromIncomingEvent: [
        "tenantId",
        "tenantName",
        "email",
        "tenantStatus",
      ],
      environmentVariablesToOutgoingEvent: {
        tenantData: ["tenantStatus", "tenantConfig"]
      },
      scriptEnvironmentVariables: {},
      outgoingEvent: {
        success: props.controlPlane.eventManager.createControlPlaneEvent("PROVISION_SUCCESS"),
        failure: props.controlPlane.eventManager.createControlPlaneEvent("PROVISION_FAILURE")
      },
      incomingEvent: props.controlPlane.eventManager.createControlPlaneEvent("ONBOARDING_REQUEST"),
      eventManager: props.controlPlane.eventManager,
    };

    const provisioningJobRunner: ScriptJob = new ScriptJob(
      this,
      "provisioningJobRunner",
      provisioningJobRunnerProps
    );

    this.codeBuildProject = provisioningJobRunner.codebuildProject;

    // TODO: Lab1 - Add SBT core utils component
    new CoreApplicationPlane(this, "CoreApplicationPlane", {
      eventManager: props.controlPlane.eventManager,
      scriptJobs: [provisioningJobRunner],
    });
  }
}
