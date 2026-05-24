"""
Pattern 4 — Session Management
================================
Demonstrates how to use runtimeSessionId to maintain conversational context
across multiple invocations of the same agent, and how to stop a session.

Usage:
    export AGENT_ARN="arn:aws:bedrock-agentcore:..."
    python session_demo.py
"""

import os
import json
import time
import logging
import boto3
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
AGENT_ARN = os.getenv("AGENT_ARN")


def invoke(client, agent_arn: str, session_id: str, prompt: str) -> str:
    """Send a prompt to the agent within a specific session."""
    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt}).encode(),
    )
    body = response["body"].read().decode()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def stop_session(client, agent_arn: str, session_id: str):
    """Terminate an active session to free resources."""
    try:
        client.stop_runtime_session(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=session_id,
        )
        logger.info("Session %s terminated.", session_id)
    except client.exceptions.ResourceNotFoundException:
        logger.warning("Session %s not found or already terminated.", session_id)
    except Exception as exc:
        logger.error("Error stopping session: %s", exc)


def demo_single_session(client, agent_arn: str):
    """Show that the agent remembers context within the same session."""
    session_id = f"user-demo-{uuid4().hex[:8]}-conversation-{uuid4().hex[:8]}"
    print(f"\n{'='*60}")
    print(f" Single-Session Context Demo")
    print(f" Session ID: {session_id}")
    print(f"{'='*60}")

    turns = [
        "My name is Alice and I'm a software engineer.",
        "What did I just tell you about myself?",
        "What career do I have?",
    ]

    for prompt in turns:
        print(f"\n  👤 User  : {prompt}")
        reply = invoke(client, agent_arn, session_id, prompt)
        print(f"  🤖 Agent : {reply}")
        time.sleep(1)

    stop_session(client, agent_arn, session_id)


def demo_isolated_sessions(client, agent_arn: str):
    """Show that two sessions are completely isolated from each other."""
    session_a = f"user-alice-{uuid4().hex[:8]}-conversation-{uuid4().hex[:8]}"
    session_b = f"user-bob-{uuid4().hex[:8]}-conversation-{uuid4().hex[:8]}"

    print(f"\n{'='*60}")
    print(f" Session Isolation Demo")
    print(f" Session A (Alice): {session_a}")
    print(f" Session B (Bob)  : {session_b}")
    print(f"{'='*60}")

    # Alice introduces herself
    print("\n  [Session A] 👤 Alice: My favourite colour is blue.")
    reply_a = invoke(client, agent_arn, session_a, "My favourite colour is blue.")
    print(f"  [Session A] 🤖 Agent: {reply_a}")

    # Bob asks in his own isolated session — should not know Alice's preference
    print("\n  [Session B] 👤 Bob : What is my favourite colour?")
    reply_b = invoke(client, agent_arn, session_b, "What is my favourite colour?")
    print(f"  [Session B] 🤖 Agent: {reply_b}")

    for sid in (session_a, session_b):
        stop_session(client, agent_arn, sid)


if __name__ == "__main__":
    if not AGENT_ARN:
        print("⚠️  AGENT_ARN is not set. Deploy an agent first (pattern 01).")
        print("   export AGENT_ARN=arn:aws:bedrock-agentcore:...:runtime/my-agent")
    else:
        bedrock_client = boto3.client("bedrock-agentcore", region_name=REGION)
        demo_single_session(bedrock_client, AGENT_ARN)
        demo_isolated_sessions(bedrock_client, AGENT_ARN)
