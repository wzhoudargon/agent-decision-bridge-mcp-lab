# MCP Server

This folder will hold the Decision Inbox MCP server prototype.

Current local file:

- `restricted_test_workspace_server.py`: a minimal stdio JSON-RPC MCP server for Phase 1 synthetic workspace access testing.
- `decision_inbox_store.py`: file-backed Decision Inbox storage with task id validation and restricted writes.
- `decision_inbox_server.py`: legacy package/advice/status server over stdio JSON-RPC.
- `full_agent_server.py`: workspace MCP backend with connected-agent, read-only-project, and full-agent profiles.
- `decision_inbox_http_server.py`: Streamable HTTP `/mcp` wrapper with mode selection, OAuth Owner password auth, optional/default OAuth state persistence by mode, bearer-token compatibility auth, Origin checks, Host allowlisting, and optional public base URL configuration.

## v1 Scope

The server should expose only decision-task exchange tools.

Candidate tools:

- `list_decision_tasks`
- `get_decision_package`
- `submit_advice`
- `get_task_status`

## v1 Non-Goals

Do not implement these in v1:

- arbitrary filesystem read,
- arbitrary filesystem write,
- shell command execution,
- Git operations,
- dependency installation,
- secret inspection,
- automatic implementation of advisor output.

The Phase 1 synthetic server is even narrower than the v1 Decision Inbox server. It exposes only read-only synthetic test files so connector allowlist behavior can be verified before package exchange is implemented.

The Decision Inbox server exposes only decision package exchange, advice
writeback, and task status tools. It can write advisor markdown only under a
task's `advice/` folder. Fact-check request files remain a local protocol
artifact, but the default Auto MCP web tool surface does not expose a
`request_local_fact_check` tool.

## Implementation Notes

Prefer a simple implementation first:

- plain files under `decision-inbox/`,
- human-readable Markdown,
- small JSON metadata files,
- explicit validation of task paths,
- no parent-directory traversal,
- no hidden filesystem expansion.

The file protocol is documented in `docs/decision-inbox-protocol.md`. Server implementation should follow that document before adding new tools or permissions.

## Running The Phase 1 Local Server

Run:

```bash
python3 server/restricted_test_workspace_server.py
```

The server reads newline-delimited JSON-RPC messages from stdin and writes newline-delimited JSON-RPC responses to stdout.

Available tools:

- `list_synthetic_files`
- `read_synthetic_file`

Default allowed root:

```text
test-workspace/synthetic-project/
```

Use `--root <path>` only for another synthetic test root. Do not point this server at a real project.

## Running The Decision Inbox MCP v1 Server

Run:

```bash
python3 server/decision_inbox_server.py
```

The server reads newline-delimited JSON-RPC messages from stdin and writes newline-delimited JSON-RPC responses to stdout.

Available tools:

- `list_decision_tasks`
- `get_decision_package`
- `submit_advice`
- `get_task_status`

Default tasks root:

```text
decision-inbox/tasks/
```

Do not point this server at a real project root. It expects Decision Inbox task directories only.

## Running The HTTP Server For ChatGPT Connector Testing

Default compatibility mode is `auto-mcp`. It exposes only the legacy
package/advice/status tools. Product workspace mode uses `connected-agent`.

Run locally with OAuth Owner password auth:

```bash
openssl rand -base64 32 > /tmp/decision-inbox-oauth-owner-token
chmod 600 /tmp/decision-inbox-oauth-owner-token

python3 server/decision_inbox_http_server.py \
  --mode auto-mcp \
  --host 127.0.0.1 \
  --port 8765 \
  --oauth-owner-token-file /tmp/decision-inbox-oauth-owner-token
```

Local MCP endpoint:

```text
http://127.0.0.1:8765/mcp
```

ChatGPT requires an HTTPS-reachable connector URL, so this local endpoint must be exposed through an approved temporary tunnel before ChatGPT Web can connect. Keep the tunnel temporary, use OAuth Owner password approval for ChatGPT connector runs, and shut the tunnel down after testing.

Before asking ChatGPT to call tools, run:

```bash
python3 scripts/decision_inbox_preflight.py \
  --mode auto-mcp \
  --public-base-url "https://decision-inbox.example.com" \
  --require-public
```

For Connected Agent:

```bash
python3 server/decision_inbox_http_server.py \
  --mode connected-agent \
  --host 127.0.0.1 \
  --port 8765 \
  --allowed-root "$PWD" \
  --oauth-owner-token-file /tmp/decision-inbox-oauth-owner-token
```

Expected tools: `open_workspace`, `ls`, `read`, `write`, `edit`, `grep`,
`glob`, `bash`, `enable_danger_auto`, `danger_auto_status`,
`disable_danger_auto`, `request_workspace_access`, and
`grant_workspace_access`. This mode does not generate or serve a decision
package. Write/edit/bash require approval by default. Danger Auto starts only
after `dangerously trust connected agent`.

For tunnel/reverse-proxy runs, provide the public origin without `/mcp`:

```bash
DECISION_INBOX_PUBLIC_BASE_URL="https://decision-inbox.example.com" \
python3 server/decision_inbox_http_server.py \
  --mode auto-mcp \
  --host 127.0.0.1 \
  --port 8765 \
  --oauth-owner-token-file /tmp/decision-inbox-oauth-owner-token
```

The public MCP endpoint is then:

```text
https://decision-inbox.example.com/mcp
```

The server derives its allowed Host headers from the local bind host and public
base URL. Use `--allow-host <host>` only for an intentional additional reverse
proxy host.

The server exposes OAuth discovery endpoints for MCP clients:

```text
/.well-known/oauth-protected-resource/mcp
/.well-known/oauth-authorization-server
/oauth/register
/oauth/authorize
/oauth/token
```

Static bearer-token auth through `DECISION_INBOX_MCP_TOKEN` is kept for local and
temporary compatibility testing. Do not put tokens in ChatGPT connector URLs
unless explicitly accepting the higher query-token risk.

OAuth client and token state is in memory by default. To let ChatGPT connector
authorization survive local server restarts, explicitly provide a state file
outside the repo:

```bash
AUTH_DIR="$HOME/.local/share/decision-inbox-mcp-lab"
mkdir -p "$AUTH_DIR"
chmod 700 "$AUTH_DIR"
openssl rand -base64 32 > "$AUTH_DIR/oauth-owner-token"
chmod 600 "$AUTH_DIR/oauth-owner-token"

python3 server/decision_inbox_http_server.py \
  --host 127.0.0.1 \
  --port 8765 \
  --oauth-owner-token-file "$AUTH_DIR/oauth-owner-token" \
  --oauth-state-file "$AUTH_DIR/oauth-state.json" \
  --oauth-refresh-token-ttl-seconds 604800
```

The OAuth state file contains access and refresh tokens. Treat it as secret
material, keep it at mode `0600`, and delete it with
`python3 scripts/reset_decision_inbox_auth.py` when revoking local connector
state.

## Running Connected Agent Mode

Connected Agent mode exposes local file read/write/edit/search and bash tools
to the connected MCP client under allowed roots. Bash runs with the local user
account; this is not a security sandbox.

Start Connected Agent with at least one allowed project root:

```bash
DECISION_INBOX_PUBLIC_BASE_URL="https://decision-inbox.example.com" \
python3 server/decision_inbox_http_server.py \
  --mode connected-agent \
  --host 127.0.0.1 \
  --port 8765 \
  --allowed-root "$HOME/work/my-project"
```

By default Connected Agent uses persistent auth files outside the repo:

```text
~/.local/share/agent-decision-bridge/oauth-owner-token
~/.local/share/agent-decision-bridge/oauth-state.json
```

Use `--oauth-state-file none` to disable Connected Agent OAuth persistence. To revoke
the default Connected Agent auth files:

```bash
python3 scripts/reset_decision_inbox_auth.py --full-agent-defaults
```

Risk coefficient for Connected Agent is `3/5-5/5`; Danger Auto is fixed `5/5`.

Before exposing the endpoint, run:

```bash
python3 scripts/decision_inbox_doctor.py
```

The doctor reports bearer-token and Owner-password presence, local probe status,
OAuth state-file status, public URL shape, and risk coefficient without printing
secret values.

For Connected Agent diagnostics:

```bash
python3 scripts/decision_inbox_doctor.py --mode connected-agent
```

Deprecated `full-agent` and `read-only-project` modes remain available only for
old connector tests.

## Importing Submitted Advice In Codex

Run:

```bash
python3 scripts/import_advice_review.py phase-1-package-only-mcp-review
```

This is a read-only helper. It prints an `agent-decision-bridge` Import Mode gate and does not classify or execute advisor recommendations.

## Verification

Every server tool should have a minimal local test or command-level verification note before being used with a web advisor.

Current local tests:

```bash
python3 -m unittest discover -s tests
```
