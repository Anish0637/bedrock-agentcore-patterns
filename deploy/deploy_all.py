"""
Unified Deploy Script — All AgentCore Patterns
===============================================
Orchestrates full deployment of all patterns to AWS:
  1. IAM roles
  2. Pattern 1: AI Agent Runtime
  3. Pattern 2: MCP Server
  4. Pattern 3: A2A Server
  5. Pattern 5: Async Agent
  6. Pattern 6: Memory resource
  7. Pattern 9: Gateway + Lambda target

Usage:
    python deploy/deploy_all.py [--pattern 01]

Options:
    --pattern <id>   Deploy only a specific pattern (01, 02, 03, 05, 06, 09)
    --dry-run        Show what would be deployed without making changes
"""

import os
import sys
import json
import logging
import argparse
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")


# ── Helpers ────────────────────────────────────────────────────────────────────

def run(script: Path, dry_run: bool = False) -> bool:
    """Run a Python deploy script in its own directory."""
    if dry_run:
        print(f"  [DRY RUN] Would execute: python {script.relative_to(ROOT)}")
        return True
    logger.info("Running: %s", script)
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(script.parent),
        capture_output=False,
    )
    if result.returncode != 0:
        logger.error("Script failed: %s (exit %d)", script, result.returncode)
        return False
    return True


def check_prerequisites() -> bool:
    issues = []
    if not ACCOUNT_ID:
        issues.append("AWS_ACCOUNT_ID is not set in .env")
    if not REGION:
        issues.append("AWS_DEFAULT_REGION is not set in .env")
    for issue in issues:
        print(f"  ❌ {issue}")
    return len(issues) == 0


# ── Pattern registry ────────────────────────────────────────────────────────────

PATTERNS = {
    "iam":  (ROOT / "infra"       / "iam_setup.py",       "IAM Roles & Policies"),
    "01":   (ROOT / "01_ai_agent" / "deploy.py",          "AI Agent Runtime"),
    "02":   (ROOT / "02_mcp_server" / "deploy.py",        "MCP Server"),
    "03":   (ROOT / "03_a2a_server" / "deploy.py",        "A2A Server"),
    "05":   (ROOT / "05_async_agents" / "deploy.py",      "Async Agent"),
    "06":   (ROOT / "06_memory" / "memory_setup.py",      "Memory Resource"),
    "09":   (ROOT / "09_gateway" / "gateway_setup.py",    "Gateway + Lambda Target"),
}

DEPLOY_ORDER = ["iam", "01", "02", "03", "05", "06", "09"]


def deploy_all(pattern_filter: str | None = None, dry_run: bool = False):
    print("\n🚀 AgentCore Patterns — Deployment")
    print(f"   Region : {REGION}")
    print(f"   Account: {ACCOUNT_ID or '(not set)'}")
    print(f"   Dry run: {dry_run}\n")

    if not check_prerequisites():
        print("\n⚠️  Fix prerequisites before deploying.")
        return

    keys = [pattern_filter] if pattern_filter else DEPLOY_ORDER
    results = {}

    for key in keys:
        if key not in PATTERNS:
            print(f"  ⚠️  Unknown pattern '{key}'. Valid: {list(PATTERNS.keys())}")
            continue
        script, description = PATTERNS[key]
        print(f"\n▶  Deploying Pattern {key}: {description}")
        ok = run(script, dry_run=dry_run)
        results[key] = "✅ OK" if ok else "❌ FAILED"

    print("\n\n📊 Deployment Summary")
    print("─" * 40)
    for key, status in results.items():
        _, desc = PATTERNS[key]
        print(f"  {status}  [{key}] {desc}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy AgentCore patterns to AWS")
    parser.add_argument("--pattern", type=str, help="Deploy a specific pattern (e.g. 01)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without deploying")
    args = parser.parse_args()

    deploy_all(pattern_filter=args.pattern, dry_run=args.dry_run)
