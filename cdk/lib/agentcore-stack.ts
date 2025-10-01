import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as path from "path";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";

export interface AgentCoreStackProps extends cdk.NestedStackProps {
  kbId: string;
  s3BucketName: string;
  athenaResultsBucketName: string;
  userPool: cognito.UserPool;
  athenaDatabase: string;
  athenaTable: string;
  athenaWorkgroup: string;
}

export class AgentCoreStack extends cdk.NestedStack {
  public readonly userPoolId: string;
  public readonly userClientId: string;
  public readonly m2mClientId: string;
  public readonly m2mClientSecret: string;
  public readonly agentCoreRoleArn: string;
  public readonly logMcpLambdaArn: string;
  public readonly kbMcpLambdaArn: string;

  constructor(scope: Construct, id: string, props: AgentCoreStackProps) {
    super(scope, id, props);

    // Import existing S3 bucket
    const logsBucket = s3.Bucket.fromBucketName(this, "LogsBucket", props.s3BucketName);

    // Import existing Athena results bucket
    const athenaResultsBucket = s3.Bucket.fromBucketName(this, "AthenaResultsBucket", props.athenaResultsBucketName);

    // Use the existing user pool from props
    const userPool = props.userPool;

    // Use the props
    const kbId = props.kbId;
    const s3BucketName = props.s3BucketName;

    // We're creating one resource server for both gateways
    const resourceServerInfo = this.createResourceServer(
      userPool,
      "AgentCore-Gateway"
    );

    // Create app clients
    const userClient = this.createUserClient(userPool);
    const m2mClient = this.createM2MClient({ userPool, ...resourceServerInfo });

    const logMcpHandlerRole = this.createLogMcpHandlerRole(s3BucketName, props.athenaResultsBucketName, props.athenaDatabase, props.athenaTable, props.athenaWorkgroup);
    // LAB 2: Uncomment this line to create a basic role for ABAC
    // const abacRole = this.createLogMcpHandlerBasicRole();

    // LAB 2: Uncomment this line to create the ABAC role
    // const abacRole = this.createAbacRole(s3BucketName, athenaResultsBucketName);

    // LAB 2: Switch between logMcpHandlerRole (current) and abacRole to enable ABAC within the Lambda function
    const logMcpLambda = this.createLogMcpHandlerLambda(s3BucketName, props.athenaResultsBucketName, props.athenaDatabase, props.athenaTable, props.athenaWorkgroup, logMcpHandlerRole);
    const kbMcpLambda = this.createKbMcpHandlerLambda(kbId);

    // Create IAM role for AgentCore Gateway
    const agentCoreRole = this.createAgentCoreRole();
    logMcpLambda.grantInvoke(agentCoreRole);
    kbMcpLambda.grantInvoke(agentCoreRole);

    // Store outputs as public properties
    this.userPoolId = userPool.userPoolId;
    this.userClientId = userClient.userPoolClientId;
    this.m2mClientId = m2mClient.userPoolClientId;
    this.m2mClientSecret = m2mClient.userPoolClientSecret.unsafeUnwrap();
    this.agentCoreRoleArn = agentCoreRole.roleArn;
    this.logMcpLambdaArn = logMcpLambda.functionArn;
    this.kbMcpLambdaArn = kbMcpLambda.functionArn;

    // Create CloudWatch log groups for gateway logs
    const logGatewayLogGroup = this.createGatewayLogGroup("LogGateway");
    const kbGatewayLogGroup = this.createGatewayLogGroup(
      "KnowledgeBaseGateway"
    );
    logGatewayLogGroup.grantWrite(agentCoreRole);
    kbGatewayLogGroup.grantWrite(agentCoreRole);

    // Add outputs
    new cdk.CfnOutput(this, "UserPoolId", {
      value: userPool.userPoolId,
      description: "The ID of the Cognito User Pool",
    });

    new cdk.CfnOutput(this, "UserPoolArn", {
      value: userPool.userPoolArn,
      description: "The ARN of the Cognito User Pool",
    });

    new cdk.CfnOutput(this, "UserClientId", {
      value: userClient.userPoolClientId,
      description: "The ID of the User Client",
    });

    new cdk.CfnOutput(this, "M2MClientId", {
      value: m2mClient.userPoolClientId,
      description: "The ID of the M2M Client",
    });

    new cdk.CfnOutput(this, "M2MClientSecret", {
      value: m2mClient.userPoolClientSecret.unsafeUnwrap(),
      description: "The Secret of the M2M Client",
    });

    new cdk.CfnOutput(this, "LogMcpLambdaArn", {
      value: logMcpLambda.functionArn,
      description: "The ARN of the Log MCP Lambda",
    });

    new cdk.CfnOutput(this, "KbMcpLambdaArn", {
      value: kbMcpLambda.functionArn,
      description: "The ARN of the KB MCP Lambda",
    });

    new cdk.CfnOutput(this, "AgentCoreRoleArn", {
      value: agentCoreRole.roleArn,
      description: "The ARN of the AgentCore Gateway IAM Role",
    });

    new cdk.CfnOutput(this, "AthenaResultsBucketName", {
      value: athenaResultsBucket.bucketName,
      description: "The name of the Athena results bucket",
    });    
  }



// LAB 2: Basic Role - Uncomment to enable ABAC
/*
private createLogMcpHandlerBasicRole(): iam.Role {
  return new iam.Role(this, "LogMcpHandlerBasicRole", {
    assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    managedPolicies: [
      iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole")
    ],
    inlinePolicies: {
      AssumeAbacRole: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: ["sts:AssumeRole"],
            resources: [`arn:aws:iam::${this.account}:role/LogMcpHandlerAbacRole`]
          })
        ]
      })
    }
  });
}
*/

// LAB 2: ABAC Role - Uncomment to enable ABAC
/*
private createAbacRole(s3BucketName: string, athenaResultsBucketName: string, athenaDatabase: string, athenaTable: string, athenaWorkgroup: string): iam.Role {
  return new iam.Role(this, "LogMcpHandlerAbacRole", {
    assumedBy: new iam.ArnPrincipal(`arn:aws:iam::${this.account}:role/LogMcpHandlerBasicRole`),
    inlinePolicies: {
      TenantSpecificAccess: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: [
              "kms:Decrypt",
              "kms:DescribeKey",
              "kms:GenerateDataKey*",
              "kms:Encrypt",
              "kms:ReEncrypt*"
            ],
            resources: ["*"]
          }),
          new iam.PolicyStatement({
            actions: [
              "athena:StartQueryExecution",
              "athena:GetQueryExecution",
              "athena:GetQueryResults",
              "athena:StopQueryExecution",
              "athena:GetWorkGroup"
            ],
            resources: [`arn:aws:athena:${this.region}:${this.account}:workgroup/${athenaWorkgroup}`]
          }),
          new iam.PolicyStatement({
            actions: [
              "glue:GetDatabase",
              "glue:GetDatabases",
              "glue:GetTable",
              "glue:GetTables",
              "glue:GetPartition",
              "glue:GetPartitions",
              "glue:BatchGetPartition"
            ],
            resources: [
              `arn:aws:glue:${this.region}:${this.account}:catalog`,
              `arn:aws:glue:${this.region}:${this.account}:database/${athenaDatabase}`,
              `arn:aws:glue:${this.region}:${this.account}:table/${athenaDatabase}/${athenaTable}`
            ]
          }),
          new iam.PolicyStatement({
            actions: [
              "s3:GetBucketLocation",
              "s3:ListBucket"
            ],
            resources: [
              `arn:aws:s3:::${athenaResultsBucketName}`,
              `arn:aws:s3:::${s3BucketName}`
            ]
          }),
          new iam.PolicyStatement({
            actions: [
              "s3:PutObject",
              "s3:GetObject",
              "s3:AbortMultipartUpload",
              "s3:ListMultipartUploadParts"
            ],
            resources: [
              `arn:aws:s3:::${athenaResultsBucketName}/*`,
              `arn:aws:s3:::${s3BucketName}/\${aws:PrincipalTag/tenant_id}/*`
            ]
          })
        ]
      })
    }
  });
}
*/
  
private createLogMcpHandlerRole(s3BucketName: string, athenaResultsBucketName: string, athenaDatabase: string, athenaTable: string, athenaWorkgroup: string): iam.Role {
  return new iam.Role(this, "LogMcpHandlerRole", {
    assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    managedPolicies: [
      iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole")
    ],
    inlinePolicies: {
      AthenaQueryAccess: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: [
              "kms:Decrypt",
              "kms:DescribeKey",
              "kms:GenerateDataKey*",
              "kms:Encrypt",
              "kms:ReEncrypt*"
            ],
            resources: ["*"]
          }),
          new iam.PolicyStatement({
            actions: [
              "athena:StartQueryExecution",
              "athena:GetQueryExecution",
              "athena:GetQueryResults",
              "athena:StopQueryExecution",
              "athena:GetWorkGroup"
            ],
            resources: [`arn:aws:athena:${this.region}:${this.account}:workgroup/${athenaWorkgroup}`]
          }),
          new iam.PolicyStatement({
            actions: [
              "glue:GetDatabase",
              "glue:GetDatabases",
              "glue:GetTable",
              "glue:GetTables",
              "glue:GetPartition",
              "glue:GetPartitions",
              "glue:BatchGetPartition"
            ],
            resources: [
              `arn:aws:glue:${this.region}:${this.account}:catalog`,
              `arn:aws:glue:${this.region}:${this.account}:database/${athenaDatabase}`,
              `arn:aws:glue:${this.region}:${this.account}:table/${athenaDatabase}/${athenaTable}`
            ]
          }),
          new iam.PolicyStatement({
            actions: [
              "s3:GetBucketLocation",
              "s3:ListBucket"
            ],
            resources: [
              `arn:aws:s3:::${athenaResultsBucketName}`,
              `arn:aws:s3:::${s3BucketName}`
            ]
          }),
          new iam.PolicyStatement({
            actions: [
              "s3:PutObject",
              "s3:GetObject",
              "s3:AbortMultipartUpload",
              "s3:ListMultipartUploadParts"
            ],
            resources: [
              `arn:aws:s3:::${athenaResultsBucketName}/*`,
              `arn:aws:s3:::${s3BucketName}/*`
            ]
          })
        ]
      })
    }
  });
}

private createLogMcpHandlerLambda(s3BucketName: string, athenaResultsBucketName: string, athenaDatabase: string, athenaTable: string, athenaWorkgroup: string, role: iam.Role) {
  return new lambda.Function(this, "LogMcpHandler", {
    functionName: "AgentCore-LogMcpHandler",
    description: "Lambda function handler for the log MCP server with Athena query capabilities",
    runtime: lambda.Runtime.PYTHON_3_12,
    handler: "handler.handler",
    code: lambda.Code.fromAsset(path.join(__dirname, "../lambda/log-mcp-handler")),
    role: role,
    timeout: cdk.Duration.seconds(60),
    memorySize: 512,
    environment: {
      ATHENA_DATABASE: athenaDatabase,
      ATHENA_TABLE: athenaTable,
      ATHENA_WORKGROUP: athenaWorkgroup,
      ATHENA_OUTPUT: `s3://${athenaResultsBucketName}/athena-output/`
      // LAB 2: Uncomment this line for ABAC
      // ABAC_ROLE_ARN: abacRole.roleArn      
    }
  });
}

private createKbMcpHandlerLambda(kbId: string) {
  const kbRole = new iam.Role(this, "KbMcpHandlerRole", {
    assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    managedPolicies: [
      iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole")
    ],
    inlinePolicies: {
      BedrockKnowledgeBasePolicy: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: ["bedrock:Retrieve"],
            resources: [`arn:aws:bedrock:${this.region}:${this.account}:knowledge-base/${kbId}`]
          }),
          new iam.PolicyStatement({
            actions: [
              "kms:Decrypt",
              "kms:DescribeKey", 
              "kms:GenerateDataKey*",
              "kms:Encrypt",
              "kms:ReEncrypt*"
            ],
            resources: ["*"]
          })
        ]
      })
    }
  });

  return new lambda.Function(this, "KbMcpHandler", {
    functionName: "AgentCore-KbMcpHandler",
    description: "Lambda function handler for the KB MCP server",
    runtime: lambda.Runtime.PYTHON_3_12,
    handler: "handler.handler",
    code: lambda.Code.fromAsset(path.join(__dirname, "../lambda/kb-mcp-handler")),
    role: kbRole,
    environment: {
      BEDROCK_KB_ID: kbId,
      KB_TOP_K: "8"
    }
  });
}

  private createResourceServer(
    userPool: cdk.aws_cognito.UserPool,
    identifier: string
  ): {
    server: cognito.UserPoolResourceServer;
    scope: cognito.ResourceServerScope;
  } {
    const scope = new cognito.ResourceServerScope({
      scopeName: "invoke",
      scopeDescription: "Scope for invoking the AgentCore Gateway",
    });

    const server = userPool.addResourceServer("ResourceServer", {
      identifier,
      scopes: [scope],
    });

    return { server, scope };
  }


  private createUserClient(userPool: cognito.UserPool): cognito.UserPoolClient {
    return userPool.addClient("user-client", {
      userPoolClientName: "user-client",
      generateSecret: false,
      authFlows: {
        userPassword: true,
        adminUserPassword: true,
        custom: true,
        user: true,
      },
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
        },
        scopes: [
          cognito.OAuthScope.PHONE,
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.PROFILE,
        ],
      },
      supportedIdentityProviders: [
        cognito.UserPoolClientIdentityProvider.COGNITO,
      ],
    });
  }

  private createM2MClient({
    userPool,
    server,
    scope,
  }: {
    userPool: cognito.UserPool;
    server: cognito.UserPoolResourceServer;
    scope: cognito.ResourceServerScope;
  }): cognito.UserPoolClient {
    return userPool.addClient("m2m-client", {
      userPoolClientName: "m2m-client",
      generateSecret: true,
      supportedIdentityProviders: [
        cognito.UserPoolClientIdentityProvider.COGNITO,
      ],
      oAuth: {
        flows: {
          clientCredentials: true,
        },
        scopes: [cognito.OAuthScope.resourceServer(server, scope)],
      },
      preventUserExistenceErrors: true,
    });
  }

  private createAgentCoreRole(): iam.Role {
    const role = new iam.Role(this, "AgentCoreRole", {
      roleName: "AgentCoreGatewayRole",
      assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
      inlinePolicies: {
        AgentCoreGatewayPolicy: new iam.PolicyDocument({
          statements: [
            // ECR Image Access
            new iam.PolicyStatement({
              sid: "ECRImageAccess",
              actions: [
                "ecr:BatchGetImage",
                "ecr:GetDownloadUrlForLayer",
              ],
              resources: [`arn:aws:ecr:${this.region}:${this.account}:repository/*`],
            }),
            // ECR Token Access
            new iam.PolicyStatement({
              sid: "ECRTokenAccess",
              actions: ["ecr:GetAuthorizationToken"],
              resources: ["*"],
            }),
            // CloudWatch Logs
            new iam.PolicyStatement({
              actions: [
                "logs:DescribeLogStreams",
                "logs:CreateLogGroup",
              ],
              resources: [
                `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/bedrock-agentcore/runtimes/*`,
              ],
            }),
            new iam.PolicyStatement({
              actions: ["logs:DescribeLogGroups"],
              resources: [
                `arn:aws:logs:${this.region}:${this.account}:log-group:*`,
              ],
            }),
            new iam.PolicyStatement({
              actions: [
                "logs:CreateLogStream",
                "logs:PutLogEvents",
              ],
              resources: [
                `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*`,
              ],
            }),
            // X-Ray
            new iam.PolicyStatement({
              actions: [
                "xray:PutTraceSegments",
                "xray:PutTelemetryRecords",
                "xray:GetSamplingRules",
                "xray:GetSamplingTargets",
              ],
              resources: ["*"],
            }),
            // CloudWatch Metrics
            new iam.PolicyStatement({
              actions: ["cloudwatch:PutMetricData"],
              resources: ["*"],
              conditions: {
                StringEquals: {
                  "cloudwatch:namespace": "bedrock-agentcore",
                },
              },
            }),
            // Bedrock AgentCore Runtime
            new iam.PolicyStatement({
              sid: "BedrockAgentCoreRuntime",
              actions: ["bedrock-agentcore:InvokeAgentRuntime"],
              resources: [
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:runtime/*`,
              ],
            }),
            // Bedrock AgentCore Memory Create
            new iam.PolicyStatement({
              sid: "BedrockAgentCoreMemoryCreateMemory",
              actions: ["bedrock-agentcore:CreateMemory"],
              resources: ["*"],
            }),
            // Bedrock AgentCore Memory
            new iam.PolicyStatement({
              sid: "BedrockAgentCoreMemory",
              actions: [
                "bedrock-agentcore:CreateEvent",
                "bedrock-agentcore:GetEvent",
                "bedrock-agentcore:GetMemory",
                "bedrock-agentcore:GetMemoryRecord",
                "bedrock-agentcore:ListActors",
                "bedrock-agentcore:ListEvents",
                "bedrock-agentcore:ListMemoryRecords",
                "bedrock-agentcore:ListSessions",
                "bedrock-agentcore:DeleteEvent",
                "bedrock-agentcore:DeleteMemoryRecord",
                "bedrock-agentcore:RetrieveMemoryRecords",
              ],
              resources: [
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:memory/*`,
              ],
            }),
            // Bedrock AgentCore Identity API Key
            new iam.PolicyStatement({
              sid: "BedrockAgentCoreIdentityGetResourceApiKey",
              actions: ["bedrock-agentcore:GetResourceApiKey"],
              resources: [
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:token-vault/default`,
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:token-vault/default/apikeycredentialprovider/*`,
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default`,
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default/workload-identity/ops_agent-*`,
              ],
            }),
            // Bedrock AgentCore Code Execution Permission
            new iam.PolicyStatement({
              sid: "BedrockAgentCoreCodeExecutionPolicy",
              actions: ["bedrock-agentcore:StartCodeInterpreterSession",
                "bedrock-agentcore:StopCodeInterpreterSession",
                "bedrock-agentcore:InvokeCodeInterpreter"
              ],
              resources: [
                `arn:aws:bedrock-agentcore:${this.region}:aws:code-interpreter/aws.codeinterpreter.v1`,
              ],
            }),              
            // Bedrock AgentCore Identity OAuth2
            new iam.PolicyStatement({
              sid: "BedrockAgentCoreIdentityGetResourceOauth2Token",
              actions: ["bedrock-agentcore:GetResourceOauth2Token"],
              resources: [
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:token-vault/default`,
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:token-vault/default/oauth2credentialprovider/*`,
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default`,
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default/workload-identity/ops_agent-*`,
              ],
            }),
            // Bedrock AgentCore Workload Access Token
            new iam.PolicyStatement({
              sid: "BedrockAgentCoreIdentityGetWorkloadAccessToken",
              actions: [
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
              ],
              resources: [
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default`,
                `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default/workload-identity/ops_agent-*`,
              ],
            }),
            // Bedrock Model Invocation
            new iam.PolicyStatement({
              sid: "BedrockModelInvocation",
              actions: [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ApplyGuardrail",
              ],
              resources: [
                "arn:aws:bedrock:*::foundation-model/*",
                `arn:aws:bedrock:${this.region}:${this.account}:*`,
              ],
            }),
            // Secrets Manager Access
            new iam.PolicyStatement({
              sid: "SecretsManagerAccess",
              actions: [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret",
              ],
              resources: [
                `arn:aws:secretsmanager:${this.region}:${this.account}:secret:*`,
              ],
            }),
          ],
        }),
      },
    });

    return role;
  }

  private createGatewayLogGroup(gatewayName: string): logs.LogGroup {
    return new logs.LogGroup(this, `${gatewayName}LogGroup`, {
      logGroupName: `/aws/vendedlogs/bedrock-agentcore/gateway/${gatewayName}`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
  }
}
