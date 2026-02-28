
# VibeCheck API - Product Requirements Document

## Project Overview

**Project:** VibeCheck API
**Event:** HackIllinois 2026 - Stripe Track: Best Web API
**Prize:** 1st: $2,000 + JBL headphones | Honorable mention: $500 + $100 Amazon GC
**Deployed at:** https://vibecheck-api.fly.dev (or similar)

**One-liner:** A public API that security-scans vibe-coded apps in two modes: lightweight (scans a GitHub repo or uploaded directory) and robust (AI agents red-team your running app through a WebSocket tunnel). IDE agents like Cursor can call it autonomously with a simple rules file.

---

## Architecture

```
                         ┌──────────────────────────────┐
                         │    VibeCheck API (Public)     │
                         │    vibecheck-api.fly.dev      │
                         │                              │
                         │  ┌───────┐  ┌─────────────┐ │
    GitHub ──clone──────▶│  │ Light │  │   Robust    │ │
                         │  │ weight│  │   Scanner   │ │
                         │  │Scanner│  │  (AI Agents)│ │
                         │  └───────┘  └──────┬──────┘ │
                         │                    │        │
                         │  ┌─────────────────▼──────┐ │
                         │  │   WebSocket Tunnel     │ │
                         │  │   Proxy Manager        │ │
                         │  └─────────────┬──────────┘ │
                         │                │            │
                         │  ┌──────────┐  │ ┌────────┐ │
                         │  │ SQLite/  │  │ │ Claude │ │
                         │  │ Postgres │  │ │  API   │ │
                         │  └──────────┘  │ └────────┘ │
                         └────────────────┼────────────┘
                                          │
                              WebSocket   │
                              Connection  │
                                          │
                         ┌────────────────▼────────────┐
                         │   Developer's Machine        │
                         │                              │
  ┌───────────┐          │  ┌────────────────────────┐ │
  │  Cursor / │──HTTP───▶│  │  vibecheck connect     │ │
  │  Claude   │  to API  │  │  (WS client)           │ │
  │  Code     │          │  │                        │ │
  └───────────┘          │  │  Proxies API requests  │ │
                         │  │  to localhost:3000     │ │
                         │  └────────────┬───────────┘ │
                         │               │             │
                         │  ┌────────────▼───────────┐ │
                         │  │  User's App            │ │
                         │  │  localhost:3000         │ │
                         │  └────────────────────────┘ │
                         └──────────────────────────────┘
```

### Lightweight Mode
1. User sends a GitHub repo URL (or directory contents) to the API
2. API clones the repo (or receives the files), analyzes code for vulnerabilities
3. Returns findings

### Robust Mode
1. User runs `vibecheck connect <port>` on their machine
2. Client opens a WebSocket to the public API, receives a session ID
3. User (or IDE agent) calls `POST /v1/assessments` with `mode: "robust"` and the session ID
4. API's AI agents generate HTTP requests to probe the app
5. API forwards each request through the WebSocket tunnel to the user's machine
6. Client makes the actual `localhost:<port>` request, sends the response back over WS
7. Agents analyze responses, adapt strategy, report findings

This is essentially a built-in reverse tunnel. No ngrok, no cloudflared, no third-party dependencies.

---

## Judging Criteria Alignment

**Functionality:** Both modes end-to-end working, proper HTTP status codes, error handling
**Usefulness & Creativity:** Real problem, novel approach (built-in WS tunnel + AI red teaming), trending topic
**API Design:** REST best practices, pagination, filtering, idempotency, multiple HTTP methods, stateful (assessments, tunnel sessions)
**Documentation & DX:** Auto-generated OpenAPI docs, cURL examples, IDE rules file, clear errors

---

## Tech Stack

| Component | Technology | Rationale |
|---|---|---|
| API Framework | FastAPI (Python) | Auto OpenAPI docs, async, WebSocket support built-in |
| AI Agents | Anthropic Claude API (tool use) | Agentic red teaming with tool calling |
| Static Analysis | Regex + entropy + Claude contextual analysis | Speed + intelligence |
| Database | SQLite (SQLAlchemy async) | Zero-config, swap to Postgres for prod |
| WebSocket Tunnel | FastAPI WebSocket + Python client script | Built-in, no third-party tunnel deps |
| Git Operations | `git` CLI (subprocess) or `gitpython` | Clone repos for lightweight scanning |
| Deployment | Fly.io | Free tier, bonus points for public API |
| Docs | FastAPI Swagger UI + ReDoc | Auto-generated from code |

---

## Data Models

### Assessment

```python
class Assessment:
    id: str                    # "asm_" + 12 hex chars
    mode: "lightweight" | "robust"
    status: "queued" | "cloning" | "analyzing" | "scanning" | "complete" | "failed"
    # Lightweight fields
    repo_url: str | None       # GitHub repo URL
    # Robust fields
    tunnel_session_id: str | None  # Links to an active WS tunnel
    agents: list[str] | None
    depth: str                 # "quick" | "standard" | "deep"
    context_limit: int          # Max chars sent to LLM (default 50000, max 500000; lightweight only)
    # Shared
    finding_counts: dict       # {critical, high, medium, low, info, total}
    idempotency_key: str | None
    error_type: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
```

### Finding

```python
class Finding:
    id: str                    # "fnd_" + 12 hex chars
    assessment_id: str
    severity: "critical" | "high" | "medium" | "low" | "info"
    category: str
    title: str
    description: str
    location: dict | None      # {file, line, column} or {url, method, parameter}
    evidence: dict | None      # {payload, response_code, response_preview}
    remediation: str
    agent: str | None
    created_at: datetime
```

### AgentLog

```python
class AgentLog:
    id: str                    # "log_" + 12 hex chars
    assessment_id: str
    agent: str
    step: int
    action: str
    target: str
    payload: str | None
    response_code: int | None
    response_preview: str | None
    reasoning: str
    finding_id: str | None
    timestamp: datetime
```

### TunnelSession

```python
class TunnelSession:
    id: str                    # "tun_" + 12 hex chars
    target_port: int           # Port on user's machine
    status: "connected" | "disconnected"
    created_at: datetime
    last_heartbeat: datetime
```

---

## API Endpoints

### Assessments

```
POST   /v1/assessments                Create scan (lightweight or robust)
GET    /v1/assessments                List assessments (paginated, filterable)
GET    /v1/assessments/{id}           Get status + summary
DELETE /v1/assessments/{id}           Delete assessment + findings + logs
POST   /v1/assessments/{id}/rerun     Re-run assessment
```

### Findings

```
GET    /v1/assessments/{id}/findings              Paginated, filterable
GET    /v1/assessments/{id}/findings/{finding_id}  Single finding
```

### Agent Logs

```
GET    /v1/assessments/{id}/logs      Agent activity (robust mode only)
```

### Tunnel

```
WebSocket  /v1/tunnel                 WebSocket endpoint for tunnel client
GET        /v1/tunnel/sessions        List active tunnel sessions
GET        /v1/tunnel/sessions/{id}   Get tunnel session status
```

### Reference

```
GET    /v1/agents                     List available agents
GET    /v1/agents/{name}              Agent detail
GET    /v1/health                     Health check
GET    /docs                          Swagger UI
GET    /redoc                         ReDoc
```

---

## Endpoint Specifications

### POST /v1/assessments

**Lightweight (GitHub repo):**
```json
{
  "mode": "lightweight",
  "repo_url": "https://github.com/user/my-vibe-coded-app",
  "context_limit": 50000
}
```

**Lightweight (direct file upload):**
```json
{
  "mode": "lightweight",
  "files": [
    {
      "path": "src/api/users.ts",
      "content": "import { db } from '../db';\n\nexport async function GET(req) {\n  const id = req.nextUrl.searchParams.get('id');\n  const user = await db.query(`SELECT * FROM users WHERE id = ${id}`);\n  return Response.json(user);\n}"
    },
    {
      "path": "package.json",
      "content": "{\"dependencies\": {\"next\": \"^14.0.0\", \"pg\": \"^8.11.0\"}}"
    }
  ],
  "context_limit": 100000
}
```

**Robust:**
```json
{
  "mode": "robust",
  "tunnel_session_id": "tun_a1b2c3d4e5f6",
  "agents": ["recon", "auth", "injection", "config"],
  "depth": "standard"
}
```

**Response (202 Accepted):**
```json
{
  "id": "asm_a1b2c3d4e5f6",
  "mode": "lightweight",
  "status": "queued",
  "repo_url": "https://github.com/user/my-vibe-coded-app",
  "created_at": "2026-02-28T12:00:00Z",
  "links": {
    "self": "/v1/assessments/asm_a1b2c3d4e5f6",
    "findings": "/v1/assessments/asm_a1b2c3d4e5f6/findings",
    "logs": "/v1/assessments/asm_a1b2c3d4e5f6/logs"
  }
}
```

**Errors:**
| Code | Status | When |
|---|---|---|
| INVALID_MODE | 400 | Mode not "lightweight" or "robust" |
| MISSING_REPO_URL | 400 | Lightweight with no repo_url and no files |
| MISSING_TUNNEL_SESSION | 400 | Robust with no tunnel_session_id |
| INVALID_REPO_URL | 400 | Cannot parse as GitHub URL |
| TUNNEL_NOT_CONNECTED | 400 | tunnel_session_id doesn't have an active connection |
| INVALID_AGENT | 400 | Unknown agent name |
| CLONE_FAILED | 502 | Failed to clone the repo (private, doesn't exist) |
| DUPLICATE_IDEMPOTENCY_KEY | 409 | Same key, different params |

### GET /v1/assessments

**Query params:** `page`, `per_page`, `mode`, `status`, `sort` (default "-created_at")

```json
{
  "data": [ ... ],
  "pagination": { "page": 1, "per_page": 20, "total": 42, "total_pages": 3 }
}
```

### GET /v1/assessments/{id}

```json
{
  "id": "asm_a1b2c3d4e5f6",
  "mode": "robust",
  "status": "complete",
  "tunnel_session_id": "tun_x1y2z3w4a5b6",
  "agents": ["recon", "auth", "injection", "config"],
  "depth": "standard",
  "created_at": "2026-02-28T12:00:00Z",
  "completed_at": "2026-02-28T12:03:45Z",
  "finding_counts": {
    "critical": 2, "high": 3, "medium": 1, "low": 0, "info": 2, "total": 8
  },
  "links": { ... }
}
```

### GET /v1/assessments/{id}/findings

**Query params:** `page`, `per_page`, `severity`, `category`, `agent`, `sort`

```json
{
  "data": [
    {
      "id": "fnd_x1y2z3w4a5b6",
      "severity": "critical",
      "category": "sql_injection",
      "title": "SQL Injection in /api/search endpoint",
      "description": "The search parameter is concatenated directly into a SQL query without parameterization.",
      "location": { "type": "endpoint", "url": "/api/search", "method": "GET", "parameter": "q" },
      "evidence": {
        "payload": "' OR 1=1 --",
        "response_code": 200,
        "response_preview": "Returned 847 rows (expected 0-1)"
      },
      "remediation": "Use parameterized queries instead of string concatenation.",
      "agent": "injection",
      "created_at": "2026-02-28T12:02:15Z"
    }
  ],
  "pagination": { ... }
}
```

### GET /v1/assessments/{id}/logs

Returns `400 LOGS_NOT_AVAILABLE` for lightweight mode.

```json
{
  "data": [
    {
      "id": "log_001a002b003c",
      "agent": "injection",
      "step": 3,
      "action": "POST /api/login with SQL payload in email field",
      "target": "/api/login",
      "payload": "admin' OR 1=1 --",
      "response_code": 200,
      "response_preview": "{\"token\": \"eyJhbG...\"}",
      "reasoning": "Login endpoint accepts email/password. Testing SQL injection in email to attempt auth bypass.",
      "finding_id": "fnd_x1y2z3w4a5b6",
      "timestamp": "2026-02-28T12:02:10Z"
    }
  ],
  "pagination": { ... }
}
```

### WebSocket /v1/tunnel

Client connects, server assigns a session ID. Protocol:

```
Client -> Server: {"type": "connect", "target_port": 3000}
Server -> Client: {"type": "session_created", "session_id": "tun_abc123"}

# During robust scan, server sends HTTP requests through the tunnel:
Server -> Client: {"type": "http_request", "request_id": "req_001", "method": "GET", "path": "/api/users", "headers": {...}, "body": null}
Client -> Server: {"type": "http_response", "request_id": "req_001", "status_code": 200, "headers": {...}, "body": "..."}

# Heartbeat to keep alive:
Server -> Client: {"type": "ping"}
Client -> Server: {"type": "pong"}
```

### GET /v1/tunnel/sessions

```json
{
  "data": [
    {
      "id": "tun_a1b2c3d4e5f6",
      "target_port": 3000,
      "status": "connected",
      "created_at": "2026-02-28T11:55:00Z",
      "last_heartbeat": "2026-02-28T12:04:30Z"
    }
  ]
}
```

### GET /v1/agents

```json
{
  "data": [
    {
      "name": "recon",
      "display_name": "Reconnaissance Agent",
      "description": "Maps routes, discovers hidden endpoints, admin panels, debug pages, directory listings, exposed files.",
      "categories": ["exposed_endpoints", "directory_listing", "debug_mode", "information_disclosure"],
      "mode": "robust"
    },
    {
      "name": "auth",
      "display_name": "Authentication Agent",
      "description": "Tests for missing auth, default credentials, broken access control (IDOR), session issues, privilege escalation.",
      "categories": ["missing_auth", "broken_access_control", "idor", "session_manipulation"],
      "mode": "robust"
    },
    {
      "name": "injection",
      "display_name": "Injection Agent",
      "description": "Probes for SQL injection, XSS, command injection, template injection with real payloads.",
      "categories": ["sql_injection", "xss", "command_injection", "template_injection"],
      "mode": "robust"
    },
    {
      "name": "config",
      "display_name": "Configuration Agent",
      "description": "Checks security headers, CORS, exposed stack traces, debug mode, server info disclosure.",
      "categories": ["cors_misconfiguration", "missing_headers", "exposed_stacktrace", "insecure_tls"],
      "mode": "robust"
    },
    {
      "name": "static",
      "display_name": "Static Analyzer",
      "description": "Analyzes source code for hardcoded secrets, vulnerable dependencies, insecure patterns, dangerous defaults.",
      "categories": ["hardcoded_secret", "vulnerable_dependency", "insecure_pattern", "dangerous_default"],
      "mode": "lightweight"
    }
  ]
}
```

### GET /v1/health

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "active_tunnels": 3,
  "agents_available": true
}
```

---

## Error Response Format

```json
{
  "error": {
    "type": "not_found",
    "message": "Assessment 'asm_abc123' not found.",
    "code": "ASSESSMENT_NOT_FOUND",
    "param": null,
    "doc_url": "https://vibecheck-api.fly.dev/docs#errors"
  }
}
```

---

## WebSocket Tunnel Protocol

### Server Side (in the API)

The API maintains a dict of active tunnel sessions, keyed by session ID. Each maps to an open WebSocket connection. When an AI agent needs to make an HTTP request to the target app:

1. Agent calls its `http_request` tool with a path like `/api/users`
2. The tool handler looks up the tunnel session for the current assessment
3. Sends an `http_request` message over the WebSocket with a unique request_id
4. Waits for the matching `http_response` message (with timeout)
5. Returns the response to the agent

```python
# Simplified server-side tunnel proxy
async def tunnel_request(session_id: str, method: str, path: str, headers: dict, body: str) -> dict:
    ws = active_tunnels[session_id]
    request_id = generate_id("req")
    
    await ws.send_json({
        "type": "http_request",
        "request_id": request_id,
        "method": method,
        "path": path,
        "headers": headers or {},
        "body": body
    })
    
    # Wait for response (with timeout)
    response = await pending_responses[request_id].wait(timeout=15)
    return response
```

### Client Side (tunnel connect script)

A standalone Python script the user runs. ~80 lines of code.

```bash
pip install vibecheck-client
vibecheck connect 3000

# Output:
# Connected to VibeCheck API
# Tunnel session: tun_a1b2c3d4e5f6
# Proxying to localhost:3000
# Ready for robust scanning.
```

The client:
1. Opens a WebSocket to `wss://vibecheck-api.fly.dev/v1/tunnel`
2. Sends `{"type": "connect", "target_port": 3000}`
3. Receives session ID, prints it
4. Listens for `http_request` messages
5. For each request, makes the actual HTTP call to `localhost:<port>` using httpx
6. Sends the response back over the WebSocket
7. Handles heartbeats to stay alive

---

## IDE Integration

### .cursor/rules (or equivalent)

IDE agents call the public API directly via HTTP. No auth needed (hackathon MVP). The rules file teaches the agent how.

```markdown
# VibeCheck Security Scanner

The VibeCheck API is running at https://vibecheck-api.fly.dev

## When to use
When the user asks to scan for security issues, check for vulnerabilities, audit security, or red-team their app.

## Lightweight Scan (code analysis)
For scanning the current project's code:

1. Gather the project's source files (focus on: route handlers, API endpoints, database queries, auth logic, config files, dependency manifests)
2. POST to https://vibecheck-api.fly.dev/v1/assessments:
   - If it's a public GitHub repo: {"mode": "lightweight", "repo_url": "https://github.com/user/repo"}
   - If you have local files: {"mode": "lightweight", "files": [{"path": "relative/path.ts", "content": "file contents"}, ...]}
   - Optional: set "context_limit" (default 50000, max 500000) to control how much code is sent to the LLM for deeper analysis
3. Poll GET /v1/assessments/{id} until status is "complete"
4. GET /v1/assessments/{id}/findings to retrieve results
5. Present findings grouped by severity, offer to fix each one

## Robust Scan (live red team)
For attacking a running application:

1. Ask the user what port their app is running on
2. Tell the user to run: vibecheck connect <port>
3. Ask the user for the tunnel session ID that was printed
4. POST to https://vibecheck-api.fly.dev/v1/assessments:
   {"mode": "robust", "tunnel_session_id": "<session_id>", "agents": ["recon", "auth", "injection", "config"], "depth": "standard"}
5. Poll GET /v1/assessments/{id} until status is "complete" (may take 2-5 minutes)
6. GET /v1/assessments/{id}/findings for vulnerabilities with evidence
7. GET /v1/assessments/{id}/logs for step-by-step agent reasoning
8. Present findings and offer to fix

## After fixing
Re-scan to verify: POST /v1/assessments/{id}/rerun

## Errors
If something fails, check error.message for guidance. Common issues:
- CLONE_FAILED: Repo is private or doesn't exist
- TUNNEL_NOT_CONNECTED: User needs to run vibecheck connect first
```

---

## Project Structure

```
vibecheck/
├── README.md
├── pyproject.toml
├── Dockerfile
├── fly.toml                     # Fly.io deployment config
├── .env.example
│
├── api/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, middleware, router registration
│   ├── config.py                # pydantic-settings
│   ├── database.py              # SQLAlchemy async engine
│   │
│   ├── models/
│   │   ├── assessment.py
│   │   ├── finding.py
│   │   ├── agent_log.py
│   │   └── tunnel_session.py
│   │
│   ├── schemas/
│   │   ├── assessment.py
│   │   ├── finding.py
│   │   ├── agent_log.py
│   │   ├── tunnel.py
│   │   └── errors.py
│   │
│   ├── routers/
│   │   ├── assessments.py
│   │   ├── findings.py
│   │   ├── logs.py
│   │   ├── agents.py
│   │   ├── tunnel.py            # WebSocket endpoint + session routes
│   │   └── health.py
│   │
│   ├── services/
│   │   ├── assessment_service.py
│   │   ├── lightweight_scanner.py  # Git clone + analysis
│   │   ├── robust_scanner.py       # Agent orchestration
│   │   └── tunnel_manager.py       # WebSocket session management
│   │
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── recon_agent.py
│   │   ├── auth_agent.py
│   │   ├── injection_agent.py
│   │   └── config_agent.py
│   │
│   └── utils/
│       ├── id_generator.py
│       ├── pagination.py
│       ├── errors.py
│       └── http_client.py       # Makes requests through WS tunnel
│
├── client/                      # Tunnel client (pip installable)
│   ├── pyproject.toml
│   └── vibecheck_client/
│       ├── __init__.py
│       └── cli.py               # `vibecheck connect <port>`
│
├── ide/
│   ├── cursor_rules.md
│   ├── claude_code_rules.md
│   └── README.md
│
├── examples/
│   ├── vulnerable-app/          # Intentionally vulnerable Flask app
│   │   ├── app.py
│   │   ├── requirements.txt
│   │   └── README.md
│   └── curl_examples.sh
│
└── tests/
    ├── conftest.py
    ├── test_health.py
    ├── test_assessments.py
    ├── test_findings.py
    ├── test_agents.py
    └── test_tunnel.py
