"""
Pattern 2 — MCP Server on AgentCore Runtime
============================================
Hosts a FastMCP server exposing mathematical and utility tools.
AgentCore Runtime expects the MCP endpoint at 0.0.0.0:8000/mcp.

Usage (local):
    python mcp_server.py

Deploy to AgentCore Runtime:
    python deploy.py
"""

import os
import math
import logging
from typing import List

from fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

# AgentCore Runtime requires: host=0.0.0.0, stateless_http=True
mcp = FastMCP(name="AgentCore-MCP-Server", host="0.0.0.0", stateless_http=True)


# ── Mathematical tools ────────────────────────────────────────────────────────

@mcp.tool()
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together.

    Args:
        a: First number.
        b: Second number.
    """
    result = a + b
    logger.info("add_numbers(%s, %s) = %s", a, b, result)
    return result


@mcp.tool()
def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers together.

    Args:
        a: First number.
        b: Second number.
    """
    result = a * b
    logger.info("multiply_numbers(%s, %s) = %s", a, b, result)
    return result


@mcp.tool()
def power(base: float, exponent: float) -> float:
    """Raise base to the given exponent.

    Args:
        base: The base number.
        exponent: The exponent to raise base to.
    """
    result = math.pow(base, exponent)
    logger.info("power(%s, %s) = %s", base, exponent, result)
    return result


@mcp.tool()
def square_root(number: float) -> float:
    """Return the square root of a non-negative number.

    Args:
        number: Non-negative number to take the square root of.
    """
    if number < 0:
        raise ValueError("Cannot take square root of a negative number.")
    result = math.sqrt(number)
    logger.info("square_root(%s) = %s", number, result)
    return result


@mcp.tool()
def factorial(n: int) -> int:
    """Return the factorial of a non-negative integer.

    Args:
        n: Non-negative integer.
    """
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers.")
    result = math.factorial(n)
    logger.info("factorial(%s) = %s", n, result)
    return result


@mcp.tool()
def fibonacci(n: int) -> List[int]:
    """Return the first n Fibonacci numbers.

    Args:
        n: How many Fibonacci numbers to generate (max 50).
    """
    n = min(n, 50)
    seq: List[int] = []
    a, b = 0, 1
    for _ in range(n):
        seq.append(a)
        a, b = b, a + b
    logger.info("fibonacci(%s) = %s", n, seq)
    return seq


@mcp.tool()
def greet_user(name: str) -> str:
    """Greet a user by name.

    Args:
        name: The user's name.
    """
    return f"Hello, {name}! Welcome to the AgentCore MCP Server."


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting MCP server on 0.0.0.0:8000/mcp …")
    mcp.run(transport="streamable-http")
