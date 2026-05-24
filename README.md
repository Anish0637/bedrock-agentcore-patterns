# AWS Bedrock AgentCore Patterns

End-to-end Python implementations of every major pattern covered in the **AWS Bedrock AgentCore Deep Dive**.  
Each pattern is self-contained, deployable to AWS, and framework-agnostic (Strands Agents used throughout).

## Patterns

| # | Directory | Pattern | Key Concepts |
|---|-----------|---------|--------------|
| 1 | `01_ai_agent/` | AI Agent Runtime | `BedrockAgentCoreApp`, `@app.entrypoint`, custom tools, `/invocations` |
| 2 | `02_mcp_server/` | MCP Server | `FastMCP`, `@mcp.tool`, Streamable-HTTP transport |
| 3 | `03_a2a_server/` | A2A Server | `A2AServer`, Agent Card, A2A client |
| 4 | `04_sessions/` | Session Management | `runtimeSessionId`, context isolation, `stop_runtime_session` |
| 5 | `05_async_agents/` | Async Long-Running Agents | `@app.async_task`, `HealthyBusy`, background polling |
| 6 | `06_memory/` | Memory Integration | Short-term + long-term memory, `MemoryHookProvider`, strategies |
| 7 | `07_memory_branching/` | Memory Branching Multi-Agent | `ShortTermMemoryHook`, branch isolation, Strands `GraphBuilder` |
| 8 | `08_identity/` | Identity Management | Workload identity, ABAC tags, OAuth 2LO credential provider |
| 9 | `09_gateway/` | Gateway + Lambda Tools | Gateway targets, Lambda tool schema, MCP client |
| 10 | `10_code_interpreter/` | Code Interpreter | `AgentCoreCodeInterpreter`, sandbox execution |
| 11 | `11_browser_tool/` | Browser Tool | `AgentCoreBrowser`, web navigation, session isolation |

## Architecture

```
bedrock-agentcore-patterns/
├── 01_ai_agent/          # Pattern 1 — AI Agent
├── 02_mcp_server/        # Pattern 2 — MCP Server
├── 03_a2a_server/        # Pattern 3 — A2A Server
├── 04_sessions/          # Pattern 4 — Session Management
├── 05_async_agents/      # Pattern 5 — Async Agents
├── 06_memory/            # Pattern 6 — Memory Integration
├── 07_memory_branching/  # Pattern 7 — Memory Branching
├── 08_identity/          # Pattern 8 — Identity Management
├── 09_gateway/           # Pattern 9 — Gateway + Lambda
├── 10_code_interpreter/  # Pattern 10 — Code Interpreter
├── 11_browser_tool/      # Pattern 11 — Browser Tool
├── deploy/               # Unified deploy orchestrator
├── infra/                # IAM roles and policies
├── requirements.txt
└── .env.example
```

## Quick Start

### 1. Prerequisites

- AWS account with Bedrock and AgentCore access enabled
- Python 3.11+
- Docker (for container builds during deploy)
- AWS CLI configured: `aws configure`

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your AWS_ACCOUNT_ID, region, model ID, etc.
```

### 4. Bootstrap IAM

```bash
python infra/iam_setup.py
```

### 5. Deploy all patterns

```bash
python deploy/deploy_all.py
```

Or deploy a single pattern:

```bash
python deploy/deploy_all.py --pattern 01
```

Dry-run (shows what would be deployed):

```bash
python deploy/deploy_all.py --dry-run
```

## Pattern Details

### Pattern 1 — AI Agent Runtime

Deploys a Strands agent with custom tools (`get_weather`, `get_current_time`, `unit_converter`, `calculator`) to AgentCore Runtime.

```bash
cd 01_ai_agent
python agent.py     # test locally
python deploy.py    # deploy to AWS
```

### Pattern 2 — MCP Server

FastMCP server with mathematical tools (`add`, `multiply`, `power`, `sqrt`, `factorial`, `fibonacci`).

```bash
cd 02_mcp_server
python mcp_server.py   # runs on 0.0.0.0:8000/mcp
python deploy.py
```

### Pattern 3 — A2A Server

Calculator agent wrapped in an A2A server. Includes a client that fetches the Agent Card and sends messages.

```bash
cd 03_a2a_server
python a2a_server.py   # runs on 0.0.0.0:9000
python a2a_client.py   # sends test messages
python deploy.py
```

### Pattern 4 — Sessions

Demonstrates same-session context retention and cross-session isolation.

```bash
cd 04_sessions
export AGENT_ARN=<arn-from-pattern-01>
python session_demo.py
```

### Pattern 5 — Async Agents

Agent accepts a task, responds immediately with `accepted`, processes in the background (`@app.async_task`), and allows polling.

```bash
cd 05_async_agents
python async_agent.py    # local
python async_client.py   # polls until done
python deploy.py
```

### Pattern 6 — Memory Integration

Creates an AgentCore Memory resource with Semantic, UserPreference, and Summary strategies.  
`MemoryHookProvider` auto-loads recent turns on init, retrieves relevant memories per message, and persists every turn.

```bash
cd 06_memory
python memory_setup.py          # creates memory resource (once)
export MEMORY_ID=<id>
python agent_with_memory.py     # interactive chat loop
```

### Pattern 7 — Memory Branching (Travel Planner)

Three-agent system (coordinator + flight + hotel) using isolated memory branches for safe parallel execution.

```bash
cd 07_memory_branching
export MEMORY_ID=<id-from-pattern-06>
python travel_planner.py
```

### Pattern 8 — Identity Management

Creates a WorkloadIdentity, OAuth 2LO CredentialProvider, and demonstrates ABAC tag-based access control.

```bash
cd 08_identity
python identity_demo.py
```

### Pattern 9 — Gateway + Lambda Tools

Deploys an order management Lambda function and exposes it as three MCP tools through an AgentCore Gateway.

```bash
cd 09_gateway
python gateway_setup.py     # creates gateway + target (once)
export GATEWAY_ID=<id>
python gateway_client.py    # agent using gateway tools
```

### Pattern 10 — Code Interpreter

Agent executes Python code in a sandboxed environment for data analysis, algorithm implementation, and computation.

```bash
cd 10_code_interpreter
python code_interpreter_demo.py
```

### Pattern 11 — Browser Tool

Agent navigates live websites, extracts structured information, and summarises content.

```bash
cd 11_browser_tool
python browser_demo.py
```

## Required IAM Roles

| Role | Used By |
|------|---------|
| `BedrockAgentCoreExecutionRole` | AgentCore Runtime containers |
| `BedrockAgentCoreGatewayRole` | AgentCore Gateway → Lambda |
| `BedrockAgentCoreLambdaRole` | Lambda functions (Gateway targets) |

Run `python infra/iam_setup.py` to create all roles automatically.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AWS_DEFAULT_REGION` | AWS region (default: `us-west-2`) |
| `AWS_ACCOUNT_ID` | Your 12-digit AWS account ID |
| `MODEL_ID` | Bedrock model ID |
| `MEMORY_ID` | AgentCore Memory resource ID (after `memory_setup.py`) |
| `AGENT_ARN` | Deployed AgentCore Runtime ARN (after `deploy.py`) |
| `GATEWAY_ID` | AgentCore Gateway ID (after `gateway_setup.py`) |
| `BEARER_TOKEN` | Auth token for A2A client |
| `AGENTCORE_RUNTIME_URL` | Full runtime invocation URL |
| `ACTOR_ID` | Actor identifier for memory operations |
| `SESSION_ID` | Session identifier for memory operations |

## References

- [AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [AgentCore GitHub](https://github.com/aws/bedrock-agentcore)
- [Strands Agents](https://github.com/strands-agents/sdk-python)
- [FastMCP](https://github.com/jlowin/fastmcp)
