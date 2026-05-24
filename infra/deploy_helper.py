"""
Shared deployment helper for AgentCore Runtime creation.

Uses boto3 bedrock-agentcore-control with codeConfiguration (S3-based),
so no Docker build or ECR push is needed.
"""

import os
import io
import time
import zipfile
import logging
import boto3
from pathlib import Path

logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def _account_id() -> str:
    return os.getenv("AWS_ACCOUNT_ID", "")


def _bucket_name() -> str:
    return f"bedrock-agentcore-patterns-{_account_id()}"


def _exec_role() -> str:
    return f"arn:aws:iam::{_account_id()}:role/BedrockAgentCoreExecutionRole"


# ── S3 helpers ────────────────────────────────────────────────────────────────

def ensure_bucket(s3_client) -> str:
    """Create S3 bucket if it doesn't exist. Returns bucket name."""
    bucket = _bucket_name()
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    try:
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=bucket)
        else:
            s3_client.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        logger.info("S3 bucket created: %s", bucket)
    except s3_client.exceptions.BucketAlreadyOwnedByYou:
        logger.info("S3 bucket already exists: %s", bucket)
    except s3_client.exceptions.BucketAlreadyExists:
        logger.info("S3 bucket already exists: %s", bucket)
    return bucket


def zip_pattern_directory(pattern_dir: str, extra_files: dict | None = None) -> bytes:
    """
    Zip all .py files from pattern_dir plus any extra_files dict
    { 'filename_in_zip': 'content_string' }.
    Also includes the root requirements.txt if no requirements.txt is in the pattern dir.
    """
    buf = io.BytesIO()
    pattern_path = Path(pattern_dir)
    root_path = pattern_path.parent

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add all .py files from the pattern directory (flat in zip root)
        for py_file in sorted(pattern_path.glob("*.py")):
            zf.write(py_file, py_file.name)
            logger.debug("  zipped: %s", py_file.name)

        # Include requirements.txt
        req_file = pattern_path / "requirements.txt"
        if not req_file.exists():
            req_file = root_path / "requirements.txt"
        if req_file.exists():
            zf.write(req_file, "requirements.txt")
            logger.debug("  zipped: requirements.txt")

        # Extra files (e.g. generated configs)
        if extra_files:
            for fname, content in extra_files.items():
                zf.writestr(fname, content)

    return buf.getvalue()


def upload_code(s3_client, pattern_dir: str, s3_key: str) -> str:
    """Zip and upload code to S3. Returns s3_key."""
    ensure_bucket(s3_client)
    bucket = _bucket_name()
    zip_bytes = zip_pattern_directory(pattern_dir)
    s3_client.put_object(Bucket=bucket, Key=s3_key, Body=zip_bytes)
    logger.info("Code uploaded: s3://%s/%s (%d bytes)", bucket, s3_key, len(zip_bytes))
    return s3_key


# ── Runtime helpers ───────────────────────────────────────────────────────────

def create_or_update_agent_runtime(
    cp_client,
    runtime_name: str,
    s3_key: str,
    entry_point: list[str],
    env_vars: dict | None = None,
) -> dict:
    """
    Create (or recreate) an AgentCore Runtime using codeConfiguration.
    Returns the full create_agent_runtime response.
    """
    env_vars = env_vars or {}

    # Check if runtime already exists
    try:
        existing = cp_client.list_agent_runtimes()
        for rt in existing.get("agentRuntimes", []):
            if rt["agentRuntimeName"] == runtime_name:
                rt_id = rt["agentRuntimeId"]
                logger.info("Runtime '%s' already exists (id=%s) — skipping create", runtime_name, rt_id)
                return rt
    except Exception:
        pass

    bucket = _bucket_name()
    resp = cp_client.create_agent_runtime(
        agentRuntimeName=runtime_name,
        description=f"AgentCore pattern runtime: {runtime_name}",
        roleArn=_exec_role(),
        agentRuntimeArtifact={
            "codeConfiguration": {
                "code": {
                    "s3": {
                        "bucket": bucket,
                        "prefix": s3_key,
                    }
                },
                "runtime": "PYTHON_3_12",
                "entryPoint": entry_point,
            }
        },
        environmentVariables=env_vars,
        networkConfiguration={"networkMode": "PUBLIC"},
    )
    logger.info("Runtime created: %s", resp.get("agentRuntimeArn", resp))
    return resp


def wait_for_runtime_active(cp_client, runtime_id: str, timeout: int = 300) -> str:
    """Poll until runtime status is READY (the live/active state). Returns status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = cp_client.get_agent_runtime(agentRuntimeId=runtime_id)
        status = resp.get("status", "UNKNOWN")
        if status == "READY":
            logger.info("Runtime %s is READY", runtime_id)
            return status
        if status in ("CREATE_FAILED", "UPDATE_FAILED", "DELETING"):
            raise RuntimeError(f"Runtime reached terminal error status: {status}")
        logger.info("Runtime %s status: %s — waiting…", runtime_id, status)
        time.sleep(15)
    raise TimeoutError(f"Runtime {runtime_id} did not become READY within {timeout}s")


# ── Convenience builder ───────────────────────────────────────────────────────

def deploy_pattern(
    pattern_dir: str,
    runtime_name: str,
    entry_script: str,
    extra_env: dict | None = None,
) -> str:
    """
    Full deploy: zip → S3 → create runtime → wait ACTIVE → return ARN.
    """
    s3 = boto3.client("s3", region_name=REGION)
    cp = boto3.client("bedrock-agentcore-control", region_name=REGION)

    model_id = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    memory_id = os.getenv("MEMORY_ID", "")

    env_vars = {
        "MODEL_ID": model_id,
        "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        "AWS_ACCOUNT_ID": _account_id(),
    }
    if memory_id:
        env_vars["MEMORY_ID"] = memory_id
    if extra_env:
        env_vars.update(extra_env)

    s3_key = f"patterns/{runtime_name}/code.zip"
    upload_code(s3, pattern_dir, s3_key)

    resp = create_or_update_agent_runtime(
        cp,
        runtime_name=runtime_name,
        s3_key=s3_key,
        entry_point=[entry_script],
        env_vars=env_vars,
    )

    arn = resp.get("agentRuntimeArn", "")
    rt_id = resp.get("agentRuntimeId", "")
    if rt_id and resp.get("status") != "READY":
        wait_for_runtime_active(cp, rt_id)

    return arn
