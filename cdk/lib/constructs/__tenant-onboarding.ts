import * as path from 'path';
import { Arn, Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { SourceBucket } from './source-bucket';

export interface TenantOnboardingProps {
  readonly onboardingProjectName: string;
  readonly deletionProjectName: string;
  readonly assetDirectory?: string;
}

/**
 * Represents a tenant onboarding project.
 */
export class TenantOnboarding extends Construct {
  readonly onboardingProject: codebuild.Project;
  readonly deletionProject: codebuild.Project;
  readonly codebuildRole: iam.Role;

  constructor(scope: Construct, id: string, props: TenantOnboardingProps) {
    super(scope, id);

    // Create a role for the CodeBuild projects
    this.codebuildRole = new iam.Role(this, 'CodeBuildRole', {
      assumedBy: new iam.ServicePrincipal('codebuild.amazonaws.com'),
    });

    // Add permissions to the role
    this.addTenantOnboardingPermissions(this.codebuildRole);

    // Create a source bucket for the onboarding scripts
    const sourceBucket = new SourceBucket(this, 'SourceBucket', {
      name: 'tenant-onboarding',
      assetDirectory: props.assetDirectory || path.join(__dirname, '../../scripts'),
    });

    // Create the onboarding project
    this.onboardingProject = new codebuild.Project(this, 'OnboardingProject', {
      projectName: props.onboardingProjectName,
      description: 'Project for onboarding tenants',
      role: this.codebuildRole,
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: ['yum install -y jq'],
          },
          build: {
            commands: [
              'chmod +x ./provisioning.sh',
              './provisioning.sh'
            ],
          },
        },
      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.AMAZON_LINUX_2_4,
        privileged: true,
      },
      environmentVariables: {
        TENANT_ID: {
          value: '',
        },
        COMPANY_NAME: {
          value: '',
        },
        ADMIN_EMAIL: {
          value: '',
        },
        PLAN: {
          value: '',
        },
        AWS_ACCOUNT: {
          value: Stack.of(this).account,
        },
        AWS_REGION: {
          value: Stack.of(this).region,
        },
      },
      timeout: Duration.minutes(30),
      source: sourceBucket.source,
    });

    // Create the deletion project
    this.deletionProject = new codebuild.Project(this, 'DeletionProject', {
      projectName: props.deletionProjectName,
      description: 'Project for deleting tenants',
      role: this.codebuildRole,
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          install: {
            commands: ['yum install -y jq'],
          },
          build: {
            commands: [
              'chmod +x ./deprovisioning.sh',
              './deprovisioning.sh'
            ],
          },
        },
      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.AMAZON_LINUX_2_4,
        privileged: true,
      },
      environmentVariables: {
        TENANT_ID: {
          value: '',
        },
        AWS_ACCOUNT: {
          value: Stack.of(this).account,
        },
        AWS_REGION: {
          value: Stack.of(this).region,
        },
      },
      timeout: Duration.minutes(30),
      source: sourceBucket.source,
    });
  }

  private addTenantOnboardingPermissions(projectRole: iam.IRole) {
    // Add permissions for CloudFormation and other services
    projectRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'cloudformation:*',
          'cognito-idp:*',
          's3:*',
          'dynamodb:*',
          'iam:*',
          'lambda:*',
          'apigateway:*',
          'logs:*',
          'bedrock:*',
          'kms:*',
          'ssm:GetParameter',
        ],
        resources: ['*'],
      })
    );

    // Add permissions to start CodeBuild projects
    projectRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'codebuild:StartBuild',
          'codebuild:BatchGetBuilds',
          'codebuild:ListBuildsForProject',
        ],
        resources: ['*'],
      })
    );

    // Add permissions for DynamoDB tenant table
    projectRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['dynamodb:PutItem', 'dynamodb:DeleteItem'],
        resources: [
          Arn.format(
            { service: 'dynamodb', resource: 'table', resourceName: 'TenantDataTable' },
            Stack.of(this)
          ),
        ],
      })
    );
  }
}