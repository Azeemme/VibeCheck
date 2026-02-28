VibeCheck API
=============

AI‑powered security scanning for vibe‑coded applications. VibeCheck exposes a public HTTP API and WebSocket tunnel that can:

- **Lightweight mode**: statically analyze a GitHub repo or uploaded files for vulnerable dependencies, insecure patterns, hardcoded secrets, and config issues.
- **Robust mode** (scaffolded): red‑team a running app through a built‑in WebSocket reverse tunnel using AI agents.

The project is designed for **hackathon‑friendly DX**: zero auth, clear errors, OpenAPI docs, and a tiny tunnel client (`vibecheck connect`) you can run locally.

---

Table of Contents
-----------------

- [Architecture](#architecture)
- [Features](#features)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Requirements](#requirements)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running the API](#running-the-api)
  - [Running the Tunnel Client](#running-the-tunnel-client)
- [API Overview](#api-overview)
  - [Health](#health)
  - [Assessments](#assessments)
  - [Findings](#findings)
  - [Agent Logs](#agent-logs)
  - [Agents](#agents)
  - [Tunnel](#tunnel)
  - [Error Format](#error-format)
- [Lightweight Scanning Engine](#lightweight-scanning-engine)
  - [What It Detects](#what-it-detects)
  - [Scanner Modules](#scanner-modules)
- [Usage Examples](#usage-examples)
  - [Lightweight: GitHub Repo](#lightweight-github-repo)
  - [Lightweight: Direct File Upload](#lightweight-direct-file-upload)
  - [Robust Mode (High Level)](#robust-mode-high-level)
- [Development](#development)
  - [Running Tests](#running-tests)
  - [Code Style](#code-style)
- [Roadmap](#roadmap)

---

Architecture
------------

At a high level:

- The **VibeCheck API** runs on the internet and exposes `/v1/*` endpoints plus a WebSocket tunnel at `/v1/tunnel`.
- In **lightweight** mode the API:
  - Clones a public GitHub repo **or** accepts a list of files.
  - Runs a suite of static scanners.
  - Persists results as `Assessment` and `Finding` records.
- In **robust** mode (future prompts):
  - A small Python client opens a WebSocket to `/v1/tunnel`.
  - The API proxies HTTP requests via this tunnel to your local app (e.g. `localhost:3000`).
  - AI agents orchestrate real HTTP attacks and log their reasoning.

Conceptual diagram (from `PRD.md`):

- Public API (FastAPI + SQLite)
- Lightweight Scanner (static analysis)
- Robust Scanner (AI agents + HTTP tools)
- WebSocket Tunnel (FastAPI `WebSocket` + Python client)
- IDE / agents talk to the API over HTTP and optionally the tunnel.

---

Features
--------

- **FastAPI** backend with async SQLAlchemy and SQLite (aiosqlite).
- **Lightweight scanning engine**:
  - Vulnerable dependency detection against a small built‑in CVE table.
  - Regex‑based pattern scanning for SQLi, XSS, command injection, insecure deserialization, debug mode, and more.
  - Hardcoded secret detection using regexes and entropy heuristics.
  - Config analysis for `.gitignore`, Dockerfiles, Next.js config, `docker-compose`, `package.json` scripts.
  - Optional AI‑powered contextual analysis with Gemini.
- **Stateful assessments**:
  - `Assessment` tracks mode, status, errors, finding counts, and links.
  - `Finding` contains severity, category, location, evidence, and remediation text.
- **WebSocket tunnel** for robust mode (already scaffolded and tested).
- **Great DX**:
  - Self‑documenting OpenAPI at `/docs` and `/redoc`.
  - Consistent error envelope (`{"error": {...}}`).
  - Pagination, filtering and sorting across list endpoints.

---

Project Structure
-----------------

Key pieces of the repository:

```text
vibecheck/
├── pyproject.toml           # API package metadata + dependencies
├── .env.example             # Example environment variables
│
├── api/
│   ├── main.py              # FastAPI app, middleware, router registration
│   ├── config.py            # pydantic-settings Settings
│   ├── database.py          # Async SQLAlchemy engine + session factory
│   │
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── assessment.py
│   │   ├── finding.py
│   │   ├── agent_log.py
│   │   └── tunnel_session.py
│   │
│   ├── schemas/             # Pydantic response/request models
│   │   ├── assessment.py
│   │   ├── finding.py
│   │   ├── agent_log.py
│   │   ├── tunnel.py
│   │   ├── errors.py
│   │   └── pagination.py
│   │
│   ├── routers/             # FastAPI routers (HTTP + WebSocket)
│   │   ├── health.py
│   │   ├── agents.py
│   │   ├── assessments.py
│   │   ├── findings.py
│   │   ├── logs.py
│   │   └── tunnel.py
│   │
│   ├── services/
│   │   ├── tunnel_manager.py       # WebSocket session management
│   │   ├── lightweight_scanner.py  # Orchestrator for lightweight scans
│   │   └── scanners/               # Individual static scanners (+ optional LLM)
│   │       ├── dependency_scanner.py
│   │       ├── pattern_scanner.py
│   │       ├── secret_scanner.py
│   │       ├── config_scanner.py
│   │       └── claude_scanner.py   # Gemini-based contextual analyzer
│   │
│   └── utils/
│       ├── id_generator.py
│       ├── pagination.py
│       └── errors.py               # VibeCheckError and helpers
│
└── client/
    ├── pyproject.toml
    └── vibecheck_client/
        ├── __init__.py
        └── cli.py                  # `vibecheck connect <port>`
```

---

Getting Started
---------------

### Requirements

- Python **3.11+**
- `git` on your `PATH` (for cloning GitHub repos in lightweight mode)
- On Windows, PowerShell or a shell that can run `python` and `pip`

### Installation

From the `vibecheck` directory:

```bash
cd vibecheck
python -m pip install -e "."
```

This installs the API package and its dependencies (FastAPI, SQLAlchemy, aiosqlite, httpx, google-genai, etc.) into your current Python environment.

To install the tunnel client (for robust mode), from `vibecheck/client`:

```bash
cd client
python -m pip install -e .
```

This will expose a `vibecheck` command on your `PATH` (or you can run `python -m vibecheck_client.cli` directly).

### Configuration

Configuration is managed via `pydantic-settings` in `api/config.py`. The following environment variables are supported:

| Variable        | Default                                   | Description                                  |
|-----------------|-------------------------------------------|----------------------------------------------|
| `DATABASE_URL`  | `sqlite+aiosqlite:///./vibecheck.db`      | SQLAlchemy async database URL                |
| `GEMINI_API_KEY`| `""`                                      | Gemini API key (optional; for LLM analysis)  |
| `CLONE_DIR`     | `/tmp/vibecheck-repos`                    | Directory to clone GitHub repos into         |
| `DEBUG`         | `false`                                   | Enables SQLAlchemy engine echo logging       |

For local development, create a `.env` file next to `pyproject.toml`:

```env
DATABASE_URL=sqlite+aiosqlite:///./vibecheck.db
GEMINI_API_KEY=sk-gemini-...optional...
CLONE_DIR=/tmp/vibecheck-repos
DEBUG=true
```

The settings are loaded into `api.config.settings`.

### Running the API

From `vibecheck`:

```bash
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Then open:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Running the Tunnel Client

Robust mode uses a small local client that exposes your app via WebSocket tunnel to the VibeCheck API.

1. Start your app locally, e.g. `http://localhost:3000`.
2. In another shell:

```bash
vibecheck connect 3000 --server ws://localhost:8000/v1/tunnel
```

You should see:

```text
Connecting to ws://localhost:8000/v1/tunnel...
Connected to VibeCheck API
Tunnel session: tun_xxx...
Proxying to localhost:3000
Ready for robust scanning.
```

You then use that `tunnel_session_id` when creating robust assessments.

---

API Overview
------------

All endpoints are versioned under `/v1` (except the WebSocket, which is mounted by the `Tunnel` router but lives at `/v1/tunnel`).

### Health

- `GET /v1/health`  
  Returns a simple health document:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "active_tunnels": 0,
  "agents_available": true
}
```

### Assessments

Assessments represent scan runs (lightweight or robust).

- `POST /v1/assessments` – create a new assessment
- `GET /v1/assessments` – list assessments (paginated, filterable)
- `GET /v1/assessments/{id}` – get a single assessment
- `DELETE /v1/assessments/{id}` – delete an assessment and its findings/logs
- `POST /v1/assessments/{id}/rerun` – rerun an existing assessment

Important fields on the `Assessment` resource:

- `mode`: `"lightweight"` or `"robust"`.
- `status`: `"queued" | "cloning" | "analyzing" | "scanning" | "complete" | "failed"`.
- `repo_url` or `files` (for lightweight).
- `context_limit`: max characters of source code sent to the LLM (default 50,000, max 500,000; lightweight mode only).
- `tunnel_session_id`, `agents`, `depth` (for robust).
- `finding_counts`: counts of findings per severity.
- `error_type` and `error_message` when a scan fails.
- `links`: `self`, `findings`, and `logs` URLs.

### Findings

- `GET /v1/assessments/{id}/findings`  
  Paginated list of findings for an assessment.

Query parameters:

- `page`, `per_page` – standard pagination.
- `severity` – filter by severity (`critical`, `high`, `medium`, `low`, `info`).
- `category` – filter by category (e.g. `sql_injection`).
- `agent` – filter by agent (currently `"static"` in lightweight mode).
- `sort` – defaults to `"severity"`, with domain ordering (critical → info) or by another column.

- `GET /v1/assessments/{id}/findings/{finding_id}`  
  Return a single finding (404 if not found or not associated with that assessment).

### Agent Logs

- `GET /v1/assessments/{id}/logs`  
  Returns step‑by‑step agent activity for **robust** assessments.

For **lightweight** mode, this endpoint returns a `400` error with code `LOGS_NOT_AVAILABLE`.

### Agents

- `GET /v1/agents` – static list of available agents (recon, auth, injection, config, static).
- `GET /v1/agents/{name}` – single agent details, or `AGENT_NOT_FOUND` (404) if not known.

### Tunnel

- `WebSocket /v1/tunnel` – entrypoint for the tunnel client.
  - Client sends `{"type": "connect", "target_port": 3000}`.
  - Server replies with `{"type": "session_created", "session_id": "tun_..."}`.
  - During robust assessments the API sends `http_request` messages and expects `http_response` replies.
- `GET /v1/tunnel/sessions` – list all `TunnelSession` records.
- `GET /v1/tunnel/sessions/{id}` – details for a single session (404 if missing).

### Error Format

All errors are normalized to:

```json
{
  "error": {
    "type": "not_found",
    "message": "Assessment 'asm_abc123' not found.",
    "code": "ASSESSMENT_NOT_FOUND",
    "param": null
  }
}
```

Backend code raises `VibeCheckError`, which carries:

- `type` – high‑level category (`validation_error`, `not_found`, `conflict`, `tunnel_error`, etc.).
- `message` – human‑readable string.
- `code` – machine‑readable code (e.g. `CLONE_FAILED`, `DUPLICATE_IDEMPOTENCY_KEY`).
- `status_code` – HTTP status (e.g. 400, 404, 409, 502).
- `param` – optional parameter name associated with the error (e.g. `"mode"`, `"agents"`).

For Pydantic validation errors, the API returns:

```json
{
  "error": {
    "type": "validation_error",
    "message": "...",
    "code": "VALIDATION_ERROR"
  }
}
```

---

Lightweight Scanning Engine
---------------------------

When you POST a lightweight assessment, the API queues a background task:

1. **Input**:
   - `mode: "lightweight"`.
   - Either `repo_url` (GitHub) or `files` (array of `{path, content}`).
2. **Clone or hydrate files**:
   - If `repo_url` is provided, the API:
     - Sets `status = "cloning"`.
     - Clones the repo into `CLONE_DIR/<assessment_id>` using `git clone --depth 1`.
     - Walks the tree and loads relevant files (code + config).
   - Else it uses the `files` array as‑is.
3. **Analyze**:
   - Sets `status = "analyzing"`.
   - Runs all scanners over the in‑memory file list.
4. **Persist findings**:
   - For each scanner result, creates a `Finding` row.
   - Increments the `finding_counts` per severity.
5. **Finalize**:
   - Sets `status = "complete"` and `completed_at` timestamp.
   - On errors, sets `status = "failed"`, `error_type` and `error_message`.
   - Cleans up any cloned repository directory.

### What It Detects

Out of the box, the lightweight engine can detect:

- **Vulnerable dependencies** (Node.js and Python) against a curated list of popular CVEs:
  - `express`, `jsonwebtoken`, `lodash`, `axios`, `node-fetch`, `minimist`, `qs`, `tar`, `glob-parent`, `next`, `sequelize`, `mysql2`, `helmet`, `cors`, `passport`.
  - `flask`, `django`, `pyyaml`, `requests`, `urllib3`, `pillow`, `cryptography`, `jinja2`, `sqlalchemy`, `werkzeug`.
- **Insecure patterns** in source code:
  - SQL injection via string concatenation, template literals, Python f‑strings, ORM `.raw()` calls.
  - XSS via `innerHTML`, `dangerouslySetInnerHTML`, `v-html`.
  - Code / command injection via `eval`, `exec`, `new Function`, `child_process.exec`, `os.system`, `subprocess.run(..., shell=True)` patterns.
  - Insecure deserialization with `pickle` and `yaml.load` without `SafeLoader`.
  - Missing input validation for common `req.params/query/body` access patterns.
  - Debug mode enabled (generic `DEBUG = true`/`True` and Flask `app.run(debug=True)`).
  - CORS misconfiguration (`Access-Control-Allow-Origin: *`, permissive middleware).
  - Logging of sensitive values (passwords, tokens, secrets).
- **Hardcoded secrets**:
  - AWS access and secret keys.
  - GitHub, Stripe, Slack, SendGrid, Twilio, Google API keys.
  - JWT secrets, DB URLs with credentials, PEM private keys.
  - High‑entropy strings in `*secret*/*key*/*token*/*password*` assignments.
- **Config issues**:
  - `.env` present but not ignored in `.gitignore`.
  - Missing `.gitignore` file.
  - Docker images running as root or copying `.env` into the image.
  - Risky `next.config.*` settings (disabled strict mode, wildcard image domains).
  - `package.json` install lifecycle scripts (`preinstall` / `postinstall`).
  - `docker-compose` services bound to `0.0.0.0` ports.
- **Contextual issues** (optional, via LLM):
  - Business logic flaws, broken auth/authorization, data exposure, cryptographic misuse, etc., based on a prompt‑driven code review.

### Scanner Modules

- `dependency_scanner.scan(files, project_info)`  
  - Uses dependency metadata from `detect_project_info` to find vulnerable libraries.
  - Emits `vulnerable_dependency` findings with `evidence.cve` and `installed_version`.

- `pattern_scanner.scan(files)`  
  - Regex‑based static analysis over source files.
  - Emits categories like `sql_injection`, `xss`, `code_injection`, `command_injection`, `debug_mode`, `cors_misconfiguration`, `information_disclosure`.

- `secret_scanner.scan(files)`  
  - Pattern and entropy‑based secret detection.
  - Redacts secrets in snippets (`JWT_SECR*****************123"`‑style).
  - Emits `hardcoded_secret` findings.

- `config_scanner.scan(files, project_info)`  
  - Looks at `.gitignore`, Dockerfiles, Next.js config, `docker-compose`, `package.json`.
  - Emits `exposed_secrets`, `missing_gitignore`, `container_security`, `network_exposure`, `framework_config`, `supply_chain`.

- `claude_scanner.scan(files, project_info, max_chars=50_000)`  
  - If `GEMINI_API_KEY` is set, sends a prioritized subset of files (up to `max_chars` characters) to a Gemini model.
  - `max_chars` is controlled by the `context_limit` parameter on the assessment request (default 50,000, max 500,000).
  - Asks for JSON‑formatted findings with severity/category/title/description/location/remediation.
  - Safely ignored if the call fails.

---

Usage Examples
--------------

### Lightweight: GitHub Repo

Create a new assessment that scans a public GitHub repository:

```bash
curl -X POST "http://localhost:8000/v1/assessments" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "lightweight",
    "repo_url": "https://github.com/user/my-vibe-coded-app"
  }'
```

To send more code to the LLM for deeper analysis, set `context_limit` (default 50,000, max 500,000):

```bash
curl -X POST "http://localhost:8000/v1/assessments" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "lightweight",
    "repo_url": "https://github.com/user/my-vibe-coded-app",
    "context_limit": 200000
  }'
```

Response (202 Accepted):

```json
{
  "id": "asm_...",
  "mode": "lightweight",
  "status": "queued",
  "repo_url": "https://github.com/user/my-vibe-coded-app",
  "created_at": "2026-02-28T12:00:00Z",
  "links": {
    "self": "/v1/assessments/asm_...",
    "findings": "/v1/assessments/asm_.../findings",
    "logs": "/v1/assessments/asm_.../logs"
  }
}
```

Then poll until `status` becomes `"complete"`:

```bash
curl "http://localhost:8000/v1/assessments/asm_..."
```

And fetch findings:

```bash
curl "http://localhost:8000/v1/assessments/asm_.../findings"
```

### Lightweight: Direct File Upload

Scan an ad‑hoc bundle of files:

```bash
curl -X POST "http://localhost:8000/v1/assessments" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "lightweight",
    "files": [
      {
        "path": "app.py",
        "content": "import os\nJWT_SECRET = \"supersecret123\"\ndb.execute(f\"SELECT * FROM users WHERE id = {request.args.get('id')}\")\nos.system(\"rm -rf \" + user_input)\napp.run(debug=True)"
      },
      {
        "path": "package.json",
        "content": "{\"dependencies\": {\"express\": \"4.17.0\", \"jsonwebtoken\": \"8.5.0\", \"lodash\": \"4.17.19\"}}"
      }
    ]
  }'
```

This should produce:

- `hardcoded_secret` finding for `JWT_SECRET`.
- `sql_injection` finding for the f‑string `db.execute(...)`.
- `command_injection` finding for `os.system("rm -rf " + user_input)`.
- `debug_mode` findings for `app.run(debug=True)`.
- `vulnerable_dependency` findings for `express`, `jsonwebtoken`, and `lodash`.

### Robust Mode (High Level)

Robust mode wiring is scaffolded but the agent logic is intentionally left for a later prompt. The flow will be:

1. User runs the tunnel client:

   ```bash
   vibecheck connect 3000 --server ws://localhost:8000/v1/tunnel
   ```

2. The client prints a `tunnel_session_id`, e.g. `tun_418ad471b5fc`.
3. User creates a robust assessment:

   ```bash
   curl -X POST "http://localhost:8000/v1/assessments" \
     -H "Content-Type: application/json" \
     -d '{
       "mode": "robust",
       "tunnel_session_id": "tun_418ad471b5fc",
       "agents": ["recon", "auth", "injection", "config"],
       "depth": "standard"
     }'
   ```

4. In future prompts, AI agents will send `http_request` messages via the WebSocket tunnel and log their activity as `AgentLog` records.

---

Development
-----------

### Running Tests

If you add a `tests/` directory as described in the PRD, you can run tests with:

```bash
pytest
```

Make sure your test suite starts and stops the FastAPI app appropriately, or uses `TestClient`.

### Code Style

- Python 3.11+ typing (`list[str]`, `str | None`, `Literal[...]`).
- Async SQLAlchemy 2.x style (`select()`, async sessions).
- Pydantic v2 models and `ConfigDict(from_attributes=True)` for ORM integration.
- Avoid redundant comments; keep docstrings focused on behavior and constraints.

---

Roadmap
-------

Potential extensions and follow‑ups:

- Implement the **robust scanner** agent orchestration using an LLM (Gemini).
- Store full **AgentLog** traces for robust assessments.
- Add **examples/**:
  - Intentionally vulnerable demo apps in different frameworks.
  - Ready‑to‑run `curl` and `httpie` scripts.
- Wire up **CI** for linting and tests.
- Add **Fly.io** deployment config (`fly.toml` + Dockerfile) and publish a public instance.

For detailed product requirements and design decisions, see `PRD.md` at the repo root.

