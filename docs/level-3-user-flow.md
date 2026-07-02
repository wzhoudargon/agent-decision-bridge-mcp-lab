# Connected Agent User Flow

This is the non-technical product flow for Connected Agent consultations.
Legacy "Level 3" wording maps to Connected Agent in V1.1.

## What The User Says

```text
用第三档帮我咨询 GPT Pro：<你的问题>
```

Codex should treat this as `Connected Agent`, not as Ask First.

## What Codex Does

1. Reports that Connected Agent is risk `3/5-5/5` while online; Danger Auto is
   fixed risk `5/5`.
2. Uses the current project as the allowed root only after the user has clearly
   asked for Level 3.
3. Checks that an advisor channel is available:
   - `user-web`: the user will send the prompt in ChatGPT Web,
   - `browser-automation`: Codex is allowed to operate ChatGPT Web and will
     occupy the visible browser while it runs,
   - `direct-tool`: Codex has a callable advisor tool.
4. Opens a short Connected Agent session only after the advisor channel is ready.
5. Runs public health checks before asking ChatGPT Web to use the connector.
6. Tells the user to use GPT-5.5 Thinking, not GPT-5.5 Pro, for the connector
   call because Pro models do not expose ChatGPT Apps/MCP tools.
7. Gives ChatGPT Web a compact prompt that inspects context first, lets the
   advisor choose task-relevant files under the allowed root, and hard-blocks
   high-risk credential paths at the server.
8. Allows write/edit/bash only after approval by default. Danger Auto starts
   only if the user types `dangerously trust connected agent`, and server policy
   still blocks unsafe commands and sensitive paths.
9. Imports the returned advice.
10. Classifies recommendations as `Adopt`, `Ask`, or `Reject`.
11. Keeps the session open after capture and lets the idle watchdog close it 20
   minutes after the last Connected Agent use.

If the advisor channel is not ready or local preparation fails before a real
answer returns, Codex should say:

```text
GPT Pro has not been consulted yet; the system is still preparing or waiting.
```

For a quick product-readable status, Codex can run:

```bash
python3 scripts/level3_status.py
```

The first lines should answer:

```text
Can use now: yes/no
Exposure now: closed/open
Normal flow: prepare -> ChatGPT Web answer -> capture
```

For the user, the default status card should be compact:

```text
Connected Agent: ready / waiting_for_advisor_channel / online / closed
Advisor channel: user-web / browser-automation / direct-tool / unknown
Workspace: <current project>
Risk while online: 3/5-5/5; Danger Auto 5/5
Current step: prepare / web-consult / capture / idle-wait / close
Next action: <who does what next>
```

## What The User May Need To Do

In the current `browser-automation` path, the user needs to authorize Codex to
operate ChatGPT Web and then avoid using the computer while the browser is
being controlled:

```text
1. Keep ChatGPT Web logged in with GPT-5.5 Thinking selected and the Connected Agent connector attached.
2. Let Codex paste/send the prompt and copy the answer.
3. Wait for Codex to capture the answer, refresh the 20-minute idle window, and
   report the result.
```

In the safer `user-web` fallback, the user only needs to:

```text
1. Open ChatGPT Web with GPT-5.5 Thinking selected and the Connected Agent connector attached.
2. Paste and send the prompt that Codex copied/prepared.
3. Paste ChatGPT's answer back into Codex.
```

The user should not need to run backend commands.

## What Codex Runs After The Answer Comes Back

When the user pastes the ChatGPT answer back, Codex captures it as external
advice data:

```bash
python3 scripts/level3_consultation_flow.py capture \
  --advisor chatgpt-web-connected-agent \
  "<original question>"
```

The answer is saved under:

```text
decision-inbox/level3-consultations/<consultation-id>/advice/
```

This is a transcript/review record only. It is not authorization to execute.
The `capture` action refreshes the Connected Agent idle timer after saving the advice.
The session remains open by default and the watchdog closes it 20 minutes after
the last Connected Agent use. Use `--close-after-capture` only when the user explicitly
wants an immediate shutdown.

## What The Result Should Look Like

Codex reports:

```text
Current state: review_only
Risk status: ...
File changes: none
Commands run: read_only_only
Advisor rounds used: 1

Adopt:
- ...

Ask:
- ...

Reject:
- ...

Next local action:
- ...
```

External advice is never authorization. File edits, shell commands, dependency
installs, Git operations, publishing, deletion, and use of secrets still require
the user's explicit approval in Codex.

## Current Maturity

Connected Agent is verified as a repeatable short-window connector flow, but
it is not an always-on production endpoint and not a background/no-friction
browser automation product.

Currently reliable:

- Connected Agent MCP server and tool surface.
- Short Tailscale Funnel windows after passing health checks.
- ChatGPT Web reading task-relevant project files through the connector after
  the server blocks high-risk credential paths.
- Codex capturing returned advice and entering a review-only gate.
- Automatic recovery check after intermittent public health, and automatic close
  if the connector is still not stable.
- Twenty-minute sliding idle window: each new Connected Agent use refreshes the timer, and
  completed consultations do not close the window immediately.
- Three capture-backed ChatGPT Web browser-automation rounds using the
  Full-Agent connector, local capture, and clean close verification.

Still not fully frictionless:

- Browser automation occupies the user's visible browser; the user should not
  operate the computer while it runs.
- Tailscale Funnel can be intermittent; it must pass health checks before each
  Level 3 task window.
- Cloudflare Named Tunnel is not configured until Cloudflare login/origin
  certificate setup is complete.
