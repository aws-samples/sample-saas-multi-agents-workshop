// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { ControlPlaneStack } from "../lib/control-plane-stack";
import { AppPlaneStack } from "../lib/app-plane-stack";
import { CommonResourcesStack } from "../lib/tenant-template/common-resources-stack";
import { ServicesStack } from "../lib/services-stack";
import { AgentCoreStack } from "../lib/agentcore-stack";

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
  crossRegionReferences: true, // Enable cross-region references
});

new AppPlaneStack(app, "ApplicationPlane", {
  env,
  eventBusArn: controlPlaneStack.eventBusArn,
});

const commonResource = new CommonResourcesStack(
  app,
  "saas-genai-workshop-common-resources",
  {
    env, // Use the same environment as ControlPlaneStack
    crossRegionReferences: true, // Enable cross-region references
    controlPlaneApiGwUrl: controlPlaneStack.controlPlaneUrl,
  }
);

// Create the ServicesStack
new ServicesStack(app, "ServicesStack", {
  env,
});

// new AgentCoreStack(app, "AgentCoreStack", {
//   env,
//   kbId: commonResource.node.tryGetContext('KnowledgeBaseId') || 'EOB1EVNAAC',
//   s3BucketName: commonResource.node.tryGetContext('DataBucketName') || 's3://saas-logs-bucket-822849401905',
// });

new AgentCoreStack(app, "AgentCoreStack", {
  env,
  kbId: 'EOB1EVNAAC',
  s3BucketName: 'saas-logs-bucket-822849401905',
  athenaResultsBucketName: `athena-query-results-${env.account || '822849401905'}`,
});