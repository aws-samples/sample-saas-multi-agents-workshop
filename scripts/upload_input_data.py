#!/usr/bin/env python3

import boto3
import json
import os
from pathlib import Path

def main():
    # Bucket names - replace with actual bucket names or leave as None to prompt
    kb_bucket = "saas-knowlege-base-bucket-822849401905"  # Replace with your KB bucket name
    logs_bucket = "saas-logs-bucket-822849401905"  # Replace with your logs bucket name
    
    # Get bucket names if not specified
    if not kb_bucket:
        kb_bucket = input("Enter Knowledge Base S3 bucket name: ").strip()
    if not logs_bucket:
        logs_bucket = input("Enter Logs S3 bucket name: ").strip()
    
    s3 = boto3.client('s3')
    
    # Delete all objects in buckets
    print("Deleting existing objects...")
    for bucket in [kb_bucket, logs_bucket]:
        try:
            objects = s3.list_objects_v2(Bucket=bucket)
            if 'Contents' in objects:
                delete_keys = [{'Key': obj['Key']} for obj in objects['Contents']]
                s3.delete_objects(Bucket=bucket, Delete={'Objects': delete_keys})
        except Exception as e:
            print(f"Error clearing bucket {bucket}: {e}")
    
    # Upload knowledge base documents
    data_path = Path("data")
    
    # Get all tenant folders
    tenants = [d.name for d in data_path.iterdir() if d.is_dir()]
    
    for tenant in tenants:
        tenant_path = data_path / tenant
        
        # Upload KB documents
        for kb_file in tenant_path.glob("*.md"):
            key = f"{tenant}_{kb_file.name}"
            s3.upload_file(str(kb_file), kb_bucket, key, 
                          ExtraArgs={'Metadata': {'tenant_id': tenant}})
            
            # Create metadata file for Bedrock KB
            metadata = {
                "metadataAttributes": {
                    "tenant_id": tenant
                }
            }
            metadata_key = f"{tenant}_{kb_file.stem}.md.metadata.json"
            s3.put_object(Bucket=kb_bucket, Key=metadata_key, 
                         Body=json.dumps(metadata),
                         Metadata={'tenant_id': tenant})
            
            print(f"Uploaded {key} and metadata for {tenant}")
        
        # Upload logs
        logs_path = tenant_path / "logs"
        if logs_path.exists():
            for log_file in logs_path.glob("*"):
                if log_file.is_file():
                    key = f"{tenant}/{log_file.name}"
                    s3.upload_file(str(log_file), logs_bucket, key,
                                  ExtraArgs={'Metadata': {'tenant_id': tenant}})
                    print(f"Uploaded {key}")
    
    print("Upload completed!")

if __name__ == "__main__":
    main()