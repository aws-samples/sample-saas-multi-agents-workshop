import {
  CoreApplicationPlane,
  TenantLifecycleScriptJobProps,
  EventManager,
  ProvisioningScriptJob,
  DeprovisioningScriptJob
} from '@cdklabs/sbt-aws';
import { Stack, StackProps, CfnOutput, aws_s3_assets as assets } from 'aws-cdk-lib';
import { EventBus } from 'aws-cdk-lib/aws-events';
import { Effect, PolicyDocument, PolicyStatement } from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import * as fs from 'fs';
import * as path from 'path';

export interface AppPlaneStackProps extends StackProps {
  readonly eventBusArn: string;
}

export class AppPlaneStack extends Stack {
  constructor(scope: Construct, id: string, props: AppPlaneStackProps) {
    super(scope, id, props);

    let eventBus;
    let eventManager;
    if (props?.eventBusArn) {
      eventBus = EventBus.fromEventBusArn(this, 'EventBus', props.eventBusArn);
      eventManager = new EventManager(this, 'EventManager', {
        eventBus: eventBus,
      });
    } else {
      eventManager = new EventManager(this, 'EventManager');
    }

    const provisioningScriptJobProps: TenantLifecycleScriptJobProps = {
      eventManager,
      permissions: new PolicyDocument({
        statements: [
          new PolicyStatement({
            actions: [
              's3:GetObject',
              's3:PutObject',
              's3:ListBucket',
              'dynamodb:PutItem',
              'dynamodb:GetItem',
              'dynamodb:UpdateItem',
              'dynamodb:Query',
              'cognito-idp:AdminCreateUser',
              'cognito-idp:AdminAddUserToGroup',
              'cognito-idp:AdminSetUserPassword',
              "cognito-idp:AdminUpdateUserAttributes",
              "cognito-idp:AdminGetUser",
              "cognito-idp:CreateGroup",
              "cognito-idp:GetGroup",
              'events:PutEvents',
              'cloudformation:DescribeStacks',
              'codebuild:StartBuild',
              "lambda:AddPermission",
              "events:PutRule",
              "events:PutTargets",
              'apigateway:*'
            ],
            resources: ['*'], // In a production environment, this should be more specific
            effect: Effect.ALLOW,
          }),
        ],
      }),
      // Use the script directly for simplicity, but in a production environment
      // consider using an asset for better versioning and deployment
      script: fs.readFileSync('./scripts/provisioning.sh', 'utf8'),
      environmentStringVariablesFromIncomingEvent: [
        'tenantId',
        'tier',
        'tenantName',
        'email',
        // 'tenantStatus',
      ],
      environmentVariablesToOutgoingEvent: {
        tenantData:[
          'tenantS3Bucket',
          'tenantConfig',
          // 'tenantStatus',
          'prices', // added so we don't lose it for targets beyond provisioning (ex. billing)
          'tenantName', // added so we don't lose it for targets beyond provisioning (ex. billing)
          'email', // added so we don't lose it for targets beyond provisioning (ex. billing)
        ],
        tenantRegistrationData: ['registrationStatus'],
      }
      
    };

    const deprovisioningScriptJobProps: TenantLifecycleScriptJobProps = {
      eventManager,
      permissions: new PolicyDocument({
        statements: [
          new PolicyStatement({
            actions: [
              's3:DeleteObject',
              's3:ListBucket',
              'dynamodb:DeleteItem',
              'dynamodb:GetItem',
              'cognito-idp:AdminDeleteUser',
              'cognito-idp:ListUsers',
              'events:PutEvents',
            ],
            resources: ['*'], // In a production environment, this should be more specific
            effect: Effect.ALLOW,
          }),
        ],
      }),
      script: fs.readFileSync('./scripts/deprovisioning.sh', 'utf8'),
      environmentStringVariablesFromIncomingEvent: ['tenantId', 'tier'],
      environmentVariablesToOutgoingEvent: {
        tenantRegistrationData: ['registrationStatus']
      },
      
    };

    const provisioningScriptJob: ProvisioningScriptJob = new ProvisioningScriptJob(
      this,
      'provisioningScriptJob',
      provisioningScriptJobProps
    );
    const deprovisioningScriptJob: DeprovisioningScriptJob = new DeprovisioningScriptJob(
      this,
      'deprovisioningScriptJob',
      deprovisioningScriptJobProps
    );

    new CoreApplicationPlane(this, 'CoreApplicationPlane', {
      eventManager: eventManager,
      scriptJobs: [provisioningScriptJob, deprovisioningScriptJob]
    });
    
    // Add outputs
    new CfnOutput(this, 'EventBusArn', {
      value: eventManager.busArn,
      description: 'The ARN of the Event Bus',
    });
    
    new CfnOutput(this, 'ProvisioningScriptJobId', {
      value: provisioningScriptJob.node.id,
      description: 'The ID of the Provisioning Script Job',
    });
    
    new CfnOutput(this, 'DeprovisioningScriptJobId', {
      value: deprovisioningScriptJob.node.id,
      description: 'The ID of the Deprovisioning Script Job',
    });
  }
}