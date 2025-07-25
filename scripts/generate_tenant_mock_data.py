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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize S3 client
s3 = boto3.client('s3')

# Industry-specific data templates
INDUSTRY_TEMPLATES = {
    "mining": {
        "company_name": "Global Mining Corp",
        "services": ["Gold Extraction", "Copper Mining", "Iron Ore Processing", "Coal Mining", "Diamond Mining"],
        "locations": ["Alaska", "Arizona", "Nevada", "Wyoming", "Montana", "Colorado"],
        "equipment": ["Excavator", "Dump Truck", "Drill Rig", "Crusher", "Conveyor Belt", "Screening Plant"],
        "issues": ["Equipment Failure", "Safety Incident", "Environmental Concern", "Permit Delay", "Production Shortfall"],
        "resolutions": [
            "Replaced faulty hydraulic system on primary excavator",
            "Implemented new safety protocols for underground operations",
            "Installed additional water filtration systems to address environmental concerns",
            "Expedited permit renewal through regulatory liaison",
            "Optimized crusher settings to increase throughput by 15%"
        ],
        "sop_titles": [
            "Emergency Evacuation Procedures",
            "Equipment Maintenance Schedule",
            "Environmental Compliance Checklist",
            "Safety Inspection Protocol",
            "Ore Quality Testing Procedure"
        ]
    },
    "finance": {
        "company_name": "Global Financial Services",
        "services": ["Personal Banking", "Mortgage Lending", "Investment Management", "Credit Cards", "Insurance"],
        "locations": ["New York", "London", "Singapore", "Tokyo", "Frankfurt", "Sydney"],
        "systems": ["Core Banking System", "Payment Gateway", "Trading Platform", "Customer Portal", "Mobile App"],
        "issues": ["Transaction Failure", "System Downtime", "Security Alert", "Compliance Violation", "Customer Complaint"],
        "resolutions": [
            "Restored transaction processing by restarting payment gateway",
            "Implemented additional authentication layer for high-value transfers",
            "Updated compliance reporting to meet new regulatory requirements",
            "Resolved customer data synchronization issue between systems",
            "Fixed interest calculation bug in mortgage processing module"
        ],
        "sop_titles": [
            "Anti-Money Laundering Procedures",
            "Customer Onboarding Process",
            "Disaster Recovery Protocol",
            "Data Security Standards",
            "Regulatory Reporting Guidelines"
        ]
    },
    "healthcare": {
        "company_name": "MediCare Solutions",
        "services": ["Patient Care", "Diagnostic Services", "Pharmacy", "Telemedicine", "Medical Records"],
        "locations": ["Boston", "Chicago", "Houston", "Los Angeles", "Miami", "Seattle"],
        "systems": ["Electronic Health Records", "Appointment Scheduler", "Billing System", "Lab Results Portal", "Pharmacy Management"],
        "issues": ["System Outage", "Data Access Error", "Billing Discrepancy", "Appointment Scheduling Failure", "Medication Error"],
        "resolutions": [
            "Restored EHR system after network outage",
            "Fixed patient data synchronization between departments",
            "Corrected billing codes for insurance claims",
            "Optimized appointment scheduling algorithm to reduce wait times",
            "Updated medication interaction checking system with latest drug database"
        ],
        "sop_titles": [
            "Patient Privacy Protocols",
            "Emergency Response Procedures",
            "Infection Control Guidelines",
            "Medication Administration Process",
            "Medical Records Management"
        ]
    },
    "retail": {
        "company_name": "Global Retail Enterprises",
        "services": ["In-store Sales", "E-commerce", "Inventory Management", "Customer Service", "Marketing"],
        "locations": ["New York", "Los Angeles", "Chicago", "Dallas", "Miami", "Seattle"],
        "systems": ["Point of Sale", "Inventory Management", "E-commerce Platform", "CRM System", "Payment Processing"],
        "issues": ["Inventory Discrepancy", "Payment Processing Failure", "Website Outage", "Order Fulfillment Delay", "Customer Complaint"],
        "resolutions": [
            "Reconciled inventory discrepancies through full stock audit",
            "Restored payment processing by updating gateway credentials",
            "Optimized website performance during high traffic periods",
            "Implemented new warehouse picking system to reduce fulfillment times",
            "Enhanced customer service chatbot with additional response scenarios"
        ],
        "sop_titles": [
            "Store Opening and Closing Procedures",
            "Inventory Management Process",
            "Customer Return Policy",
            "Payment Handling Guidelines",
            "Order Fulfillment Protocol"
        ]
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
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["retail"])
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
                message = f"Request failed for {random.choice(template['services'])} endpoint"
            elif service == "auth-service":
                message = "Authentication failed for user"
            elif service == "data-service":
                message = f"Failed to retrieve data for {random.choice(template['services'])}"
            elif service == "notification-service":
                message = "Failed to send notification to user"
            else:
                message = "User profile update failed"
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
        
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "service": service,
            "message": message,
            "request_id": request_id,
            "location": random.choice(template["locations"])
        }
        
        logs.append(log_entry)
    
    return logs

def generate_kb_documents(industry, count=5):
    """Generate knowledge base documents"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["retail"])
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
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["retail"])
    documents = []
    
    for i in range(count):
        issue = random.choice(template["issues"])
        resolution = random.choice(template["resolutions"])
        service = random.choice(template["services"])
        
        title = f"Resolution: {issue} in {service}"
        content = f"""
# {title}

## Issue Description
A {issue} was reported in the {service} area at {random.choice(template['locations'])}.

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
            "resolution": resolution,
            "service": service,
            "resolution_date": generate_timestamp(days_ago=60).split()[0]
        })
    
    return documents

def generate_sop_documents(industry, count=5):
    """Generate Standard Operating Procedure documents"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["retail"])
    documents = []
    
    for i in range(count):
        sop_title = template["sop_titles"][i % len(template["sop_titles"])]
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

def upload_to_s3(bucket, tenant_id, data, file_path):
    """Upload data to S3 bucket under tenant prefix"""
    key = f"{tenant_id}/{file_path}"
    
    try:
        if isinstance(data, (dict, list)):
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(data, indent=2),
                ContentType='application/json'
            )
        else:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType='text/plain'
            )
        logging.info(f"Successfully uploaded {key} to S3 bucket {bucket}")
        return True
    except Exception as e:
        logging.error(f"Error uploading to S3: {e}")
        return False

def generate_meeting_data(tenant_id, industry="retail", count=5) -> List[Dict[str, Any]]:
    """Generate structured meeting data for DynamoDB"""
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["retail"])
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

def generate_and_upload_tenant_data(bucket, tenant_id, industry="retail"):
    """Generate and upload all tenant data to S3 and DynamoDB"""
    
    # 1. Generate microservice logs
    logs = generate_microservice_logs(industry, count=30)
    upload_to_s3(bucket, tenant_id, logs, "logs/microservice-logs.json")
    
    # 2. Generate KB documents
    kb_docs = generate_kb_documents(industry, count=8)
    for i, doc in enumerate(kb_docs):
        file_name = f"kb/{doc['title'].replace(' ', '-').lower()}.md"
        upload_to_s3(bucket, tenant_id, doc["content"], file_name)
    
    # 3. Generate resolution documents
    resolutions = generate_resolution_documents(industry, count=10)
    for i, doc in enumerate(resolutions):
        file_name = f"resolutions/{doc['title'].replace(' ', '-').lower()}.md"
        upload_to_s3(bucket, tenant_id, doc["content"], file_name)
    
    # 4. Generate SOP documents
    sops = generate_sop_documents(industry, count=5)
    for i, doc in enumerate(sops):
        file_name = f"sops/{doc['title'].replace(' ', '-').lower()}.md"
        upload_to_s3(bucket, tenant_id, doc["content"], file_name)
    
    # 5. Generate a tenant-specific meeting notes file similar to the existing ones
    template = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["retail"])
    meeting_notes = f"""
Meeting Notes for {template['company_name']} - Quarterly Review

1. Meeting Date: {(datetime.datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")}
   Topics Discussed: {random.choice(template['services'])}, {random.choice(template['services'])}
   Notes: Reviewed performance metrics and identified areas for improvement. Customer satisfaction scores have increased by 5% since last quarter.

2. Meeting Date: {(datetime.datetime.now() - timedelta(days=25)).strftime("%Y-%m-%d")}
   Topics Discussed: {random.choice(template['services'])}, {random.choice(template['services'])}
   Notes: Discussed upcoming regulatory changes and their impact on operations. Compliance team to prepare implementation plan by next month.

3. Meeting Date: {(datetime.datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")}
   Topics Discussed: {random.choice(template['services'])}, Technology Updates
   Notes: Reviewed new technology implementation timeline. Initial testing shows promising results with 15% efficiency improvement.

4. Meeting Date: {(datetime.datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")}
   Topics Discussed: Customer Feedback, Service Improvements
   Notes: Analyzed recent customer feedback and identified key areas for service enhancement. Team to implement changes within 60 days.

5. Meeting Date: {(datetime.datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")}
   Topics Discussed: {random.choice(template['services'])}, Market Trends
   Notes: Evaluated current market trends and competitive landscape. Strategy team to present adaptation recommendations next week.

End of Meeting Notes.
"""
    upload_to_s3(bucket, tenant_id, meeting_notes, "meeting-notes.txt")
    
    # 6. Generate and store structured meeting data in DynamoDB
    meetings = generate_meeting_data(tenant_id, industry, count=5)
    write_to_dynamodb(tenant_id, meetings)
    
    logging.info(f"Successfully generated and uploaded all mock data for tenant {tenant_id}")
    return True

def determine_industry_from_tenant_name(tenant_name):
    """Determine industry based on tenant name"""
    tenant_name_lower = tenant_name.lower()
    
    if any(keyword in tenant_name_lower for keyword in ["mining", "mineral", "resource", "extract"]):
        return "mining"
    elif any(keyword in tenant_name_lower for keyword in ["bank", "finance", "invest", "capital"]):
        return "finance"
    elif any(keyword in tenant_name_lower for keyword in ["health", "medical", "hospital", "care"]):
        return "healthcare"
    elif any(keyword in tenant_name_lower for keyword in ["retail", "shop", "store", "market"]):
        return "retail"
    else:
        # Default to retail if no match
        return "retail"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate and upload mock tenant data to S3 and DynamoDB')
    parser.add_argument('--tenant-id', type=str, required=True, help='Tenant ID')
    parser.add_argument('--tenant-name', type=str, required=True, help='Tenant Name')
    parser.add_argument('--bucket', type=str, required=True, help='S3 bucket name')
    parser.add_argument('--table', type=str, help='DynamoDB table name')
    parser.add_argument('--industry', type=str, help='Industry type (mining, finance, healthcare, retail)')
    
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