# SaaS Multi-Agents Workshop

This workshop demonstrates how to build a multi-tenant, multi-agent architecture for a SaaS platform called "SmartResolve" - a generative AI-powered intelligent resolution engine for technical support.

## Architecture Overview

The solution implements a multi-tenant architecture with the following components:

1. **Knowledge Base**: A pooled knowledge base with tenant isolation through metadata filtering
2. **Agents**: Multiple specialized agents for different tasks
3. **Tenant Isolation**: Implemented through metadata filtering and session attributes

### Tenant Structure

The solution supports multiple tenants, with the following example tenants:

1. **ClearPay (FinTech)**: A company that provides payment and transaction reconciliation services for small to mid-sized financial institutions.
2. **MediOps (HealthTech)**: A platform offering EHR (Electronic Health Records) infrastructure and automation tools for medium-sized healthcare providers.

### Data Structure

Each tenant has the following data structure in Amazon Simple Storage Service (Amazon S3):

```
tenant-id/
  ├── logs/
  │   └── microservice-logs.json
  ├── kb/
  │   └── [knowledge-base-documents].md
  ├── resolutions/
  │   └── [resolution-documents].md
  ├── sops/
  │   └── [sop-documents].md
  ├── meeting-notes.txt
  └── [tenant]_Error_Codes.txt
```

### Technical Support Agent

The technical support agent provides the following capabilities:

1. **Knowledge Base Search**: Search the knowledge base for relevant information
2. **Error Code Lookup**: Get details about specific error codes
3. **Log Analysis**: Search logs for specific patterns or time periods
4. **Issue Management**: Create, view, and resolve technical support issues

## Multi-Agent Architecture

The solution uses a multi-agent architecture with the following components:

1. **Orchestrator Agent**: Coordinates the work of specialized agents
2. **Knowledge Base Agent**: Queries the knowledge base for relevant information
3. **Log Agent**: Analyzes logs to identify issues
4. **Code Agent**: Generates code to fix issues

## Tenant Isolation

Tenant isolation is implemented through the following mechanisms:

1. **Amazon S3 Object Metadata**: Each object in Amazon S3 has a `tenant_id` metadata field
2. **Session Attributes**: The tenant ID is passed as a session attribute to agents
3. **Amazon DynamoDB Partitioning**: Data in Amazon DynamoDB is partitioned by tenant ID
4. **AWS Identity and Access Management (IAM) Policies**: IAM policies restrict access to tenant-specific resources

## Knowledge Base

The knowledge base contains the following types of documents:

1. **Error Codes**: Documentation of error codes and their resolutions
2. **SOPs**: Standard Operating Procedures for routine operational activities such as incident response, system maintenance, and data backup procedures
3. **Resolution Documents**: Documentation of past issue resolutions
4. **Knowledge Base Documents**: General knowledge base articles

## Mock Data

The solution includes mock data for the following tenants:

1. **ClearPay (FinTech)**:
   - Error codes related to payment processing
   - SOPs for transaction handling
   - Resolution documents for common payment issues

2. **MediOps (HealthTech)**:
   - Error codes related to EHR systems
   - SOPs for patient data handling
   - Resolution documents for common healthcare IT issues

## Getting Started

To deploy the solution:

1. Run the AWS Cloud Development Kit (AWS CDK) deployment script
2. Provision tenants using the tenant provisioning script
3. Generate mock data for each tenant

## Workshop Labs

The workshop consists of the following labs:

1. **Lab 1**: Multi-tenant RAG architecture
   - Introduction to multi-tenant RAG
   - Querying the knowledge base with tenant isolation

2. **Lab 2**: Multi-tenant multi-agents architecture
   - Introduction to multi-agent systems
   - Orchestrating multiple agents for multi-step troubleshooting scenarios, such as analyzing logs, querying knowledge bases, and generating resolution recommendations

3. **Lab 3**: Tenant isolation
   - Implementing tenant isolation through metadata filtering
   - Implementing tenant data protection with enhanced security features through IAM policies

4. **Lab 4**: Cost per tenant
   - Tracking and analyzing costs per tenant
   - Implementing cost optimization strategies including resource right-sizing, usage monitoring, and automated scaling policies
