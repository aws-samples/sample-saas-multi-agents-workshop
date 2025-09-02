import * as cdk from 'aws-cdk-lib';
import {
  Architecture,
  Code,
  Runtime,
  LayerVersion,
  Function,
  ILayerVersion,
} from "aws-cdk-lib/aws-lambda";
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cr from 'aws-cdk-lib/custom-resources';
import { Construct } from 'constructs';

export interface BedrockKnowledgeBaseResourceProps {
  knowledgeName: string;
  description: string;
  roleArn: string;
  embeddingModelArn: string;
  indexArn: string;
  lambdaLayer: ILayerVersion;
}

export class BedrockKnowledgeBaseResource extends Construct {
  public readonly knowledgeBaseId: string;
  public readonly knowledgeBaseArn: string;
  public readonly bedrockKb: cdk.CustomResource;

  constructor(scope: Construct, id: string, props: BedrockKnowledgeBaseResourceProps) {
    super(scope, id);

    const bedrockKbCreatorRole = new iam.Role(this, 'BedrockKBCreatorRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });

    bedrockKbCreatorRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          'bedrock:CreateKnowledgeBase',
          'bedrock:DeleteKnowledgeBase',
          'bedrock:GetKnowledgeBase',
          'bedrock:ListKnowledgeBases'
        ],
        resources: ['*'],
      })
    );

    bedrockKbCreatorRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          's3vectors:GetVectors',
          's3vectors:GetIndex',
          's3vectors:ListIndices',
          's3vectors:QueryVectors',
          's3vectors:DescribeVectorBucket',
        ],
        resources: ['*'],
      })
    );

    bedrockKbCreatorRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['iam:PassRole'],
        resources: [props.roleArn],
      })
    );

    const bedrockKbCreator = new Function(this, 'BedrockKBCreator', {
      runtime: Runtime.PYTHON_3_13,
      handler: 'index.handler',
      code: Code.fromAsset('./lambda/bedrock-kb-creator'),
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      role: bedrockKbCreatorRole,
      layers: [props.lambdaLayer],
      environment: {
        REGION: cdk.Stack.of(this).region,
        AWS_ACCOUNT_ID: cdk.Stack.of(this).account,
        POWERTOOLS_SERVICE_NAME: 'BedrockKnowledgeBase',
        POWERTOOLS_METRICS_NAMESPACE: 'BedrockKnowledgeBase',
        POWERTOOLS_LOG_LEVEL: 'INFO',
      },
    });

    const bedrockKbProvider = new cr.Provider(this, 'BedrockKBProvider', {
      onEventHandler: bedrockKbCreator,
      logGroup: new logs.LogGroup(this, 'BedrockKBProviderLogGroup', {
        retention: logs.RetentionDays.ONE_WEEK,
      }),
    });

    const properties: { [key: string]: any } = {
      KnowledgeName: props.knowledgeName,
      Description: props.description,
      RoleArn: props.roleArn,
      EmbeddingModelArn: props.embeddingModelArn,
      IndexArn: props.indexArn,
    };

    this.bedrockKb = new cdk.CustomResource(this, 'BedrockKnowledgeBase', {
      serviceToken: bedrockKbProvider.serviceToken,
      properties,
    });

    this.knowledgeBaseId = this.bedrockKb.getAttString('KnowledgeBaseId');
    this.knowledgeBaseArn = this.bedrockKb.getAttString('KnowledgeBaseArn');
  }
}
