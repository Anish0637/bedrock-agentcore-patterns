"""
Pattern 1 — AI Agent with Bedrock AgentCore Runtime
====================================================
Deploys a Strands-based agent (with custom tools) to AgentCore Runtime.
The BedrockAgentCoreApp wrapper auto-creates /invocations and /ping HTTP
endpoints expected by the runtime.

Usage (local):
    python agent.py

Deploy to AgentCore Runtime:
    python deploy.py
"""

import os
import json
import logging
from datetime import datetime

from dotenv import load_dotenv
from strands import Agent, tool
from strands_tools import calculator
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")

# ── Custom tools ──────────────────────────────────────────────────────────────

@tool
def get_current_time() -> str:
    """Return the current UTC date and time."""
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


@tool
def get_weather(city: str) -> str:
    """Return a mock weather report for the given city.

    Args:
        city: Name of the city to get weather for.
    """
    mock_weather = {
        "seattle": "🌧 Rainy, 12°C",
        "new york": "⛅ Partly cloudy, 22°C",
        "los angeles": "☀️ Sunny, 28°C",
    }
    return mock_weather.get(city.lower(), f"Weather data unavailable for {city}")


@tool
def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units (km/miles, celsius/fahrenheit, kg/lbs).

    Args:
        value: Numeric value to convert.
        from_unit: Source unit (km, miles, c, f, kg, lbs).
        to_unit: Target unit (km, miles, c, f, kg, lbs).
    """
    conversions = {
        ("km", "miles"): lambda v: v * 0.621371,
        ("miles", "km"): lambda v: v * 1.60934,
        ("c", "f"): lambda v: v * 9 / 5 + 32,
        ("f", "c"): lambda v: (v - 32) * 5 / 9,
        ("kg", "lbs"): lambda v: v * 2.20462,
        ("lbs", "kg"): lambda v: v * 0.453592,
    }
    key = (from_unit.lower(), to_unit.lower())
    if key in conversions:
        result = conversions[key](value)
        return f"{value} {from_unit} = {result:.4f} {to_unit}"
    return f"Conversion from {from_unit} to {to_unit} is not supported."


# ── AgentCore App ─────────────────────────────────────────────────────────────

app = BedrockAgentCoreApp()

model = BedrockModel(model_id=MODEL_ID)

agent = Agent(
    model=model,
    tools=[calculator, get_current_time, get_weather, unit_converter],
    system_prompt=(
        "You are a helpful assistant. You can perform calculations, tell the time, "
        "report the weather, and convert units. Always use the appropriate tool when possible."
    ),
)


@app.entrypoint
def invoke(payload: dict) -> str:
    """Main entrypoint — receives JSON payload, returns text response."""
    user_input = payload.get("prompt", "")
    logger.info("Received prompt: %s", user_input)

    if not user_input:
        return json.dumps({"error": "Missing 'prompt' in payload"})

    response = agent(user_input)
    reply = response.message["content"][0]["text"]
    logger.info("Agent reply: %s", reply[:120])
    return reply


# ── Local runner ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run()
