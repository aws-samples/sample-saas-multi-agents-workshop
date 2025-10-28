import { CfnOutput, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as path from 'path';
import { TenantOnboarding } from './constructs/tenant-onboarding';

export interface ServicesStackProps extends StackProps {
  readonly customDomain?: string;
}

export class ServicesStack extends Stack {
  constructor(scope: Construct, id: string, props: ServicesStackProps) {
    super(scope, id, props);

    // Create a role for the CodeBuild projects
    const role = new iam.Role(this, 'CodebuildRole', {
      assumedBy: new iam.ServicePrincipal('codebuild.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AdministratorAccess')
      ]
    });

    new TenantOnboarding(this, 'TenantOnboarding', {
      codebuildRole: role,
      onboardingProjectName: 'TenantOnboardingProject',
      deletionProjectName: 'TenantDeletionProject',
      assetDirectory: path.join(__dirname, '..', 'services', 'tenant-onboarding'),
      applicationServiceBuildProjectNames: [],
    });
  }
}
