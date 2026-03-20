import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as cr from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";
import { S3Table, Database, Schema, DataFormat } from "@aws-cdk/aws-glue-alpha";

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
    const database = new Database(this, "SaaSLogsDatabase", {
      databaseName: this.ATHENA_DB,
      description: "Database for SaaS logs analysis",
    });

    // Create table with custom resource to handle existing
    const table = new S3Table(this, "TenantLogsTable", {
      database: database,
      tableName: this.ATHENA_TABLE,
      bucket: s3.Bucket.fromBucketName(this, "LogsBucket", s3BucketName),

      // Your exact column schema
      columns: [
        { name: "timestamp", type: Schema.STRING },
        { name: "level", type: Schema.STRING },
        { name: "environment", type: Schema.STRING },
        { name: "component", type: Schema.STRING },
        { name: "correlation_id", type: Schema.STRING },
        { name: "request_id", type: Schema.STRING },
        { name: "event", type: Schema.STRING },
        { name: "path", type: Schema.STRING },
        { name: "job", type: Schema.STRING },
        { name: "status", type: Schema.STRING },
        { name: "entity_id", type: Schema.STRING },
        { name: "detail", type: Schema.STRING },
      ],

      // Your exact partition config
      partitionKeys: [{ name: "tenant_id", type: Schema.STRING }],

      // Your exact projection config
      parameters: {
        "projection.enabled": "true",
        "projection.tenant_id.type": "injected",
        "storage.location.template": `s3://${s3BucketName}/\$\{tenant_id\}/`,
        classification: "json",
        typeOfData: "file",
      },

      dataFormat: DataFormat.JSON,
    });

    // Proper dependency management (no race conditions)
    table.node.addDependency(database);
  }
}
