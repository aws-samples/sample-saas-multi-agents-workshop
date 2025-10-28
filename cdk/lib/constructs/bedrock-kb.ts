// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Construct } from "constructs";
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { S3VectorBucketResource } from '../tenant-template/s3-vector-bucket-resource';
import { BedrockKnowledgeBaseResource } from '../tenant-template/bedrock-knowledge-base-resource';
import { Bucket } from "aws-cdk-lib/aws-s3";
import { Config } from "../config";
import { ResourceNaming } from "../naming";
import { Stack } from "aws-cdk-lib";

/**
 * Properties for the BedrockKnowledgeBase construct
 */
export interface BedrockKnowledgeBaseProps {
  /**
   * Name for the knowledge base
   */
  knowledgeBaseName: string;
  
  /**
   * Description for the knowledge base
   */
  description?: string;
  
  /**
   * ARN of the IAM role for Bedrock
   */
  roleArn: string;
  
  /**
   * S3 bucket for data source
   */
  dataBucket: Bucket;
  
  /**
   * Lambda layer for utilities
   */
  lambdaLayer: lambda.ILayerVersion;
  
  /**
   * Vector bucket name (optional)
   */
  vectorBucketName?: string;
  
  /**
   * Vector index name (optional)
   */
  vectorIndexName?: string;
  
  /**
   * Vector dimension (default: 1024)
   */
  dimension?: number;
  
  /**
   * Distance metric for vector search (default: 'cosine')
   */
  distanceMetric?: string;
  
  /**
   * Data type for vectors (default: 'float32')
   */
  dataType?: string;
}

/**
 * A construct that creates a complete Bedrock knowledge base
 * including vector store, knowledge base, and data source with proper dependencies
 */
export class BedrockKnowledgeBase extends Construct {
  /**
   * The vector bucket resource
   */
  public readonly vectorBucket: S3VectorBucketResource;
  
  /**
   * The knowledge base resource
   */
  public readonly knowledgeBase: BedrockKnowledgeBaseResource;
  
  /**
   * The data source
   */
  public readonly dataSource: bedrock.CfnDataSource;
  
  /**
   * The knowledge base ID
   */
  public readonly knowledgeBaseId: string;
  
  /**
   * The knowledge base ARN
   */
  public readonly knowledgeBaseArn: string;
  
  constructor(scope: Construct, id: string, props: BedrockKnowledgeBaseProps) {
    super(scope, id);
    
    const stack = Stack.of(this);
    const naming = new ResourceNaming(stack);

    // Create the bucket name using the same naming convention
    const vectorBucketName = props.vectorBucketName || naming.bucketName('kb-vectors');
    const vectorIndexName = props.vectorIndexName || `kb-embeddings-index-${stack.account}`;
    
    // Create vector bucket
    this.vectorBucket = new S3VectorBucketResource(this, 'VectorBucket', {
      bucketName: vectorBucketName,
      indexName: vectorIndexName,
      dimension: props.dimension || 1024,
      distanceMetric: props.distanceMetric || 'cosine',
      dataType: props.dataType || 'float32',
      sseType: 'AES256',
      lambdaLayer: props.lambdaLayer,
    });
    
    // Create knowledge base with dependency on vector bucket
    this.knowledgeBase = new BedrockKnowledgeBaseResource(this, 'KnowledgeBase', {
      knowledgeName: props.knowledgeBaseName,
      description: props.description || 'Knowledge base for custom data source',
      roleArn: props.roleArn,
      embeddingModelArn: Config.getEmbeddingModelArn(stack.region),
      indexArn: `arn:aws:s3vectors:${stack.region}:${stack.account}:bucket/${vectorBucketName}/index/${vectorIndexName}`,
      lambdaLayer: props.lambdaLayer,
    });
    
    // Create data source with dependency on knowledge base
    this.dataSource = new bedrock.CfnDataSource(this, 'DataSource', {
      knowledgeBaseId: this.knowledgeBase.knowledgeBaseId,
      name: naming.dataSourceName(props.knowledgeBaseName),
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: {
          bucketArn: props.dataBucket.bucketArn
        },
      },
    });
    
    // Set properties
    this.knowledgeBaseId = this.knowledgeBase.knowledgeBaseId;
    this.knowledgeBaseArn = this.knowledgeBase.knowledgeBaseArn;
    
    // Dependencies are automatically tracked through references,
    // but we'll add explicit dependencies to be sure
    this.knowledgeBase.node.addDependency(this.vectorBucket);
    this.dataSource.node.addDependency(this.knowledgeBase);
  }
}