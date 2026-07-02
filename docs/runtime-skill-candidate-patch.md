# Runtime Skill Candidate Patch

Date: 2026-06-24

Status: historical. This candidate was applied after explicit user confirmation
on 2026-06-24, but it is now superseded by the V1.1 Ask First + Connected
Agent + Danger Auto model documented in `docs/plan.md` and
`docs/conversation-product-mode.md`.

Do not use this file as the current product entry point. It is retained only as
an audit trail for the older Level 1 / Level 2 / Level 3 design.

Lifecycle update status: project scripts/docs updated on 2026-06-24 for the new
10-minute sliding Level 3 window. Runtime skill wording still needs a separate
explicit confirmation before `~/.codex/skills/agent-decision-bridge/SKILL.md`
is modified again.

## Target File

```text
~/.codex/skills/agent-decision-bridge/SKILL.md
```

## Why A Patch Is Still Needed

The runtime skill already contains the first conversation-product update:

- Level 1 creates manual packages.
- Level 2 is Read-Only Project Advisor and should not generate packages.
- Level 3 is Full-Agent Execution and should not generate packages.
- External advice is not authorization.

The remaining risk is operational drift: future Codex sessions may still treat
Level 3 as a manual package flow, may open a `5/5` session before confirming an
advisor channel, or may forget to capture returned ChatGPT Web advice as
review-only data.

The project scripts now enforce the most important runtime behavior locally:

- `conversation_product_gate.py` reports that GPT Pro has not been consulted
  when the system is still waiting for an advisor channel.
- `level3_consultation_flow.py prepare` repeats that failure notice on
  local-side failures before a real advisor answer.
- `level3_consultation_flow.py prepare` warns that browser automation will
  control ChatGPT Web and the user should not use the mouse or keyboard during
  that Web step.
- `level3_consultation_flow.py capture` now refreshes the 10-minute idle window
  instead of closing the session immediately by default.

The runtime skill patch has now been applied so future Codex conversations can
load these same product rules without rediscovering them from this lab's docs.

This patch is now backed by three capture-backed ChatGPT Web Full-Agent rounds
in this lab:

```text
decision-inbox/level3-consultations/level3-live-capture-20260624/
decision-inbox/level3-consultations/level3-live-capture-20260624-round2/
decision-inbox/level3-consultations/level3-live-capture-20260624-round3/
```

All three rounds used the Full-Agent connector from ChatGPT Web, read the
default three-file safe set, captured the answer locally, and closed the `5/5`
session.

The later lifecycle policy changed after those rounds: completed consultations
now keep the Level 3 session open until 10 minutes after the last Level 3 use,
unless the user explicitly requests immediate close.

This candidate patch is intentionally small. It should not turn the runtime
skill into a long tunnel manual.

## Expected Benefit

- Makes the current Level 3 product flow explicit in the reusable skill.
- Reduces false claims that GPT Pro was consulted when no advisor answer was
  returned.
- Keeps Level 2 and Level 3 package-free.
- Pushes Codex toward the tested helper path:
  `level3_consultation_flow.py prepare` -> ChatGPT Web connector -> returned
  advice -> `level3_consultation_flow.py capture` -> review gate -> 10-minute
  idle close.
- Keeps `5/5` windows short, sliding, and tied to actual Level 3 use.
- Makes browser automation explicit: it can complete the Web step, but it
  occupies the user's visible browser and should not be described as background
  automation.

## Risk

- Runtime skill changes affect all future Codex sessions, not only this lab.
- If the wording is too aggressive, Codex may try to open Full-Agent when the
  user only wanted a normal manual consultation.
- If the wording is too broad, Codex may over-trust browser automation even
  though it is not yet fully frictionless.
- Level 3 remains high risk while online because it can expose file write/edit
  and bash tools under an allowed root.

## Rollback Path

Use the existing runtime skill backup:

```text
~/.codex/skill-backups/agent-decision-bridge/2026-06-18-pre-automation/
```

Or manually remove the inserted Level 3 helper/capture notes from:

```text
~/.codex/skills/agent-decision-bridge/SKILL.md
```

## Candidate Change Summary

Patch only the `Conversation Product Mode` section and nearby Level 3 wording.

Add these rules:

```markdown
For Level 3 in this lab repository, prefer the bounded helper flow when the
files exist:

1. Run `scripts/level3_consultation_flow.py prepare` only after the advisor
   channel is confirmed as `user-web`, `browser-automation`, or `direct-tool`
   with health `ready`.
2. Do not open the Full-Agent session while advisor channel is `unknown`.
3. If the helper reports non-stable public health, close the session and report
   the failure instead of retrying indefinitely.
4. After ChatGPT Web returns an answer, run
   `scripts/level3_consultation_flow.py capture` to save the answer as
   external advice data before local review and refresh the 10-minute idle
   window by default.
5. Then classify material recommendations as `Adopt`, `Ask`, or `Reject`.
6. Let the watchdog close 10 minutes after the last Level 3 use, unless the
   user explicitly asks to close immediately.
```

Clarify these boundaries:

```markdown
Level 3 is not a Codex-owned GPT Pro API call. It is a ChatGPT Web connector
plus an advisor channel. If Codex cannot access a direct advisor tool and the
user has not authorized browser automation, use `user-web`: Codex prepares and
keeps the session ready, while the user sends the prompt in ChatGPT Web.

Do not claim "GPT Pro reviewed this" unless a real answer was returned through
MCP/tooling, browser automation evidence, or user-pasted evidence.

If browser automation is used, say before starting:
"浏览器自动化会临时控制你的电脑 UI，请不要操作鼠标键盘；如果不方便，改用
user-web 手动粘贴。" If the user does not authorize browser automation, use
`user-web` handoff.

On any failure before a real advisor answer returns, report:
"GPT Pro has not been consulted yet; the system is still preparing or waiting."
```

Add one stop condition:

```markdown
If the user asks whether Level 3 is mature, distinguish:

- `connector_verified`: tools and public session work,
- `user_web_usable`: user can send the prepared prompt and return advice,
- `browser_automation_usable`: browser automation can complete the Web step,
  but occupies the user's browser,
- `mature`: only for bounded short-window use after capture-backed live rounds
  and clean close verification; do not imply always-on or background use.
```

## Confirmation

The user explicitly confirmed: `确认应用 runtime skill patch`.

Applied target:

```text
~/.codex/skills/agent-decision-bridge/SKILL.md
```

Post-apply structural check:

```text
runtime skill structural check: ok
```
