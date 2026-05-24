"""
Pattern 3 — Deploy A2A Server to AgentCore Runtime
"""
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
from infra.deploy_helper import deploy_pattern

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

REGION       = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
PATTERN_DIR  = os.path.dirname(os.path.abspath(__file__))
RUNTIME_NAME = "BedrockAgentCore_A2AServer"
ENTRY_SCRIPT = "a2a_server.py"

if __name__ == "__main__":
    arn = deploy_pattern(PATTERN_DIR, RUNTIME_NAME, ENTRY_SCRIPT)
    print("\n✅ Pattern 03 A2A Server deployed!")
    print(f"   ARN: {arn}")
    if arn:
        runtime_url = (
            f"https://bedrock-agentcore.{REGION}.amazonaws.com"
            f"/runtimes/{arn}/invocations/"
        )
        print(f"   Runtime URL: {runtime_url}")
        print(f"\nAdd to .env: AGENTCORE_RUNTIME_URL={runtime_url}")
