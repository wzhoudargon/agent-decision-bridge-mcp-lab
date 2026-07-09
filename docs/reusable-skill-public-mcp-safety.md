# Reusable Skill Public MCP Safety

This note defines the safety rules for turning this lab into reusable
`agent-decision-bridge` behavior for other users.

## Baseline

Public tunnels are scanned quickly. A reusable skill must assume that any public
MCP URL will receive probes for paths such as:

```text
/.env
/.git/config
/server-status
/wp-json/
/xmlrpc.php
```

The goal is not to prevent scans. The goal is to make scans harmless:

- no local file mapping,
- no token in URLs,
- no static file server,
- no shell/Git/dependency tools,
- no long-running public endpoint by default.

## DevSpace Reference

DevSpace treats public MCP access as remote access to the development machine.
Its safety model includes:

- narrow filesystem roots chosen by the user,
- OAuth approval with an Owner password,
- Host header allowlisting derived from the configured public URL,
- explicit MCP tool calls for coding actions,
- a public HTTPS URL supplied by the user through Cloudflare Tunnel, ngrok,
  Pinggy, Tailscale Funnel, or another reverse proxy,
- a warning that the tunnel URL should not be treated as a secret,
- warnings that shell commands are powerful and run as local commands,
- advice to avoid broad roots such as the home directory or filesystem root.

This is appropriate for a full local coding workspace, but it is broader than
Decision Inbox v1.

## What We Borrow

Connected Agent can borrow these DevSpace ideas:

- self-hosted local MCP server,
- public HTTPS base URL as an origin only,
- Host header allowlist,
- explicit user approval before public exposure,
- OAuth Owner password approval when a web connector supports OAuth discovery,
- optional OAuth state persistence outside the repo,
  stored outside the repo, and paired with a reset command,
- strong per-run secret,
- a local doctor command,
- a read-only preflight command that checks local/public endpoint reachability
  and tool allowlists before prompting ChatGPT,
- bounded tunnel lifecycle commands for open/status/close,
- clear tunnel setup and shutdown instructions,
- warning that public URLs are not secrets.

## What Connected Agent Must Still Guard

Connected Agent must not expose these capabilities without approval or
server-side policy:

- arbitrary file reads,
- sensitive path reads such as `.env`, `.git`, keys, credentials, and tokens,
- file edits by default,
- shell commands by default,
- Git operations,
- dependency installation,
- automatic implementation of advisor advice.
- local fact-check request tools that imply the web advisor can make Codex
  inspect the machine.

The hidden danger switch intentionally borrows controlled file and shell automation, but
only inside Connected Agent after the user typed
`dangerously trust connected agent`. It is always risk `5/5`. Normal product
use should keep Connected Agent online only for the active Codex task window
and auto-close after a short idle timeout.

## Required Default Behavior

Default mode for normal users:

```text
Ask First manual package export/import
no public tunnel
no local MCP exposure
risk coefficient: 1/5
```

Connected Agent public MCP mode must be opt-in and temporary:

```text
Connected Agent
explicit user confirmation
OAuth Owner password or short-lived token
short test window
automatic cleanup
explicit --allowed-root
persistent OAuth state by default
session-window lifecycle preferred
auto-close after 20 minutes idle
risk coefficient while active: 3/5-5/5
hidden danger switch risk coefficient: 5/5
OAuth scope: connected-agent
tools: open_default_workspace, open_workspace, ls, read, read_lines, write, edit, grep, glob, bash,
       enable_danger_auto, danger_auto_status, disable_danger_auto,
       grant_action_approval, request_workspace_access, grant_workspace_access
```

Public endpoint rule:

```text
users bring their own public HTTPS endpoint
the skill must not provide one shared maintainer domain for all users
```

Endpoint guidance:

| Option | Use when | Main strength | Main risk/tradeoff |
|---|---|---|---|
| Tailscale Funnel | The user has no domain and wants short verified task windows | No domain purchase; repeatable `.ts.net` hostname; easy close/reset | Local Tailscale health, DNS, proxy, and OS settings can make it intermittent |
| Cloudflare Quick Tunnel | One-off smoke tests | Free, fast, no domain setup | Random hostname; not durable for ChatGPT connector reuse |
| Cloudflare Named Tunnel | Stable repeated connector use | User-owned stable hostname and mature tunnel controls | Requires a Cloudflare account plus user-owned domain setup |
| ngrok / Pinggy | Temporary developer tests | Quick public HTTPS exposure | Stable URLs and policy controls depend on provider/tier |
| Custom HTTPS reverse proxy | Advanced users or teams | Full control over TLS/auth/logging/network policy | Requires secure ops setup |

Do not encourage users to share a single maintainer-owned tunnel/domain. That
would convert a local skill into a hosted broker and centralize other users'
local-machine access risk.

If query-string token auth is required, raise risk:

```text
risk coefficient: 4/5
```

## Server Requirements

A reusable Decision Inbox MCP server must:

- bind to `127.0.0.1` by default,
- respond only on `/mcp`,
- return `404` for all non-MCP paths,
- return `401` for `/mcp` without authentication,
- validate Host headers when public URL metadata is configured,
- never map URL paths to local filesystem paths,
- never serve static files from the project directory,
- never log token values,
- keep token material outside the repository,
- expose only package/advice/status tools.

## Workflow Requirements

Before opening a public tunnel:

1. Generate a fresh Owner password or token.
2. Run the local doctor.
3. Confirm public URL shape.
4. Confirm tool list is package-only.
5. Confirm any persistent OAuth state file is outside the repo and mode `0600`.
6. Run preflight.
7. Warn the user that public scanners are expected.

During the public window:

1. Run no-token negative check.
2. Run authenticated `tools/list`.
3. Run path traversal negative check.
4. Run unknown shell/Git tool negative check.
5. Complete the ChatGPT connector test.

After the public window:

1. Stop Funnel/tunnel.
2. Stop the local MCP server.
3. Delete the temporary token.
4. If OAuth state was persisted, run the local reset command for that state file.
5. Scan the repo for accidental token or tunnel URL residue.
6. Report final risk coefficient.

Connector profile rule:

- Ask First uses package files and does not need a workspace connector.
- Connected Agent uses the `connected-agent` scope and one workspace connector.
- Connected Agent default mode allows read/search/list and uses one-action
  approval before write/edit/bash: the tool returns `approval_id`, the user
  approves the exact action in chat, then ChatGPT calls `grant_action_approval`
  and retries the same action once.
- `dangerously trust connected agent` is not a separate connector or product
  mode. It is a session-only hidden danger switch inside Connected Agent,
  enabled only after the user types that exact phrase, and is always risk
  `5/5`.
- Legacy `read-only-project` and `full-agent` connector scopes may remain only
  for compatibility tests or old ChatGPT apps.

## Runtime Skill Candidate

If this behavior is promoted into the runtime `agent-decision-bridge` skill, add
only a short rule block. Do not turn the skill into a tunnel manual.

Candidate rule:

```text
For public MCP automation, default to no public exposure. Public tunnel use is
opt-in, short-lived, authenticated, and cleaned up immediately after the
connector test. Never expose shell, Git, dependency installation, arbitrary file
read/write, or real project workspace tools in Decision Inbox v1. Treat public
tunnel URLs as non-secret but actively scanned; tokens must not be placed in
query strings unless no other option exists, and that raises risk to 4/5.
```

Runtime skill modification requires explicit user approval after reviewing the
target file, benefit, risk, and rollback path.
