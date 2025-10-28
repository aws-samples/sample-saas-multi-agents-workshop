#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { TenantOnboardingStack } from '../lib/tenant-onboarding-stack';

const env = {
  account: process.env.AWS_ACCOUNT,
  region: process.env.AWS_REGION
};


const app = new cdk.App();

new TenantOnboardingStack(app, `TenantStack-${process.env.TENANT_ID}`, {
  env,
  plan: process.env.PLAN!,
  tenantid: process.env.TENANT_ID!,
});