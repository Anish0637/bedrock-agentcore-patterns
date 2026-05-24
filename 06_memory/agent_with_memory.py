"""
Pattern 6 — Agent with Short-Term + Long-Term Memory
======================================================
Wraps a Strands agent with MemoryHookProvider so every conversation
turn is persisted and context is automatically injected on future calls.

Usage:
    python memory_setup.py       # run once to create memory resource
    python agent_with_memory.py  # interactive chat loop
"""

import os
import logging
from datetime import datetime
from dotenv import load_dotenv

from strands import Agent, tool
from strands_tools import http_request
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from memory_hook import MemoryHookProvider

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
MEMORY_ID = os.getenv("MEMORY_ID")
ACTOR_ID = os.getenv("ACTOR_ID", "actor-001")
SESSION_ID = os.getenv("SESSION_ID", "session-001")

app = BedrockAgentCoreApp()

# ── Custom tools ──────────────────────────────────────────────────────────────

@tool
def get_current_date() -> str:
    """Return today's date."""
    return datetime.utcnow().strftime("%Y-%m-%d")


@tool
def search_web(query: str) -> str:
    """Perform a simple web search (stubbed — replace with real search API).

    Args:
        query: Search query string.
    """
    # In production wire this to a real search API (Tavily, Serper, etc.)
    return (
        f"[Stubbed search result for '{query}']: "
        "Please connect a real search provider for live results."
    )


# ── Agent factory ─────────────────────────────────────────────────────────────

def build_agent() -> Agent:
    if not MEMORY_ID:
        raise ValueError("MEMORY_ID env var is not set. Run memory_setup.py first.")

    memory_client = MemoryClient(region_name=REGION)
    hook = MemoryHookProvider(memory_client=memory_client, memory_id=MEMORY_ID, k_turns=5)

    return Agent(
        name="MemoryPersonalAssistant",
        model=MODEL_ID,
        system_prompt=(
            f"You are a helpful personal assistant. Today is {datetime.utcnow().strftime('%Y-%m-%d')}.\n"
            "You remember details from previous conversations and personalise your responses accordingly.\n"
            "Be concise, friendly, and proactive."
        ),
        tools=[get_current_date, search_web],
        hooks=[hook],
        state={"actor_id": ACTOR_ID, "session_id": SESSION_ID},
    )


# ── AgentCore entrypoint ──────────────────────────────────────────────────────

@app.entrypoint
def invoke(payload: dict) -> str:
    agent = build_agent()
    user_input = payload.get("prompt", "")
    response = agent(user_input)
    return response.message["content"][0]["text"]


# ── Local interactive loop ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🤖 Memory-enabled Personal Assistant (type 'quit' to exit)\n")
    agent = build_agent()

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        if not user_input:
            continue
        response = agent(user_input)
        print(f"Agent: {response.message['content'][0]['text']}\n")
