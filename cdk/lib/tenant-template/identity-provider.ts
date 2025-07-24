// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { aws_cognito, StackProps, Duration } from "aws-cdk-lib";
import { Construct } from "constructs";
import { IdentityDetails } from "../interfaces/identity-details";

export class IdentityProvider extends Construct {
  public readonly tenantUserPool: aws_cognito.UserPool;
  public readonly tenantUserPoolClient: aws_cognito.UserPoolClient;
  public readonly identityDetails: IdentityDetails;
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id);

    this.tenantUserPool = new aws_cognito.UserPool(this, "tenantUserPool", {
      autoVerify: { email: true },
      accountRecovery: aws_cognito.AccountRecovery.EMAIL_ONLY,
      standardAttributes: {
        email: {
          required: true,
          mutable: true,
        },
      },
      customAttributes: {
        tenantId: new aws_cognito.StringAttribute({
          mutable: true,
        }),
        userRole: new aws_cognito.StringAttribute({
          mutable: true,
        }),
      },
    });

    const writeAttributes = new aws_cognito.ClientAttributes()
      .withStandardAttributes({ email: true })
      .withCustomAttributes("tenantId", "userRole");

    this.tenantUserPoolClient = new aws_cognito.UserPoolClient(
      this,
      "tenantUserPoolClient",
      {
        userPool: this.tenantUserPool,
        generateSecret: false,
        accessTokenValidity: Duration.minutes(180),
        idTokenValidity: Duration.minutes(180),
        authFlows: {
          userPassword: true,
          adminUserPassword: false,
          userSrp: true,
          custom: false,
        },
        writeAttributes: writeAttributes,
        oAuth: {
          scopes: [
            aws_cognito.OAuthScope.EMAIL,
            aws_cognito.OAuthScope.OPENID,
            aws_cognito.OAuthScope.PROFILE,
          ],
          flows: {
            authorizationCodeGrant: true,
            implicitCodeGrant: true,
          },
        },
      }
    );

    this.identityDetails = {
      name: "Cognito",
      details: {
        userPoolId: this.tenantUserPool.userPoolId,
        appClientId: this.tenantUserPoolClient.userPoolClientId,
      },
    };
  }
}
