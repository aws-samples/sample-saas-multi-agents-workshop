// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Construct } from "constructs";
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cloudwatch_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as sns from 'aws-cdk-lib/aws-sns';
import { Config } from "../config";
import { Duration, RemovalPolicy } from "aws-cdk-lib";

/**
 * Properties for the LambdaLogging construct
 */
export interface LambdaLoggingProps {
  /**
   * The Lambda function to configure logging for
   */
  function: lambda.Function;
  
  /**
   * Log retention period in days (default: 7 days)
   */
  logRetention?: logs.RetentionDays;
  
  /**
   * Service name for Powertools (default: function name)
   */
  serviceName?: string;
  
  /**
   * Metrics namespace for Powertools (default: 'SaaSGenAIWorkshop')
   */
  metricsNamespace?: string;
  
  /**
   * Log level (default: 'INFO')
   */
  logLevel?: string;
  
  /**
   * Whether to create alarms (default: true)
   */
  createAlarms?: boolean;
  
  /**
   * SNS topic for alarms (optional)
   */
  alarmTopic?: sns.ITopic;
  
  /**
   * Error threshold for alarm (default: 1)
   */
  errorThreshold?: number;
  
  /**
   * Duration threshold for alarm in milliseconds (default: 3000)
   */
  durationThreshold?: number;
}

/**
 * A construct that configures standardized logging and monitoring for Lambda functions
 */
export class LambdaLogging extends Construct {
  /**
   * The error alarm
   */
  public readonly errorAlarm?: cloudwatch.Alarm;
  
  /**
   * The duration alarm
   */
  public readonly durationAlarm?: cloudwatch.Alarm;
  
  constructor(scope: Construct, id: string, props: LambdaLoggingProps) {
    super(scope, id);
    
    // Set default values
    const logRetention = props.logRetention || logs.RetentionDays.ONE_WEEK;
    const serviceName = props.serviceName || props.function.functionName;
    const metricsNamespace = props.metricsNamespace || 'SaaSGenAIWorkshop';
    const logLevel = props.logLevel || 'INFO';
    const createAlarms = props.createAlarms !== undefined ? props.createAlarms : true;
    const errorThreshold = props.errorThreshold || 1;
    const durationThreshold = props.durationThreshold || 3000;
    
    // Configure log retention
    new logs.LogGroup(this, 'LogGroup', {
      logGroupName: `/aws/lambda/${props.function.functionName}`,
      retention: logRetention,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    
    // Add environment variables for Powertools
    props.function.addEnvironment('POWERTOOLS_SERVICE_NAME', serviceName);
    props.function.addEnvironment('POWERTOOLS_METRICS_NAMESPACE', metricsNamespace);
    props.function.addEnvironment('LOG_LEVEL', logLevel);
    
    // Enable X-Ray tracing
    props.function.addEnvironment('POWERTOOLS_TRACER_CAPTURE_RESPONSE', 'true');
    props.function.addEnvironment('POWERTOOLS_TRACER_CAPTURE_ERROR', 'true');
    
    // Create alarms if enabled
    if (createAlarms) {
      // Error alarm
      this.errorAlarm = new cloudwatch.Alarm(this, 'ErrorAlarm', {
        metric: props.function.metricErrors(),
        threshold: errorThreshold,
        evaluationPeriods: 1,
        alarmDescription: `Lambda function ${props.function.functionName} is experiencing errors`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      
      // Duration alarm
      this.durationAlarm = new cloudwatch.Alarm(this, 'DurationAlarm', {
        metric: props.function.metricDuration(),
        threshold: durationThreshold,
        evaluationPeriods: 3,
        datapointsToAlarm: 2,
        alarmDescription: `Lambda function ${props.function.functionName} is experiencing high latency`,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      });
      
      // Add alarm actions if topic is provided
      if (props.alarmTopic) {
        this.errorAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(props.alarmTopic));
        this.durationAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(props.alarmTopic));
      }
    }
  }
  
  /**
   * Creates a standard Lambda function with logging configuration
   * @param scope The construct scope
   * @param id The construct ID
   * @param props Lambda function properties
   * @param loggingProps Optional logging properties
   * @returns A Lambda function with logging configuration
   */
  public static createFunction(
    scope: Construct, 
    id: string, 
    props: lambda.FunctionProps, 
    loggingProps?: Partial<LambdaLoggingProps>
  ): lambda.Function {
    // Create the Lambda function
    const lambdaFunction = new lambda.Function(scope, id, props);
    
    // Add logging configuration
    new LambdaLogging(scope, `${id}Logging`, {
      function: lambdaFunction,
      ...loggingProps
    });
    
    return lambdaFunction;
  }
}