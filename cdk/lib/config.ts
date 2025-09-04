// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { App } from "aws-cdk-lib";

/**
 * Central configuration class for the CDK application
 * Provides access to configuration values from context, environment variables,
 * or default values
 */
export class Config {
  // AWS Lambda Powertools configuration
  public static readonly POWERTOOLS_LAYER_ACCOUNT = '017000801446';
  public static readonly POWERTOOLS_LAYER_VERSION = '59';
  
  // Bedrock model configuration
  public static readonly EMBEDDING_MODEL = 'amazon.titan-embed-text-v2:0';
  
  // Resource naming prefixes
  public static readonly RESOURCE_PREFIX = 'saas-ws';
  
  /**
   * Gets the AWS Lambda Powertools layer ARN for the specified region
   * @param region AWS region
   * @returns The ARN for the Lambda Powertools layer
   */
  public static getPowerToolsLayerArn(region: string): string {
    return `arn:aws:lambda:${region}:${this.POWERTOOLS_LAYER_ACCOUNT}:layer:AWSLambdaPowertoolsPythonV2:${this.POWERTOOLS_LAYER_VERSION}`;
  }
  
  /**
   * Gets the Bedrock embedding model ARN for the specified region
   * @param region AWS region
   * @returns The ARN for the Bedrock embedding model
   */
  public static getEmbeddingModelArn(region: string): string {
    return `arn:aws:bedrock:${region}::foundation-model/${this.EMBEDDING_MODEL}`;
  }
  
  /**
   * Gets a standardized resource name with prefix and account
   * @param baseName Base name of the resource
   * @param account AWS account ID
   * @returns Formatted resource name
   */
  public static getResourceName(baseName: string, account: string): string {
    return `${this.RESOURCE_PREFIX}-${baseName}-${account}`;
  }
  
  /**
   * Gets a context value from the CDK app, with fallback to default value
   * @param app CDK App instance
   * @param key Context key to retrieve
   * @param defaultValue Default value if context key is not found
   * @returns The context value or default value
   */
  public static getContextValue(app: App, key: string, defaultValue: any): any {
    return app.node.tryGetContext(key) || defaultValue;
  }
  
  /**
   * Gets a nested context value from the CDK app, with fallback to default value
   * @param app CDK App instance
   * @param section Context section
   * @param key Context key within section
   * @param defaultValue Default value if context key is not found
   * @returns The context value or default value
   */
  public static getNestedContextValue(app: App, section: string, key: string, defaultValue: any): any {
    const sectionObj = app.node.tryGetContext(section) || {};
    return sectionObj[key] || defaultValue;
  }
}