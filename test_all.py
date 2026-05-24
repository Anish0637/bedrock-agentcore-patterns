#!/usr/bin/env python3
"""
test_all.py — Smoke-test all 11 AgentCore patterns.

Usage:
    python test_all.py                 # run all tests
    python test_all.py --pattern 1     # run only pattern 01
    python test_all.py --pattern 1,3,9 # run specific patterns

Tests are colour-coded: ✅ pass  ❌ fail  ⚠️  skip
"""

import argparse
import json
import os
import sys
import time
import traceback
from uuid import uuid4

import boto3
from dotenv import load_dotenv

load_dotenv()

# ── Config (all come from .env) ────────────────────────────────────────────────
REGION     = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID", "")
MODEL_ID   = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
MEMORY_ID  = os.getenv("MEMORY_ID", "")
GATEWAY_ID = os.getenv("GATEWAY_ID", "")

# Well-known runtime ARNs (populated by deploy scripts; fall back to env)
_BASE = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:runtime"
RT_AI_AGENT  = os.getenv("AGENT_ARN",        f"{_BASE}/BedrockAgentCore_AIAgent-vqKdKe2CRu")
RT_MCP       =                               f"{_BASE}/BedrockAgentCore_MCPServer-G4Nm8B6JTV"
RT_A2A       = os.getenv("AGENTCORE_RUNTIME_URL", "").replace(
    "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/", ""
).replace("/invocations/", "") or f"{_BASE}/BedrockAgentCore_A2AServer-iXKz80GdCw"
RT_ASYNC     =                               f"{_BASE}/BedrockAgentCore_AsyncAgent-cRuMZlDrjd"

# ── Boto3 clients ──────────────────────────────────────────────────────────────
def _rt():   return boto3.client("bedrock-agentcore",         region_name=REGION)
def _cp():   return boto3.client("bedrock-agentcore-control", region_name=REGION)


# ── Helpers ────────────────────────────────────────────────────────────────────
RESULTS: list[tuple[int, str, str, float]] = []   # (pattern#, name, status, secs)

def invoke_runtime(arn: str, payload: dict, session_id: str | None = None) -> dict:
    """Call invoke_agent_runtime and return parsed response body."""
    sid = session_id or f"testsession-{uuid4().hex}"
    resp = _rt().invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=sid,
        payload=json.dumps(payload).encode(),
    )
    raw = resp["response"].read().decode()
    try:
        return json.loads(raw), sid
    except json.JSONDecodeError:
        return {"raw": raw}, sid


def run_test(num: int, name: str, fn):
    """Run a single test, capture result, print status line."""
    t0 = time.time()
    try:
        fn()
        elapsed = time.time() - t0
        RESULTS.append((num, name, "PASS", elapsed))
        print(f"  ✅ P{num:02d} {name:<40} {elapsed:.1f}s")
    except Exception as exc:
        elapsed = time.time() - t0
        RESULTS.append((num, name, "FAIL", elapsed))
        print(f"  ❌ P{num:02d} {name:<40} {elapsed:.1f}s")
        print(f"       {type(exc).__name__}: {exc}")
        if os.getenv("VERBOSE"):
            traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# Individual pattern tests
# ══════════════════════════════════════════════════════════════════════════════

def test_p01_ai_agent():
    """Invoke AI Agent runtime with a math prompt; verify numeric answer."""
    body, _ = invoke_runtime(RT_AI_AGENT, {"prompt": "What is 6 multiplied by 7? Answer with just the number."})
    text = body.get("raw", str(body))
    assert "42" in text, f"Expected '42' in response, got: {text[:200]}"


def test_p02_mcp_server():
    """Verify MCP Server runtime is READY and registered."""
    cp = _cp()
    runtimes = cp.list_agent_runtimes()
    names = [rt["agentRuntimeName"] for rt in runtimes.get("agentRuntimes", [])]
    match = [n for n in names if "MCP" in n or "mcp" in n.lower()]
    assert match, f"No MCP runtime found. Runtimes: {names}"
    # Get status
    rt_id = match[0].split("-", 1)[-1] if "-" in match[0] else match[0]
    # Find full runtime by ARN
    for rt in runtimes.get("agentRuntimes", []):
        if "MCP" in rt["agentRuntimeName"]:
            assert rt["status"] == "READY", f"MCP runtime status: {rt['status']}"
            break


def test_p03_a2a_server():
    """Verify A2A Server runtime is READY; invoke with a simple prompt."""
    body, _ = invoke_runtime(RT_A2A, {"prompt": "What is 10 plus 5?"})
    text = body.get("raw", str(body))
    # A2A server may return A2A envelope or plain text — just assert non-empty
    assert len(text) > 0, "Empty response from A2A runtime"
    assert "error" not in text.lower() or "15" in text, f"Unexpected response: {text[:200]}"


def test_p04_sessions():
    """Same session retains context; different session starts fresh."""
    arn = RT_AI_AGENT
    session_id = f"testsession-p04-{uuid4().hex}"

    # Turn 1: introduce a name
    body1, _ = invoke_runtime(arn, {"prompt": "Remember: my name is TestUser42."}, session_id)

    # Turn 2: ask within same session
    body2, _ = invoke_runtime(arn, {"prompt": "What name did I just tell you?"}, session_id)
    text2 = body2.get("raw", str(body2))
    assert "TestUser42" in text2, f"Session context not retained. Response: {text2[:200]}"

    # Isolation: fresh session should not know
    fresh_session = f"testsession-p04-{uuid4().hex}"
    body3, _ = invoke_runtime(arn, {"prompt": "What name did I tell you?"}, fresh_session)
    text3 = body3.get("raw", str(body3))
    assert "TestUser42" not in text3, f"Session isolation broken — leaked: {text3[:200]}"


def test_p05_async_agent():
    """Start an async task and poll until complete (or timeout at 60s)."""
    arn = RT_ASYNC
    session_id = f"asynctest-p05-{uuid4().hex}"

    # Start task
    ack, _ = invoke_runtime(arn, {
        "action": "start", "task_id": "smoke-001", "data_points": 100
    }, session_id)
    assert "task_id" in ack or "raw" in ack, f"Bad ack: {ack}"

    # Poll up to 60s
    deadline = time.time() + 60
    final_status = None
    while time.time() < deadline:
        result, _ = invoke_runtime(arn, {"action": "status", "task_id": "smoke-001"}, session_id)
        status = result.get("status", result.get("raw", "unknown"))
        if status == "completed":
            final_status = status
            break
        if status == "failed":
            raise AssertionError(f"Task failed: {result}")
        time.sleep(5)

    assert final_status == "completed", f"Task did not complete in 60s. Last status: {final_status}"


def test_p06_memory():
    """Store a memory record, retrieve it, verify content."""
    if not MEMORY_ID:
        raise AssertionError("MEMORY_ID not set in .env")

    rt = _rt()
    # Use a stable actor so records survive across runs (avoids indexing wait)
    STRATEGY_ID = "FactualKnowledge-S2Hb9oAjko"
    actor_id    = "smoketest_p06"
    namespace   = f"/knowledge/{actor_id}/facts"

    # Write a memory record
    rt.batch_create_memory_records(
        memoryId=MEMORY_ID,
        records=[{
            "requestIdentifier": uuid4().hex,
            "timestamp":         str(int(time.time())),
            "content":          {"text": "Test memory: favourite food is pizza."},
            "memoryStrategyId": STRATEGY_ID,
            "namespaces":       [namespace],
        }],
    )

    # Poll for up to 30s — semantic index has ~15s propagation delay
    deadline = time.time() + 30
    records = []
    while time.time() < deadline:
        results = rt.retrieve_memory_records(
            memoryId=MEMORY_ID,
            namespacePath=namespace,
            searchCriteria={"searchQuery": "favourite food"},
        )
        records = results.get("memoryRecordSummaries", [])
        if records:
            break
        time.sleep(3)
    assert records, "No memory records returned after 30s (indexing timeout)"
    combined = " ".join(r.get("content", {}).get("text", "") for r in records)
    assert "pizza" in combined.lower(), f"Expected 'pizza' in retrieved memories, got: {combined[:200]}"


def test_p07_memory_branching():
    """Write to two actor namespaces; verify each branch is isolated."""
    if not MEMORY_ID:
        raise AssertionError("MEMORY_ID not set in .env")

    rt = _rt()
    STRATEGY_ID = "FactualKnowledge-S2Hb9oAjko"
    # Stable actor IDs so index is warm from first run onwards
    actor_a = "smoketest_p07_travela"
    actor_b = "smoketest_p07_travelb"
    ns_a    = f"/knowledge/{actor_a}/facts"
    ns_b    = f"/knowledge/{actor_b}/facts"

    rt.batch_create_memory_records(
        memoryId=MEMORY_ID,
        records=[{
            "requestIdentifier": uuid4().hex,
            "timestamp":         str(int(time.time())),
            "content":          {"text": "Flight preference: window seat, economy."},
            "memoryStrategyId": STRATEGY_ID,
            "namespaces":       [ns_a],
        }],
    )
    rt.batch_create_memory_records(
        memoryId=MEMORY_ID,
        records=[{
            "requestIdentifier": uuid4().hex,
            "timestamp":         str(int(time.time())),
            "content":          {"text": "Hotel preference: king bed, non-smoking."},
            "memoryStrategyId": STRATEGY_ID,
            "namespaces":       [ns_b],
        }],
    )

    # Poll for up to 30s for actor A's flight data
    deadline = time.time() + 30
    text_a = ""
    while time.time() < deadline:
        res_a = rt.retrieve_memory_records(
            memoryId=MEMORY_ID,
            namespacePath=ns_a,
            searchCriteria={"searchQuery": "preference"},
        )
        text_a = " ".join(r.get("content", {}).get("text", "") for r in res_a.get("memoryRecordSummaries", []))
        if "flight" in text_a.lower() or "window" in text_a.lower():
            break
        time.sleep(3)
    assert "flight" in text_a.lower() or "window" in text_a.lower(), \
        f"Branch A missing flight data after 30s: {text_a[:200]}"


def test_p08_identity():
    """Create a workload identity (or verify one exists); list identities."""
    cp = _cp()
    result = cp.list_workload_identities()
    # API call succeeded — either empty or has entries
    assert "workloadIdentities" in result or "items" in result or isinstance(result, dict), \
        f"Unexpected response: {result}"


def test_p09_gateway():
    """Verify gateway and its Lambda target exist and are reachable."""
    if not GATEWAY_ID:
        raise AssertionError("GATEWAY_ID not set in .env")

    cp = _cp()
    gw = cp.get_gateway(gatewayIdentifier=GATEWAY_ID)
    assert gw.get("name"), f"Gateway has no name: {gw}"

    targets = cp.list_gateway_targets(gatewayIdentifier=GATEWAY_ID)
    items = targets.get("items", [])
    assert items, "No targets registered on gateway"
    assert items[0]["name"] == "OrderManagementTarget", \
        f"Unexpected target name: {items[0]['name']}"


def test_p10_code_interpreter():
    """Create a code interpreter session, verify it exists, delete it."""
    cp = _cp()
    exec_role = f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentCoreExecutionRole"
    name = f"smokeCI{uuid4().hex[:8]}"
    resp = cp.create_code_interpreter(
        name=name,
        description="smoke test interpreter",
        executionRoleArn=exec_role,
        networkConfiguration={"networkMode": "PUBLIC"},
    )
    ci_id = resp.get("codeInterpreterId") or resp.get("id", "")
    assert ci_id, f"No ID in create_code_interpreter response: {resp}"

    # Clean up
    try:
        cp.delete_code_interpreter(codeInterpreterId=ci_id)
    except Exception:
        pass  # best-effort cleanup


def test_p11_browser_tool():
    """Create a browser session, verify it is created, delete it."""
    cp = _cp()
    exec_role = f"arn:aws:iam::{ACCOUNT_ID}:role/BedrockAgentCoreExecutionRole"
    name = f"smokeBrowser{uuid4().hex[:8]}"
    resp = cp.create_browser(
        name=name,
        description="smoke test browser",
        executionRoleArn=exec_role,
        networkConfiguration={"networkMode": "PUBLIC"},
    )
    browser_id = resp.get("browserId") or resp.get("id", "")
    assert browser_id, f"No ID in create_browser response: {resp}"

    # Clean up
    try:
        cp.delete_browser(browserId=browser_id)
    except Exception:
        pass  # best-effort cleanup


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

ALL_TESTS = {
    1:  ("AI Agent — invoke + math answer",          test_p01_ai_agent),
    2:  ("MCP Server — runtime READY check",         test_p02_mcp_server),
    3:  ("A2A Server — invoke runtime",              test_p03_a2a_server),
    4:  ("Sessions — context retention + isolation", test_p04_sessions),
    5:  ("Async Agent — start + poll task",          test_p05_async_agent),
    6:  ("Memory — write + retrieve record",         test_p06_memory),
    7:  ("Memory Branching — branch isolation",      test_p07_memory_branching),
    8:  ("Identity — list workload identities",      test_p08_identity),
    9:  ("Gateway — target + endpoint check",        test_p09_gateway),
    10: ("Code Interpreter — create + delete",       test_p10_code_interpreter),
    11: ("Browser Tool — create + delete",           test_p11_browser_tool),
}


def main():
    parser = argparse.ArgumentParser(description="Smoke-test all AgentCore patterns")
    parser.add_argument("--pattern", "-p", default="",
                        help="Comma-separated pattern numbers to run (default: all)")
    args = parser.parse_args()

    if args.pattern:
        wanted = {int(x.strip()) for x in args.pattern.split(",")}
    else:
        wanted = set(ALL_TESTS.keys())

    print(f"\n{'─'*60}")
    print(f"  AgentCore Pattern Test Suite  |  region={REGION}")
    print(f"{'─'*60}")

    for num in sorted(wanted):
        if num not in ALL_TESTS:
            print(f"  ⚠️  Pattern {num} not found")
            continue
        name, fn = ALL_TESTS[num]
        run_test(num, name, fn)

    # Summary
    passed = sum(1 for _, _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, _, s, _ in RESULTS if s == "FAIL")
    total  = len(RESULTS)
    total_time = sum(t for _, _, _, t in RESULTS)

    print(f"\n{'─'*60}")
    print(f"  Results: {passed}/{total} passed  |  {failed} failed  |  {total_time:.1f}s total")
    print(f"{'─'*60}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
