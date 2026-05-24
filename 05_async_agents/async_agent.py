"""
Pattern 5 — Asynchronous & Long-Running Agents
===============================================
Demonstrates async task tracking with stdlib ThreadingHTTPServer + boto3.
Dependencies (boto3) are bundled in the lib/ directory within the zip.

Usage (local):
    python async_agent.py

Deploy to AgentCore Runtime:
    python deploy.py
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Add bundled lib/ directory (vendored dependencies in the zip)
_bundle_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if os.path.isdir(_bundle_lib):
    sys.path.insert(0, _bundle_lib)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

HOST, PORT = "0.0.0.0", 8080

# Shared in-memory task store (use DynamoDB in production)
_task_store: dict[str, dict] = {}
_task_lock = threading.Lock()


def _run_analysis(task_id: str, data_points: int):
    """Background thread: simulate a multi-stage analysis job."""
    logger.info("[%s] Analysis started — %d data points", task_id, data_points)
    stages = [
        ("Loading data",        20),
        ("Preprocessing",       40),
        ("Running model",       70),
        ("Generating report",   90),
        ("Finalizing results", 100),
    ]
    for stage_name, progress in stages:
        time.sleep(2)  # Simulate work
        with _task_lock:
            _task_store[task_id].update({"progress": progress, "current_stage": stage_name})
        logger.info("[%s] %s — %d%%", task_id, stage_name, progress)

    with _task_lock:
        _task_store[task_id].update({
            "status": "completed",
            "result": f"Analysis of {data_points} data points finished.",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    logger.info("[%s] Analysis completed!", task_id)


class AsyncAgentHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/ping", "/health"):
            self._respond(200, {"status": "healthy"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/invocations":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) if length else b"{}")
            action = payload.get("action", "start")

            if action == "start":
                task_id = payload.get("task_id", f"task-{int(time.time())}")
                data_points = int(payload.get("data_points", 1000))
                with _task_lock:
                    _task_store[task_id] = {
                        "status": "running",
                        "progress": 0,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    }
                t = threading.Thread(target=_run_analysis, args=(task_id, data_points), daemon=True)
                t.start()
                self._respond(200, {
                    "status": "accepted",
                    "task_id": task_id,
                    "message": f"Analysis of {data_points} data points started.",
                    "raw": "accepted",
                })

            elif action == "status":
                task_id = payload.get("task_id")
                with _task_lock:
                    result = dict(_task_store.get(task_id, {"status": "not_found"}))
                result["raw"] = result.get("status", "unknown")
                self._respond(200, result)

            else:
                self._respond(400, {"error": f"Unknown action: {action}"})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)


if __name__ == "__main__":
    logger.info("Starting Async Agent server on %s:%d", HOST, PORT)
    server = ThreadingHTTPServer((HOST, PORT), AsyncAgentHandler)
    server.serve_forever()
