# Agent Decision Bridge MCP Lab

Agent Decision Bridge turns ChatGPT Web into a permission-tiered external
agent for Codex. Use stronger web models for deep reasoning, review, and
second opinions while Codex keeps local verification and execution control.

The short version:

- Use Codex as the local executor and fact checker.
- Use ChatGPT Web as an external advisor, project reader, or, in explicit
  high-risk mode, a connected Full-Agent.
- Pick one of three permission tiers instead of giving a web model unchecked
  access to your machine.
- Make Codex usage more durable by moving architecture review, strategy,
  tradeoff analysis, and second-opinion work into ChatGPT Web.

This project turns the current `agent-decision-bridge` manual workflow into a staged MCP automation experiment.

## Product Positioning

Agent Decision Bridge is for users who want the ChatGPT web app to participate
in Codex tasks without collapsing every task into a single risky "AI can do
everything" mode.

The product framing is:

```text
Codex = local fact checker and executor
ChatGPT Web = external agent / advisor
GPT-5.5 Pro = manual deep-reasoning consultant in Ask First
GPT-5.5 Thinking = MCP/App connector model for project-aware tool calls
```

This matters because ChatGPT Pro plans advertise higher usage capacity,
GPT-5.5 Pro reasoning, maximum Codex tasks, maximum deep research and agent
mode, and maximum memory/context. This project uses that web-side capacity as a
separate reasoning lane for Codex work. It does not literally multiply Codex
quota, but it can make Codex usage more durable by offloading review,
architecture judgment, risk analysis, and product decisions to ChatGPT Web
before Codex spends local execution effort.

It supports three product tiers:

1. **Ask First**: Codex prepares a focused package; the user manually asks a web
   advisor such as GPT-5.5 Pro, Claude, or Gemini. No MCP exposure. Risk `1/5`.
2. **Read-Only Project Advisor**: ChatGPT Web can read/search an allowed project
   root through MCP, but cannot write files or run commands. Risk `3/5-4/5`.
3. **Full-Agent Execution**: ChatGPT Web can access read/write/edit/search/bash
   tools inside an explicit allowed root. Write/edit/bash actions must ask for
   user approval of the exact file or command before tool use. Risk `5/5`.

For MCP/App connector tiers, use **GPT-5.5 Thinking** in ChatGPT Web. GPT-5.5
Pro can be used for the manual Ask First tier, but current ChatGPT Pro models
do not expose Apps/MCP connector tools.

The important boundary: GPT-5.5 Pro is strongest for the manual deep-consulting
path, while MCP/App connector work should use GPT-5.5 Thinking because Pro
models do not expose connector tools in the current ChatGPT product.

## Public HTTPS URL Policy

This project does not create or provide a shared public tunnel/domain for other
users. Each user must supply their own public HTTPS endpoint when they want
ChatGPT Web to call local MCP tools.

By tier:

- **Ask First** does not need Tailscale, Cloudflare, ngrok, or any public
  tunnel.
- **Read-Only Project Advisor** needs a public HTTPS endpoint only when
  ChatGPT Web should directly list/read/search the user's local project.
- **Full-Agent Execution** needs a public HTTPS endpoint for ChatGPT Web
  connector use, because the web app must reach the local Full-Agent MCP
  server.

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

For launch copy, see [`docs/product-promotion.zh.md`](docs/product-promotion.zh.md).

The default goal is not to let ChatGPT Web or another external model freely edit
local projects. The default goal is to reduce repetitive copy-paste while
preserving the safety model we already defined:

- Codex owns local fact checking and execution.
- ChatGPT Pro, Claude, Gemini, or another advisor model can review and suggest.
- External model instructions are advice, not user authorization.
- Level 2 Read-Only Project Advisor lets ChatGPT Web read and search allowed
  project roots without package generation, file writes, or shell execution.
- Level 3 Full-Agent mode is available only when explicitly requested with
  `--mode full-agent` and `--allowed-root`; it exposes local file tools and
  shell access and is always risk `5/5`.

## Current Status

Phase: Decision Inbox MCP v1 verified; Full-Agent high-risk mode implemented locally.

Verified on 2026-06-21:

- ChatGPT Web connected to the local Decision Inbox MCP server through a temporary HTTPS tunnel.
- ChatGPT Web listed the safe task, read the prepared decision package, and submitted advisor advice.
- Negative checks rejected path-like task ids and exposed no shell, Git, dependency installation, arbitrary read, or arbitrary write tools.
- Codex imported the submitted advice in review-only mode; external advice remains non-authoritative.

Implemented after verification:

- Default legacy HTTP mode is `auto-mcp`, exposing only package/advice/status tools.
- Product Level 2 HTTP mode is `read-only-project`, exposing only project
  read/search tools under configured allowed roots.
- Explicit `full-agent` mode exposes DevSpace-like file read/write/edit/search
  and bash tools under configured allowed roots.
- Full-Agent mode defaults to persistent OAuth state under
  `~/.local/share/agent-decision-bridge/` and must be revoked with the reset
  helper when no longer wanted.

This folder is the durable project context for future Codex threads. New threads should start by reading:

1. `README.md`
2. `PROJECT_CONTEXT.md`
3. `docs/plan.md`
4. `docs/security.md`
5. `docs/security-public.md`
6. `docs/architecture.md`
7. `docs/decision-inbox-protocol.md`
8. `docs/connector-runbook.md`
9. `docs/reusable-skill-public-mcp-safety.md`
10. `docs/conversation-product-mode.md`
11. `docs/level-3-user-flow.md`
12. `docs/phase-2-decision-inbox-local-verification.md`
13. `docs/phase-5-full-agent-live-verification.md`
14. `docs/level-3-completion-audit.md`
15. `docs/product-promotion.zh.md`

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
│   ├── architecture.md
│   ├── connector-runbook.md
│   ├── decision-inbox-protocol.md
│   ├── level-3-completion-audit.md
│   ├── level-3-user-flow.md
│   ├── phase-1-local-verification.md
│   ├── phase-1-restricted-access-test.md
│   ├── phase-2-decision-inbox-local-verification.md
│   ├── phase-2-external-connector-verification.md
│   ├── plan.md
│   ├── product-promotion.zh.md
│   ├── reusable-skill-public-mcp-safety.md
│   ├── security.md
│   ├── security-public.md
│   └── tailscale-funnel-verification.md
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

## Product Tiers

Level 1: Manual Package

- package/advice files only,
- no MCP exposure,
- risk `1/5`.

Level 2: Read-Only Project Advisor

- requires `--mode read-only-project` and `--allowed-root`,
- does not generate a decision package,
- exposes `open_workspace`, `ls`, `read`, `grep`, and `glob`,
- hard-blocks high-risk credential paths such as `.env*`, `.git`, SSH and
  cloud credential directories, private-key material, and known token/OAuth
  state files,
- otherwise lets the web advisor choose task-relevant files under the allowed
  root,
- no file writes,
- no shell,
- risk `3/5-4/5` depending on local/public exposure.

Level 3: Full-Agent Execution, explicit high-risk mode

- requires `--mode full-agent` and `--allowed-root`,
- exposes `open_workspace`, `read`, `write`, `edit`, `grep`, `glob`, `ls`, and `bash`,
- hard-blocks the same high-risk credential paths by default, but remains
  `5/5` because bash is not a sandbox and can affect the local machine,
- write/edit/bash are real Full-Agent capabilities; the product prompt requires
  action-level user approval before invoking each such tool,
- defaults to persistent OAuth state,
- recommended product path is a Codex-task session window:
  Codex opens Full-Agent, keeps it online across completed consultation steps,
  refreshes the timer on each new Level 3 use, and auto-closes 20 minutes after
  the last use,
- risk `5/5` while the session is open.

## Next Step

Use Manual Package for the safest flow. Use Read-Only Project Advisor when the
user wants ChatGPT Web to inspect project content without changing it. Use
Full-Agent only when the user intentionally wants a DevSpace-like coding
connector.

For Read-Only Project Advisor or Full-Agent connector calls, select
GPT-5.5 Thinking in ChatGPT Web. Do not select GPT-5.5 Pro for MCP/App
connector work: OpenAI's current ChatGPT docs say Pro models do not expose
Apps/MCP tools, while GPT-5.5 Thinking supports ChatGPT tools.

Read-Only Project Advisor and Full-Agent must be configured as two separate
ChatGPT connectors with two separate scopes:

- Read-Only Project Advisor: `read-only-project` scope.
- Full-Agent: `full-agent` scope.

Do not reuse one ChatGPT app as both the read-only advisor connector and the
execution connector. Legacy package-only Auto MCP can remain available for
compatibility under `auto-mcp` / `decision-inbox`, but it is no longer the
product Level 2.

The current optimization borrows DevSpace's self-hosted connector hygiene
without borrowing its broad workspace permissions:

- configure a public HTTPS base URL as an origin,
- derive a Host allowlist from that public URL,
- use OAuth Owner password approval for stable ChatGPT connector runs,
- keep Auto MCP OAuth persistence opt-in,
- default Full-Agent OAuth persistence outside the repo for repeated runs,
  with local reset support,
- keep short-lived bearer tokens only for local or temporary compatibility tests,
- require users to bring their own public HTTPS URL for Level 2 and Level 3
  connector runs,
- prefer a stable user-owned public URL for repeated ChatGPT connector runs,
- run `python3 scripts/decision_inbox_doctor.py` before exposing the endpoint,
- use a user-provided Tailscale Funnel endpoint when a stable no-owned-domain URL is needed.
- run `python3 scripts/decision_inbox_preflight.py` before asking ChatGPT Web to call tools,
- manage the public window with `scripts/decision_inbox_tunnel_window.py open/status/close`
  when using Tailscale Funnel.
- for Level 3, prefer `scripts/full_agent_session.py open/touch/status/close`;
  the default idle timeout is 1200 seconds.
- for user-facing Level 3 consultations, prefer
  `scripts/level3_consultation_flow.py prepare/capture/close`; it wraps the
  advisor gate, Full-Agent open, public health check, prompt generation, advice
  capture, and idle-window lifecycle into one bounded workflow.
- after a Level 3 answer returns, use
  `scripts/level3_consultation_flow.py capture`; it saves the advice as data,
  renders the review-only gate, refreshes the idle timer, and leaves the session
  open until 20 minutes after the last Level 3 use by default.
- for non-technical Level 3 usage, see `docs/level-3-user-flow.md`.

Do not start Full-Agent unless the user explicitly requests `--mode full-agent`
and chooses at least one allowed project root.

For the intended Level 3 user experience, the user should only need to ask
Codex for a Full-Agent consultation. Codex first checks that a real advisor
channel is available, then starts the session, checks the connector, asks the
external advisor, imports the result, classifies recommendations as `Adopt`,
`Ask`, or `Reject`, and lets the idle watchdog close the window 20 minutes after
the last Level 3 use.
When this repository is available, Codex should use
`scripts/level3_consultation_flow.py prepare` to open the short task window and
copy the compact ChatGPT Web prompt, then use `scripts/level3_consultation_flow.py
capture` after advice is captured. The capture step keeps the window open and
refreshes the idle timer by default; use `close` only for an explicit manual
shutdown. The wrapper no longer assumes browser automation is available by
default; Codex must explicitly mark an advisor channel such as `user-web`,
`browser-automation`, or `direct-tool` as `ready` before the `5/5` Full-Agent
window opens.

Important limitation: Full-Agent is an inbound ChatGPT Web connector, not a
GPT Pro API that Codex can automatically call by itself. The conversation
product flow in `docs/conversation-product-mode.md` requires Codex to detect
whether an advisor channel is available. If not, Codex must report
`waiting_for_advisor_channel` instead of pretending that GPT Pro was consulted.

Current Level 3 live status is recorded in
`docs/phase-5-full-agent-live-verification.md`: the Full-Agent connector tools
have been verified against this workspace, and multiple compact ChatGPT Web
Full-Agent consultations have succeeded. Earlier verification used a fixed
three-file safe set. The current product prompt now defaults to self-directed
task-relevant inspection under the allowed root, backed by server-side
high-risk credential path blocking and a required read/list/search report from
the advisor. Browser automation is usable but not yet frictionless: the
connector path works, while UI prompt entry can still need fallback handling.
The current maturity audit is recorded in
`docs/level-3-completion-audit.md`: Level 3 is classified as
`usable_short_window_user_web`, not yet a fully autonomous mature product.
Tailscale Funnel is currently classified as conditionally usable for short
Level 3 task windows: a 2026-06-24 retest passed `status
--check-public-health` 5/5 and ChatGPT Web successfully read the three default
files through the connector. It is not an always-on production endpoint yet,
because the local Tailscale daemon still reports a macOS Screen Time health
warning and direct public challenge latency can be high. Before each Level 3
web consultation, check the active session with `python3
scripts/full_agent_session.py status --check-public-health`. Cloudflare Named
Tunnel remains the stable fallback for long-lived public URLs, but the tested
Cloudflare account did not expose a selectable zone/domain for tunnel
authorization, so it is not configured in this lab yet.
