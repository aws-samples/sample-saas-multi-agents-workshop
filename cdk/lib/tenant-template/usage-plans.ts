// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { Construct } from "constructs";
import {
  ApiKey,
  Period,
  type RestApi,
  type UsagePlan,
} from "aws-cdk-lib/aws-apigateway";

interface UsagePlansProps {
  apiGateway: RestApi;
}

export class UsagePlans extends Construct {
  public readonly usagePlanBasicTier: UsagePlan;
  constructor(scope: Construct, id: string, props: UsagePlansProps) {
    super(scope, id);

    this.usagePlanBasicTier = props.apiGateway.addUsagePlan(
      "SaaSGenAIWorkshopUsagePlan",
      {
        quota: {
          limit: 100,
          period: Period.DAY,
        },
        throttle: {
          burstLimit: 30,
          rateLimit: 10,
        },
      }
    );

    for (const usagePlanTier of [this.usagePlanBasicTier]) {
      usagePlanTier.addApiStage({
        api: props.apiGateway,
        stage: props.apiGateway.deploymentStage,
      });
    }
  }
}
