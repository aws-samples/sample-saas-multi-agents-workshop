// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import { Bucket } from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface CostUsageReportUploadProps extends cdk.StackProps {
  curBucketName: string;
  folderName: string;
}

export class CostUsageReportUpload extends Construct {
  constructor(scope: Construct, id: string, props: CostUsageReportUploadProps) {
    super(scope, id);

    const curBucketName = s3.Bucket.fromBucketName(
      this,
      "curBucketName",
      props.curBucketName
    );
    const folderName = props.folderName;

    // Deploy the local folder to the S3 bucket
    new s3deploy.BucketDeployment(this, "DeployCostUsageReports", {
      sources: [s3deploy.Source.asset("../data/cur_report_2025.zip")],
      destinationBucket: curBucketName,
      destinationKeyPrefix: folderName,
    });
  }
}
