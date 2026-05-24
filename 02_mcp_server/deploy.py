"""
Pattern 2 — Deploy MCP Server to AgentCore Runtime
"""

import os
import boto3
import logging
from dotenv import load_dotenv
from bedrock_agentcore_control_plane import BedrockAgentCoreControlPlane

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")


def deploy():
    cp = BedrockAgentCoreControlPlane(region_name=REGION)
    logger.info("Deploying MCP Server to AgentCore Runtime …")

    response = cp.create_agent_runtime(
        name="bedrock-agentcore-mcp-server",
        description="Pattern 2: FastMCP server with math and utility tools",
        source_directory=os.path.dirname(__file__),
        entrypoint="mcp_server:mcp",
        protocol="MCP",           # Tell AgentCore this is an MCP server
        execution_role_arn=f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentCoreExecutionRole",
        environment_variables={"AWS_DEFAULT_REGION": REGION},
    )

    runtime_arn = response["agentRuntimeArn"]
    logger.info("MCP Server deployed. ARN: %s", runtime_arn)

    print("\n✅ MCP Server deployed!")
    print(f"   ARN: {runtime_arn}")
    print("   Invoke via: POST /mcp with MCP JSON-RPC messages")
    return runtime_arn


if __name__ == "__main__":
    deploy()
