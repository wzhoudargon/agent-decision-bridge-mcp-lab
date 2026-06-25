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

Read-Only Project Advisor can borrow these DevSpace ideas:

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

## What Read-Only Project Advisor Does Not Borrow

Read-Only Project Advisor must not borrow these DevSpace capabilities:

- arbitrary file reads,
- sensitive path reads such as `.env`, `.git`, keys, credentials, and tokens,
- file edits,
- shell commands,
- Git operations,
- dependency installation,
- automatic implementation of advisor advice.
- local fact-check request tools that imply the web advisor can make Codex
  inspect the machine.

Full-Agent mode intentionally borrows file and shell capabilities, but only
when explicitly started with `--mode full-agent` and `--allowed-root`. It is
always risk `5/5`. Normal product use should keep Full-Agent online only for
the active Codex task window and auto-close after a short idle timeout.

## Required Default Behavior

Default mode for normal users:

```text
Ask First manual package export/import
no public tunnel
no local MCP exposure
risk coefficient: 1/5
```

Public MCP mode must be opt-in and temporary:

```text
Read-Only Project Advisor
explicit user confirmation
OAuth Owner password or short-lived token
short test window
automatic cleanup
risk coefficient while active: 3/5-4/5
OAuth scope: read-only-project
tools: open_workspace, ls, read, grep, glob
```

Full-Agent public MCP mode:

```text
explicit --mode full-agent
explicit --allowed-root
persistent OAuth state by default
session-window lifecycle preferred
auto-close after 20 minutes idle
file read/write/edit/search and shell tools
risk coefficient: 5/5
OAuth scope: full-agent
separate ChatGPT connector from Read-Only Project Advisor
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

Connector separation:

- Read-Only Project Advisor and Full-Agent must be two connector profiles, not
  one mutable profile.
- The read-only connector uses `read-only-project` scope and project read/search
  tools only.
- The execution connector uses `full-agent` scope and is always risk `5/5`.

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
