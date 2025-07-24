// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { ControlPlane, CognitoAuth } from "@cdklabs/sbt-aws";
import { Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";
import { CustomCognitoAuth } from "./cp-custom-cognito-auth/custom-cognito-auth";

interface ControlPlaneStackProps extends StackProps {
  readonly systemAdminRoleName?: string;
  readonly systemAdminEmail?: string;
}

export class ControlPlaneStack extends Stack {
  public readonly regApiGatewayUrl: string;
  public readonly controlPlane: ControlPlane;

  constructor(scope: Construct, id: string, props: ControlPlaneStackProps) {
    super(scope, id, props);

    const systemAdminEmail =
      props.systemAdminEmail ||
      process.env.CDK_PARAM_SYSTEM_ADMIN_EMAIL ||
      "admin@example.com";

    if (!process.env.CDK_PARAM_SYSTEM_ADMIN_ROLE_NAME) {
      process.env.CDK_PARAM_SYSTEM_ADMIN_ROLE_NAME = "SystemAdmin";
    }

    const customCognitoAuth = new CustomCognitoAuth(this, "CognitoAuth", {
      // Avoid checking scopes for API endpoints. Done only for testing purposes.
      setAPIGWScopes: false,
    });

    // TODO: Lab1 - Add SBT Control plane
    const controlPlane = new ControlPlane(this, "ControlPlane", {
      auth: customCognitoAuth,
      systemAdminEmail: systemAdminEmail,
    });
    this.controlPlane = controlPlane;

    this.regApiGatewayUrl = controlPlane.controlPlaneAPIGatewayUrl;
    this.controlPlane = controlPlane;
  }
}
