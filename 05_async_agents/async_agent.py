"""
Pattern 5 — Asynchronous & Long-Running Agents
===============================================
Demonstrates the @app.async_task decorator pattern.
The agent immediately acknowledges the request and processes
a background task — the /ping status reports HealthyBusy until done.

Usage (local):
    python async_agent.py

Deploy to AgentCore Runtime:
    python deploy.py
"""

import os
import asyncio
import logging
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from bedrock_agentcore.runtime import BedrockAgentCoreApp

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

# Shared task results store (in-memory; use DynamoDB / ElastiCache in production)
task_store: dict[str, dict] = {}


# ── Background task ────────────────────────────────────────────────────────────

@app.async_task
async def long_running_analysis(task_id: str, data_points: int):
    """
    Simulate a long-running data analysis job.
    While this coroutine is running, /ping returns HealthyBusy so the
    runtime knows the session is still active.
    """
    logger.info("[%s] Analysis started — %d data points", task_id, data_points)
    task_store[task_id] = {"status": "running", "progress": 0, "started_at": datetime.utcnow().isoformat()}

    # Simulate work in stages
    stages = [
        ("Loading data",        20),
        ("Preprocessing",       40),
        ("Running model",       70),
        ("Generating report",   90),
        ("Finalizing results", 100),
    ]

    for stage_name, progress in stages:
        await asyncio.sleep(3)   # Simulate I/O-bound work
        task_store[task_id]["progress"] = progress
        task_store[task_id]["current_stage"] = stage_name
        logger.info("[%s] %s — %d%%", task_id, stage_name, progress)

    task_store[task_id].update({
        "status": "completed",
        "result": f"Analysis of {data_points} data points finished successfully.",
        "finished_at": datetime.utcnow().isoformat(),
    })
    logger.info("[%s] Analysis completed!", task_id)


# ── Entrypoint ────────────────────────────────────────────────────────────────

@app.entrypoint
async def handler(payload: dict) -> dict:
    """
    Immediately returns an acknowledgement, then kicks off the background task.
    The same session can be polled with action=status to check progress.
    """
    action = payload.get("action", "start")

    if action == "start":
        task_id = payload.get("task_id", f"task-{int(time.time())}")
        data_points = int(payload.get("data_points", 1000))

        # Fire and forget — async_task decorator tracks /ping HealthyBusy status
        asyncio.create_task(long_running_analysis(task_id, data_points))

        return {
            "status": "accepted",
            "task_id": task_id,
            "message": (
                f"Analysis of {data_points} data points started. "
                "Poll with action=status to check progress."
            ),
        }

    elif action == "status":
        task_id = payload.get("task_id")
        if not task_id or task_id not in task_store:
            return {"status": "not_found", "task_id": task_id}
        return task_store[task_id]

    return {"error": f"Unknown action: {action}"}


# ── Local runner ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run()
