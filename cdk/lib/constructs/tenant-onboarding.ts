import * as path from 'path';
import { Duration, Stack } from 'aws-cdk-lib';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { SourceBucket } from './source-bucket';

export interface TenantOnboardingProps {
  readonly projectName: string;
  readonly environmentVariables?: { [key: string]: codebuild.BuildEnvironmentVariable };
}

/**
 * Represents a tenant onboarding project.
 */
export class TenantOnboarding extends Construct {
  readonly onboardingProject: codebuild.Project;
  readonly deletionProject: codebuild.Project;

  constructor(scope: Construct, id: string, props: TenantOnboardingProps) {
    super(scope, id);

    // Create a source bucket for the onboarding scripts
    const sourceBucket = new SourceBucket(this, 'SourceBucket', {
      name: 'tenant-onboarding',
      assetDirectory: path.join(__dirname, '../../scripts'),
    });

    // Create the onboarding project
    this.onboardingProject = new codebuild.Project(this, 'OnboardingProject', {
      projectName: props.projectName,
      description: 'Project for onboarding tenants',
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
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
      environmentVariables: props.environmentVariables,
      timeout: Duration.minutes(30),
      source: sourceBucket.source,
    });

    // Create the deletion project
    this.deletionProject = new codebuild.Project(this, 'DeletionProject', {
      projectName: `${props.projectName}Deletion`,
      description: 'Project for deleting tenants',
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
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
      environmentVariables: props.environmentVariables,
      timeout: Duration.minutes(30),
      source: sourceBucket.source,
    });

    // Add permissions for CloudFormation and other services
    const cfnPolicy = new iam.PolicyStatement({
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
      ],
      resources: ['*'],
    });

    this.onboardingProject.addToRolePolicy(cfnPolicy);
    this.deletionProject.addToRolePolicy(cfnPolicy);
  }
}