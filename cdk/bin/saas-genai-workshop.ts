// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
// import { BootstrapTemplateStack } from "../lib/tenant-template/bootstrap-template-stack";
// import { MultiAgentsBootstrapTemplateStack } from "../lib/tenant-template/multi-agents-bootstrap-template-stack";
import { ControlPlaneStack } from "../lib/control-plane-stack";
import { AppPlaneStack } from '../lib/app-plane-stack';
import { CommonResourcesStack } from '../lib/tenant-template/common-resources-stack';
// import { CoreUtilsTemplateStack } from "../lib/core-utils-template-stack";

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

// const coreUtilsTemplateStack = new CoreUtilsTemplateStack(
//   app,
//   "saas-genai-workshop-core-utils-stack",
//   {
//     controlPlane: controlPlaneStack.controlPlane,
//   }
// );

// const bootstrapTemplateStack = new BootstrapTemplateStack(
//   app,
//   "saas-genai-workshop-bootstrap-template",
//   {
//     coreUtilsStack: coreUtilsTemplateStack,
//     controlPlaneApiGwUrl:
//       controlPlaneStack.controlPlane.controlPlaneAPIGatewayUrl,
//   }
// );

// const multiAgentsBootstrapTemplateStack = new MultiAgentsBootstrapTemplateStack(
//   app,
//   "saas-genai-workshop-bootstrap-template",
//   {
//     env, // Add the same environment as other stacks
//   }
// );
