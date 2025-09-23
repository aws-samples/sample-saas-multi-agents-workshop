# Example Payload
# {
#   "tenant_id": "clearpay",
#   "query": "What is the solution for Database authentication fails after automated credential rotation"
# }


# lambda_kb_tool/handler.py
import os, json, re, boto3
from typing import Any, Dict, List

REGION = os.getenv("AWS_REGION", "us-east-1")
KB_ID = os.getenv("BEDROCK_KB_ID")
TOP_K = int(os.getenv("KB_TOP_K", "8"))

bedrock_rt = boto3.client("bedrock-agent-runtime", region_name=REGION)

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Expected payload: {"tenant_id":"...", "query":"...", "top_k":8}
    tenant_id = event.get("tenant_id", "")
    query = event.get("query", "").strip()
    if not query:
        return {"status":"error","message":"query required"}
    top_k = int(event.get("top_k", TOP_K))

    _tenant_filter = {
        "equals": {
            "key": "tenant_id",
            "value": tenant_id
        }
    }

    resp = bedrock_rt.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": top_k,
                "filter": _tenant_filter
                }
        },
    )
    results = []
    for r in resp.get("retrievalResults", []):
        content = r.get("content", {}).get("text", "")
        score = r.get("score", 0)
        source = r.get("location", {}).get("s3Location", {}).get("uri", "Unknown")
        
        results.append({
            "content": content,
            "score": score,
            "source": source
        })
    
    return {
        "status": "success", 
        "tenant_id": tenant_id, 
        "results": results,
        "result_count": len(results)
    }