# Architecture & Code Flow

End-to-end walkthrough of how each pattern is built, deployed, and tested.

---

## Table of Contents

1. [Repository Layout](#repository-layout)
2. [Runtime Model — How AgentCore Works](#runtime-model)
3. [Bundling Dependencies](#bundling-dependencies)
4. [Agent HTTP Server Contract](#agent-http-server-contract)
5. [Pattern-by-Pattern Code Flow](#patterns)
   - [P01 — AI Agent](#p01-ai-agent)
   - [P02 — MCP Server](#p02-mcp-server)
   - [P03 — A2A Server](#p03-a2a-server)
   - [P04 — Session Management](#p04-sessions)
   - [P05 — Async Long-Running Agent](#p05-async-agent)
   - [P06 — Memory Integration](#p06-memory)
   - [P07 — Memory Branching](#p07-memory-branching)
   - [P08 — Identity Management](#p08-identity)
   - [P09 — Gateway + Lambda Tools](#p09-gateway)
   - [P10 — Code Interpreter](#p10-code-interpreter)
   - [P11 — Browser Tool](#p11-browser-tool)
6. [Smoke-Test Suite (`test_all.py`)](#smoke-test-suite)
7. [Key Gotchas & Lessons Learned](#gotchas)

---

## Repository Layout

```
bedrock-agentcore-patterns/
├── 01_ai_agent/
│   ├── agent.py              # Pattern 1 runtime code (deployed to AgentCore)
│   └── requirements.txt
├── 02_mcp_server/            # MCP server runtime code
├── 03_a2a_server/
│   ├── a2a_server.py         # Pattern 3 runtime code
│   └── requirements.txt
├── 04_sessions/              # Session management examples & client code
├── 05_async_agents/
│   ├── async_agent.py        # Pattern 5 runtime code
│   └── requirements.txt
├── 06_memory/                # Memory integration scripts
├── 07_memory_branching/      # Multi-agent memory branching scripts
├── 08_identity/              # Identity management scripts
├── 09_gateway/               # Gateway + Lambda setup scripts
├── 10_code_interpreter/      # Code interpreter scripts
├── 11_browser_tool/          # Browser tool scripts
├── infra/
│   └── deploy_helper.py      # Shared S3-zip deploy utility
├── deploy/                   # Orchestrated deploy scripts
├── test_all.py               # 11-pattern smoke-test suite
├── requirements.txt          # Local dev dependencies
└── .env                      # Runtime config (not committed)
```

---

## Runtime Model

AWS Bedrock AgentCore manages a fully serverless compute tier. You never run or
manage a container yourself. The lifecycle is:

```
Your code (agent.py)
       │
       ▼
  Zip file (agent.py + lib/)
       │
       ▼  upload
   Amazon S3 bucket
       │
       ▼  create_agent_runtime / update_agent_runtime
  AgentCore Control Plane  ──► Runtime (PYTHON_3_12)
       │                              │
       │                              │  executes
       │                              ▼
       │                       python3 agent.py   ← entryPoint
       │                              │
       │                         HTTP server on :8080
       │
       ▼  invoke_agent_runtime (data plane)
  AgentCore Data Plane  ──► POST /invocations  ──► your handler
```

**Two separate boto3 clients are needed:**

| Client | Service name | Purpose |
|--------|-------------|---------|
| Control plane | `bedrock-agentcore-control` | Create/update/list runtimes, memory, gateways, identities |
| Data plane | `bedrock-agentcore` | Invoke a runtime (`invoke_agent_runtime`) |

The `PYTHON_3_12` managed runtime executes `python3 <entryPoint>` and routes all
HTTP traffic to your process. **No packages are pre-installed** — not even boto3.
Everything must be bundled inside the zip.

---

## Bundling Dependencies

Because `pip install` does not run inside the managed runtime, all third-party
packages are vendored into a `lib/` subdirectory within the deployment zip:

```bash
# One-time build (pure Python packages are cross-platform)
pip install boto3 --target /tmp/agentcore_bundle/lib
```

The zip layout:

```
code.zip
├── agent.py          ← entry point
├── lib/
│   ├── boto3/
│   ├── botocore/
│   └── ...           ← all transitive deps (~2 100 files, ~15 MB)
```

Each agent adds this at the top to put `lib/` on the path:

```python
_bundle_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if os.path.isdir(_bundle_lib):
    sys.path.insert(0, _bundle_lib)
```

---

## Agent HTTP Server Contract

Every deployed agent must implement two endpoints on `0.0.0.0:8080`:

| Endpoint | Method | Purpose | Expected response |
|----------|--------|---------|-------------------|
| `/ping` | GET | Health check — AgentCore polls this during startup | `{"status": "healthy"}` |
| `/invocations` | POST | Invoke the agent | Any valid JSON |

If `/ping` does not return HTTP 200 within ~30 seconds the runtime transitions to
`FAILED`.

The data plane call from the test:
```python
resp = client.invoke_agent_runtime(
    agentRuntimeArn=arn,
    runtimeSessionId=session_id,   # ≥ 33 characters
    payload=json.dumps(payload).encode(),
)
body = resp["response"].read().decode()   # StreamingBody — must call .read()
```

---

## Patterns

### P01 — AI Agent

**File:** `01_ai_agent/agent.py`

**What it does:** Stateful conversational agent backed by Amazon Nova Lite via
the Bedrock Converse API. Maintains per-session conversation history in memory.

**Code flow:**

```
invoke_agent_runtime(payload={"prompt": "..."}, runtimeSessionId=sid)
        │
        ▼  AgentCore routes to
POST /invocations
        │
        ▼  AgentHandler.do_POST()
1. Read Content-Length → parse JSON body → extract "prompt"
2. Read header: X-Amzn-Bedrock-AgentCore-Runtime-Session-Id → session_id
3. _call_bedrock(session_id, prompt)
   a. Acquire _sessions_lock
   b. Append {"role": "user", ...} to _sessions[session_id]
   c. Snapshot the full history as `messages`
   d. Release lock
   e. boto3 bedrock-runtime.converse(modelId, messages, system=[...])
   f. Extract reply text from resp["output"]["message"]["content"][0]["text"]
   g. Acquire lock → append {"role": "assistant", ...} → release
4. Return {"response": reply, "raw": reply}
```

**Session header:** `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`
Forwarded by AgentCore to the agent on every `/invocations` call.
This is how multi-turn conversations work within a `runtimeSessionId`.

---

### P02 — MCP Server

**File:** `02_mcp_server/`

**What it does:** Registers an MCP (Model Context Protocol) server as an
AgentCore runtime. The test only verifies the runtime is `READY`.

**Code flow (test):**
```
bedrock-agentcore-control.list_agent_runtimes()
        │
        ▼
Filter for name containing "MCP"
        │
        ▼
Assert runtime["status"] == "READY"
```

---

### P03 — A2A Server

**File:** `03_a2a_server/a2a_server.py`

**What it does:** A2A-compatible agent — a calculator that accepts prompts and
returns arithmetic results via Nova Lite. Same HTTP server pattern as P01 but
stateless (no session history).

**Code flow:**

```
POST /invocations  {"prompt": "What is 10 plus 5?"}
        │
        ▼  A2AHandler.do_POST()
1. Parse payload → extract "prompt"
2. _call_bedrock(prompt)
   → boto3 bedrock-runtime.converse(single-turn, calculator system prompt)
   → returns text
3. Return {"response": reply, "raw": reply, "agent": "A2A Calculator"}
```

---

### P04 — Session Management

**Shares runtime with P01** (`RT_AI_AGENT`).

**What it demonstrates:** Same `runtimeSessionId` retains full conversation
history; a different session ID starts fresh.

**Test flow:**

```
Turn 1: invoke({"prompt": "Remember: my name is TestUser42."}, session_id=S1)
Turn 2: invoke({"prompt": "What name did I just tell you?"},   session_id=S1)
        → assert "TestUser42" in response   ✓ history carried forward

Turn 3: invoke({"prompt": "What name did I tell you?"},        session_id=S2)
        → assert "TestUser42" NOT in response   ✓ isolated namespace
```

The history is keyed by the raw `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`
header value. Each unique session ID gets its own `list` in `_sessions`.

---

### P05 — Async Long-Running Agent

**File:** `05_async_agents/async_agent.py`

**What it does:** Accepts a task, immediately acknowledges it, runs a
multi-stage analysis in a background thread, and reports progress via a
separate status call.

**Code flow:**

```
POST /invocations  {"action": "start", "task_id": "smoke-001", "data_points": 100}
        │
        ▼  action == "start"
1. Register _task_store["smoke-001"] = {"status": "running", "progress": 0}
2. Spawn daemon thread: _run_analysis("smoke-001", 100)
3. Return immediately: {"status": "accepted", "task_id": "smoke-001", "raw": "accepted"}

Background thread (_run_analysis):
    For each stage in [Loading→20%, Preprocessing→40%, Running→70%,
                        Generating→90%, Finalizing→100%]:
        sleep(2)
        update _task_store[task_id]["progress"] and "current_stage"
    Set status="completed"

POST /invocations  {"action": "status", "task_id": "smoke-001"}
        │
        ▼  action == "status"
Read _task_store["smoke-001"] under lock → return snapshot
```

`ThreadingHTTPServer` (vs plain `HTTPServer`) is critical — it handles the
`start` and `status` requests concurrently rather than serially.

**Test polling pattern:**
```python
deadline = time.time() + 60
while time.time() < deadline:
    result = invoke_runtime(arn, {"action": "status", "task_id": "smoke-001"})
    if result["status"] == "completed": break
    time.sleep(5)
```

---

### P06 — Memory Integration

**Uses:** `bedrock-agentcore` data plane — `batch_create_memory_records` and
`retrieve_memory_records`.

**Memory strategies (pre-provisioned):**

| Strategy ID | Type |
|-------------|------|
| `FactualKnowledge-S2Hb9oAjko` | SEMANTIC |
| `SessionSummary-qf3xahD0wz` | SUMMARIZATION |
| `UserPreferences-VYIROOBIwu` | USER_PREFERENCE |

**Code flow:**

```
1. batch_create_memory_records(
       memoryId=MEMORY_ID,
       records=[{
           "requestIdentifier": uuid4().hex,   # dedup key
           "timestamp":         str(int(time.time())),
           "content":           {"text": "favourite food is pizza"},
           "memoryStrategyId":  "FactualKnowledge-S2Hb9oAjko",
           "namespaces":        ["/knowledge/smoketest_p06/facts"],
       }])

2. Poll (up to 30s, 3s intervals):  ← ~15s semantic index propagation delay
   retrieve_memory_records(
       memoryId=MEMORY_ID,
       namespacePath="/knowledge/smoketest_p06/facts",  ← prefix search
       searchCriteria={"searchQuery": "favourite food"},
   )

3. Assert "pizza" in combined record text
```

**Key API details:**
- Parameter is `records` (not `memoryRecords`).
- Use `namespacePath` (prefix match) instead of `namespace` (exact match) for
  reliable retrieval before the namespace is fully indexed.
- `searchCriteria` wraps the query: `{"searchQuery": "..."}`.

---

### P07 — Memory Branching

**Demonstrates:** Two actors write to separate namespaces; reads from one
namespace do not see the other's records.

**Code flow:**

```
Actor A namespace: /knowledge/smoketest_p07_travela/facts
Actor B namespace: /knowledge/smoketest_p07_travelb/facts

Write A: "Flight preference: window seat, economy."
Write B: "Hotel preference: king bed, non-smoking."

Poll namespacePath=ns_a, searchQuery="preference"
  → assert "flight" or "window" in results
  → assert "hotel" NOT leaked from ns_b
```

Using stable (fixed) actor IDs across test runs means the namespace index is
already warm from the first run, eliminating the 15-second wait on reruns.

---

### P08 — Identity Management

**What it does:** Verifies the workload identity API is reachable and returns a
valid structure.

**Code flow:**
```
bedrock-agentcore-control.list_workload_identities()
        │
        ▼
Assert response is a dict (API call succeeded)
```

---

### P09 — Gateway + Lambda Tools

**What it does:** Verifies a pre-provisioned API gateway has its Lambda target
registered and named correctly.

**Code flow:**
```
bedrock-agentcore-control.get_gateway(gatewayIdentifier=GATEWAY_ID)
        → assert gw["name"] is non-empty

bedrock-agentcore-control.list_gateway_targets(gatewayIdentifier=GATEWAY_ID)
        → assert items[0]["name"] == "OrderManagementTarget"
```

`GATEWAY_ID` is read from `.env`.

---

### P10 — Code Interpreter

**What it does:** Creates a sandboxed code interpreter session, asserts an ID is
returned, then deletes it.

**Code flow:**
```
bedrock-agentcore-control.create_code_interpreter(
    name="smokeCI<hex>",
    executionRoleArn=...,
    networkConfiguration={"networkMode": "PUBLIC"},
)
        → extract codeInterpreterId
        → assert non-empty

bedrock-agentcore-control.delete_code_interpreter(codeInterpreterId=ci_id)
```

---

### P11 — Browser Tool

**What it does:** Creates a browser automation session, asserts an ID is
returned, then deletes it.

**Code flow:**
```
bedrock-agentcore-control.create_browser(
    name="smokeBrowser<hex>",
    executionRoleArn=...,
    networkConfiguration={"networkMode": "PUBLIC"},
)
        → extract browserId
        → assert non-empty

bedrock-agentcore-control.delete_browser(browserId=browser_id)
```

---

## Smoke-Test Suite

**File:** `test_all.py`

### Structure

```
load_dotenv()                   ← reads .env for REGION, ACCOUNT_ID, MODEL_ID,
                                  MEMORY_ID, GATEWAY_ID, AGENT_ARN
                                  
_rt()  → boto3 client("bedrock-agentcore")          # data plane
_cp()  → boto3 client("bedrock-agentcore-control")  # control plane

invoke_runtime(arn, payload, session_id)
    │
    ├─ generates session_id = "testsession-{uuid4().hex}"  (≥33 chars)
    ├─ calls _rt().invoke_agent_runtime(agentRuntimeArn, runtimeSessionId, payload)
    ├─ reads resp["response"].read().decode()   ← StreamingBody
    └─ returns (parsed_dict, session_id)

run_test(num, name, fn)
    │
    ├─ records wall-clock time
    ├─ calls fn()
    ├─ appends (num, name, "PASS"|"FAIL", elapsed) to RESULTS
    └─ prints ✅ / ❌ line

ALL_TESTS = {1: (...), 2: (...), ..., 11: (...)}

main()
    ├─ parse --pattern flag (comma-separated, default all)
    ├─ iterate sorted(wanted) → run_test(num, name, fn)
    └─ print summary, sys.exit(1) if any failures
```

### Running

```bash
# All patterns
AWS_PROFILE=anish0637 python3 test_all.py

# Specific patterns
AWS_PROFILE=anish0637 python3 test_all.py --pattern 1,3,4

# Verbose traceback on failure
VERBOSE=1 AWS_PROFILE=anish0637 python3 test_all.py
```

---

## Gotchas

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Runtime stuck at `UPDATING`, then `FAILED` with "module not found" | `PYTHON_3_12` managed runtime has NO pre-installed packages — not even boto3 | Bundle all deps in `lib/` inside the zip; use `sys.path.insert(0, lib_dir)` |
| `invoke_agent_runtime` raises `KeyError: 'body'` | Response key is `response`, not `body` | `resp["response"].read().decode()` |
| Session ID validation error | Minimum 33 characters required | Use `f"testsession-{uuid4().hex}"` (45 chars) |
| Memory records not found immediately after write | Semantic index has ~15s propagation delay | Poll with 3s sleep up to 30s instead of `time.sleep(15)` |
| `batch_create_memory_records` `ValidationException` | Required fields `requestIdentifier` and `timestamp` missing; param is `records` not `memoryRecords` | Add both fields; use `records=` parameter |
| Memory `namespace` exact match returns nothing for new namespaces | Namespace index not yet propagated; exact match differs from prefix match | Use `namespacePath=` (prefix search) instead of `namespace=` |
| Model `ResourceNotFoundException` | `us.anthropic.claude-3-7-sonnet-20250219-v1:0` is end-of-life | Use `amazon.nova-lite-v1:0` |
| P04 context not retained between turns | Agent was single-turn — no history tracking | Read `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` header; maintain `_sessions` dict keyed by session ID |
| P05 `/invocations` blocks on `start` while background task runs | `HTTPServer` is single-threaded | Use `ThreadingHTTPServer` so status polls are served concurrently |
| `replace_string_in_file` fails on certain files | Whitespace/encoding mismatch in oldString | Write to a new file then `mv` to overwrite |
