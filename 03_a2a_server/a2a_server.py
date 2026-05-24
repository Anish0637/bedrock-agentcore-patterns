"""
Pattern 3 — A2A Server on AgentCore Runtime
============================================
Implements a simple A2A-compatible agent using stdlib HTTPServer + boto3.
Dependencies (boto3) are bundled in the lib/ directory within the zip.

Usage (local):
    python a2a_server.py

Deploy to AgentCore Runtime:
    python deploy.py
"""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# Add bundled lib/ directory (vendored dependencies in the zip)
_bundle_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if os.path.isdir(_bundle_lib):
    sys.path.insert(0, _bundle_lib)

import boto3

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-lite-v1:0")
REGION   = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
HOST, PORT = "0.0.0.0", 8080


def _call_bedrock(prompt: str) -> str:
    """Call Claude via Bedrock Converse API and return text."""
    client = boto3.client("bedrock-runtime", region_name=REGION)
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        system=[{"text": (
            "You are a precise calculator assistant. "
            "Always compute arithmetic results accurately. "
            "Return only the numeric result with a brief explanation."
        )}],
    )
    return resp["output"]["message"]["content"][0]["text"]


class A2AHandler(BaseHTTPRequestHandler):
    """Minimal A2A-compatible HTTP handler implementing /ping and /invocations."""

    def do_GET(self):
        if self.path in ("/ping", "/health"):
            self._respond(200, {"status": "healthy"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/invocations":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) if length else b"{}")
            prompt = payload.get("prompt", "")
            logger.info("Received prompt: %s", prompt)
            if not prompt:
                self._respond(400, {"error": "Missing 'prompt'"})
                return
            try:
                reply = _call_bedrock(prompt)
                logger.info("Reply: %s", reply[:80])
                self._respond(200, {"response": reply, "raw": reply, "agent": "A2A Calculator"})
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

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)


if __name__ == "__main__":
    logger.info("Starting A2A server on %s:%d", HOST, PORT)
    server = HTTPServer((HOST, PORT), A2AHandler)
    server.serve_forever()

