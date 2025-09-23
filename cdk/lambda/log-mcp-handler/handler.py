# {
#   "tenant_id": "clearpay",
#   "sql": "SELECT * FROM tenant_logs where tenant = 'clearpay'"
# }

import os
import time
import json
import logging
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment configuration
REGION = os.getenv("AWS_REGION", "us-east-1")
ATHENA_DB = os.getenv("ATHENA_DATABASE", "saas_logs_db")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
ATHENA_OUTPUT = os.getenv("ATHENA_OUTPUT", "s3://your-athena-query-output/")
# LAB 2: ABAC Role ARN (uncomment when using ABAC Lambda)
# ABAC_ROLE_ARN = os.getenv("ABAC_ROLE_ARN")

# Athena client
athena = boto3.client("athena", region_name=REGION)
# LAB 2: STS client for role assumption (uncomment when using ABAC Lambda)
# sts = boto3.client("sts", region_name=REGION)


def _wait(qid: str, timeout_s: int = 180):
    start = time.time()
    while time.time() - start < timeout_s:
        resp = athena.get_query_execution(QueryExecutionId=qid)
        state = resp["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if state != "SUCCEEDED":
                reason = resp["QueryExecution"]["Status"].get("StateChangeReason", "")
                raise RuntimeError(f"Athena ended {state}: {reason}")
            return
        time.sleep(1)
    raise TimeoutError("Athena polling timeout")


def _fetch(qid: str) -> List[Dict[str, Any]]:
    paginator = athena.get_paginator("get_query_results")
    out: List[Dict[str, Any]] = []
    headers: Optional[List[str]] = None

    for page in paginator.paginate(
        QueryExecutionId=qid,
        PaginationConfig={"PageSize": 1000},
    ):
        rs = page.get("ResultSet", {}) or {}
        meta = rs.get("ResultSetMetadata", {}) or {}
        cols = meta.get("ColumnInfo", []) or []

        if headers is None:
            headers = [(c.get("Label") or c.get("Name") or f"col{i}") for i, c in enumerate(cols)]

        for row in rs.get("Rows", []):
            data = row.get("Data", []) or []
            vals = [d.get("VarCharValue") if isinstance(d, dict) else None for d in data]

            if len(vals) < len(headers):
                vals += [None] * (len(headers) - len(vals))

            if headers and vals[:len(headers)] == headers:
                continue

            out.append(dict(zip(headers, vals)))

    return out


def _exec(sql: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "QueryString": sql,
        "WorkGroup": ATHENA_WORKGROUP,
    }
    # Provide output location unless relying on enforced workgroup settings
    if ATHENA_OUTPUT:
        params["ResultConfiguration"] = {"OutputLocation": ATHENA_OUTPUT}
    if database:
        params["QueryExecutionContext"] = {"Database": database}

    resp = athena.start_query_execution(**params)
    qid = resp["QueryExecutionId"]
    _wait(qid)
    return _fetch(qid)


# LAB 2: ABAC Role Assumption Function (uncomment when using ABAC Lambda)
# def assume_tenant_role(tenant_id: str) -> Dict[str, Any]:
#     """Assume the ABAC role with tenant-specific tags"""
#     try:
#         response = sts.assume_role(
#             RoleArn=ABAC_ROLE_ARN,
#             RoleSessionName=f"tenant-{tenant_id}-session",
#             Tags=[
#                 {
#                     'Key': 'tenant_id',
#                     'Value': tenant_id
#                 }
#             ]
#         )
#         return response['Credentials']
#     except Exception as e:
#         logger.error(f"Failed to assume role for tenant {tenant_id}: {str(e)}")
#         raise

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Expected payload:
      {"tenant_id":"TENANT123","sql":"SELECT ...", "database":"optional_db"}
    """
    try:
        tenant_id = event.get("tenant_id")  # kept for request/response echo, not used in SQL
        sql = event.get("sql", "")
        if not sql:
            return {"status": "error", "message": "sql required"}

        # LAB 2: ABAC Implementation (uncomment when using ABAC Lambda)
        # Assume tenant-specific role for ABAC
        # if tenant_id and ABAC_ROLE_ARN:
        #     credentials = assume_tenant_role(tenant_id)
        #     # Create new Athena client with assumed role credentials
        #     global athena
        #     athena = boto3.client(
        #         "athena",
        #         region_name=REGION,
        #         aws_access_key_id=credentials['AccessKeyId'],
        #         aws_secret_access_key=credentials['SecretAccessKey'],
        #         aws_session_token=credentials['SessionToken']
        #     )

        db = event.get("database") or ATHENA_DB
        rows = _exec(sql, database=db)

        return {
            "status": "success",
            "tenant_id": tenant_id,
            "sql": sql,
            "database": db,
            "rows": rows,
        }
    except Exception as e:
        logger.exception("Athena query failed")
        return {"status": "error", "message": str(e)}
