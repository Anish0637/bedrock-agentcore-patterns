"""
Pattern 6 — Memory Integration (Short-Term + Long-Term)
========================================================
Creates an AgentCore Memory resource with SEMANTIC and USER_PREFERENCE
strategies, then runs an agent that uses a MemoryHookProvider to:
  • Load the last 5 conversation turns on agent init (short-term)
  • Retrieve relevant long-term memories on each user message
  • Persist every conversation turn

Usage:
    python memory_setup.py   # Creates the memory resource (run once)
    python agent_with_memory.py
"""

import os
import json
import logging
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
MEMORY_NAME = "AgentCorePatternMemory"


def create_memory() -> str:
    client = MemoryClient(region_name=REGION)

    strategies = [
        {
            StrategyType.SEMANTIC.value: {
                "name": "FactualKnowledge",
                "description": "Extracts and stores key facts from conversations",
                "namespaces": ["/knowledge/{actorId}/facts"],
            }
        },
        {
            StrategyType.USER_PREFERENCE.value: {
                "name": "UserPreferences",
                "description": "Tracks user preferences, choices, and personal style",
                "namespaces": ["/knowledge/{actorId}/preferences"],
            }
        },
        {
            StrategyType.SUMMARY.value: {
                "name": "SessionSummary",
                "description": "Creates rolling summaries of each conversation session",
                "namespaces": ["/knowledge/{actorId}/sessions/{sessionId}/summary"],
            }
        },
    ]

    try:
        memory = client.create_memory_and_wait(
            name=MEMORY_NAME,
            strategies=strategies,
            description="AgentCore pattern demo memory with semantic + preference + summary",
            event_expiry_days=90,
        )
        memory_id = memory["id"]
        logger.info("Memory created: %s", memory_id)
        return memory_id

    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "ValidationException" and "already exists" in str(exc):
            existing = client.list_memories()
            memory_id = next(
                (m["id"] for m in existing if m.get("name") == MEMORY_NAME), None
            )
            if memory_id:
                logger.info("Memory already exists: %s", memory_id)
                return memory_id
        raise

    except Exception as exc:
        logger.error("Failed to create memory: %s", exc)
        raise


if __name__ == "__main__":
    memory_id = create_memory()
    print(f"\n✅ Memory ready: {memory_id}")
    print(f"   Add to .env: MEMORY_ID={memory_id}")
