"""
Pattern 9 — Gateway Client: Agent using Gateway MCP tools
==========================================================
Creates a Strands agent that discovers and calls tools exposed through the
AgentCore Gateway via MCP Streamable-HTTP transport.

Usage:
    export GATEWAY_ID=<gateway-id>
    python gateway_client.py
"""

import os
import logging
from dotenv import load_dotenv
from strands import Agent
from strands.tools.mcp import MCPClient
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import boto3

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
GATEWAY_ID = os.getenv("GATEWAY_ID")
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")


def get_gateway_endpoint(gateway_id: str) -> str:
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    resp = client.get_gateway(gatewayIdentifier=gateway_id)
    return resp["gatewayEndpoint"]


def run_agent_with_gateway_tools(endpoint: str):
    mcp_url = f"{endpoint}/mcp"
    logger.info("Connecting to Gateway MCP endpoint: %s", mcp_url)

    with MCPClient(lambda: streamablehttp_client(mcp_url)) as mcp_client:
        tools = mcp_client.list_tools_sync()
        logger.info("Discovered %d tools via Gateway", len(tools))
        for t in tools:
            logger.info("  • %s: %s", t.name, t.description)

        agent = Agent(
            model=MODEL_ID,
            tools=tools,
            system_prompt=(
                "You are an order management assistant. "
                "Use the available tools to help users check order status, "
                "update orders, and list orders. Always confirm actions before taking them."
            ),
        )

        questions = [
            "List all pending orders.",
            "Get the details of order ORD-001.",
            "Update order ORD-002 to processing status.",
            "List all delivered orders.",
        ]

        for question in questions:
            print(f"\n📤 {question}")
            response = agent(question)
            print(f"🤖 {response.message['content'][0]['text']}")


if __name__ == "__main__":
    if not GATEWAY_ID:
        print("⚠️  GATEWAY_ID is not set. Run gateway_setup.py first.")
    else:
        endpoint = get_gateway_endpoint(GATEWAY_ID)
        run_agent_with_gateway_tools(endpoint)
