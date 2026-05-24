"""
Pattern 1 — Deploy AI Agent to AgentCore Runtime
"""

import os
import json
import boto3
import logging
from dotenv import load_dotenv
from bedrock_agentcore_control_plane import BedrockAgentCoreControlPlane

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")

cp = BedrockAgentCoreControlPlane(region_name=REGION)


def deploy():
    logger.info("Deploying AI Agent to AgentCore Runtime …")

    # Package and deploy — SDK handles Docker build, ECR push, and runtime creation
    response = cp.create_agent_runtime(
        name="bedrock-agentcore-ai-agent",
        description="Pattern 1: AI Agent with custom tools",
        # Points to the directory containing agent.py
        source_directory=os.path.dirname(__file__),
        entrypoint="agent:app",
        execution_role_arn=f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentCoreExecutionRole",
        environment_variables={
            "MODEL_ID": MODEL_ID,
            "AWS_DEFAULT_REGION": REGION,
        },
    )

    agent_arn = response["agentRuntimeArn"]
    logger.info("Agent deployed successfully. ARN: %s", agent_arn)

    # Smoke test — invoke the deployed agent
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    test_response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId="deploy-smoke-test-session-00001",
        payload=json.dumps({"prompt": "What is 42 * 7?"}).encode(),
    )
    body = test_response["body"].read().decode()
    logger.info("Smoke test response: %s", body)

    print("\n✅ Deployment complete!")
    print(f"   ARN : {agent_arn}")
    print(f"   Test: {body}")
    return agent_arn


if __name__ == "__main__":
    deploy()
