"""
Pattern 3 — A2A Server on AgentCore Runtime
============================================
Implements a Strands-based calculator agent wrapped in an A2A server,
then exposes it via FastAPI at 0.0.0.0:9000/.

Usage (local):
    python a2a_server.py

Deploy to AgentCore Runtime:
    python deploy.py

Invoke:
    python a2a_client.py
"""

import os
import logging
import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

from strands import Agent
from strands_tools.calculator import calculator
from strands.multiagent.a2a import A2AServer

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

# AgentCore Runtime sets AGENTCORE_RUNTIME_URL at deploy time.
# For local testing fall back to the loopback address.
RUNTIME_URL = os.environ.get("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")

HOST, PORT = "0.0.0.0", 9000

# ── Agent ─────────────────────────────────────────────────────────────────────

strands_agent = Agent(
    name="Calculator Agent",
    description=(
        "A calculator agent that can perform basic arithmetic operations: "
        "addition, subtraction, multiplication, division, and more."
    ),
    model=MODEL_ID,
    tools=[calculator],
    callback_handler=None,
    system_prompt=(
        "You are a precise calculator assistant. "
        "Always use the calculator tool to perform arithmetic operations. "
        "Return only the numeric result with a brief explanation."
    ),
)

# ── A2A Server ────────────────────────────────────────────────────────────────

a2a_server = A2AServer(
    agent=strands_agent,
    http_url=RUNTIME_URL,
    serve_at_root=True,   # Serves locally at / regardless of remote URL path
)

app = FastAPI(title="AgentCore A2A Calculator Server")


@app.get("/ping")
def ping():
    """Health check endpoint required by AgentCore Runtime."""
    return {"status": "Healthy"}


@app.get("/health")
def health():
    return {"status": "ok", "agent": "Calculator Agent"}


# Mount A2A routes at root
app.mount("/", a2a_server.to_fastapi_app())

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting A2A server on %s:%d", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT)
