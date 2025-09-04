// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Stack } from "aws-cdk-lib";
import { Config } from "./config";

/**
 * Resource naming strategy class to ensure consistent naming across resources
 */
export class ResourceNaming {
  private readonly stack: Stack;
  private readonly prefix: string;
  private readonly environment: string;
  
  /**
   * Creates a new ResourceNaming instance
   * @param stack The CDK stack
   * @param prefix Optional prefix override (defaults to Config.RESOURCE_PREFIX)
   * @param environment Optional environment name (defaults to 'dev')
   */
  constructor(stack: Stack, prefix?: string, environment?: string) {
    this.stack = stack;
    this.prefix = prefix || Config.RESOURCE_PREFIX;
    this.environment = environment || 'dev';
  }
  
  /**
   * Generates a standardized bucket name
   * @param resourceName Base name of the bucket
   * @returns Formatted bucket name
   */
  public bucketName(resourceName: string): string {
    return `${this.prefix}-${resourceName}-${this.stack.account}`;
  }
  
  /**
   * Generates a standardized table name
   * @param resourceName Base name of the table
   * @returns Formatted table name
   */
  public tableName(resourceName: string): string {
    return `${this.prefix}-${resourceName}-table`;
  }
  
  /**
   * Generates a standardized role name
   * @param resourceName Base name of the role
   * @returns Formatted role name
   */
  public roleName(resourceName: string): string {
    return `${this.prefix}-${resourceName}-role`;
  }
  
  /**
   * Generates a standardized function name
   * @param resourceName Base name of the function
   * @returns Formatted function name
   */
  public functionName(resourceName: string): string {
    return `${this.prefix}-${resourceName}-function`;
  }
  
  /**
   * Generates a standardized knowledge base name
   * @param resourceName Base name of the knowledge base
   * @returns Formatted knowledge base name
   */
  public knowledgeBaseName(resourceName: string): string {
    return `${this.prefix}-${resourceName}-kb`;
  }
  
  /**
   * Generates a standardized data source name
   * @param resourceName Base name of the data source
   * @returns Formatted data source name
   */
  public dataSourceName(resourceName: string): string {
    return `${this.prefix}-${resourceName}-ds`;
  }
  
  /**
   * Generates a standardized resource name with environment
   * @param resourceName Base name of the resource
   * @param resourceType Type of resource (optional suffix)
   * @returns Formatted resource name with environment
   */
  public resourceName(resourceName: string, resourceType?: string): string {
    const suffix = resourceType ? `-${resourceType}` : '';
    return `${this.prefix}-${resourceName}-${this.environment}${suffix}`;
  }
}