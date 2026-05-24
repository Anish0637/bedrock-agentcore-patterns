"""
Pattern 11 — Browser Tool
==========================
Demonstrates using AgentCore Browser Tool to let the agent interact with
live web pages: navigate, extract content, fill forms, and summarise.

Usage:
    python browser_demo.py
"""

import os
import logging
from dotenv import load_dotenv
from strands import Agent
from strands_tools.browser import AgentCoreBrowser

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")

SYSTEM_PROMPT = """You are a web research assistant with access to a managed browser.
You can navigate websites, read content, and extract structured information.
Always:
1. Navigate to the specified URL first.
2. Read and summarise the page content.
3. Extract specific information as requested.
4. Present findings in a clear, structured format."""


def build_agent() -> Agent:
    browser_tool = AgentCoreBrowser(region=REGION)
    return Agent(
        model=MODEL_ID,
        tools=[browser_tool.browser],
        system_prompt=SYSTEM_PROMPT,
    )


RESEARCH_TASKS = [
    {
        "title": "AWS Bedrock AgentCore Overview",
        "prompt": (
            "Visit https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html "
            "and summarise: (1) what is AgentCore, (2) the main services it provides, "
            "and (3) key use cases."
        ),
    },
    {
        "title": "AWS Bedrock Homepage",
        "prompt": (
            "Visit https://aws.amazon.com/bedrock/ and extract: "
            "(1) the main value proposition, (2) key features listed on the page, "
            "and (3) any pricing information visible."
        ),
    },
    {
        "title": "Python Documentation",
        "prompt": (
            "Visit https://docs.python.org/3/library/asyncio.html and explain "
            "what asyncio is and list the top 5 key concepts covered on the page."
        ),
    },
]


if __name__ == "__main__":
    print("🌐 AgentCore Browser Tool Demo\n")
    agent = build_agent()

    for task in RESEARCH_TASKS:
        print(f"\n{'='*60}")
        print(f" Research: {task['title']}")
        print(f"{'='*60}")
        response = agent(task["prompt"])
        print(f"\n{response.message['content'][0]['text']}")
        print()
