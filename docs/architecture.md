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
Level 1 Ask First
  Codex -> creates package
  User -> manually sends package to GPT Pro
  User -> brings advice back

Level 2 Connected Agent
  ChatGPT Web -> MCP connector
  MCP server -> opens allowed project root
  ChatGPT Web -> lists/reads/searches project files by default
  ChatGPT Web -> may write/edit/run safe local bash only after approval or hidden danger switch
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
- switches to Connected Agent with explicit `--mode connected-agent`,
- keeps `--mode read-only-project` and `--mode full-agent` only as deprecated
  compatibility aliases,
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
- provides Connected Agent task-window lifecycle management through
  `scripts/full_agent_session.py`.
- prepares Manual Package / legacy package-only consultation tasks through
  `scripts/prepare_consultation.py`.

Not role:

- not an account-side ChatGPT app manager,
- not a shared tunnel provider,
- not a permission expansion beyond Decision Inbox unless Connected Agent or a
  deprecated workspace connector mode is explicitly selected.

For Connected Agent ChatGPT Web connector use, the user supplies the public
HTTPS endpoint. The project can validate a public base URL and manage local
task windows, but it does not provide a shared domain for other users' local
machines. Acceptable transports include Tailscale Funnel, Cloudflare Tunnel,
ngrok, Pinggy, or a user-managed HTTPS reverse proxy.

For repeated ChatGPT Web testing, prefer a stable public URL. Temporary tunnel
URLs are acceptable for one-off tests, but changing the URL usually requires an
explicit ChatGPT connector reconnect or recreation.

Connected Agent is the V1.1 account-side connector. Legacy package-only Auto
MCP remains separate. Legacy Read-Only Project Advisor and Full-Agent scopes
are deprecated aliases for existing connectors and tests:

```text
Legacy Auto MCP             -> OAuth scope decision-inbox
Connected Agent             -> OAuth scope connected-agent
Read-Only Project Advisor   -> OAuth scope read-only-project  (deprecated)
Full-Agent Execution        -> OAuth scope full-agent          (deprecated)
```

Do not mutate one ChatGPT app back and forth between legacy scopes and
Connected Agent. Reuse can leave stale endpoint/scope/tool-cache ambiguity and
make the current access boundary unclear.

## Connected Agent Mode

The product second tier lets ChatGPT Web inspect and, when approved, modify
necessary project context directly without a decision package:

- `--mode connected-agent` is required,
- at least one `--allowed-root` is required,
- home and filesystem roots are rejected,
- tools include `open_workspace`, `ls`, `read`, `write`, `edit`, `grep`,
  `glob`, `bash`, `enable_danger_auto`, `danger_auto_status`,
  `disable_danger_auto`, `grant_action_approval`, `request_workspace_access`, and
  `grant_workspace_access`,
- high-risk credential paths such as `.env*`, `.git`, SSH and cloud credential
  directories, private-key material, and known token/OAuth state files are
  blocked,
- other task-relevant project files may be chosen by the web advisor,
- writes, edits, and bash use one-action approval by default: return
  `approval_id`, confirm with the user in chat, call `grant_action_approval`,
  then retry the same tool call once,
- The hidden danger switch starts only after the user typed
  `dangerously trust connected agent`,
- the hidden danger switch can auto-run project-local write/edit and safe local bash, but
  still blocks network, browser/desktop, clipboard, secret-path, path escape,
  dependency install, Git remote, and broad destructive command classes,
- risk is `3/5-5/5`; the hidden danger switch is fixed `5/5`.

## Deprecated Full-Agent Mode

DevSpace is powerful because it can let ChatGPT Web read, edit, search, and run
commands on a local workspace through MCP.

This lab keeps an explicit Full-Agent mode for compatibility with old connector
tests:

- `--mode full-agent` is required,
- at least one `--allowed-root` is required,
- home and filesystem roots are rejected,
- tools include file read/write/edit/search and bash,
- high-risk credential paths are blocked by default,
- OAuth state is persistent by default under
  `~/.local/share/agent-decision-bridge/`,
- risk is always `5/5`.

Connected Agent is the product second tier. The part borrowed by default is connector hygiene:
self-hosted server, explicit
public base URL, Host allowlist, local doctor, preflight, and cleanup discipline.

This lab starts narrower because the product value of `agent-decision-bridge` is the review gate:

- self-contained decision package,
- advisor reasoning,
- Codex fact checking,
- user authorization,
- stop rules for cross-model loops.

Workspace execution access is now available through Connected Agent approval
gates and the hidden danger switch, not through the legacy package-only Auto MCP flow.

## Connected Agent Session Window

Connected Agent product use should route through a session manager instead of asking the
user to manually keep backend commands running.

```text
Codex task
  -> scripts/full_agent_session.py open
  -> Connected Agent HTTP MCP server
  -> Tailscale Funnel public URL
  -> ChatGPT Connected Agent connector
  -> advisor result
  -> Codex import/classification: Adopt / Ask / Reject
  -> scripts/full_agent_session.py touch after active steps
  -> watchdog closes server and Funnel after idle timeout
```

Responsibilities:

- session manager: process lifecycle, public window, preflight, idle shutdown,
- HTTP MCP server: OAuth, host/origin validation, Connected Agent tools,
- Codex: decide when to open/touch/close, import advice, classify recommendations,
- user: explicitly request Connected Agent and choose/accept the allowed project root.

The session window shortens exposure time. It is not a sandbox and does not
lower the online risk below `5/5`.

## Advisor Invocation Boundary

Connected Agent is an inbound connector. It lets ChatGPT Web call local tools when
the ChatGPT conversation exposes the connector:

```text
ChatGPT Web -> MCP connector -> local Connected Agent tools
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
