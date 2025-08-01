// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { ControlPlaneStack } from "../lib/control-plane-stack";
import { AppPlaneStack } from '../lib/app-plane-stack';
import { CommonResourcesStack } from '../lib/tenant-template/common-resources-stack';
import { ServicesStack } from '../lib/services-stack';


const env = {
  account: process.env.AWS_ACCOUNT,
  region: process.env.AWS_REGION,
};

const app = new cdk.App();
const saasAdminEmail = process.env.CDK_PARAM_SYSTEM_ADMIN_EMAIL!;

const controlPlaneStack = new ControlPlaneStack(app, "ControlPlaneStack", {
  // systemAdminRoleName: process.env.CDK_PARAM_SYSTEM_ADMIN_ROLE_NAME,
  systemAdminEmail: saasAdminEmail,
  env, // Add the same environment as AppPlaneStack
});

new AppPlaneStack(app, 'ApplicationPlane', {
  env,
  eventBusArn: controlPlaneStack.eventBusArn,
});

const commonResource = new CommonResourcesStack(app, 'saas-genai-workshop-common-resources', {
  env,
});

// Create the ServicesStack
new ServicesStack(app, 'ServicesStack', {
  env,
  appSiteDistributionId: 'dummy-distribution-id',
  appSiteCloudFrontDomain: 'dummy-cloudfront-domain',
});
