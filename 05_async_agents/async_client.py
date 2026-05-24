"""
Pattern 5 — Async Agent Deploy + Poll Client
"""

import os
import json
import time
import boto3
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
AGENT_ARN = os.getenv("AGENT_ARN")


def invoke(client, agent_arn: str, session_id: str, payload: dict) -> dict:
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=json.dumps(payload).encode(),
    )
    body = resp["body"].read().decode()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


def poll_task(client, agent_arn: str, session_id: str, task_id: str, interval: int = 5):
    """Poll every `interval` seconds until the task completes."""
    print(f"\n⏳ Polling task {task_id} …")
    while True:
        result = invoke(client, agent_arn, session_id, {"action": "status", "task_id": task_id})
        status = result.get("status", "unknown")
        progress = result.get("progress", "?")
        stage = result.get("current_stage", "")
        print(f"   [{status}] {progress}% — {stage}")

        if status == "completed":
            print(f"\n✅ Task complete: {result.get('result')}")
            break
        if status == "failed":
            print(f"\n❌ Task failed: {result}")
            break

        time.sleep(interval)


if __name__ == "__main__":
    if not AGENT_ARN:
        print("⚠️  AGENT_ARN is not set.")
    else:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        session_id = f"async-demo-session-{'x'*16}"

        # Start the long-running task
        ack = invoke(client, AGENT_ARN, session_id, {
            "action": "start",
            "task_id": "analysis-001",
            "data_points": 5000,
        })
        print(f"📨 Acknowledged: {ack}")

        # Poll until done
        poll_task(client, AGENT_ARN, session_id, ack.get("task_id", "analysis-001"))
