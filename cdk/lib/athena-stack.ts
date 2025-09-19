import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as cr from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";

export interface AthenaStackProps extends cdk.NestedStackProps {
  s3BucketName: string;
}

export class AthenaStack extends cdk.NestedStack {
  public readonly athenaResultsBucket: s3.Bucket;
  public readonly ATHENA_DB = "saas_logs_db";
  public readonly ATHENA_TABLE = "tenant_logs";
  public readonly ATHENA_WORKGROUP = "primary";

  constructor(scope: Construct, id: string, props: AthenaStackProps) {
    super(scope, id, props);

    // Create Athena results bucket
    this.athenaResultsBucket = new s3.Bucket(this, "AthenaResultsBucket", {
      bucketName: `athena-query-results-${this.account}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Create Athena database and table
    this.createAthenaResources(props.s3BucketName);

    // Output the Athena results bucket name
    new cdk.CfnOutput(this, "AthenaResultsBucketName", {
      value: this.athenaResultsBucket.bucketName,
      description: "The name of the Athena results bucket",
    });
  }

  private createAthenaResources(s3BucketName: string) {
    // Create database with custom resource to handle existing
    const createDatabase = new cr.AwsCustomResource(this, "CreateDatabase", {
      onCreate: {
        service: "Glue",
        action: "createDatabase",
        parameters: {
          DatabaseInput: {
            Name: this.ATHENA_DB,
            Description: "Database for SaaS logs analysis",
          },
        },
        physicalResourceId: cr.PhysicalResourceId.of(this.ATHENA_DB),
        ignoreErrorCodesMatching: "AlreadyExistsException",
      },
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
        resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE,
      }),
    });

    // Create table with custom resource to handle existing
    const createTable = new cr.AwsCustomResource(this, "CreateTable", {
      onCreate: {
        service: "Glue",
        action: "createTable",
        parameters: {
          DatabaseName: this.ATHENA_DB,
          TableInput: {
            Name: this.ATHENA_TABLE,
            Description: "Table for tenant logs",
            TableType: "EXTERNAL_TABLE",
            Parameters: {
              classification: "json",
              typeOfData: "file",
            },
            StorageDescriptor: {
              Columns: [
                { Name: "timestamp", Type: "string" },
                { Name: "level", Type: "string" },
                { Name: "tenant", Type: "string" },
                { Name: "environment", Type: "string" },
                { Name: "component", Type: "string" },
                { Name: "correlation_id", Type: "string" },
                { Name: "request_id", Type: "string" },
                { Name: "event", Type: "string" },
                { Name: "path", Type: "string" },
                { Name: "job", Type: "string" },
                { Name: "status", Type: "string" },
                { Name: "entity_id", Type: "string" },
                { Name: "detail", Type: "string" },
              ],
              Location: `s3://${s3BucketName}/`,
              InputFormat: "org.apache.hadoop.mapred.TextInputFormat",
              OutputFormat: "org.apache.hadoop.hive.ql.io.IgnoreKeyTextOutputFormat",
              SerdeInfo: {
                SerializationLibrary: "org.openx.data.jsonserde.JsonSerDe",
                Parameters: {
                  "ignore.malformed.json": "true",
                },
              },
            },
          },
        },
        physicalResourceId: cr.PhysicalResourceId.of(`${this.ATHENA_DB}.${this.ATHENA_TABLE}`),
        ignoreErrorCodesMatching: "AlreadyExistsException",
      },
      policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
        resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE,
      }),
    });

    // Add explicit dependency to ensure database is created before table
    createTable.node.addDependency(createDatabase);
  }
}