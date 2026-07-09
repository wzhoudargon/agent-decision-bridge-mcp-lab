# Level 3 Completion Audit

Date: 2026-06-24

Scope: audit the current state of the Level 3 Full-Agent product flow for the
`agent-decision-bridge` lab.

## Current Safety State

Current state:

```text
full_agent_session_closed
```

Observed after the latest status check:

```text
Public exposure: closed
Tailscale Funnel: No serve config
Local MCP listener on port 8765: not listening
Risk now: 2/5 if persistent OAuth state remains, otherwise 1/5
Risk while Level 3 is open: 5/5
```

## User Goal Audit

User goal:

```text
Run the real third tier multiple times with ChatGPT Web, use this skill itself
as the consultation subject, and reach a mature skill that a user can use
smoothly without known blocking bugs.
```

Current audit:

| Requirement | Status | Evidence |
|---|---:|---|
| Real ChatGPT Web Level 3 consultations happened | Pass | `docs/phase-5-full-agent-live-verification.md` records multiple real ChatGPT Web rounds where the connector was attached and project files were read. |
| Three capture-backed real web-side rounds exist | Pass | Rounds H, I, and J each used ChatGPT Web, Full-Agent connector reads, browser automation, local capture, and session close verification. |
| ChatGPT Web can read project context through Full-Agent | Pass | ChatGPT Web has read project files through the connector in prior live rounds. Current prompt behavior lets the advisor choose task-relevant files under the allowed root while the server hard-blocks high-risk credential paths. |
| The connector tools work under the allowed workspace | Pass | Local/account-side checks verified `open_workspace`, `ls`, `read`, `write`, `edit`, `grep`, `glob`, and `bash`; parent traversal was rejected. |
| Public task window can be opened and closed | Pass | Full-Agent session open/close and Tailscale close checks were verified; latest state is closed. |
| Product wrapper avoids opening 5/5 before advisor readiness | Pass | `scripts/level3_consultation_flow.py` defaults to unknown advisor state and requires `user-web`, `browser-automation`, or `direct-tool` marked ready. |
| Returned advice can be captured as review-only data | Pass | `scripts/level3_consultation_flow.py capture` captures ChatGPT Web Level 3 answers under `decision-inbox/level3-consultations/` and now refreshes the 20-minute idle window instead of closing immediately by default. |
| Connector model choice is explicit | Pass | Current product guidance tells users to select GPT-5.5 Thinking, not GPT-5.5 Pro, because Pro models do not expose ChatGPT Apps/MCP tools. |
| Failure states avoid false GPT Pro claims | Pass | `scripts/conversation_product_gate.py` and `scripts/level3_consultation_flow.py` now print that GPT Pro has not been consulted yet when the system is still preparing or waiting. |
| Browser automation warns that the computer is occupied | Pass | `scripts/level3_consultation_flow.py prepare` prints a browser-automation warning before Codex controls ChatGPT Web. |
| Browser automation is fully frictionless | Not yet | Browser automation completed repeated runs, but it still occupies the visible browser and the user should not operate the computer while it controls ChatGPT Web. |
| Tailscale is stable enough for always-on production | Not yet | Tailscale Funnel is conditionally usable for short task windows after passing health checks, not a reliable always-on endpoint. |
| Runtime skill has the final product instructions applied | Pass | The user confirmed the runtime skill patch; `~/.codex/skills/agent-decision-bridge/SKILL.md` now contains the bounded Level 3 helper/capture flow, false-consultation guardrail, browser-automation warning, and maturity labels. |
| Three capture-backed live Level 3 rounds completed | Pass | Rounds H, I, and J used wrapper prepare, ChatGPT Web Full-Agent connector reads, browser automation, capture, and close verification together. |

## Maturity Verdict

Current verdict:

```text
usable_short_window_browser_automation
```

Meaning:

- The connector capability is real.
- The ChatGPT Web path has been proven with multiple live rounds.
- The strongest proven current experience is `browser-automation`: Codex
  opens/checks the local Full-Agent session, prepares the prompt, drives
  ChatGPT Web, captures/imports the answer, and keeps the session open until
  the 20-minute idle watchdog closes it.
- `user-web` remains the safer fallback when the user wants to avoid Computer
  Use occupying the browser.
- The system is not yet a stable always-on or fully autonomous GPT Pro caller.
- The system is not yet a no-friction product for ordinary users because
  browser automation occupies the user's computer and the public endpoint must
  pass health checks for each short task window.

## Current Best User Flow

For a non-technical user, the intended Level 3 usage is:

```text
用第三档帮我咨询 GPT Pro：<问题>
```

Codex should then:

1. report `Risk while open: 5/5`,
2. confirm the current project as the allowed root,
3. verify that an advisor channel is ready,
4. run `scripts/connected_agent_flow.py prepare`,
5. ask ChatGPT Web with GPT-5.5 Thinking selected to use the Full-Agent connector,
6. capture the returned answer with `scripts/connected_agent_flow.py capture`,
7. classify recommendations as `Adopt`, `Ask`, or `Reject`,
8. let the 20-minute idle watchdog close the session unless the user asks to
   close it immediately.

The compact user-facing state should be:

```text
Level 3: ready / waiting_for_advisor_channel / online / closed
Advisor channel: user-web / browser-automation / direct-tool / unknown
Workspace: <allowed-root>
Risk while online: 5/5
Current step: prepare / web-consult / capture / idle-wait / close
Next action: <user or Codex action>
```

The preferred product path after the answer returns is now:

```bash
python3 scripts/connected_agent_flow.py capture \
  --advisor chatgpt-web-full-agent \
  "<original question>"
```

This captures the answer and refreshes the 20-minute idle window by default.

## Remaining Product Gaps

1. Advisor channel dependency:
   Full-Agent is an inbound connector from ChatGPT Web to local tools. It is not
   an outbound GPT Pro API. Codex still needs `user-web`, browser automation, or
   a future direct advisor tool to reach ChatGPT Web.

2. Public URL stability:
   Tailscale Funnel works for bounded windows after a passing health check, but
   it has shown warmup latency, timeout, and macOS Screen Time warnings.
   Cloudflare Named Tunnel remains the likely long-term stable fallback if a
   domain/account path is available.

3. Browser automation:
   It can operate ChatGPT Web and has completed repeated prompt/send/copy
   flows, but it still occupies the visible browser. Do not promise that the
   user can keep using the computer during the run.

4. Runtime skill finalization:
   Completed after explicit user confirmation. Future Codex sessions that load
   the global `agent-decision-bridge` skill now inherit the tested
   wrapper/capture flow and false-success guardrails.

5. User-facing polish:
   Three capture-backed live proofs now exist. The wrapper now has a product
   fast path: `scripts/connected_agent_flow.py prepare` defaults to
   `--speed fast --output compact`, while the older conservative probe profile
   remains available as `--speed safe --output verbose`. Browser automation
   must still be clearly labeled as occupying the user's computer while it runs.

## Stop Condition Before "Mature"

Do not report Level 3 as mature until all of these are true:

1. `python3 -m unittest discover -s tests` passes.
2. `scripts/full_agent_session.py status --check-public-health` reports closed
   when idle or stable while intentionally open.
3. Tailscale Funnel or the selected public tunnel closes cleanly after the task.
4. A real ChatGPT Web answer has been captured through
   `scripts/connected_agent_flow.py capture`.
5. Codex has produced an `Adopt` / `Ask` / `Reject` review from that captured
   answer.
6. The final response clearly states whether the user still needs to touch
   ChatGPT Web or whether automation completed the web step.

Latest result after three capture-backed Web rounds:

```text
All six stop-condition checks passed for the current capture-backed browser
automation path. Do not call the product "no-friction mature"; call it
"usable short-window browser automation." The runtime skill patch is now
applied. Full regression after the product-message fixes passed:
python3 -m unittest discover -s tests
Ran 138 tests in 20.558s
OK
```
