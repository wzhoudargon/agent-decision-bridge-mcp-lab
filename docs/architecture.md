# Architecture

## Current Manual Flow

```text
Codex
  -> creates decision package
User
  -> copies package to ChatGPT Pro / Claude / Gemini
External advisor
  -> returns advice
User
  -> copies advice back to Codex
Codex
  -> verifies local facts, classifies advice, waits for authorization
```

## Legacy Package MCP Flow

```text
Codex
  -> writes package to decision-inbox
ChatGPT Web
  -> uses MCP connector
MCP server
  -> reads package from decision-inbox
ChatGPT Web
  -> submits advice through MCP
MCP server
  -> writes advice to decision-inbox
Codex
  -> imports advice and runs review gate
```

This remains useful for compatibility and controlled tests, but it is no longer
the product Level 2.

## Product Mode Flow

```text
Level 1 Manual Package
  Codex -> creates package
  User -> manually sends package to GPT Pro
  User -> brings advice back

Level 2 Read-Only Project Advisor
  ChatGPT Web -> MCP connector
  MCP server -> opens allowed project root
  ChatGPT Web -> lists/reads/searches project files
  Codex -> receives advice and judges Adopt / Ask / Reject

Level 3 Full-Agent Execution
  ChatGPT Web -> MCP connector
  MCP server -> opens allowed project root
  ChatGPT Web -> reads/writes/edits/searches/runs bash
  Codex/User -> retain final authorization and review responsibility
```

## Components

### Codex

Role:

- local fact gatherer,
- package author,
- import reviewer,
- executor only after user authorization.

### Web Advisor

Role:

- second opinion,
- strategy reviewer,
- risk reviewer,
- alternative generator.

Not role:

- not local source of truth,
- not execution authority,
- not permission source.

### Decision Inbox

Role:

- file-based transfer layer between Codex and the MCP server.

Suggested structure:

```text
decision-inbox/
└── tasks/
    └── <task-id>/
        ├── metadata.json
        ├── package.md
        ├── advice/
        │   └── <timestamp>-<advisor>.md
        └── fact-check-requests/
            └── <timestamp>.md
```

The active lab structure includes:

- `decision-inbox/tasks/_template/` for new decision tasks.
- `decision-inbox/tasks/phase-1-package-only-mcp-review/` for the first package-only advisor review.
- `docs/decision-inbox-protocol.md` for the file protocol and validation rules.

### MCP Server

Role:

- exposes narrow tools for task package exchange.
- validates task ids and paths before reading or writing.
- writes advisor output only under the matching task's `advice/` directory.
- validates HTTP Origin and Host headers when exposed through the HTTP wrapper.

Not role in Auto MCP:

- not a filesystem browser,
- not a shell runner,
- not a full coding agent.
- not a local fact-check request executor.

### Connector Runtime

Role:

- runs the HTTP MCP endpoint locally,
- defaults to package/advice/status legacy Auto MCP for compatibility,
- switches to Read-Only Project Advisor with explicit `--mode read-only-project`,
- switches to Full-Agent only with explicit `--mode full-agent`,
- maps an optional public HTTPS origin to `/mcp`,
- derives allowed Host headers from the local bind host and public base URL,
- uses OAuth Owner password approval for stable ChatGPT connector runs,
- optionally persists OAuth client/access/refresh token state outside the repo,
- keeps static bearer-token auth for temporary/local compatibility tests,
- provides local diagnostics through `scripts/decision_inbox_doctor.py`.
- provides read-only endpoint/tool preflight through
  `scripts/decision_inbox_preflight.py`.
- provides Tailscale Funnel open/status/close lifecycle management through
  `scripts/decision_inbox_tunnel_window.py`.
- provides Full-Agent task-window lifecycle management through
  `scripts/full_agent_session.py`.
- prepares Manual Package / legacy package-only consultation tasks through
  `scripts/prepare_consultation.py`.

Not role:

- not an account-side ChatGPT app manager,
- not a shared tunnel provider,
- not a permission expansion beyond Decision Inbox unless Full-Agent is
  explicitly selected.

For Level 2 and Level 3 ChatGPT Web connector use, the user supplies the public
HTTPS endpoint. The project can validate a public base URL and manage local
task windows, but it does not provide a shared domain for other users' local
machines. Acceptable transports include Tailscale Funnel, Cloudflare Tunnel,
ngrok, Pinggy, or a user-managed HTTPS reverse proxy.

For repeated ChatGPT Web testing, prefer a stable public URL. Temporary tunnel
URLs are acceptable for one-off tests, but changing the URL usually requires an
explicit ChatGPT connector reconnect or recreation.

Read-Only Project Advisor and Full-Agent are different account-side connectors.
Legacy package-only Auto MCP remains separate:

```text
Legacy Auto MCP             -> OAuth scope decision-inbox
Read-Only Project Advisor   -> OAuth scope read-only-project
Full-Agent Execution        -> OAuth scope full-agent
```

The same ChatGPT app should not be reused across read-only and execution
connectors. Reuse creates stale endpoint/scope/tool-cache ambiguity and makes it
harder for the user to know whether the current conversation has read-only or
execution-level access.

## Read-Only Project Advisor Mode

The product second tier lets ChatGPT Web inspect necessary project context
directly without a decision package:

- `--mode read-only-project` is required,
- at least one `--allowed-root` is required,
- home and filesystem roots are rejected,
- tools include `open_workspace`, `ls`, `read`, `grep`, and `glob`,
- high-risk credential paths such as `.env*`, `.git`, SSH and cloud credential
  directories, private-key material, and known token/OAuth state files are
  blocked,
- other task-relevant project files may be chosen by the web advisor,
- writes and shell commands are not exposed,
- risk is `3/5-4/5`.

## Full-Agent Mode

DevSpace is powerful because it can let ChatGPT Web read, edit, search, and run
commands on a local workspace through MCP.

This lab now implements an explicit Full-Agent mode for that workflow:

- `--mode full-agent` is required,
- at least one `--allowed-root` is required,
- home and filesystem roots are rejected,
- tools include file read/write/edit/search and bash,
- high-risk credential paths are blocked by default,
- OAuth state is persistent by default under
  `~/.local/share/agent-decision-bridge/`,
- risk is always `5/5`.

Read-Only Project Advisor is the product second tier. The part borrowed by default is connector hygiene:
self-hosted server, explicit
public base URL, Host allowlist, local doctor, preflight, and cleanup discipline.

This lab starts narrower because the product value of `agent-decision-bridge` is the review gate:

- self-contained decision package,
- advisor reasoning,
- Codex fact checking,
- user authorization,
- stop rules for cross-model loops.

Full workspace execution access is now available only through the explicit
Full-Agent permission expansion, not through Read-Only Project Advisor.

## Full-Agent Session Window

Level 3 product use should route through a session manager instead of asking the
user to manually keep backend commands running.

```text
Codex task
  -> scripts/full_agent_session.py open
  -> Full-Agent HTTP MCP server
  -> Tailscale Funnel public URL
  -> ChatGPT Full-Agent connector
  -> advisor result
  -> Codex import/classification: Adopt / Ask / Reject
  -> scripts/full_agent_session.py touch after active steps
  -> watchdog closes server and Funnel after idle timeout
```

Responsibilities:

- session manager: process lifecycle, public window, preflight, idle shutdown,
- HTTP MCP server: OAuth, host/origin validation, Full-Agent tools,
- Codex: decide when to open/touch/close, import advice, classify recommendations,
- user: explicitly request Level 3 and choose/accept the allowed project root.

The session window shortens exposure time. It is not a sandbox and does not
lower the online risk below `5/5`.

## Advisor Invocation Boundary

Full-Agent is an inbound connector. It lets ChatGPT Web call local tools when
the ChatGPT conversation exposes the connector:

```text
ChatGPT Web -> MCP connector -> local Full-Agent tools
```

It does not automatically give Codex an outbound GPT Pro model call:

```text
Codex -/-> GPT Pro Web model
```

For ChatGPT Web connector calls, the user or automation should select
GPT-5.5 Thinking. GPT-5.5 Pro should not be used for MCP/App connector work
because current OpenAI ChatGPT docs say Pro models do not expose those tools.

Conversation product mode must therefore check the current advisor channel:

- `direct-tool`: Codex has a callable advisor tool and may complete the loop.
- `browser-automation`: the user authorized UI automation.
- `user-web`: the user will trigger ChatGPT Web manually while Codex keeps the
  connector/session ready.
- `manual`: Ask First package exchange.
- `unknown`: no available advisor channel; Codex must stop at
  `waiting_for_advisor_channel`.

The product must not create a package and imply that GPT Pro has reviewed it
unless returned advice exists through MCP, browser automation, a direct advisor
tool, or pasted user evidence.
