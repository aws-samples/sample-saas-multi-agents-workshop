#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import json
import argparse
import logging
import os
import random
import datetime
from datetime import timedelta
import uuid
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize S3 client
s3 = boto3.client('s3')

# Industry-specific data templates for SmartResolve SaaS platform
INDUSTRY_TEMPLATES = {
    "finance": {
        "company_name": "ClearPay",
        "description": "A company that provides payment and transaction reconciliation services for small to mid-sized financial institutions.",
        "services": ["Payment Processing", "Transaction Reconciliation", "ACH Transfers", "Card Processing", "Fraud Detection"],
        "locations": ["New York", "London", "Singapore", "Tokyo", "Frankfurt", "Sydney"],
        "systems": ["Core Banking System", "Payment Gateway", "Transaction Processing", "Customer Portal", "Mobile App"],
        "issues": [
            "Transaction Failure", 
            "System Downtime", 
            "Security Alert", 
            "Compliance Violation", 
            "Customer Complaint",
            "ACH Transfer Failure",
            "Card Transaction Reversal Failure",
            "Reconciliation Discrepancy",
            "API Error",
            "Batch Processing Failure"
        ],
        "error_codes": [
            "ERR_ROUTING_TIMEOUT",
            "INVALID_ACCOUNT_CODE",
            "ACH_R01",
            "API_ERROR_2041",
            "BATCH_PROCESSING_ERROR",
            "TRANSACTION_TIMEOUT",
            "INSUFFICIENT_FUNDS",
            "INVALID_CARD_NUMBER",
            "SECURITY_VIOLATION",
            "NETWORK_ERROR"
        ],
        "resolutions": [
            "Restored transaction processing by restarting payment gateway",
            "Implemented additional authentication layer for high-value transfers",
            "Updated compliance reporting to meet new regulatory requirements",
            "Resolved customer data synchronization issue between systems",
            "Fixed interest calculation bug in mortgage processing module",
            "Updated routing codes in the configuration database",
            "Increased timeout settings for international transactions",
            "Applied hotfix to correct batch processing logic",
            "Implemented retry mechanism with exponential backoff",
            "Added validation checks for account numbers"
        ],
        "sop_titles": [
            "Handling Failed ACH Transactions",
            "End-of-Day Reconciliation Discrepancy Resolution",
            "Responding to PCI DSS Breach Events",
            "Transaction Failure Troubleshooting",
            "Customer Complaint Resolution Process"
        ]
    },
    "healthcare": {
        "company_name": "MediOps",
        "description": "A platform offering EHR (Electronic Health Records) infrastructure and automation tools for medium-sized healthcare providers.",
        "services": ["Electronic Health Records", "Lab Results Integration", "Patient Scheduling", "Billing Management", "Telemedicine"],
        "locations": ["Boston", "Chicago", "Houston", "Los Angeles", "Miami", "Seattle"],
        "systems": ["EHR Platform", "Lab Integration System", "Appointment Scheduler", "Billing System", "Patient Portal"],
        "issues": [
            "System Outage", 
            "Data Access Error", 
            "Billing Discrepancy", 
            "Appointment Scheduling Failure", 
            "Medication Error",
            "Lab Results Sync Failure",
            "Patient Record Mismatch",
            "HL7 Integration Error",
            "FHIR Mapping Error",
            "Authentication Failure"
        ],
        "error_codes": [
            "LAB_SYNC_TIMEOUT",
            "FHIR_MAPPING_ERROR",
            "HL7_PARSE_ERROR",
            "EHR_AUTH_FAILURE",
            "PATIENT_ID_MISMATCH",
            "APPOINTMENT_CONFLICT",
            "DATABASE_CONN_ERROR",
            "API_RATE_LIMIT",
            "DATA_VALIDATION_ERROR",
            "HIPAA_COMPLIANCE_ALERT"
        ],
        "resolutions": [
            "Restored EHR system after network outage",
            "Fixed patient data synchronization between departments",
            "Corrected billing codes for insurance claims",
            "Optimized appointment scheduling algorithm to reduce wait times",
            "Updated medication interaction checking system with latest drug database",
            "Implemented new HL7 parser to handle non-standard messages",
            "Updated FHIR mapping templates for lab results",
            "Increased connection pool size for database access",
            "Added data validation checks for patient records",
            "Implemented caching layer to reduce API calls"
        ],
        "sop_titles": [
            "Electronic Health Record Outage Response",
            "Patient Health Information (PHI) Breach Escalation",
            "Resolving HL7 Lab Integration Failures",
            "EHR System Backup and Recovery",
            "Patient Data Integrity Verification"
        ]
    }
}

# Common error codes across all tenants
COMMON_ERROR_CODES = {
    "ERROR_1001": {
        "name": "INSUFFICIENT_FUNDS",
        "description": "The sending account does not have sufficient funds to complete the transaction.",
        "resolution": "Ensure adequate funds are available in the sending account before initiating the transfer. Consider setting up balance alerts to monitor account levels."
    },
    "ERROR_1002": {
        "name": "INVALID_ACCOUNT",
        "description": "The specified account number is invalid or does not exist.",
        "resolution": "Verify the account number is correct and active. Check for typos or formatting errors in the account number."
    },
    "ERROR_1003": {
        "name": "SYSTEM_TIMEOUT",
        "description": "The operation timed out due to system delays or connectivity issues.",
        "resolution": "Retry the operation. If the issue persists, check network connectivity and system status before contacting support."
    },
    "ERROR_1004": {
        "name": "AUTHENTICATION_FAILED",
        "description": "User authentication failed due to invalid credentials or expired session.",
        "resolution": "Verify credentials are correct. Reset password if necessary. Check if account is locked due to multiple failed attempts."
    },
    "ERROR_1005": {
        "name": "PERMISSION_DENIED",
        "description": "User does not have sufficient permissions to perform the requested action.",
        "resolution": "Contact system administrator to review and update user permissions as needed."
    }
}

def generate_timestamp(days_ago=30):
    """Generate a random timestamp within the last X days"""
    now = datetime.datetime.now()
    random_days = random.randint(0, days_ago)
    random_hours = random.randint(0, 23)
    random_minutes = random.randint(0, 59)
    random_seconds = random.randint(0, 59)
    
    timestamp = now - timedelta(
        days=random_days,
        hours=random_hours,
        minutes=random_minutes,
        seconds=random_seconds
    )
    
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")

def generate_microservice_logs(industry, count=20):
    """Generate mock microservice logs"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["finance"])
    logs = []
    
    services = ["api-gateway", "auth-service", "data-service", "notification-service", "user-service"]
    log_levels = ["INFO", "WARN", "ERROR", "DEBUG"]
    log_level_weights = [0.7, 0.15, 0.05, 0.1]  # Probability distribution
    
    for _ in range(count):
        service = random.choice(services)
        level = random.choices(log_levels, log_level_weights)[0]
        timestamp = generate_timestamp()
        
        if level == "ERROR":
            if service == "api-gateway":
                error_code = random.choice(template['error_codes'])
                message = f"Request failed for {random.choice(template['services'])} endpoint. Error code: {error_code}"
            elif service == "auth-service":
                message = "Authentication failed for user. Error code: AUTHENTICATION_FAILED"
            elif service == "data-service":
                error_code = random.choice(template['error_codes'])
                message = f"Failed to retrieve data for {random.choice(template['services'])}. Error code: {error_code}"
            elif service == "notification-service":
                message = "Failed to send notification to user. Error code: NOTIFICATION_DELIVERY_FAILED"
            else:
                message = "User profile update failed. Error code: DATA_UPDATE_ERROR"
        elif level == "WARN":
            if service == "api-gateway":
                message = "High latency detected in API responses"
            elif service == "auth-service":
                message = "Multiple failed login attempts detected"
            elif service == "data-service":
                message = "Slow database query performance"
            elif service == "notification-service":
                message = "Notification delivery rate below threshold"
            else:
                message = "User session timeout"
        else:
            if service == "api-gateway":
                message = f"Request processed for {random.choice(template['services'])} endpoint"
            elif service == "auth-service":
                message = "User authenticated successfully"
            elif service == "data-service":
                message = f"Data retrieved for {random.choice(template['services'])}"
            elif service == "notification-service":
                message = "Notification sent to user"
            else:
                message = "User profile updated"
        
        request_id = str(uuid.uuid4())
        transaction_id = str(uuid.uuid4())
        
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "service": service,
            "message": message,
            "request_id": request_id,
            "transaction_id": transaction_id,
            "location": random.choice(template["locations"])
        }
        
        logs.append(log_entry)
    
    return logs

def generate_error_codes_document(industry):
    """Generate error codes document"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["finance"])
    
    content = f"""
# {template['company_name']} Error Codes

This document provides a comprehensive list of error codes that may be encountered when using {template['company_name']} services.

## Common Error Codes

These error codes are common across all services:

"""
    
    # Add common error codes
    for code, details in COMMON_ERROR_CODES.items():
        content += f"""
### {code}: {details['name']}
**Description**: {details['description']}
**Resolution**: {details['resolution']}

"""
    
    # Add industry-specific error codes
    content += f"""
## {template['company_name']} Specific Error Codes

These error codes are specific to {template['company_name']} services:

"""
    
    for i, error_code in enumerate(template['error_codes']):
        resolution = template['resolutions'][i % len(template['resolutions'])]
        service = template['services'][i % len(template['services'])]
        
        content += f"""
### {error_code}
**Service**: {service}
**Description**: Error encountered during {service} operation.
**Resolution**: {resolution}

"""
    
    return {
        "title": f"{template['company_name']}_Error_Codes",
        "content": content
    }

def generate_kb_documents(industry, count=5):
    """Generate knowledge base documents"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["finance"])
    documents = []
    
    for i in range(count):
        service = random.choice(template["services"])
        title = f"{service} Knowledge Base Document {i+1}"
        content = f"""
# {title}

## Overview
This document provides comprehensive information about {service} at {template['company_name']}.

## Key Information
- Service: {service}
- Primary Location: {random.choice(template['locations'])}
- Last Updated: {generate_timestamp(days_ago=90).split()[0]}

## Detailed Description
{template['company_name']} offers {service} to meet the needs of our clients. 
This service is designed to provide efficient and reliable solutions for our customers.

## Common Use Cases
1. {random.choice(template['issues'])} resolution
2. Optimizing {service} performance
3. Integration with other services

## Common Error Codes
1. {random.choice(template['error_codes'])} - Occurs when there are connectivity issues
2. {random.choice(template['error_codes'])} - Occurs when validation fails

## Best Practices
- Regular monitoring of {service} metrics
- Following established SOPs for {service}
- Proper documentation of all changes and updates

## Contact Information
For more information about {service}, please contact the service team.
"""
        documents.append({
            "title": title,
            "content": content,
            "service": service,
            "created_date": generate_timestamp(days_ago=180).split()[0]
        })
    
    return documents

def generate_resolution_documents(industry, count=8):
    """Generate known resolution documents"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["finance"])
    documents = []
    
    for i in range(count):
        issue = random.choice(template["issues"])
        resolution = random.choice(template["resolutions"])
        service = random.choice(template["services"])
        error_code = random.choice(template["error_codes"])
        
        title = f"Resolution: {issue} in {service}"
        content = f"""
# {title}

## Issue Description
A {issue} was reported in the {service} area at {random.choice(template['locations'])}.
Error Code: {error_code}

## Impact
This issue affected service delivery and required immediate attention.

## Resolution Steps
1. Identified the root cause of the {issue}
2. Implemented temporary workaround to restore service
3. {resolution}
4. Verified service restoration and functionality

## Prevention Measures
To prevent similar issues in the future, the following measures have been implemented:
- Enhanced monitoring for early detection
- Updated documentation and training materials
- Scheduled regular maintenance checks

## Resolution Date
{generate_timestamp(days_ago=60).split()[0]}

## Resolved By
Technical Support Team
"""
        documents.append({
            "title": title,
            "content": content,
            "issue": issue,
            "error_code": error_code,
            "resolution": resolution,
            "service": service,
            "resolution_date": generate_timestamp(days_ago=60).split()[0]
        })
    
    return documents

def generate_sop_documents(industry, count=5):
    """Generate Standard Operating Procedure documents"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["finance"])
    documents = []
    
    for i in range(min(count, len(template["sop_titles"]))):
        sop_title = template["sop_titles"][i]
        service = random.choice(template["services"])
        
        content = f"""
# {sop_title}

## Purpose
This Standard Operating Procedure (SOP) outlines the steps required for {sop_title.lower()} at {template['company_name']}.

## Scope
This procedure applies to all {service} operations across all locations.

## Responsibilities
- Managers: Ensure compliance with this SOP
- Staff: Follow the procedure as outlined
- Quality Assurance: Regular audits of procedure implementation

## Procedure
1. Preparation
   - Review relevant documentation
   - Ensure all necessary equipment is available
   - Verify prerequisites are met

2. Execution
   - Follow step-by-step process
   - Document all actions taken
   - Report any deviations from standard procedure

3. Verification
   - Confirm successful completion
   - Validate results against expected outcomes
   - Document any issues encountered

4. Documentation
   - Complete all required forms
   - Update relevant systems
   - Notify stakeholders of completion

## References
- Industry standards and regulations
- Internal policies and guidelines
- Related SOPs and work instructions

## Revision History
- Created: {generate_timestamp(days_ago=365).split()[0]}
- Last Updated: {generate_timestamp(days_ago=90).split()[0]}
- Next Review: {(datetime.datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")}
"""
        documents.append({
            "title": sop_title,
            "content": content,
            "service": service,
            "created_date": generate_timestamp(days_ago=365).split()[0],
            "updated_date": generate_timestamp(days_ago=90).split()[0]
        })
    
    return documents

def generate_clearpay_specific_data():
    """Generate ClearPay specific data"""
    content = """
# ClearPay Transaction Failure SOP

## Title: Handling Failed ACH Transactions
Steps:
1. Verify transaction error code in system logs.
2. Check if recipient account is valid and active.
3. If error code R01 (Account Closed), notify customer and request updated bank details.
4. Retry transaction after correction.
5. Escalate to support lead if the issue recurs more than twice for the same account.

# End-of-Day Reconciliation Playbook

## Title: Reconciliation Discrepancy Resolution
Steps:
1. Retrieve daily reconciliation batch report.
2. Identify mismatched transaction IDs and amounts.
3. Cross-reference against manual ledger entries.
4. If discrepancies are unresolved after 2 attempts, initiate incident ticket and notify finance team.
5. Document discrepancy and resolution path for audit.

# PCI DSS Compliance Incident SOP

## Title: Responding to PCI DSS Breach Events
Steps:
1. Isolate impacted systems.
2. Notify Compliance Officer within 15 minutes of detection.
3. Collect and secure all relevant logs.
4. Complete PCI incident worksheet.
5. Contact external PCI assessor if required.
"""
    return content

def generate_mediops_specific_data():
    """Generate MediOps specific data"""
    content = """
# EHR Downtime SOP

## Title: Electronic Health Record Outage Response
Steps:
1. Acknowledge downtime ticket in ITSM system.
2. Inform clinical staff via approved communication channel.
3. Attempt service restart on EHR application server.
4. If downtime >30min, transition to manual charting as per clinical backup procedures.
5. Report status to operations lead and maintain recovery log.

# PHI Breach Playbook

## Title: Patient Health Information (PHI) Breach Escalation
Steps:
1. Immediately disable suspected user credentials.
2. Notify Privacy Officer within 10 minutes.
3. Secure and export access logs for review.
4. Begin HIPAA-mandated breach notification process.
5. Complete internal reporting forms and prepare external notification template.

# Lab Integration Error SOP

## Title: Resolving HL7 Lab Integration Failures
Steps:
1. Confirm error details from integration logs.
2. Validate new lab test codes in HL7 mapping table.
3. If mapping is missing, update mapping table and redeploy integration.
4. Notify lab and clinical users when issue is resolved.
"""
    return content

def upload_to_s3(bucket, tenant_id, data, file_path, metadata=None):
    """Upload data to S3 bucket under tenant prefix with optional metadata"""
    key = f"{tenant_id}/{file_path}"
    
    try:
        args = {
            'Bucket': bucket,
            'Key': key,
            'ContentType': 'application/json' if isinstance(data, (dict, list)) else 'text/plain'
        }
        
        if metadata:
            args['Metadata'] = metadata
        
        if isinstance(data, (dict, list)):
            args['Body'] = json.dumps(data, indent=2)
        else:
            args['Body'] = data
            
        s3.put_object(**args)
        logging.info(f"Successfully uploaded {key} to S3 bucket {bucket}")
        return True
    except Exception as e:
        logging.error(f"Error uploading to S3: {e}")
        return False

def generate_meeting_data(tenant_id, industry="finance", count=5) -> List[Dict[str, Any]]:
    """Generate structured meeting data for DynamoDB"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["finance"])
    meetings = []
    
    for i in range(count):
        meeting_date = (datetime.datetime.now() - timedelta(days=30-i*5)).strftime("%Y-%m-%d")
        meeting_id = f"{tenant_id}-meeting-{i+1}"
        
        # Generate 2-5 action items per meeting
        action_items = []
        num_action_items = random.randint(2, 5)
        
        for j in range(num_action_items):
            # Randomly decide if owner or due date is missing (20% chance)
            owner_missing = random.random() < 0.2
            due_date_missing = random.random() < 0.2
            
            owner = "[OWNER_MISSING]" if owner_missing else f"{random.choice(['John', 'Sarah', 'Michael', 'Emma', 'David', 'Lisa'])} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Miller'])}"
            
            # Due date between 1-30 days after meeting
            if due_date_missing:
                due_date = "[DUE_DATE_MISSING]"
            else:
                days_after = random.randint(1, 30)
                due_date = (datetime.datetime.strptime(meeting_date, "%Y-%m-%d") + timedelta(days=days_after)).strftime("%Y-%m-%d")
            
            # Generate action item based on industry
            service = random.choice(template['services'])
            descriptions = [
                f"Review {service} performance metrics and prepare report",
                f"Update documentation for {service}",
                f"Schedule training session for team on {service}",
                f"Investigate customer complaints regarding {service}",
                f"Develop improvement plan for {service}",
                f"Coordinate with vendors for {service} upgrades",
                f"Prepare budget proposal for {service} expansion"
            ]
            
            action_items.append({
                "item_id": f"{meeting_id}-item-{j+1}",
                "description": random.choice(descriptions),
                "owner": owner,
                "due_date": due_date,
                "status": random.choice(["pending", "completed", "in_progress", "delayed"]),
                "context": f"Discussion during {template['company_name']} meeting about {service} and related operational matters."
            })
        
        meeting_data = {
            "meeting_id": meeting_id,
            "date": meeting_date,
            "action_items": action_items
        }
        
        meetings.append(meeting_data)
    
    return meetings

def write_to_dynamodb(tenant_id, meetings):
    """Write meeting data to DynamoDB"""
    try:
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('TENANT_DATA_TABLE', 'TenantDataTable')
        table = dynamodb.Table(table_name)
        
        with table.batch_writer() as batch:
            for meeting in meetings:
                # Create an item for each meeting
                item = {
                    'tenantId': tenant_id,
                    'dataId': f"meeting#{meeting['meeting_id']}",
                    'data': json.dumps(meeting)
                }
                batch.put_item(Item=item)
                
                # Create separate items for each action item for easier querying
                for action_item in meeting['action_items']:
                    action_item_data = {
                        'meeting_id': meeting['meeting_id'],
                        'date': meeting['date'],
                        'item_id': action_item['item_id'],
                        'description': action_item['description'],
                        'owner': action_item['owner'],
                        'due_date': action_item['due_date'],
                        'status': action_item['status'],
                        'context': action_item['context']
                    }
                    
                    item = {
                        'tenantId': tenant_id,
                        'dataId': f"action#{action_item['item_id']}",
                        'data': json.dumps(action_item_data)
                    }
                    batch.put_item(Item=item)
        
        logging.info(f"Successfully wrote {len(meetings)} meetings to DynamoDB for tenant {tenant_id}")
        return True
    except Exception as e:
        logging.error(f"Error writing to DynamoDB: {e}")
        return False

def generate_and_upload_tenant_data(bucket, tenant_id, industry="finance"):
    """Generate and upload all tenant data to S3 and DynamoDB"""
    
    # 1. Generate microservice logs
    logs = generate_microservice_logs(industry, count=30)
    upload_to_s3(bucket, tenant_id, logs, "logs/microservice-logs.json", {"tenant_id": tenant_id})
    
    # 2. Generate Error Codes document
    error_codes_doc = generate_error_codes_document(industry)
    upload_to_s3(bucket, tenant_id, error_codes_doc["content"], f"{error_codes_doc['title']}.txt", {"tenant_id": tenant_id})
    
    # 3. Generate KB documents
    kb_docs = generate_kb_documents(industry, count=8)
    for i, doc in enumerate(kb_docs):
        file_name = f"kb/{doc['title'].replace(' ', '-').lower()}.md"
        upload_to_s3(bucket, tenant_id, doc["content"], file_name, {"tenant_id": tenant_id})
    
    # 4. Generate resolution documents
    resolutions = generate_resolution_documents(industry, count=10)
    for i, doc in enumerate(resolutions):
        file_name = f"resolutions/{doc['title'].replace(' ', '-').lower()}.md"
        upload_to_s3(bucket, tenant_id, doc["content"], file_name, {"tenant_id": tenant_id})
    
    # 5. Generate SOP documents
    sops = generate_sop_documents(industry, count=5)
    for i, doc in enumerate(sops):
        file_name = f"sops/{doc['title'].replace(' ', '-').lower()}.md"
        upload_to_s3(bucket, tenant_id, doc["content"], file_name, {"tenant_id": tenant_id})
    
    # 6. Generate tenant-specific data
    if industry == "finance":
        specific_data = generate_clearpay_specific_data()
        upload_to_s3(bucket, tenant_id, specific_data, "kb/clearpay-specific-procedures.md", {"tenant_id": tenant_id})
    elif industry == "healthcare":
        specific_data = generate_mediops_specific_data()
        upload_to_s3(bucket, tenant_id, specific_data, "kb/mediops-specific-procedures.md", {"tenant_id": tenant_id})
    
    # 7. Generate and store structured meeting data in DynamoDB
    meetings = generate_meeting_data(tenant_id, industry, count=5)
    write_to_dynamodb(tenant_id, meetings)
    
    logging.info(f"Successfully generated and uploaded all mock data for tenant {tenant_id}")
    return True

def determine_industry_from_tenant_name(tenant_name):
    """Determine industry based on tenant name"""
    tenant_name_lower = tenant_name.lower()
    
    if "clearpay" in tenant_name_lower or any(keyword in tenant_name_lower for keyword in ["bank", "finance", "invest", "capital", "pay"]):
        return "finance"
    elif "mediops" in tenant_name_lower or any(keyword in tenant_name_lower for keyword in ["health", "medical", "hospital", "care"]):
        return "healthcare"
    elif any(keyword in tenant_name_lower for keyword in ["mining", "mineral", "resource", "extract"]):
        return "mining"
    elif any(keyword in tenant_name_lower for keyword in ["retail", "shop", "store", "market"]):
        return "retail"
    else:
        # Default to finance if no match
        return "finance"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate and upload mock tenant data to S3 and DynamoDB')
    parser.add_argument('--tenant-id', type=str, required=True, help='Tenant ID')
    parser.add_argument('--tenant-name', type=str, required=True, help='Tenant Name')
    parser.add_argument('--bucket', type=str, required=True, help='S3 bucket name')
    parser.add_argument('--table', type=str, help='DynamoDB table name')
    parser.add_argument('--industry', type=str, help='Industry type (finance, healthcare)')
    
    args = parser.parse_args()
    
    # If table name provided, set it as an environment variable
    if args.table:
        os.environ['TENANT_DATA_TABLE'] = args.table
    
    # If industry not specified, try to determine from tenant name
    industry = args.industry if args.industry else determine_industry_from_tenant_name(args.tenant_name)
    
    success = generate_and_upload_tenant_data(args.bucket, args.tenant_id, industry)
    
    if success:
        print(f"Successfully generated and uploaded mock data for tenant {args.tenant_id}")
        exit(0)
    else:
        print(f"Failed to generate and upload mock data for tenant {args.tenant_id}")
        exit(1)