"""
Pattern 3 — A2A Client
=======================
Fetches the Agent Card and sends messages to the deployed A2A server.

Usage:
    export AGENTCORE_RUNTIME_URL="https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<ARN>/invocations/"
    export BEARER_TOKEN="<your-bearer-token>"
    python a2a_client.py
"""

import asyncio
import logging
import os
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import Message, Part, Role, TextPart
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300  # 5 minutes


def build_message(text: str, role: Role = Role.user) -> Message:
    return Message(
        kind="message",
        role=role,
        parts=[Part(TextPart(kind="text", text=text))],
        message_id=uuid4().hex,
    )


async def send_message(text: str):
    runtime_url = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
    bearer_token = os.environ.get("BEARER_TOKEN", "")
    session_id = str(uuid4())

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }

    logger.info("Session ID: %s", session_id)
    logger.info("Sending: %s", text)

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as http:
        resolver = A2ACardResolver(httpx_client=http, base_url=runtime_url)
        agent_card = await resolver.get_agent_card()
        logger.info("Agent card fetched: %s", agent_card.name)

        config = ClientConfig(httpx_client=http, streaming=False)
        client = ClientFactory(config).create(agent_card)

        async for event in client.send_message(build_message(text)):
            if isinstance(event, Message):
                for part in event.parts:
                    if hasattr(part.root, "text"):
                        print(f"\n🤖 Response: {part.root.text}")
            elif isinstance(event, tuple) and len(event) == 2:
                task, update = event
                logger.info("Task: %s", task.model_dump_json(exclude_none=True, indent=2))


SAMPLE_QUESTIONS = [
    "What is 101 * 11?",
    "Calculate 2 to the power of 10.",
    "What is the square root of 144?",
    "Divide 1000 by 7 and round to 4 decimal places.",
]

if __name__ == "__main__":
    for question in SAMPLE_QUESTIONS:
        print(f"\n📤 Question: {question}")
        asyncio.run(send_message(question))
