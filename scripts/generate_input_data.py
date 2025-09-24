# Install and import required packages
import os
import re
import json
import shutil
import uuid
import random
import datetime as dt
from pathlib import Path
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

# Region and Bedrock runtime with timeout configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
config = boto3.session.Config(
    read_timeout=120,
    connect_timeout=60,
    retries={'max_attempts': 3}
)
bedrock_rt = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=config)

# IMPORTANT: For Claude 3.7 Sonnet you must use an inference profile ID or ARN
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")

# Anthropic Messages API version for Bedrock
ANTHROPIC_VERSION = "bedrock-2023-05-31"

# Inference parameters
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "3000"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.25"))
TOP_P = float(os.getenv("TOP_P", "0.9"))
TOP_K = int(os.getenv("TOP_K", "250"))

# Local output root and tenants
DATA_ROOT = Path(os.getenv("DATA_ROOT", "./data"))
TENANTS = ["clearpay", "mediops"]

# Clean slate: delete and recreate tenant folders
if DATA_ROOT.exists():
    shutil.rmtree(DATA_ROOT)
for t in TENANTS:
    (DATA_ROOT / t).mkdir(parents=True, exist_ok=True)

# Run ID, timezone-aware
run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

print(f"Region={AWS_REGION} ModelId={MODEL_ID} OutputRoot={DATA_ROOT.resolve()} RunId={run_id}")

def resolve_sonnet37_profile(region="us-east-1"):
    try:
        import boto3
        bedrock = boto3.client("bedrock", region_name=region, config=config)
        profiles = bedrock.list_inference_profiles()["inferenceProfileSummaries"]
        for p in profiles:
            if p.get("inferenceProfileId","").startswith("us.anthropic.claude-3-7-sonnet-20250219-v1:0"):
                return p["inferenceProfileId"]
        raise RuntimeError("Claude 3.7 Sonnet inference profile not found")
    except Exception as e:
        print(f"Warning: Could not resolve Bedrock profile: {e}")
        return MODEL_ID  # Use default

try:
    MODEL_ID = resolve_sonnet37_profile("us-east-1")
    print(f"Using model: {MODEL_ID}")
except Exception as e:
    print(f"Using default model due to error: {e}")

def invoke_claude_messages(
    prompt_text: str,
    system_prompt: Optional[str] = None,
    temperature: float = TEMPERATURE,
    max_tokens: int = MAX_TOKENS,
    top_p: float = TOP_P,
    top_k: int = TOP_K,
) -> Dict[str, Any]:
    body = {
        "anthropic_version": ANTHROPIC_VERSION,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt_text}]}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
    }
    if system_prompt:
        body["system"] = system_prompt
    try:
        resp = bedrock_rt.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        return json.loads(resp["body"].read())
    except Exception as e:
        raise RuntimeError(f"Bedrock invoke_model failed: {e}")

def extract_text(resp: Dict[str, Any]) -> str:
    # Claude via Bedrock: content is a list of {type: "text", text: "..."}
    if isinstance(resp, dict) and "content" in resp and isinstance(resp["content"], list):
        return "\n".join(seg.get("text", "") for seg in resp["content"] if seg.get("type") == "text")
    # Fallback to dump
    return json.dumps(resp, indent=2)

SYSTEM_PROMPT = (
    "You are a precise technical writer for ops and developers. "
    "Follow the requested output format exactly. Avoid duplicates. "
    "Keep entries concise, realistic, and internally consistent."
)

# KB chunk prompts for smaller model calls
KB_CHUNKS = {
    "clearpay": [
        "Generate 4-5 Python database connection issues for ClearPay FinTech. Format: ## Error\n**Problem:** description\n**Solution:** code example\n**Module:** component",
        "Generate 4-5 Python configuration file problems for ClearPay payment processing. Format: ## Error\n**Problem:** description\n**Solution:** code example\n**Module:** component", 
        "Generate 4-5 Python memory/performance issues for ClearPay transaction services. Format: ## Error\n**Problem:** description\n**Solution:** code example\n**Module:** component",
        "Generate 4-5 Python authentication/security errors for ClearPay API services. Format: ## Error\n**Problem:** description\n**Solution:** code example\n**Module:** component"
    ],
    "mediops": [
        "Generate 4-5 Python database connection issues for MediOps HealthTech. Format: ## Error\n**Problem:** description\n**Solution:** code example\n**Module:** component",
        "Generate 4-5 Python configuration file problems for MediOps patient data processing. Format: ## Error\n**Problem:** description\n**Solution:** code example\n**Module:** component",
        "Generate 4-5 Python memory/performance issues for MediOps EHR integration. Format: ## Error\n**Problem:** description\n**Solution:** code example\n**Module:** component", 
        "Generate 4-5 Python authentication/security errors for MediOps claims handling. Format: ## Error\n**Problem:** description\n**Solution:** code example\n**Module:** component"
    ]
}

def generate_kb_document(tenant: str) -> str:
    """
    Generate KB document using multiple smaller model calls to avoid timeouts.
    """
    company = "ClearPay" if tenant == "clearpay" else "MediOps"
    header = f"# {company} Python Application Troubleshooting Guide\n\n"
    header += f"This document contains solutions for common Python issues in {company} platform.\n\n"
    
    content_parts = []
    chunks = KB_CHUNKS[tenant]
    
    for i, chunk_prompt in enumerate(chunks):
        try:
            print(f"Generating KB chunk {i+1}/{len(chunks)} for {tenant}...")
            resp = invoke_claude_messages(chunk_prompt, system_prompt=SYSTEM_PROMPT, temperature=0.3, max_tokens=1500)
            chunk_content = extract_text(resp)
            content_parts.append(chunk_content)
        except Exception as e:
            print(f"Failed to generate chunk {i+1} for {tenant}: {e}")
            continue
    
    return header + "\n\n".join(content_parts)

def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def synth_logs_for_tenant_athena(
    tenant: str,
    out_dir: Path,
    total_lines_per_file: int = 1000,
    info_ratio: float = 0.78,
    warn_ratio: float = 0.15,
    error_ratio: float = 0.07,
) -> dict:
    """
    Generate simplified Athena-parseable NDJSON application logs.
    Single file: app.log with Python errors that can be analyzed by agents.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    assert abs((info_ratio + warn_ratio + error_ratio) - 1.0) < 1e-6, "Ratios must sum to 1.0"
    env = f"{tenant}-prod"
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)

    def ts_gen():
        t = 0
        while True:
            yield (start + dt.timedelta(seconds=t)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            t += random.randint(1, 3)

    ts_iter = ts_gen()

    def ts():
        return next(ts_iter)

    def rid(prefix="req"):
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    sev_pop = (["INFO"] * int(info_ratio * 100) +
               ["WARN"] * int(warn_ratio * 100) +
               ["ERROR"] * int(error_ratio * 100)) or (["INFO"]*78 + ["WARN"]*15 + ["ERROR"]*7)

    # Tenant-specific Python error scenarios (different from KB)
    if tenant == "clearpay":
        python_errors = [
            dict(error_type="AttributeError", detail="'NoneType' object has no attribute 'encode'", module="crypto_service"),
            dict(error_type="ValueError", detail="invalid literal for int() with base 10: 'abc123'", module="validation_service"),
            dict(error_type="FileNotFoundError", detail="[Errno 2] No such file or directory: '/tmp/batch_txn.csv'", module="batch_processor"),
            dict(error_type="ConnectionError", detail="HTTPSConnectionPool(host='api.bank.com', port=443): Max retries exceeded", module="external_api"),
        ]
        entity_prefix = "txn"
    else:
        python_errors = [
            dict(error_type="AttributeError", detail="'str' object has no attribute 'strftime'", module="date_utils"),
            dict(error_type="ValueError", detail="time data '2024-13-45' does not match format '%Y-%m-%d'", module="timestamp_parser"),
            dict(error_type="FileNotFoundError", detail="[Errno 2] No such file or directory: '/data/patient_records.xml'", module="file_processor"),
            dict(error_type="ConnectionError", detail="HTTPConnectionPool(host='ehr.hospital.com', port=80): Read timed out", module="ehr_client"),
        ]
        entity_prefix = "pat"

    app_logs = []

    def emit(level, event, detail, error_type="", module="", entity_id="", correlation_id=None, request_id=None):
        entry = {
            "timestamp": ts(),
            "level": level,
            "tenant": tenant,
            "environment": env,
            "component": "python-app",
            "correlation_id": correlation_id or rid("corr"),
            "request_id": request_id or rid("req"),
            "event": event,
            "error_type": error_type,
            "module": module,
            "entity_id": entity_id or "",
            "detail": detail,
        }
        app_logs.append(json.dumps(entry, ensure_ascii=False))

    # Normal application logs
    for _ in range(int(total_lines_per_file * 0.8)):
        lvl = random.choice(sev_pop)
        if lvl == "INFO":
            emit("INFO", "request_processed", "Successfully processed request")
        elif lvl == "WARN":
            emit("WARN", "performance_warning", "Request processing took longer than expected")
        else:
            # Random Python error from our scenarios
            error = random.choice(python_errors)
            emit("ERROR", "python_exception", error["detail"], 
                 error_type=error["error_type"], module=error["module"])

    # Specific error incidents that match KB entries
    for error in python_errors:
        corr = rid("corr")
        req = rid("req")
        ent = f"{entity_prefix}_{uuid.uuid4().hex[:10]}"
        
        emit("ERROR", "python_exception", error["detail"],
             error_type=error["error_type"], module=error["module"],
             entity_id=ent, correlation_id=corr, request_id=req)

    # Fill remaining with INFO logs
    while len(app_logs) < total_lines_per_file:
        emit("INFO", "heartbeat", "Application running normally")

    # Write single app.log file
    fpath = out_dir / "app.log"
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(app_logs) + "\n")
    
    return {"app.log": fpath}

# =============================================================================
# MAIN EXECUTION - All function calls at the bottom with comments
# =============================================================================

if __name__ == "__main__":
    # Generate comprehensive knowledge base documents for both tenants
    # These contain detailed Python troubleshooting guides (different errors than in logs)
    print("Generating knowledge bases with chunked calls...")
    clearpay_kb = generate_kb_document("clearpay")
    mediops_kb = generate_kb_document("mediops")
    
    # Write KB files to tenant directories
    write_text(DATA_ROOT / "clearpay" / f"kb_{run_id}.md", clearpay_kb)
    write_text(DATA_ROOT / "mediops" / f"kb_{run_id}.md", mediops_kb)
    
    # Generate simplified application logs with Python errors
    # These logs can be queried by agents to find issues not in KB
    print("Generating application logs...")
    cp_paths = synth_logs_for_tenant_athena("clearpay", DATA_ROOT / "clearpay" / "logs", total_lines_per_file=1200)
    mo_paths = synth_logs_for_tenant_athena("mediops", DATA_ROOT / "mediops" / "logs", total_lines_per_file=1200)
    
    # Display generated files and their sizes
    print("\nGenerated files:")
    for t in TENANTS:
        for p in sorted((DATA_ROOT / t).rglob("*")):
            if p.is_file():
                print(f"  - {p} ({p.stat().st_size} bytes)")