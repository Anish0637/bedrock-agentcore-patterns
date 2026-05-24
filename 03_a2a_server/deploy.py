"""
Pattern 3 — Deploy A2A Server to AgentCore Runtime
"""

import os
import json
import boto3
import logging
from urllib.parse import quote
from uuid import uuid4
from dotenv import load_dotenv
from bedrock_agentcore_control_plane import BedrockAgentCoreControlPlane

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")


def fetch_agent_card(agent_arn: str, bearer_token: str) -> dict:
    """Retrieve the A2A Agent Card from the deployed runtime."""
    escaped_arn = quote(agent_arn, safe="")
    url = (
        f"https://bedrock-agentcore.{REGION}.amazonaws.com"
        f"/runtimes/{escaped_arn}/invocations/.well-known/agent-card.json"
    )
    import requests
    session_id = str(uuid4())
    headers = {
        "Accept": "*/*",
        "Authorization": f"Bearer {bearer_token}",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def deploy():
    cp = BedrockAgentCoreControlPlane(region_name=REGION)
    logger.info("Deploying A2A Server to AgentCore Runtime …")

    response = cp.create_agent_runtime(
        name="bedrock-agentcore-a2a-server",
        description="Pattern 3: Calculator agent exposed via A2A protocol",
        source_directory=os.path.dirname(__file__),
        entrypoint="a2a_server:app",
        protocol="A2A",
        port=9000,
        execution_role_arn=f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentCoreExecutionRole",
        environment_variables={
            "AWS_DEFAULT_REGION": REGION,
        },
    )

    runtime_arn = response["agentRuntimeArn"]
    runtime_url = (
        f"https://bedrock-agentcore.{REGION}.amazonaws.com"
        f"/runtimes/{quote(runtime_arn, safe='')}/invocations/"
    )

    logger.info("A2A Server deployed. ARN: %s", runtime_arn)

    print("\n✅ A2A Server deployed!")
    print(f"   ARN        : {runtime_arn}")
    print(f"   Runtime URL: {runtime_url}")
    print("\nNext steps:")
    print("  export AGENTCORE_RUNTIME_URL=" + repr(runtime_url))
    print("  export BEARER_TOKEN=<your-token>")
    print("  python a2a_client.py")
    return runtime_arn


if __name__ == "__main__":
    deploy()
