import { CfnOutput, CfnParameter, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
// Removed unused imports for cloudfront, route53, alias, dynamodb, iam, and Cognito
// as these components are no longer used in this stack

// This constant was used for DynamoDB table references in the commented code below
const TENANT_TABLE = 'TenantDataTable';

export interface TenantOnboardingStackProps extends StackProps {
  readonly plan: string;
  readonly tenantid: string;
  // Removed customDomain and hostedZoneId as they're no longer used
}

export class TenantOnboardingStack extends Stack {
  constructor(scope: Construct, id: string, props: TenantOnboardingStackProps) {
    super(scope, id, props);

    const tenantId = new CfnParameter(this, 'TenantId', {});
    const companyName = new CfnParameter(this, 'CompanyName', {});
    const tenantAdminEmail = new CfnParameter(this, 'TenantAdminEmail', {});
    const appDistributionId = new CfnParameter(this, 'AppDistributionId', {});
    const roleArn = new CfnParameter(this, 'RoleArn', {});

    // Removed custom domain, distribution domain, and Cognito URL handling as they're no longer needed

    // No EKS cluster creation

    // Note: The following components have been removed as they are no longer needed:
    // - HostedZone, Distribution, and ARecord (for custom domains)
    // - Cognito resources (authentication now handled by common stack)
    
    // Only keeping the tenant ID output as it's still used
    new CfnOutput(this, 'tenantId', {
      key: 'TenantId',
      value: tenantId.valueAsString,
    });

    // create tenant entry in dynamodb
    // const tableArn = Arn.format(
    //   {
    //     service: 'dynamodb',
    //     resource: 'table',
    //     resourceName: TENANT_TABLE,
    //   },
    //   this
    // );

    // NOTE: The following commented code was previously used to create tenant entries in DynamoDB
    // with Cognito authentication details. This is no longer needed as authentication is now
    // handled by the common stack.
    //
    // const tenantEntry = new cr.AwsCustomResource(this, 'TenantEntryResource', {
    //   onCreate: {
    //     service: 'DynamoDB',
    //     action: 'putItem',
    //     parameters: {
    //       TableName: TENANT_TABLE,
    //       Item: {
    //         TENANT_ID: { S: props.tenantid },
    //         COMPANY_NAME: { S: companyName.valueAsString },
    //         TENANT_EMAIL: { S: tenantAdminEmail.valueAsString },
    //         PLAN: { S: props.plan },
    //         // Auth details now come from common stack instead of tenant-specific Cognito
    //       },
    //     },
    //     physicalResourceId: cr.PhysicalResourceId.of(`TenantEntry-${props.tenantid}`),
    //   },
    //   onDelete: {
    //     service: 'DynamoDB',
    //     action: 'deleteItem',
    //     parameters: {
    //       TableName: TENANT_TABLE,
    //       Key: {
    //         TENANT_ID: { S: props.tenantid },
    //       },
    //     },
    //   },
    //   policy: cr.AwsCustomResourcePolicy.fromSdkCalls({ resources: [tableArn] }),
    // });

  }
}
