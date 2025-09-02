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

export interface S3VectorBucketResourceProps {
  bucketName: string;
  sseType?: string;
  indexName?: string;
  dimension?: number;
  distanceMetric?: string;
  dataType?: string;
  lambdaLayer: ILayerVersion;
}

export class S3VectorBucketResource extends Construct {
  public readonly bucketName: string;
  public readonly bucketArn: string;
  public readonly indexName: string;
  public readonly s3VectorBucket: cdk.CustomResource;

  constructor(scope: Construct, id: string, props: S3VectorBucketResourceProps) {
    super(scope, id);

    const s3VectorCreatorRole = new iam.Role(this, 'S3VectorCreatorRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });

    s3VectorCreatorRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          's3vectors:CreateVectorBucket',
          's3vectors:DeleteVectorBucket',
          's3vectors:DescribeVectorBucket',
          's3vectors:CreateIndex',
          's3vectors:DeleteIndex',
          's3vectors:GetIndex',
          's3vectors:GetVectors',
          's3vectors:ListIndices',
        ],
        resources: ['*'],
      })
    );

    const s3VectorCreator = new Function(this, 'S3VectorCreator', {
      runtime: Runtime.PYTHON_3_13,
      handler: 'index.handler',
      code: Code.fromAsset('./lambda/s3-vector-creator'),
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      role: s3VectorCreatorRole,
      layers: [props.lambdaLayer],
      environment: {
        POWERTOOLS_SERVICE_NAME: 'S3VectorBucket',
        POWERTOOLS_METRICS_NAMESPACE: 'S3VectorBucket',
        POWERTOOLS_LOG_LEVEL: 'INFO',
      },
    });

    const s3VectorProvider = new cr.Provider(this, 'S3VectorProvider', {
      onEventHandler: s3VectorCreator,
      logGroup: new logs.LogGroup(this, 'S3VectorProviderLogGroup', {
        retention: logs.RetentionDays.ONE_WEEK,
      }),
    });

    const properties: { [key: string]: any } = {
      BucketName: props.bucketName,
      SSEType: props.sseType || 'AES256',
      IndexName: props.indexName || 'default-index',
      Dimension: props.dimension || 1024,
      DistanceMetric: props.distanceMetric || 'cosine',
      DataType: props.dataType || 'float32',
    };

    this.s3VectorBucket = new cdk.CustomResource(this, 'S3VectorBucket', {
      serviceToken: s3VectorProvider.serviceToken,
      properties,
    });

    this.bucketName = this.s3VectorBucket.getAttString('BucketName');
    const region = cdk.Stack.of(this).region;
    const account = cdk.Stack.of(this).account;
    this.bucketArn = `arn:aws:s3vectors:${region}:${account}:bucket/${props.bucketName}`;
    this.indexName = this.s3VectorBucket.getAttString('IndexName');
  }
}
