# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import time
import json
import logging
from typing import Any, Dict, List, Optional

import boto3
from sql_modifier import append_tenant_filter

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment configuration
REGION = os.getenv("AWS_REGION", "us-east-1")
ATHENA_DB = os.getenv("ATHENA_DATABASE", "saas_logs_db")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
ATHENA_OUTPUT = os.getenv("ATHENA_OUTPUT", "s3://your-athena-query-output/")

# LAB 2: Uncomment for ABAC
#ABAC_ROLE_ARN = os.getenv("ABAC_ROLE_ARN")

def _wait(qid: str, athena_client, timeout_s: int = 180):
    start = time.time()
    while time.time() - start < timeout_s:
        resp = athena_client.get_query_execution(QueryExecutionId=qid)
        state = resp["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if state != "SUCCEEDED":
                reason = resp["QueryExecution"]["Status"].get("StateChangeReason", "")
                raise RuntimeError(f"Athena ended {state}: {reason}")
            return
        time.sleep(1)
    raise TimeoutError("Athena polling timeout")


def _fetch(qid: str, athena_client) -> List[Dict[str, Any]]:
    paginator = athena_client.get_paginator("get_query_results")
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


def _exec(sql: str, athena_client, database: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "QueryString": sql,
        "WorkGroup": ATHENA_WORKGROUP,
    }
    # Provide output location unless relying on enforced workgroup settings
    if ATHENA_OUTPUT:
        params["ResultConfiguration"] = {"OutputLocation": ATHENA_OUTPUT}
    if database:
        params["QueryExecutionContext"] = {"Database": database}

    resp = athena_client.start_query_execution(**params)
    qid = resp["QueryExecutionId"]
    _wait(qid, athena_client)
    return _fetch(qid, athena_client)



def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Expected payload:
      {"tenant_id":"TENANT123","sql":"SELECT ..."}
    """
    try:
        # TODO: LAB 2 Comment out to introduce a bug
        tenant_id = event.get("tenant_id")

        # TODO: LAB 2 Uncomment to introduce a bug
        #tenant_id = "{HARDCODED TENANT ID}"

        user_sql = event.get("query", "")
        if not user_sql:
            return {"status": "error", "message": "query required"}
        
        sql = append_tenant_filter(user_sql, tenant_id)
        logger.info(json.dumps({"tenant_id": event.get('tenant_id'), "sql": sql}))

        # LAB 2: Uncomment block below and comment out the line after it
        # sts = boto3.client("sts", region_name=REGION)
        # response = sts.assume_role(
        #     RoleArn=ABAC_ROLE_ARN,
        #     RoleSessionName=f"tenant-{event.get('tenant_id')}-session",
        #     Tags=[{'Key': 'tenant_id', 'Value': event.get('tenant_id')}]
        # )
        # creds = response['Credentials']
        # athena_client = boto3.client(
        #     "athena", region_name=REGION,
        #     aws_access_key_id=creds['AccessKeyId'],
        #     aws_secret_access_key=creds['SecretAccessKey'],
        #     aws_session_token=creds['SessionToken']
        # )
        # LAB 2: Comment this line
        athena_client = boto3.client("athena", region_name=REGION)

        db = event.get("database") or ATHENA_DB
        rows = _exec(sql, athena_client, database=db)

        for row in rows:
            logger.info(json.dumps({"tenant_id": event.get('tenant_id'), "row": row}))        

        return {
            "status": "success",
            "tenant_id": tenant_id,
            "query": sql,
            "database": db,
            "rows": rows,
        }
    except Exception as e:
        logger.exception("Athena query failed")
        return {"status": "error", "message": str(e)}
