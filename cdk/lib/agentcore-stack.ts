import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import { NodejsFunction } from "aws-cdk-lib/aws-lambda-nodejs";
import * as path from "path";
import { Construct } from "constructs";

export class AgentCoreStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create the user pool
    const userPool = this.createUserPool();

    // Create domain for OAuth2 endpoints
    const userPoolDomain = userPool.addDomain("UserPoolDomain", {
      cognitoDomain: {
        domainPrefix: `agentcore-${this.account}-${cdk.Stack.of(this).region}`,
      },
    });

    // We're creating one resource server for both gateways
    const resourceServerInfo = this.createResourceServer(
      userPool,
      "AgentCore-Gateway"
    );

    // Create app clients
    const userClient = this.createUserClient(userPool);
    const m2mClient = this.createM2MClient({ userPool, ...resourceServerInfo });

    const logMcpLambda = this.createLogMcpHandlerLambda();
    const kbMcpLambda = this.createKbMcpHandlerLambda();

    // Create IAM role for AgentCore Gateway
    const agentCoreRole = this.createAgentCoreRole();

    // Create CloudWatch log groups for gateway logs
    const logGatewayLogGroup = this.createGatewayLogGroup("LogGateway");
    const kbGatewayLogGroup = this.createGatewayLogGroup("KnowledgeBaseGateway");

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
  }

  private createLogMcpHandlerLambda() {
    return new NodejsFunction(this, "LogMcpHandler", {
      entry: path.join(__dirname, "../lambda/log-mcp-handler/index.ts"),
      functionName: "AgentCore-LogMcpHandler",
      description: "Lambda function handler for the log MCP server",
      runtime: cdk.aws_lambda.Runtime.NODEJS_22_X,
      bundling: {
        externalModules: ["aws-sdk"],
      },
    });
  }

  private createKbMcpHandlerLambda() {
    return new NodejsFunction(this, "KbMcpHandler", {
      entry: path.join(__dirname, "../lambda/kb-mcp-handler/index.ts"),
      functionName: "AgentCore-KbMcpHandler",
      description: "Lambda function handler for the KB MCP server",
      runtime: cdk.aws_lambda.Runtime.NODEJS_22_X,
      bundling: {
        externalModules: ["aws-sdk"],
      },
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

  private createUserPool(): cognito.UserPool {
    return new cognito.UserPool(this, "UserPool", {
      userPoolName: "agentcore-user-pool",
      selfSignUpEnabled: true,
      signInAliases: {
        email: true,
        username: true,
      },
      standardAttributes: {
        email: {
          required: true,
          mutable: true,
        },
      },
      customAttributes: {
        tenantId: new cognito.StringAttribute({ mutable: true }),
        tenantTier: new cognito.StringAttribute({ mutable: true }),
      },
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
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
    return new iam.Role(this, "AgentCoreRole", {
      roleName: "AgentCoreGatewayRole",
      assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName("AdministratorAccess"),
      ],
    });
  }

  private createGatewayLogGroup(gatewayName: string): logs.LogGroup {
    return new logs.LogGroup(this, `${gatewayName}LogGroup`, {
      logGroupName: `/aws/vendedlogs/bedrock-agentcore/gateway/${gatewayName}`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
  }
}
