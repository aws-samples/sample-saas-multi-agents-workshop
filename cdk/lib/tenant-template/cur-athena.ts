// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from "aws-cdk-lib";
import * as glue from "aws-cdk-lib/aws-glue";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as cr from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";

export interface CurAthenaProps extends cdk.StackProps {
  curBucketName: string;
  folderName: string;
  databaseName: string;
}

export class CurAthena extends Construct {
  public constructor(scope: Construct, id: string, props: CurAthenaProps) {
    super(scope, id);

    const curBucketName = props.curBucketName;
    const folderName = props.folderName;
    const accountId = cdk.Stack.of(this).account;
    const databaseName = props.databaseName;

    // Resources
    const awscurCrawlerComponentFunction = new iam.CfnRole(
      this,
      "AWSCURCrawlerComponentFunction",
      {
        assumeRolePolicyDocument: {
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Principal: {
                Service: ["glue.amazonaws.com"],
              },
              Action: ["sts:AssumeRole"],
            },
          ],
        },
        path: "/",
        managedPolicyArns: [
          `arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole`,
        ],
        policies: [
          {
            policyName: "AWSCURCrawlerComponentFunction",
            policyDocument: {
              Version: "2012-10-17",
              Statement: [
                {
                  Effect: "Allow",
                  Action: [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                  ],
                  Resource: `arn:aws:logs:*:*:*`,
                },
                {
                  Effect: "Allow",
                  Action: [
                    "glue:UpdateDatabase",
                    "glue:UpdatePartition",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:ImportCatalogToGlue",
                  ],
                  Resource: "*",
                },
                {
                  Effect: "Allow",
                  Action: ["s3:GetObject", "s3:PutObject"],
                  Resource: `arn:aws:s3:::${curBucketName}/${folderName}*`,
                },
              ],
            },
          },
          {
            policyName: "AWSCURKMSDecryption",
            policyDocument: {
              Version: "2012-10-17",
              Statement: [
                {
                  Effect: "Allow",
                  Action: ["kms:Decrypt"],
                  Resource: "*",
                },
              ],
            },
          },
        ],
      }
    );

    const awscurCrawlerLambdaExecutor = new iam.CfnRole(
      this,
      "AWSCURCrawlerLambdaExecutor",
      {
        assumeRolePolicyDocument: {
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Principal: {
                Service: ["lambda.amazonaws.com"],
              },
              Action: ["sts:AssumeRole"],
            },
          ],
        },
        path: "/",
        policies: [
          {
            policyName: "AWSCURCrawlerLambdaExecutor",
            policyDocument: {
              Version: "2012-10-17",
              Statement: [
                {
                  Effect: "Allow",
                  Action: [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                  ],
                  Resource: `arn:aws:logs:*:*:*`,
                },
                {
                  Effect: "Allow",
                  Action: ["glue:StartCrawler"],
                  Resource: "*",
                },
              ],
            },
          },
        ],
      }
    );

    const awscurDatabase = new glue.CfnDatabase(this, "AWSCURDatabase", {
      databaseInput: {
        name: databaseName,
      },
      catalogId: accountId,
    });

    const awss3curLambdaExecutor = new iam.CfnRole(
      this,
      "AWSS3CURLambdaExecutor",
      {
        assumeRolePolicyDocument: {
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Principal: {
                Service: ["lambda.amazonaws.com"],
              },
              Action: ["sts:AssumeRole"],
            },
          ],
        },
        path: "/",
        policies: [
          {
            policyName: "AWSS3CURLambdaExecutor",
            policyDocument: {
              Version: "2012-10-17",
              Statement: [
                {
                  Effect: "Allow",
                  Action: [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                  ],
                  Resource: `arn:aws:logs:*:*:*`,
                },
                {
                  Effect: "Allow",
                  Action: ["s3:PutBucketNotification"],
                  Resource: `arn:aws:s3:::${curBucketName}`,
                },
              ],
            },
          },
        ],
      }
    );

    const awscurCrawler = new glue.CfnCrawler(this, "AWSCURCrawler", {
      name: "AWSCURCrawler-" + folderName.toLowerCase(),
      description:
        "A recurring crawler that keeps your CUR table in Athena up-to-date.",
      role: awscurCrawlerComponentFunction.attrArn,
      databaseName: awscurDatabase.ref,
      targets: {
        s3Targets: [
          {
            path: "s3://" + curBucketName + "/" + folderName + "/",
            exclusions: [
              "**.json",
              "**.yml",
              "**.sql",
              "**.csv",
              "**.gz",
              "**.zip",
            ],
          },
        ],
      },
      schemaChangePolicy: {
        updateBehavior: "UPDATE_IN_DATABASE",
        deleteBehavior: "DELETE_FROM_DATABASE",
      },
    });
    awscurCrawler.addDependency(awscurDatabase);
    awscurCrawler.addDependency(awscurCrawlerComponentFunction);

    const awscurInitializer = new lambda.CfnFunction(
      this,
      "AWSCURInitializer",
      {
        code: {
          zipFile:
            "const { GlueClient, StartCrawlerCommand } = require('@aws-sdk/client-glue'); const response = require('./cfn-response'); exports.handler = function (event, context, callback) {\n  if (event.RequestType === 'Delete') {\n    response.send(event, context, response.SUCCESS);\n  } else {\n    const glue = new GlueClient();\n    const input = {\n      Name: 'AWSCURCrawler-" +
            folderName.toLowerCase() +
            "',\n    };\n    const command = new StartCrawlerCommand(input);\n    glue.send(command, function (err, data) {\n      if (err) {\n        const responseData = JSON.parse(this.httpResponse.body);\n        if (responseData['__type'] == 'CrawlerRunningException') {\n          callback(null, responseData.Message);\n        } else {\n          const responseString = JSON.stringify(responseData);\n          if (event.ResponseURL) {\n            response.send(event, context, response.FAILED, {\n              msg: responseString,\n            });\n          } else {\n            callback(responseString);\n          }\n        }\n      } else {\n        if (event.ResponseURL) {\n          response.send(event, context, response.SUCCESS);\n        } else {\n          callback(null, response.SUCCESS);\n        }\n      }\n    });\n  }\n};\n",
        },
        handler: "index.handler",
        timeout: 30,
        runtime: "nodejs18.x",
        reservedConcurrentExecutions: 1,
        role: awscurCrawlerLambdaExecutor.attrArn,
      }
    );
    awscurInitializer.addDependency(awscurCrawler);

    const awss3curEventLambdaPermission = new lambda.CfnPermission(
      this,
      "AWSS3CUREventLambdaPermission",
      {
        action: "lambda:InvokeFunction",
        functionName: awscurInitializer.attrArn,
        principal: "s3.amazonaws.com",
        sourceAccount: accountId,
        sourceArn: `arn:aws:s3:::${curBucketName}`,
      }
    );

    const awss3curNotification = new lambda.CfnFunction(
      this,
      "AWSS3CURNotification",
      {
        code: {
          zipFile:
            "const { S3Client, PutBucketNotificationConfigurationCommand } = require('@aws-sdk/client-s3'); const response = require('./cfn-response'); exports.handler = function (event, context, callback) {\n  const s3 = new S3Client();\n  const putConfigRequest = function (notificationConfiguration) {\n    return new Promise(function (resolve, reject) {\n      const input = {\n        Bucket: event.ResourceProperties.BucketName,\n        NotificationConfiguration: notificationConfiguration,\n      };\n      const command = new PutBucketNotificationConfigurationCommand(input);\n      s3.send(command, function (err, data) {\n        if (err)\n          reject({\n            msg: this.httpResponse.body.toString(),\n            error: err,\n            data: data,\n          });\n        else resolve(data);\n      });\n    });\n  };\n  const newNotificationConfig = {};\n  if (event.RequestType !== 'Delete') {\n    newNotificationConfig.LambdaFunctionConfigurations = [\n      {\n        Events: ['s3:ObjectCreated:*'],\n        LambdaFunctionArn:\n          event.ResourceProperties.TargetLambdaArn || 'missing arn',\n        Filter: {\n          Key: {\n            FilterRules: [\n              { Name: 'prefix', Value: event.ResourceProperties.ReportKey },\n            ],\n          },\n        },\n      },\n    ];\n  }\n  putConfigRequest(newNotificationConfig)\n    .then(function (result) {\n      response.send(event, context, response.SUCCESS, result);\n      callback(null, result);\n    })\n    .catch(function (error) {\n      response.send(event, context, response.FAILED, error);\n      console.log(error);\n      callback(error);\n    });\n};\n",
        },
        handler: "index.handler",
        timeout: 30,
        runtime: "nodejs18.x",
        reservedConcurrentExecutions: 1,
        role: awss3curLambdaExecutor.attrArn,
      }
    );
    awss3curNotification.addDependency(awscurInitializer);
    awss3curNotification.addDependency(awss3curEventLambdaPermission);
    awss3curNotification.addDependency(awss3curLambdaExecutor);

    const awsStartCURCrawler = new cdk.CfnCustomResource(
      this,
      "AWSStartCURCrawler",
      {
        serviceToken: awscurInitializer.attrArn,
      }
    );
    awsStartCURCrawler.addDependency(awscurInitializer);

    const awsPutS3CURNotification = new cdk.CustomResource(
      this,
      "AWSPutS3CURNotification",
      {
        serviceToken: awss3curNotification.attrArn,
        properties: {
          TargetLambdaArn: awscurInitializer.attrArn,
          BucketName: curBucketName,
          ReportKey: `${folderName}`,
        },
      }
    );
    awsPutS3CURNotification.node.addDependency(awss3curNotification);
    awsPutS3CURNotification.node.addDependency(awscurInitializer);
  }
}
