# Agent Decision Bridge

Agent Decision Bridge lets Codex use ChatGPT Web as an external advisor or a
connected project reviewer while Codex keeps local verification and execution
control.

Start here:

- [User Guide](docs/user-guide.md): the concentrated product and usage guide.
- [Connector Runbook](docs/connector-runbook.md): public endpoint, OAuth, and
  connector setup details.
- [Security Summary](docs/security-public.md): the short safety model for web
  advisor reads.

The short version:

- Use Codex as the local executor and fact checker.
- Use ChatGPT Web as an external advisor or a connected project agent with
  approval gates.
- Pick Ask First or Connected Agent instead of giving a web model unchecked
  access to your machine.
- Move architecture review, strategy, tradeoff analysis, and second-opinion
  work into ChatGPT Web before Codex spends local execution effort.

This project is the implementation lab and public documentation for the
`agent-decision-bridge` workflow.

## Product Positioning

Agent Decision Bridge is for users who want the ChatGPT web app to participate
in Codex tasks without collapsing every task into a single risky "AI can do
everything" mode.

The product framing is:

```text
Codex = local fact checker and executor
ChatGPT Web = external agent / advisor
GPT Pro or another strong web model = manual deep-reasoning consultant in Ask First
ChatGPT Web with Apps/MCP connector tools = project-aware Connected Agent reviewer
```

This does not literally multiply Codex quota. It makes Codex usage more durable
by offloading review, architecture judgment, risk analysis, and product
decisions to ChatGPT Web before Codex spends local execution effort.

The current product has two modes:

1. **Ask First**: Codex prepares a focused package; the user manually asks a web
   advisor such as GPT Pro, Claude, or Gemini. No MCP exposure. Risk `1/5`.
2. **Connected Agent**: ChatGPT Web connects to allowed project roots through
   MCP. Default mode auto-allows read/search/list. Write, edit, and bash return
   a one-action `approval_id`; after the user approves that exact action in
   chat, ChatGPT calls `grant_action_approval` and retries the same tool call.
   The exact phrase `dangerously trust connected agent` is only a hidden
   session switch for reducing repeated approvals during high-risk automation.
   It is not an additional product tier. It remains server-filtered and fixed
   risk `5/5` while active.

Legacy `auto-mcp`, `read-only-project`, and `full-agent` entry points remain as
deprecated aliases for old tests and existing ChatGPT connectors. New users
should choose **Ask First** or **Connected Agent**.

For Connected Agent, use a ChatGPT Web conversation that exposes Apps/MCP
connector tools. GPT Pro can still be used for the manual Ask First path when
you want deep reasoning without opening a connector.

The important boundary: a strong Pro-style web model is useful for manual
deep-consulting, while Connected Agent requires a ChatGPT Web mode where the
connector tools are actually visible.

## Public HTTPS URL Policy

This project does not create or provide a shared public tunnel/domain for other
users. Each user must supply their own public HTTPS endpoint when they want
ChatGPT Web to call local MCP tools.

By product tier:

- **Ask First** does not need Tailscale, Cloudflare, ngrok, or any public
  tunnel.
- **Connected Agent** needs a public HTTPS endpoint only when ChatGPT Web should
  directly call the local MCP server for project read/search/write/edit/bash
  under the configured allowed roots.

Supported endpoint choices are deliberately bring-your-own-provider:
Tailscale Funnel, Cloudflare Tunnel, ngrok, Pinggy, or a user-managed HTTPS
reverse proxy. For short tests, Tailscale Funnel or Cloudflare Quick Tunnel can
be enough. For repeated stable connector use, prefer a user-owned domain with
Cloudflare Named Tunnel or another stable HTTPS reverse proxy.

Endpoint choice guide:

| Option | When to use | Main advantage | Main tradeoff |
|---|---|---|---|
| Tailscale Funnel | No owned domain, short verified task windows | Stable `.ts.net` URL after login; easy to close | Can be affected by local Tailscale health, DNS, proxy, or Screen Time issues |
| Cloudflare Quick Tunnel | Temporary tests | Fast and free without domain setup | Random hostname, not suitable as a durable ChatGPT connector |
| Cloudflare Named Tunnel | Repeated stable connector use | Stable hostname on the user's own domain; strong tunnel/DNS management | Requires a Cloudflare account and user-owned domain setup |
| ngrok | Developer tests or paid reserved endpoint | Simple CLI and diagnostics | Stable URLs often require paid/reserved setup |
| Pinggy | Lightweight one-off tunnel | Quick temporary exposure | Less suited to polished long-term product use |
| Custom HTTPS reverse proxy | Advanced users/teams | Full control over TLS, auth, logs, and network policy | Requires ops knowledge and careful configuration |

Do not route multiple users through the maintainer's domain or tunnel. That
would turn this lab into a hosted broker for other people's local machines and
would centralize security, privacy, uptime, and abuse risk in one account.

## What This Is Not

- Not an always-on remote shell.
- Not a claim that external advice authorizes local changes.
- Not a Codex-owned GPT Pro API call.
- Not a replacement for local tests, file inspection, or user approval.
- Not a reason to expose secrets, unrestricted home directories, or real
  production credentials to a web model.

For current public wording, use [`docs/user-guide.md`](docs/user-guide.md).
The older Chinese launch draft in
[`docs/archive/product-promotion.zh.md`](docs/archive/product-promotion.zh.md)
is retained as historical material and may contain superseded model or mode
names.

The default goal is not to let ChatGPT Web or another external model freely edit
local projects. The default goal is to reduce repetitive copy-paste while
preserving the safety model we already defined:

- Codex owns local fact checking and execution.
- ChatGPT Pro, Claude, Gemini, or another advisor model can review and suggest.
- External model instructions are advice, not user authorization.
- Connected Agent lets ChatGPT Web inspect allowed project roots without package
  generation. Write/edit/bash use one-action approval by default.
- `dangerously trust connected agent` is a hidden danger switch inside
  Connected Agent, not an additional tier. It is session-only, fixed risk `5/5`, and
  still blocked by server-side secret-path and command policy.

## Current Status

Phase: Decision Inbox MCP verified; Connected Agent with the hidden danger
switch implemented locally.

Verified on 2026-06-21:

- ChatGPT Web connected to the local Decision Inbox MCP server through a temporary HTTPS tunnel.
- ChatGPT Web listed the safe task, read the prepared decision package, and submitted advisor advice.
- Negative checks rejected path-like task ids and exposed no shell, Git, dependency installation, arbitrary read, or arbitrary write tools.
- Codex imported the submitted advice in review-only mode; external advice remains non-authoritative.

Implemented after verification:

- Default legacy HTTP mode is `auto-mcp`, exposing only package/advice/status tools.
- Product HTTP mode `connected-agent` exposes project tools under configured
  allowed roots. Read/search/list are automatic; write/edit/bash return a
  one-action approval request unless the hidden danger switch is active.
- The hidden danger switch uses the fixed phrase
  `dangerously trust connected agent`, is session-only, and blocks network,
  GUI, clipboard, secret-path, path-escape, install, Git remote, and broad
  destructive command classes.
- Legacy `read-only-project` and `full-agent` modes remain available as
  deprecated aliases for existing connectors/tests.
- Workspace connector modes default to persistent OAuth state under
  `~/.local/share/agent-decision-bridge/` and must be revoked with the reset
  helper when no longer wanted.

This folder is the durable project context for future Codex threads. New threads should start by reading:

1. `README.md`
2. `docs/user-guide.md`
3. `PROJECT_CONTEXT.md`
4. `docs/plan.md`
5. `docs/security.md`
6. `docs/security-public.md`
7. `docs/architecture.md`
8. `docs/decision-inbox-protocol.md`
9. `docs/connector-runbook.md`
10. `docs/reusable-skill-public-mcp-safety.md`
11. `docs/conversation-product-mode.md`
12. `docs/connected-agent-user-flow.md`
13. `docs/phase-2-decision-inbox-local-verification.md`

## Directory Layout

```text
.
├── AGENTS.md
├── PROJECT_CONTEXT.md
├── README.md
├── decision-inbox/
│   ├── README.md
│   └── tasks/
│       ├── README.md
│       ├── _template/
│       │   ├── metadata.json
│       │   ├── package.md
│       │   ├── advice/
│       │   └── fact-check-requests/
│       └── phase-1-package-only-mcp-review/
│           ├── metadata.json
│           ├── package.md
│           ├── advice/
│           └── fact-check-requests/
├── docs/
│   ├── archive/
│   ├── architecture.md
│   ├── connected-agent-user-flow.md
│   ├── connector-runbook.md
│   ├── decision-inbox-protocol.md
│   ├── phase-1-local-verification.md
│   ├── phase-1-restricted-access-test.md
│   ├── phase-2-decision-inbox-local-verification.md
│   ├── phase-2-external-connector-verification.md
│   ├── plan.md
│   ├── reusable-skill-public-mcp-safety.md
│   ├── security.md
│   ├── security-public.md
│   ├── tailscale-funnel-verification.md
│   └── user-guide.md
├── server/
│   ├── decision_inbox_http_server.py
│   ├── decision_inbox_server.py
│   ├── decision_inbox_store.py
│   ├── full_agent_server.py
│   ├── README.md
│   └── restricted_test_workspace_server.py
├── scripts/
│   ├── decision_inbox_doctor.py
│   ├── reset_decision_inbox_auth.py
│   └── import_advice_review.py
└── test-workspace/
    ├── README.md
    └── synthetic-project/
        ├── sample-file-tree.txt
        ├── sample-open-question.md
        └── sample-project-notes.md
```

Test coverage:

```text
tests/
├── test_full_agent_server.py
├── test_decision_inbox_http_server.py
├── test_decision_inbox_server.py
├── test_decision_inbox_store.py
├── test_import_advice_review.py
└── test_restricted_test_workspace_server.py
```

## Intended Workflow

Manual workflow today:

1. Codex creates a decision package.
2. User copies it into ChatGPT Pro or another advisor.
3. Advisor returns recommendations.
4. User copies recommendations back to Codex.
5. Codex runs Import Mode: fact check, classify, plan, then wait for user authorization.

Target v1 workflow:

1. Codex writes a decision package into `decision-inbox/`.
2. ChatGPT Web uses an MCP connector to read that package.
3. ChatGPT Web submits advice back into `decision-inbox/`.
4. Codex imports the advice, checks local facts, and decides whether the loop should stop.

## Product Modes

Ask First

- package/advice files only,
- no MCP exposure,
- risk `1/5`.

Connected Agent

- requires `--mode connected-agent` and `--allowed-root`,
- does not generate a decision package,
- exposes `open_default_workspace`, `open_workspace`, `ls`, `read`,
  `read_lines`, `write`, `edit`, `grep`, `glob`, `bash`,
  `enable_danger_auto`, `danger_auto_status`, `disable_danger_auto`,
  `request_workspace_access`, and
  `grant_workspace_access`,
- prefers `open_default_workspace` when one allowed root is configured, so
  ChatGPT Web does not need to pass a local absolute path,
- supports `open_workspace` path `"default"` as the same no-local-path fallback
  when ChatGPT Web still exposes a stale connector schema without
  `open_default_workspace`,
- hard-blocks high-risk credential paths such as `.env*`, `.git`, SSH and
  cloud credential directories, private-key material, and known token/OAuth
  state files,
- otherwise lets the web advisor choose task-relevant files under the allowed
  root,
- reads normal task-relevant UTF-8 source files up to 1 MB; larger source files
  should be inspected with targeted `grep` plus bounded `read_lines` ranges,
- default prompts should skip `node_modules`, build outputs, sourcemaps, image
  galleries, and dependency artifacts unless the task explicitly requires them,
- read/search/list are automatic by default,
- write/edit/bash return a one-action `approval_id` by default; after the user
  approves the exact action in chat, ChatGPT calls `grant_action_approval` and
  retries the original tool call once with that `approval_id`,
- the hidden danger switch starts only after the user types
  `dangerously trust connected agent` in ChatGPT Web,
- the hidden danger switch can auto-run project-local write/edit and safe local
  bash, but still blocks network, browser/desktop, clipboard, secret-path,
  path-escape, dependency install, Git remote, and broad destructive command classes,
- defaults to persistent OAuth state for stable reconnects; hidden switch state
  itself is not persisted,
- recommended product path is a Codex-task session window:
  Codex opens Connected Agent, keeps it online across completed consultation steps,
  refreshes the timer on each new Connected Agent use, and auto-closes 20 minutes after
  the last use,
- risk `3/5-5/5`; the hidden danger switch is fixed `5/5`.

## Next Step

Use Ask First for the safest GPT Pro / Claude / Gemini flow. Use Connected
Agent when the user wants ChatGPT Web to inspect project content and, when
approved, write/edit/run safe local commands.

For Connected Agent connector calls, use a ChatGPT Web conversation where
Apps/MCP connector tools are visible. If the chosen model or chat mode does not
show connector tools, switch to a tool-capable ChatGPT mode or use Ask First
with GPT Pro instead.

Connected Agent uses one ChatGPT connector/scope:

- Connected Agent: `connected-agent` scope.

Legacy package-only Auto MCP can remain available for compatibility under
`auto-mcp` / `decision-inbox`. Legacy `read-only-project` and `full-agent`
scopes remain deprecated aliases for old connectors/tests, not the current
product model.

The current optimization borrows DevSpace's self-hosted connector hygiene
without borrowing its broad workspace permissions:

- configure a public HTTPS base URL as an origin,
- derive a Host allowlist from that public URL,
- use OAuth Owner password approval for stable ChatGPT connector runs,
- keep Auto MCP OAuth persistence opt-in,
- default Connected Agent OAuth persistence outside the repo for repeated runs,
  with local reset support,
- keep short-lived bearer tokens only for local or temporary compatibility tests,
- require users to bring their own public HTTPS URL for Connected Agent
  connector runs,
- prefer a stable user-owned public URL for repeated ChatGPT connector runs,
- run `python3 scripts/decision_inbox_doctor.py` before exposing the endpoint,
- use a user-provided Tailscale Funnel endpoint when a stable no-owned-domain URL is needed.
- run `python3 scripts/decision_inbox_preflight.py` before asking ChatGPT Web to call tools,
- manage the public window with `scripts/decision_inbox_tunnel_window.py open/status/close`
  when using Tailscale Funnel.
- for Connected Agent, prefer `scripts/full_agent_session.py open/touch/status/close`;
  the default idle timeout is 1200 seconds.
- for user-facing Connected Agent consultations, prefer
  `scripts/connected_agent_flow.py prepare/capture/close`; it wraps the
  advisor gate, Connected Agent open, public health check, prompt generation, advice
  capture, and idle-window lifecycle into one bounded workflow.
- after a Connected Agent answer returns, use
  `scripts/connected_agent_flow.py capture`; it saves the advice as data,
  renders the review-only gate, refreshes the idle timer, and leaves the session
  open until 20 minutes after the last Connected Agent use by default.
- for non-technical Connected Agent usage, see
  `docs/connected-agent-user-flow.md`.

Do not start Connected Agent unless the user explicitly requests project-aware
web connector use and chooses at least one allowed project root.

For the intended Connected Agent user experience, the user should only need to
ask Codex for a connected consultation. Codex first checks that a real advisor
channel is available, then starts the session, checks the connector, asks the
external advisor, imports the result, classifies recommendations as `Adopt`,
`Ask`, or `Reject`, and lets the idle watchdog close the window 20 minutes after
the last use.
When this repository is available, Codex should use
`scripts/connected_agent_flow.py prepare` to open the short task window and
copy the compact ChatGPT Web prompt, then use `scripts/connected_agent_flow.py
capture` after advice is captured. The capture step keeps the window open and
refreshes the idle timer by default; use `close` only for an explicit manual
shutdown. The wrapper no longer assumes browser automation is available by
default; Codex must explicitly mark an advisor channel such as `user-web`,
`browser-automation`, or `direct-tool` as `ready` before the Connected Agent
window opens. The product default is `--speed fast --output compact`; use
`--speed safe --output verbose` only for connector verification or debugging.

Important limitation: Connected Agent is an inbound ChatGPT Web connector, not a
GPT Pro API that Codex can automatically call by itself. The conversation
product flow in `docs/conversation-product-mode.md` requires Codex to detect
whether an advisor channel is available. If not, Codex must report
`waiting_for_advisor_channel` instead of pretending that GPT Pro was consulted.

Older full-agent and tiered-mode verification notes live under `docs/archive/`.
They are retained as evidence only and are not the current product
description. The current product prompt now defaults to self-directed
task-relevant inspection under the allowed root, backed by server-side
high-risk credential path blocking and a required read/list/search report from
the advisor. Browser automation is usable but not yet frictionless: the
connector path works, while UI prompt entry can still need fallback handling.
Tailscale Funnel is currently classified as conditionally usable for short
Connected Agent task windows: a 2026-06-24 retest passed `status
--check-public-health` 5/5 and ChatGPT Web successfully read the three default
files through the connector. It is not an always-on production endpoint yet,
because the local Tailscale daemon still reports a macOS Screen Time health
warning and direct public challenge latency can be high. Before each Connected Agent
web consultation, check the active session with `python3
scripts/full_agent_session.py status --check-public-health`. Cloudflare Named
Tunnel remains the stable fallback for long-lived public URLs, but the tested
Cloudflare account did not expose a selectable zone/domain for tunnel
authorization, so it is not configured in this lab yet.
