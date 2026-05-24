"""
Pattern 1 — AI Agent with Bedrock AgentCore Runtime
====================================================
Uses boto3 Bedrock Converse API + stdlib HTTPServer.
Dependencies (boto3) are bundled in the lib/ directory within the zip.
"""

import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Add bundled lib/ directory (vendored dependencies in the zip)
_bundle_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if os.path.isdir(_bundle_lib):
    sys.path.insert(0, _bundle_lib)

import boto3

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
REGION   = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# Session header forwarded by AgentCore runtime
SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"

# In-memory conversation history keyed by session ID
_sessions: dict[str, list] = {}
_sessions_lock = threading.Lock()


def _call_bedrock(session_id: str, prompt: str) -> str:
    """Call Bedrock Converse API with full session history and return text."""
    client = boto3.client("bedrock-runtime", region_name=REGION)

    # Retrieve or init history for this session
    with _sessions_lock:
        history = _sessions.setdefault(session_id, [])
        history.append({"role": "user", "content": [{"text": prompt}]})
        messages = list(history)  # snapshot

    resp = client.converse(
        modelId=MODEL_ID,
        messages=messages,
        system=[{"text": (
            "You are a helpful assistant. "
            "For arithmetic questions, give just the numeric answer. "
            "Remember everything the user tells you within this conversation."
        )}],
    )
    reply = resp["output"]["message"]["content"][0]["text"]

    with _sessions_lock:
        _sessions[session_id].append({"role": "assistant", "content": [{"text": reply}]})

    return reply


class AgentHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler implementing /ping and /invocations."""

    def do_GET(self):
        if self.path == "/ping":
            self._respond(200, {"status": "healthy"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/invocations":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) if length else b"{}")
            prompt = payload.get("prompt", "")
            session_id = self.headers.get(SESSION_HEADER) or "default"
            logger.info("Session=%s prompt=%s", session_id[:12], prompt)
            if not prompt:
                self._respond(400, {"error": "Missing 'prompt'"})
                return
            try:
                reply = _call_bedrock(session_id, prompt)
                logger.info("Reply: %s", reply[:80])
                self._respond(200, {"response": reply, "raw": reply})
            except Exception as e:
                logger.exception("Bedrock error")
                self._respond(500, {"error": str(e)})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # suppress default access logs
        logger.debug(fmt, *args)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting AgentCore HTTP server on 0.0.0.0:%d", port)
    server = HTTPServer(("0.0.0.0", port), AgentHandler)
    server.serve_forever()

