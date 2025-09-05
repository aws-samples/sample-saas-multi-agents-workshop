// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { RemovalPolicy, Stack } from "aws-cdk-lib";
import { Bucket, BucketProps, ObjectOwnership } from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

/**
 * Factory class for creating S3 buckets with consistent configurations
 */
export class BucketFactory {
  /**
   * Creates a standard bucket with common configurations
   * @param scope The construct scope
   * @param id The construct ID
   * @param bucketName Optional bucket name
   * @param additionalProps Additional bucket properties to merge
   * @returns A new S3 bucket
   */
  public static createStandardBucket(
    scope: Construct, 
    id: string, 
    bucketName?: string,
    additionalProps: Partial<BucketProps> = {}
  ): Bucket {
    return new Bucket(scope, id, {
      bucketName,
      autoDeleteObjects: true,
      removalPolicy: RemovalPolicy.DESTROY,
      ...additionalProps
    });
  }
  
  /**
   * Creates a data bucket with tenant isolation capabilities
   * @param scope The construct scope
   * @param id The construct ID
   * @param bucketName Optional bucket name
   * @param additionalProps Additional bucket properties to merge
   * @returns A new S3 bucket configured for data storage
   */
  public static createDataBucket(
    scope: Construct, 
    id: string, 
    bucketName?: string,
    additionalProps: Partial<BucketProps> = {}
  ): Bucket {
    return this.createStandardBucket(scope, id, bucketName, {
      objectOwnership: ObjectOwnership.BUCKET_OWNER_PREFERRED,
      eventBridgeEnabled: true,
      ...additionalProps
    });
  }
  
  /**
   * Creates a logs bucket for storing application logs
   * @param scope The construct scope
   * @param id The construct ID
   * @param bucketName Optional bucket name
   * @param additionalProps Additional bucket properties to merge
   * @returns A new S3 bucket configured for logs
   */
  public static createLogsBucket(
    scope: Construct, 
    id: string, 
    bucketName?: string,
    additionalProps: Partial<BucketProps> = {}
  ): Bucket {
    return this.createStandardBucket(scope, id, bucketName, additionalProps);
  }
}