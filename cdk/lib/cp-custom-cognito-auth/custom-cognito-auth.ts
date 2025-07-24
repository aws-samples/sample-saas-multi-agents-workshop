// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as sbt from "@cdklabs/sbt-aws";
import { Stack, CustomResource, Duration } from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as python from "@aws-cdk/aws-lambda-python-alpha";
import { Construct } from "constructs";
import * as path from "path";

export class CustomCognitoAuth extends sbt.CognitoAuth {
  private readonly customResourceFunction: lambda.IFunction;

  constructor(scope: Construct, id: string, props: sbt.CognitoAuthProps) {
    super(scope, id, props);
    // https://docs.powertools.aws.dev/lambda/python/2.31.0/#lambda-layer
    const lambdaPowertoolsLayer = lambda.LayerVersion.fromLayerVersionArn(
      this,
      "LambdaPowerToolsCustumAuth",
      `arn:aws:lambda:${
        Stack.of(this).region
      }:017000801446:layer:AWSLambdaPowertoolsPythonV2:59`
    );

    this.customResourceFunction = new python.PythonFunction(
      this,
      "customResourceFunction",
      {
        entry: path.join(__dirname, "auth-custom-resource"),
        runtime: lambda.Runtime.PYTHON_3_12,
        index: "index.py",
        handler: "handler",
        timeout: Duration.seconds(60),
        layers: [lambdaPowertoolsLayer],
      }
    );
    this.userPool.grant(
      this.customResourceFunction,
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminSetUserPassword"
    );
  }
  createAdminUser(
    scope: Construct,
    id: string,
    props: sbt.CreateAdminUserProps
  ) {
    new CustomResource(scope, `CustomAuthCustomResource-${id}`, {
      serviceToken: this.customResourceFunction.functionArn,
      properties: {
        UserPoolId: this.userPool.userPoolId,
        Name: props.name,
        Email: props.email,
        Role: props.role,
      },
    });
  }
}
