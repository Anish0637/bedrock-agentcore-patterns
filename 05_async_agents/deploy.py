"""
Pattern 5 — Deploy Async Agent to AgentCore Runtime
"""
import os
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
    logger.info("Deploying Async Agent to AgentCore Runtime …")

    response = cp.create_agent_runtime(
        name="bedrock-agentcore-async-agent",
        description="Pattern 5: Long-running async agent with background task tracking",
        source_directory=os.path.dirname(__file__),
        entrypoint="async_agent:app",
        execution_role_arn=f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentCoreExecutionRole",
        environment_variables={"AWS_DEFAULT_REGION": REGION},
    )

    runtime_arn = response["agentRuntimeArn"]
    logger.info("Async Agent deployed. ARN: %s", runtime_arn)
    print(f"\n✅ Async Agent deployed!\n   ARN: {runtime_arn}")
    print(f"   Add to .env: AGENT_ARN={runtime_arn}")
    return runtime_arn


if __name__ == "__main__":
    deploy()
