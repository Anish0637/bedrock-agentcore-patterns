"""
Pattern 10 — Code Interpreter
==============================
Demonstrates using AgentCore Code Interpreter to let the agent write and
execute Python code inside a secure sandbox for data analysis tasks.

Usage:
    python code_interpreter_demo.py
"""

import os
import logging
from dotenv import load_dotenv
from strands import Agent
from strands_tools.code_interpreter import AgentCoreCodeInterpreter

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")

SYSTEM_PROMPT = """You are a data analyst assistant powered by a code execution sandbox.
When solving problems:
1. Write clean, well-commented Python code.
2. Execute the code to verify results.
3. Explain the output clearly.
4. Always validate answers through actual code execution."""


def build_agent() -> Agent:
    code_tool = AgentCoreCodeInterpreter(region=REGION)
    return Agent(
        model=MODEL_ID,
        tools=[code_tool.code_interpreter],
        system_prompt=SYSTEM_PROMPT,
    )


DEMO_TASKS = [
    # Fibonacci sequence
    "Calculate and display the first 15 Fibonacci numbers.",

    # Statistical analysis
    (
        "Given this dataset: [23, 45, 12, 67, 34, 89, 11, 56, 78, 90, 23, 45, 67, 34, 12], "
        "calculate the mean, median, standard deviation, and identify outliers using IQR method."
    ),

    # Sorting algorithms comparison
    (
        "Implement bubble sort and merge sort. "
        "Time both on a list of 1000 random integers and compare their performance."
    ),

    # Prime numbers
    "Find all prime numbers up to 100 using the Sieve of Eratosthenes and count them.",

    # Text analysis
    (
        "Analyse this text: 'The quick brown fox jumps over the lazy dog. "
        "The dog was not amused. The fox ran away quickly.' "
        "Count word frequency and find the most common words."
    ),
]


if __name__ == "__main__":
    print("💻 AgentCore Code Interpreter Demo\n")
    agent = build_agent()

    for i, task in enumerate(DEMO_TASKS, 1):
        print(f"\n{'='*60}")
        print(f" Task {i}: {task[:80]}{'…' if len(task) > 80 else ''}")
        print(f"{'='*60}")
        response = agent(task)
        print(f"\n{response.message['content'][0]['text']}")
