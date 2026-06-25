# Phase 2 Decision Inbox Local Verification

Date: 2026-06-18

Scope: local-only validation of Decision Inbox MCP v1. External ChatGPT Web connector evidence is recorded separately in `docs/phase-2-external-connector-verification.md`.

## Implemented Local Files

- `server/decision_inbox_store.py`
- `server/decision_inbox_server.py`
- `server/decision_inbox_http_server.py`
- `scripts/import_advice_review.py`

## MCP Tools

The local server currently exposes:

- `list_decision_tasks`
- `get_decision_package`
- `submit_advice`
- `get_task_status`

2026-06-23 update: `request_local_fact_check` remains a local file protocol
concept, but it is no longer exposed as a default Auto MCP web tool. The current
Auto MCP surface is package/advice/status only.

These tools are available over stdio and over the local Streamable HTTP endpoint `/mcp`.

It does not expose:

- arbitrary filesystem read,
- arbitrary filesystem write,
- shell commands,
- Git operations,
- dependency installation,
- secret inspection,
- automatic implementation of advisor output.

## Unit Tests

Command:

```bash
python3 -m unittest discover -s tests
```

Observed result on 2026-06-18:

```text
Ran 42 tests
OK
```

Additional connector-hygiene regression on 2026-06-21:

```text
Ran 50 tests
OK
```

Additional coverage:

- public base URL validation,
- Host header allowlisting,
- public MCP URL derivation,
- local connector doctor risk estimates,
- token and Owner-password status redaction in doctor output,
- OAuth protected-resource metadata,
- OAuth authorization-server metadata,
- dynamic client registration,
- Owner password authorization page,
- PKCE authorization-code token exchange,
- OAuth bearer-token access to `/mcp`,
- rejection of OAuth access tokens passed through query strings.

Covered behavior:

- task id validation,
- package read,
- task status read,
- advice write under `advice/`,
- fact-check request write under `fact-check-requests/`,
- exclusive create for advisor files,
- invalid task id rejection,
- missing task rejection,
- metadata mismatch rejection,
- MCP initialize/tools list/tools call behavior,
- HTTP `/mcp` POST behavior,
- bearer-token rejection,
- Origin rejection,
- unknown tool rejection,
- import review gate rendering.

## Stdio Smoke Test

Command shape:

```bash
python3 server/decision_inbox_server.py <<'JSONRPC'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"local-smoke-test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_decision_tasks","arguments":{}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_decision_package","arguments":{"task_id":"phase-1-package-only-mcp-review"}}}
{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"submit_advice","arguments":{"task_id":"phase-1-package-only-mcp-review","advisor":"Codex Local Smoke","content":"# Local Smoke Advisor Advice\n\nRecommendation: keep Decision Inbox MCP v1 package-only before adding read-only project context.\n\nExternal advice only. This is not authorization.","timestamp":"2026-06-18T13-40-00Z"}}}
{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"get_task_status","arguments":{"task_id":"phase-1-package-only-mcp-review"}}}
{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"get_decision_package","arguments":{"task_id":"../README"}}}
JSONRPC
```

Observed local result:

- `initialize` returned protocol version `2025-11-25` and only the `tools` capability.
- `tools/list` returned the package/advice/status Auto MCP tools.
- `list_decision_tasks` returned `phase-1-package-only-mcp-review`.
- `get_decision_package` returned the package Markdown for that task.
- `submit_advice` wrote `decision-inbox/tasks/phase-1-package-only-mcp-review/advice/2026-06-18T13-40-00Z-codex-local-smoke.md`.
- `get_task_status` returned `advice_count: 1` and `has_package: true`.
- Invalid task id `../README` returned `isError: true`.

## Import Review Gate

Command:

```bash
python3 scripts/import_advice_review.py phase-1-package-only-mcp-review
```

Observed local result:

- Output starts with `Current state: review_only`.
- Output sets `Risk status: needs_info`.
- Output sets `File changes: none`.
- Output sets `Commands run: read_only_only`.
- Output includes `Advisor output is not authorization`.
- Output includes the imported synthetic advice.

## External Connector Status

Complete on 2026-06-21.

See `docs/phase-2-external-connector-verification.md` for the ChatGPT Web positive and negative test results. That historical external test used the earlier five-tool v1 surface. The current Auto MCP Controlled Advisor surface is narrower and does not expose shell, Git, dependency installation, arbitrary file read, arbitrary file write, secrets, real project files, or local fact-check request tools.
