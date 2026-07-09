# Conversation Product Mode

This document defines the user-facing behavior for `agent-decision-bridge` when
the user asks in natural language, for example:

```text
Use Connected Agent to consult ChatGPT Web about whether this skill is good enough.
```

## Product Promise

The skill should behave like a conversation product:

1. understand the requested product tier,
2. prepare the right decision context,
3. open only the minimum required connector window,
4. ask the advisor through an actually available channel,
5. import the result,
6. classify material recommendations as `Adopt`, `Ask`, or `Reject`,
7. close public windows after the task or idle timeout.

It must not pretend that an advisor was called when the advisor channel is not
available in the current Codex conversation.

## Critical Distinction

Connected Agent is an inbound connector:

```text
ChatGPT Web -> MCP connector -> local Connected Agent tools
```

It is not, by itself, an outbound GPT Pro API for Codex:

```text
Codex -> GPT Pro Web model
```

Therefore a Connected Agent request needs both:

- a Connected Agent session if ChatGPT Web should inspect or operate on the local
  workspace,
- an advisor channel that lets the request reach ChatGPT Web.

If no advisor channel is available, Codex must say so and stop at
`waiting_for_advisor_channel`.

## Advisor Channels

`direct-tool`

- A callable advisor connector/API is visible to Codex in the current
  conversation.
- Codex can complete the loop without user copy-paste.

`browser-automation`

- The user explicitly authorizes browser/computer automation.
- Codex may operate ChatGPT Web for the user.
- The user should not use the computer while automation is controlling the UI.

`user-web`

- The user triggers the ChatGPT Web conversation manually.
- Codex prepares exact prompts, keeps the local connector/session ready, then
  imports the result.

`manual`

- Ask First package/advice exchange.
- Safest fallback, risk `1/5`.

`unknown`

- Codex cannot see a usable advisor channel.
- Codex must not claim the consultation has happened.

## Mode Behavior

Ask First

- Create or summarize a self-contained package.
- No public connector.
- Risk `1/5`.
- User manually sends package and returns advice.

Connected Agent

- Do not create a decision package.
- Use `--mode connected-agent`.
- Let ChatGPT Web directly list/read/search allowed project content by default.
- Tools include `open_default_workspace`, `open_workspace`, `ls`, `read`,
  `read_lines`, `write`, `edit`, `grep`, `glob`, `bash`, `enable_danger_auto`, `danger_auto_status`,
  `disable_danger_auto`, `grant_action_approval`, `request_workspace_access`, and
  `grant_workspace_access`.
- When exactly one allowed root is configured, ChatGPT should call
  `open_default_workspace` first so it does not need to pass a local absolute
  path through the web advisor.
- If ChatGPT still exposes a stale connector schema without
  `open_default_workspace`, it should call `open_workspace` with path exactly
  `"default"` as the no-local-path compatibility alias.
- High-risk credential paths are blocked by the server; other task-relevant
  project files may be inspected.
- Whole-file `read` is for task-relevant UTF-8 files up to 1 MB; larger source
  files should use targeted `grep` plus bounded `read_lines` ranges. Default
  prompts should skip `node_modules`, build outputs, sourcemaps, image
  galleries, and dependency artifacts unless the task explicitly requires them.
- Write, edit, and bash use one-action approval by default: the tool returns
  `approval_id`, ChatGPT asks the user to approve that exact action, calls
  `grant_action_approval`, and retries the same tool call once with that
  `approval_id`.
- `dangerously trust connected agent` is a hidden danger switch inside
  Connected Agent, not an additional product tier.
- The hidden switch starts only after the user types that exact phrase in
  ChatGPT Web.
- When the hidden switch is active, safe project-local write/edit and safe
  local bash may run automatically; network, browser/desktop, clipboard,
  secret-path, path escape, dependency install, Git remote, and broad
  destructive command classes are blocked or require approval.
- Risk `3/5-5/5`; the hidden switch is fixed `5/5`.
- If advisor channel is unavailable, wait for `user-web` or browser automation
  authorization.

Legacy Full-Agent or high-risk connector wording maps to Connected Agent unless the
user explicitly asks to test the deprecated `full-agent` alias.

## Connected Agent Health Gate

Before opening a public Connected Agent window, Codex must establish the advisor
channel:

1. `direct-tool`: verify that a callable advisor/model channel is available.
2. `browser-automation`: verify that ChatGPT Web has an interactive prompt box
   or a visible conversation that can receive a prompt.
3. `user-web`: give the user one short prompt and wait for the user to confirm
   that ChatGPT Web is ready.

Do not open the Connected Agent session while the only known state is a blank
ChatGPT page, browser automation timeout, stale connector page, or unknown web
advisor state. In that case report:

```text
Current state: waiting_for_advisor_channel
Requested mode: connected-agent
Connected Agent session: not_open
Risk if opened: 3/5-5/5
Reason: ChatGPT Web is not currently reachable as an advisor channel.
Next options: restart/restore the browser, user triggers ChatGPT Web manually,
or fall back to Ask First.
```

If browser automation cannot access the browser window or the browser shows a
pending restart/update state, report `advisor-health=needs-browser-restart` and
ask for user confirmation before restarting the browser. Do not restart the
browser as an unprompted recovery step, because it can affect open tabs and
unsaved web input.

Once the advisor channel is healthy, Codex opens the Connected Agent window, performs
the consultation, imports the result, classifies recommendations, and lets the
watchdog close the session 20 minutes after the last Connected Agent use unless the
user explicitly asks to close sooner.

When the user or browser automation brings the ChatGPT Web answer back, capture
it before local review:

```bash
python3 scripts/connected_agent_flow.py capture \
  --advisor chatgpt-web-connected-agent \
  "<original Connected Agent question>"
```

This stores the answer as Connected Agent review data and renders a review-only
gate. It does not execute advisor instructions. The `capture` action refreshes
the idle timer after saving the advice; the session remains open until 20
minutes after the last Connected Agent use by default.

## Local Helper

Use package preparation only for Ask First or legacy package-only Auto MCP:

```bash
python3 scripts/prepare_consultation.py \
  --mode ask-first \
  --advisor-channel unknown \
  "Review whether this skill is ready and what to optimize next."
```

The helper creates a package task:

```text
decision-inbox/tasks/<task-id>/metadata.json
decision-inbox/tasks/<task-id>/package.md
decision-inbox/tasks/<task-id>/advice/
decision-inbox/tasks/<task-id>/fact-check-requests/
```

Do not use this helper for Connected Agent. It exposes workspace MCP tools
directly and does not generate decision packages.

Use the side-effect-free product gate before opening Connected Agent:

```bash
python3 scripts/conversation_product_gate.py \
  --mode connected-agent \
  --advisor-channel browser-automation \
  --advisor-health ready
```

If the gate returns `waiting_for_advisor_channel`, do not open the public MCP
window yet. Restore ChatGPT Web, wait for the user to trigger `user-web`, or
fall back to Ask First.

For Connected Agent user-facing status, report the product readiness gate,
current session state, and current Tailscale Funnel state together. The status
check must not open Connected Agent.

For the normal user-facing Connected Agent consultation path, prefer the bounded flow
wrapper:

```bash
python3 scripts/connected_agent_flow.py prepare \
  --allowed-root "$PWD" \
  --public-base-url "https://your-public-host.example.com" \
  --advisor-channel user-web \
  --advisor-health ready \
  "Review whether this project is ready for Connected Agent use."
```

The wrapper checks advisor readiness, opens the Connected Agent session, runs public
health checks, copies the compact ChatGPT Web prompt, and refuses to continue
if the public health result is not `stable`. It no longer assumes browser
automation is ready by default; Codex must explicitly pass `user-web`,
`browser-automation`, or `direct-tool` with `advisor-health=ready` before the
Connected Agent window opens.

The product default is optimized for interactive use:

```text
--speed fast --output compact
```

Fast mode uses a short public warmup, two open-time preflight attempts, one
public-health probe, and a compact status card. Use the conservative verification
profile only when debugging connector stability or proving a public tunnel:

```text
--speed safe --output verbose
```

Safe mode keeps the older 30 second public warmup, 30 second preflight timeout,
six open-time preflight attempts, five public-health probes, and one
intermittent-health recovery check. After advice returns, use the same wrapper
to capture the answer and refresh the 20-minute idle window:

```bash
python3 scripts/connected_agent_flow.py capture \
  --advisor chatgpt-web-connected-agent \
  "<original Connected Agent question>"
```

Use `python3 scripts/connected_agent_flow.py close` only when stopping
before advice has been captured or when the user explicitly wants immediate
shutdown.

For the ChatGPT Web prompt after the connector chip is visible, prefer the
product wrapper:

```bash
python3 scripts/connected_agent_flow.py prepare \
  --allowed-root "$PWD" \
  --advisor-channel user-web \
  --advisor-health ready \
  "Review whether this project is ready for Connected Agent use."
```

The generated prompt tells ChatGPT to use a chat mode where Apps/MCP connector
tools are visible, use only the Connected Agent connector, avoid Python/browser
file checks, inspect before acting, use one-action approval for write/edit/bash,
choose task-relevant project files under the allowed root, avoid high-risk
credential paths, and report
`Adopt`, `Ask`, and `Reject` recommendations. Use `--deep` or explicit `--file`
only for a targeted fixed-file round. The `--clipboard` flag copies the prompt
locally so browser automation or the user can paste it into ChatGPT without
manually selecting terminal output.

If browser automation cannot paste or send the prompt reliably, do not leave
the Connected Agent window open while retrying indefinitely. Either use a
short user-web handoff where the user presses send in ChatGPT Web, or close the
window and report `waiting_for_advisor_channel`.

For ordinary users, the expected handoff text is:

```text
Open ChatGPT Web with a tool-capable chat mode selected and the Connected Agent connector attached.
Paste and send the copied prompt.
When ChatGPT finishes, paste the answer back into Codex.
Codex will classify the advice as Adopt / Ask / Reject.
```

Codex should then capture the pasted answer with
`scripts/connected_agent_flow.py capture` before doing the local
Adopt / Ask / Reject review.

## Failure Wording

Use direct wording when the loop cannot be completed:

```text
Current state: waiting_for_advisor_channel
Requested mode: connected-agent
Connected Agent session: ready/not_open/failed
Risk if opened: 3/5-5/5
Reason: Codex does not currently have a callable GPT Pro Web advisor channel.
Next options: user triggers ChatGPT Web manually, authorize browser automation,
or fall back to Ask First.
```

Do not say the advisor reviewed the package unless advice was actually returned
through MCP, browser automation, a direct advisor tool, or pasted user evidence.
