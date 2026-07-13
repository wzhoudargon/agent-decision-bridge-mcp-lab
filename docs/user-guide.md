# Agent Decision Bridge User Guide

Agent Decision Bridge lets Codex use ChatGPT Web as an external advisor or a
connected project reviewer without making web-model advice the source of local
authorization.

Use this guide as the main entry point. The other documents in this repository
are implementation notes, verification logs, and connector runbooks.

## What It Does

Agent Decision Bridge gives Codex two ways to involve another model:

1. **Ask First**: Codex prepares a focused review package. You send it to GPT
   Pro, Claude, Gemini, or another advisor. You bring the answer back to Codex.
2. **Connected Agent**: ChatGPT Web connects to a short-lived project window so
   it can inspect allowed project context and return advice. Codex then checks
   that advice locally.

Codex remains the local fact checker and executor. ChatGPT Web gives
recommendations. The user remains the final authorization source.

## When To Use It

Use Agent Decision Bridge when:

- a project architecture decision needs a stronger second opinion,
- a content, product, design, or code plan needs external review,
- the project context is too large to keep copying by hand,
- you want ChatGPT Web to participate in Codex work without turning it into an
  always-on unrestricted agent,
- you want a repeatable review workflow instead of loose copy-paste.

Do not use it to send secrets, credentials, private keys, private emails,
customer documents, or full proprietary code dumps to a web model.

## Mode 1: Ask First

Ask First is the safest mode.

Codex creates a self-contained review package with the goal, current facts,
assumptions, constraints, and requested output. You manually give that package
to GPT Pro or another advisor. After the advisor replies, you paste the answer
back into Codex. Codex then classifies recommendations and prepares next steps.

Risk: `1/5`.

Best for:

- GPT Pro deep reasoning,
- architecture and product strategy review,
- publishing or launch-readiness review,
- content-outline critique,
- cases where no public connector should be opened.

Example Codex request:

```text
Use Agent Decision Bridge Ask First to prepare a review package for this question:
Should this project architecture be simplified before launch?
```

Explicit first-tier wording such as `第一档`, `调用第一档`, or `Ask First`
selects this mode. A prepared package means only that the package is ready; it
does not mean GPT Pro or another advisor has already reviewed it.

## Canonical Vocabulary

Keep these domains separate:

- Product mode: `ask-first` or `connected-agent`.
- Advisor channel: `manual`, `user-web`, `browser-automation`, `direct-tool`,
  or `unknown`.
- Decision Inbox task status: `draft`, `package_ready`, `advice_submitted`,
  `needs_local_fact_check`, `review_complete`, or `closed`.
- Import decision: `Adopt`, `Adapt`, `Reject`, or `Need info`.
- Import execution gate: `review_only`, then `ready_for_user_authorization`,
  and only after current-user approval `ready_to_implement`.
- Connector/action status uses its own values, including
  `waiting_for_advisor_channel` and `approval_required`.

Do not treat `package_ready`, `manual_package_available`, or
`consultation_package_ready` as proof that an advisor was consulted.

## Mode 2: Connected Agent

Connected Agent is for project-aware ChatGPT Web review.

Codex opens or verifies a short project consultation window. ChatGPT Web uses a
connector to list, search, and read task-relevant files inside the allowed
project root. It returns advice. Codex imports that advice and checks it
against local facts before any action is taken.

In plain language, Connected Agent is a **controlled project executor**. It can
understand the project, propose a precise change, show what will change, apply
the approved change, and run preconfigured checks. It is not unrestricted
remote control of the computer.

Risk while online: `4/5-5/5`.

Best for:

- letting ChatGPT Web understand a real project structure,
- reducing manual context copying,
- comparing implementation or architecture options,
- turning ChatGPT Web from a chat box into a project-review entry point.

Example Codex request:

```text
Use Connected Agent to consult ChatGPT Web about whether this project structure
needs optimization.
```

## Connected Agent Requirements

Connected Agent needs three things:

1. An allowed project root.
2. A ChatGPT Web conversation using a model/chat mode that exposes Apps or MCP
   connector tools.
3. A user-provided public HTTPS endpoint for the local connector, such as
   Tailscale Funnel, Cloudflare Tunnel, ngrok, Pinggy, or a user-managed HTTPS
   reverse proxy.

In the Codex built-in ChatGPT dialog, or another ChatGPT surface that actually
exposes Connector/App tools, attach a user-created connector by typing `@` in
the composer and selecting its exact visible display name. The default
connector created for this project is named
`Agent Decision Bridge Connected Agent`. Do not merely type the name in prose,
and do not manually reconstruct the account-specific `plugin://...` reference;
the ChatGPT UI should create the connector chip/reference. Continue only after
the connector tools are visible in that conversation.

The current Connected Agent must expose its complete tool contract before a
task begins. If the attached conversation is missing tools, do not continue in
degraded mode: reopen the local session, start a fresh conversation, attach the
connector again through `@`, and verify the contract. If it remains incomplete,
update/re-publish or reinstall the connector before retrying.

GPT Pro is best used through Ask First when you want manual deep reasoning. For
Connected Agent, use a ChatGPT Web mode that actually shows the connector tools.
If the connector tools are not visible, Codex should stop at
`waiting_for_advisor_channel` instead of pretending the consultation happened.

## Normal Connected Agent Flow

1. You ask Codex for a Connected Agent consultation.
2. Codex confirms the allowed project root and advisor channel.
3. Codex opens or verifies the short connector window.
4. Codex prepares a compact prompt for ChatGPT Web.
5. ChatGPT Web inspects task-relevant project context through the connector.
6. ChatGPT Web returns advice.
7. Codex captures the advice as review data.
8. Codex classifies recommendations as `Adopt`, `Adapt`, `Reject`, or
   `Need info`.
9. The connector window is closed manually or by the idle watchdog.

Default helper:

```bash
python3 scripts/connected_agent_flow.py prepare \
  --allowed-root "$PWD" \
  --public-base-url "https://your-public-host.example.com" \
  --advisor-channel user-web \
  --advisor-health ready \
  "<question>"
```

After the answer comes back:

```bash
python3 scripts/connected_agent_flow.py capture \
  --advisor chatgpt-web-connected-agent \
  "<original question>"
```

Close explicitly when needed:

```bash
python3 scripts/connected_agent_flow.py close
```

## Safety Boundary

Default Connected Agent behavior:

- read, list, and search are allowed inside the opened allowed root,
- opening the second tier starts Controlled Auto,
- file creation, targeted edit, and ordinary project-local bash use a read-only
  `prepare_action` followed by a single token-only `commit_action`,
- an already previewed patch uses one ChatGPT-native connector confirmation in
  the bounded ChatGPT session helper, without a second `approval_id` exchange,
- Controlled Auto can apply a change shown by `preview_patch`, commit one
  immutable prepared action, or run an exact task returned by `list_tasks`,
- raw `write`, `edit`, and `bash` remain compatibility tools rather than the
  normal Controlled Auto workflow,
- high-risk credential paths are blocked by the server,
- external advice is never authorization,
- Codex keeps local verification and execution control.

Hard-blocked or approval-gated categories include:

- `.env*`, `.git`, private keys, SSH/cloud credentials, token or OAuth state,
- path escapes outside the allowed root,
- broad destructive moves or deletes,
- dependency installation,
- Git remote operations,
- network, browser, desktop, or clipboard control.

The hidden phrase `dangerously trust connected agent` is not a product mode. It
is a session-local high-risk switch inside Connected Agent. It remains fixed
risk `5/5` and does not remove the server-side hard blocks.

### The two permission choices inside Connected Agent

These are the two user-facing ways to operate the second tier:

1. **Controlled Auto**: default when you open the second tier. It may apply a
   previewed file change, commit one server-stored immutable write/edit/ordinary
   bash action after one native confirmation, or run a configured task.
   Low-level direct clients retain an internal Approval fallback, but it is not
   a user-facing mode.
2. **Danger Auto**: hidden expert switch at risk `5/5`. It allows more local
   automation but does not unlock secrets, networking, clipboard, desktop
   control, or paths outside the project.

## User Handoff Text

When Codex uses the safer `user-web` path, the handoff should be short:

```text
Open ChatGPT Web with the Connected Agent connector attached.
Paste and send the prompt that Codex prepared.
When ChatGPT finishes, paste the answer back into Codex.
Codex will classify the advice as Adopt / Adapt / Reject / Need info.
```

## Documentation Map

- `README.md`: project overview and current status.
- `docs/user-guide.md`: this user-facing guide.
- `docs/connected-agent-user-flow.md`: non-technical Connected Agent flow.
- `docs/conversation-product-mode.md`: exact conversation behavior.
- `docs/connector-runbook.md`: setup details for public endpoints and OAuth.
- `docs/security-public.md`: sanitized safety summary for web-advisor reads.
- `docs/architecture.md`: implementation architecture.
- `docs/decision-inbox-protocol.md`: legacy package/advice file protocol.

Current user-facing language is:

- **Ask First**
- **Connected Agent**
- **hidden danger switch** inside Connected Agent
