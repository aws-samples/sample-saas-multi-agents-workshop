// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { aws_cognito, StackProps, Duration } from "aws-cdk-lib";
import { Construct } from "constructs";
import { IdentityDetails } from "../interfaces/identity-details";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as path from "path";

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

    // Create Pre Token Generation Lambda
    const preTokenGenerationLambda = new lambda.Function(
      this,
      "PreTokenGenerationLambda",
      {
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: "index.handler",
        code: lambda.Code.fromAsset(
          path.join(__dirname, "../../lambda/access-token-modifier")
        ),
        description:
          "Pre Token Generation trigger to add custom attributes to tokens",
      }
    );

    // Add the trigger to the user pool
    this.tenantUserPool.addTrigger(
      aws_cognito.UserPoolOperation.PRE_TOKEN_GENERATION_CONFIG,
      preTokenGenerationLambda,
      aws_cognito.LambdaVersion.V2_0
    );

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
