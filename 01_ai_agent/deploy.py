"""
Pattern 1 — Deploy AI Agent to AgentCore Runtime
"""
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
from infra.deploy_helper import deploy_pattern

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

PATTERN_DIR  = os.path.dirname(os.path.abspath(__file__))
RUNTIME_NAME = "BedrockAgentCore_AIAgent"
ENTRY_SCRIPT = "agent.py"

if __name__ == "__main__":
    arn = deploy_pattern(PATTERN_DIR, RUNTIME_NAME, ENTRY_SCRIPT)
    print("\n✅ Pattern 01 deployed!")
    print(f"   ARN: {arn}")
    if arn:
        print(f"\nAdd to .env: AGENT_ARN={arn}")
