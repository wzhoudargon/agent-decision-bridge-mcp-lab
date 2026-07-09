# Phase 5 Full-Agent Live Verification

Date: 2026-06-24

Scope: real Level 3 Full-Agent validation for the current
`agent-decision-bridge` lab workspace.

## Current Result

Status: repeatably verified for bounded ChatGPT Web Full-Agent consultations.

Verified:

- Full-Agent session can open a short public Tailscale Funnel window.
- Account-side Full-Agent connector can open the current allowed workspace.
- Connector tools can list, read, write, edit, grep, glob, and run bash inside
  the opened workspace.
- Parent-directory traversal is rejected.
- Session close now uses `tailscale funnel reset`; Funnel was confirmed closed
  with `No serve config`.
- ChatGPT Web, through browser automation, attached the Full-Agent connector to
  the conversation and reached the local MCP backend.
- ChatGPT Web opened the workspace and successfully read `README.md` through
  `Agent Decision Bridge Full-Agent Live`.
- ChatGPT Web returned a real advisor verdict: `Ask`, because the connector
  worked but product-level completion was blocked by one safe-file read failure.
- A later compact three-file consultation succeeded through ChatGPT Web and
  read `README.md`, `docs/security-public.md`, and
  `docs/conversation-product-mode.md` with no read failures.
- A second compact targeted consultation succeeded through ChatGPT Web and read
  `scripts/level3_consultation_prompt.py`, `docs/connector-runbook.md`, and
  `docs/phase-5-full-agent-live-verification.md` with no read failures.
- A later bounded wrapper run with conservative Tailscale timings passed public
  health `5/5`; ChatGPT Web read the default three files and returned
  Adopt/Ask/Reject advice. The final maturity verdict was `Ask`, close to
  `Adopt`.
- A final capture-backed browser-automation run succeeded through ChatGPT Web:
  Full-Agent Live opened the allowed workspace, read the default three files,
  returned product-maturity advice, and
  `scripts/level3_consultation_flow.py capture` saved the advice locally before
  closing the `5/5` session.
- Two additional capture-backed browser-automation runs succeeded through
  ChatGPT Web after Round H. Both runs used the Full-Agent connector, opened the
  same allowed workspace, read the default three files, returned
  Adopt/Ask/Reject product advice, saved the advice locally, and closed the
  `5/5` session.

Not yet verified:

- A raw `docs/security.md` read through ChatGPT Web. The file was blocked by
  the platform tool-safety layer.
- Browser automation as a background/non-blocking user product. The latest run
  successfully entered the prompt, sent it, copied the answer, captured it, and
  closed the window, but it still occupies the user's visible browser while it
  runs and should not be advertised as something the user can ignore while
  continuing normal computer work.

## Evidence

Session open command:

```bash
python3 scripts/full_agent_session.py open \
  --public-base-url "https://your-device.example-tailnet.ts.net" \
  --allowed-root "$PWD" \
  --idle-timeout-seconds 300 \
  --skip-preflight
```

Observed result:

```text
Current state: full_agent_session_open
Mode: full-agent
Risk coefficient while open: 5/5
Public MCP URL: https://your-device.example-tailnet.ts.net/mcp
```

Account-side connector opened the workspace:

```text
workspace_id: ws-faa3ebc868b4409ebe2f8b74be64cfd8
root: <allowed-project-root>
profile: full-agent
risk_level: 5/5
```

Positive tool checks:

- `ls .` listed the project root.
- `read README.md` returned project content.
- `write .full-agent-smoke/smoke.txt` created a temporary file.
- `edit .full-agent-smoke/smoke.txt` replaced `initial` with `edited`.
- `grep edited .full-agent-smoke` found the edited line.
- `bash` read the temporary file, removed `.full-agent-smoke`, and returned
  `cleanup: ok`.

Negative check:

```text
read ../README.md
Access denied: parent-directory traversal is not allowed
```

Session close command:

```bash
python3 scripts/full_agent_session.py close
tailscale --socket=/tmp/tailscaled-decision-inbox.sock funnel status
```

Observed result:

```text
Current state: full_agent_session_closed
Risk coefficient now: 2/5 if persistent OAuth state remains, otherwise 1/5
No serve config
```

## Strict Public Preflight

Strict public preflight from the same Mac is sensitive to Tailscale Funnel
warmup and local `.ts.net` hairpin behavior.

Earlier runs failed:

```text
Public OAuth metadata: failed
curl exit 35: LibreSSL SSL_connect: SSL_ERROR_SYSCALL
Public unauthenticated MCP challenge: failed
```

The 2026-06-24 retest opened the same Full-Agent session with Tailscale Funnel,
10 second warmup, 10 second request timeout, and three preflight attempts. The
first two attempts reproduced SSL/timeout failures, while the third attempt
passed:

```text
Public OAuth metadata: ok scope=full-agent
Public unauthenticated MCP challenge: ok oauth_challenge scope=full-agent
Authenticated tools/list: ok expected_allowlist
Observed tools: open_workspace, ls, read, write, edit, grep, glob, bash
Preflight result: ok
```

The session was then closed and `tailscale funnel status` returned:

```text
No serve config
```

Working conclusion: Tailscale Funnel is usable for this lab after warmup and
retry. Cloudflare Named Tunnel remains a fallback if repeated warmup/retry runs
fail or if ChatGPT Web cannot reach the connector while local and authenticated
preflight probes are healthy.

Follow-up retest on 2026-06-24:

- Full-Agent was initially still open; it was closed before waiting on
  Cloudflare account-side login.
- Tailscale Funnel showed `Funnel on` and local `/mcp` was healthy.
- Two public preflight runs passed end to end.
- A third follow-up public challenge probe timed out, while authenticated
  `tools/list` still returned the expected Full-Agent allowlist.
- `tailscale status` reported that macOS Screen Time may be blocking
  Tailscale.

Current classification:

```text
Public health: conditionally usable
Reason: public metadata/challenge can pass and repeated health checks can be
stable, but earlier repeated local public probes timed out and the local
Tailscale daemon still reports a macOS Screen Time health warning.
Product implication: usable for bounded Level 3 task windows after a passing
health check, not stable enough to treat as an always-on production endpoint.
```

Follow-up with longer warmup/timeout:

```text
Open command used 15 second public warmup, 15 second preflight timeout, and up
to 5 open-time preflight attempts.
Open-time preflight: ok.
Status health command: python3 scripts/full_agent_session.py status
  --check-public-health --health-attempts 3 --health-retry-seconds 3
  --preflight-timeout 15
Observed: Public health: stable preflight_passed=3/3.
After test: full_agent_session_closed, Tailscale Funnel returned No serve config,
and port 8765 was not listening.
```

Follow-up live consultation retest on 2026-06-24:

```text
Open command used 15 second public warmup, 15 second preflight timeout, and up
to 5 open-time preflight attempts.
Open-time preflight: one transient SSL failure, then ok.
Status health command: Public health: stable preflight_passed=5/5.
Direct public /mcp challenge: HTTP 401 OAuth challenge after about 13 seconds.
ChatGPT Web Full-Agent connector: open_workspace succeeded.
Read succeeded: README.md, docs/security-public.md,
docs/conversation-product-mode.md.
Read failed: none.
No .env, .git, token, credential, browser data, bash, write, or edit was used.
ChatGPT verdict: Ask, positive direction.
After test: full_agent_session_closed, Tailscale Funnel returned No serve config,
and port 8765 was not listening.
```

Current operational rule:

```text
Use Tailscale Funnel for Level 3 only as a short task window after a passing
health check. Treat the provider state as stable for that task only when
status --check-public-health reports stable. If it reports intermittent, the
consultation may proceed only as an explicit short test. If it reports failed,
switch to Cloudflare or another stable reverse proxy.
```

Cloudflare fallback status:

```text
Cloudflare Named Tunnel: not configured
Reason: no origin cert exists under ~/.cloudflared; Cloudflare login reached
the account-side authorization page, but the current account did not expose a
selectable zone/domain for tunnel authorization in the tested flow.
Safety action: Full-Agent session was closed before waiting for login.
Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5.
```

Implemented follow-up:

- `scripts/full_agent_session.py status --check-public-health` now classifies
  the active public endpoint as `stable`, `intermittent`, or `failed` using
  repeated read-only preflight probes.
- Product reporting should use this status before asking ChatGPT Web to use the
  Full-Agent connector.
- `scripts/level3_consultation_flow.py prepare/close` now provides the
  user-facing wrapper for Level 3 consultations: advisor gate, short
  Full-Agent open, public health check, compact prompt generation, and close
  verification. It refuses to continue and closes the `5/5` window if public
  health is not `stable`.

## ChatGPT Web Automation

Attempted channels:

- Chrome plugin:
  - `openTabs` and `claimTab` worked.
  - `domSnapshot`, `screenshot`, and a minimal `evaluate` probe against the
    ChatGPT page timed out and reset the plugin kernel.
- Computer Use:
  - Chrome window and ChatGPT tab were visible to accessibility.
  - The ChatGPT page content area rendered as a gray blank area.
  - Reload, direct navigation to `https://chatgpt.com/?temporary-chat=true`, and
    hard reload did not restore an interactive prompt box.
  - A new Chrome window rendered the Chrome new-tab page normally, but navigating
    that new window to ChatGPT still produced a blank ChatGPT page.
  - Chrome showed `重新启动即可更新` in the toolbar, so the next browser recovery
    step is to restart Chrome after user confirmation.
  - On the next continuation, Computer Use returned `cgWindowNotFound` for
    Google Chrome, so the browser automation channel remained unavailable.
  - A later recovered Chrome session successfully completed Round H end to end:
    prompt entry, send, connector use, answer copy, local capture, and session
    close.
- Alternative browser:
  - Safari was installed and running, but Computer Use could not find an
    operable Safari window for this task.
  - A simple Safari window query stalled and was terminated; Safari was not a
    usable replacement advisor channel in this run.

Conclusion:

The Full-Agent connector backend is usable, and ChatGPT Web can now reach it
from the conversation when the connector chip is attached. A minimal real
consultation succeeded far enough to read `README.md` and return an `Ask`
verdict. The remaining blocker is product smoothness: raw `docs/security.md`
was blocked by the platform tool-safety layer, and long prompts can cause the
model to fall back to Python/browser file checks instead of the MCP connector.

2026-06-24 live ChatGPT Web evidence:

```text
README.md: successfully read through Agent Decision Bridge Full-Agent Live connector.
docs/security.md: blocked by platform tool-safety check.
No .env, .git, token, credential, browser data, bash, write, or edit was used.
Verdict: Ask / partially mature, cannot Adopt.
```

2026-06-24 compact prompt live evidence:

```text
Round A:
open_workspace succeeded for <allowed-project-root>.
Read succeeded: README.md, docs/security-public.md,
docs/conversation-product-mode.md.
Read failed: none.
No .env, .git, token, credential, browser data, bash, write, or edit was used.
Verdict: Ask; connector path works, product loop still needs clearer advisor-channel status.

Round B:
open_workspace succeeded for <allowed-project-root>.
Read succeeded: scripts/level3_consultation_prompt.py,
docs/connector-runbook.md, docs/phase-5-full-agent-live-verification.md.
Read failed: none.
No .env, .git, token, credential, browser data, bash, write, or edit was used.
Verdict: Ask, positive direction; compact prompt should be adopted as default,
but Level 3 overall still depends on advisor-channel health and Tailscale
stability.

Round C:
Tailscale public health passed before the prompt:
Public health: stable preflight_passed=5/5.
open_workspace succeeded for <allowed-project-root>.
Read succeeded: README.md, docs/security-public.md,
docs/conversation-product-mode.md.
Read failed: none.
No .env, .git, token, credential, browser data, bash, write, or edit was used.
Verdict: Ask, positive direction; default compact three-file flow is usable for
short Level 3 task windows, but product maturity still depends on visible
readiness status and Tailscale health.

Round D:
The user-facing wrapper was run with the more conservative task-window
parameters now used as defaults:

```text
public warmup: 30s
preflight timeout: 30s
open-time preflight attempts: 6
preflight retry: 8s
public health attempts: 5
health retry: 4s
```

Observed before asking ChatGPT Web:

```text
Open-time preflight: ok.
Public health: stable preflight_passed=5/5.
Prompt preparation: copied.
```

ChatGPT Web then used the attached Full-Agent connector and returned a real
advisor response. Read results:

```text
open_workspace: succeeded.
Read succeeded: README.md, docs/security-public.md,
docs/conversation-product-mode.md.
Read failed: none.
No .env, .git, token, credential, browser data, repo internals, bash, write,
or edit was used.
```

Advisor verdict:

```text
Final verdict: Ask, close to Adopt.
Adopt: compact three-file default, docs/security-public.md default, advice is
not authorization, short task-window model.
Ask: keep total maturity at Ask until readiness status and failure handling are
more user-visible.
Reject: treating Level 3 as low risk, pretending GPT Pro was consulted when no
advisor channel exists, and defaulting to write/edit/bash.
Smallest fixes: user-readable Level 3 readiness banner; mandatory three-file
gate before deeper review.
```

Automation note:

```text
Computer Use paste/type did not reliably enter the ChatGPT prompt box in this
run. A macOS keyboard-event paste fallback succeeded and ChatGPT Web completed
the connector call. This proves the Web advisor loop, but browser automation is
still not fully frictionless for ordinary users.
```

After the advisor response:

```text
full_agent_session_closed.
Tailscale Funnel: No serve config.
Port 8765: not listening.
Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5.
```

Round E:
Tailscale Funnel was retested independently before switching providers.

```text
Open-time preflight: ok.
Direct public OAuth metadata probe: HTTP 200, scope=full-agent.
Direct public /mcp probe: HTTP 401 OAuth challenge, scope=full-agent.
Public health: stable preflight_passed=5/5.
```

The temporary Full-Agent window was then closed:

```text
full_agent_session_closed.
Tailscale Funnel: No serve config.
Port 8765: not listening.
Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5.
```

Conclusion: Tailscale Funnel is usable for bounded Level 3 task windows when
the conservative warmup and health checks pass. Do not switch to Cloudflare
only because earlier local probes timed out. Switch providers only if repeated
health probes fail, ChatGPT Web cannot reach the connector while public
preflight passes locally, or an always-on production endpoint is required.

Round F:
The user-facing wrapper was retested after changing the default advisor gate to
`unknown`. Without an explicit ready advisor channel, `prepare` stopped at
`waiting_for_advisor_channel` and did not open Full-Agent. With an explicit
`user-web + ready` channel, it opened the short task window, verified the
open-time preflight, then ran repeated public health probes.

Observed:

```text
Open-time preflight: ok.
Authenticated tools/list: ok expected_allowlist.
Observed tools: open_workspace, ls, read, write, edit, grep, glob, bash.
Public health: intermittent preflight_passed=4/5.
Latest failure: authenticated tools/list did not match the expected connector surface.
Wrapper result: level3_flow_failed, auto-closed the 5/5 window.
```

Close verification:

```text
full_agent_session_closed.
Tailscale Funnel: No serve config.
Port 8765: not listening.
```

Product implication: the wrapper is now safer and correctly refuses to proceed
on intermittent public health. Tailscale remains conditionally usable, not a
frictionless production endpoint. Cloudflare Named Tunnel is still not
configured in this lab because no Cloudflare origin certificate exists under
the local `cloudflared` configuration directory.

Round G:
After adding the recovery check for intermittent public health, the wrapper was
run again with explicit `user-web + ready` and `--no-clipboard` for a local-side
short-window verification.

Observed:

```text
Open-time preflight: ok.
Authenticated tools/list: ok expected_allowlist.
Observed tools: open_workspace, ls, read, write, edit, grep, glob, bash.
Public health: stable preflight_passed=5/5.
Prompt preparation: ready.
User handoff: printed plain user-web steps.
```

The prompt was not sent to ChatGPT Web in this round; the purpose was to verify
the safer wrapper and public-health gate after the Round F intermittent result.
The window was then closed:

```text
full_agent_session_closed.
Tailscale Funnel: No serve config.
Port 8765: not listening.
```

Round H:
The full capture-backed product flow was run with browser automation.

Preparation:

```text
Advisor channel: browser-automation ready.
Allowed root: <allowed-project-root>.
Open-time preflight: ok.
Public health: stable preflight_passed=5/5.
Prompt preparation: copied.
Risk while open: 5/5.
```

ChatGPT Web used the attached Full-Agent connector and returned this result:

```text
Level 3 connector: truly worked.
open_workspace: succeeded.
connector profile: full-agent.
connector risk: 5/5.
Read succeeded: README.md, docs/security-public.md,
docs/conversation-product-mode.md.
Read failed: none.
No shell, write, edit, grep, glob, extra file reads, protected paths, .env,
.git, token, credential, or browser data was used.
```

Captured answer:

```text
decision-inbox/level3-consultations/level3-live-capture-20260624/advice/2026-06-24T08-55-49Z-chatgpt-web-full-agent.md
```

Local classification:

```text
Adopt: keep the three-tier model, default safe three-file review set,
advisor-channel gate, and read-only-first Level 3 packaging.
Ask: reduce Level 3 trigger friction, make failure states more user-readable,
and add a compact Level 3 state card.
Reject: default automatic execution, treating advisor output as authorization,
leaving Level 3 online long-term, and defaulting to deeper file reads.
```

Close verification:

```text
full_agent_session_closed.
Tailscale Funnel: No serve config.
Port 8765: not listening.
Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5.
```

Round I:
The same full capture-backed browser-automation product flow was run again with
the Level 3 user-entry/status-card maturity question.

Preparation:

```text
Advisor channel: browser-automation ready.
Allowed root: <allowed-project-root>.
Open-time preflight: ok.
Public health: stable preflight_passed=5/5.
Prompt preparation: copied.
Risk while open: 5/5.
```

ChatGPT Web used the attached Full-Agent connector and returned this result:

```text
Level 3 connector: truly worked.
open_workspace: succeeded.
connector profile: full-agent.
connector risk: 5/5.
Read succeeded: README.md, docs/security-public.md,
docs/conversation-product-mode.md.
Read failed: none.
No shell, write, edit, protected paths, .env, .git, token, credential, or
browser data was used.
```

Captured answer:

```text
decision-inbox/level3-consultations/level3-live-capture-20260624-round2/advice/2026-06-24T09-10-16Z-chatgpt-web-full-agent.md
```

Advisor verdict:

```text
Adopt: keep short task windows, explicit allowed root, advisor health gate,
default three-file safe prompt, capture review-only gate, and close/idle close.
Ask: make the one-line Level 3 trigger and user-readable status card more
explicit.
Reject: claiming complete maturity, opening 5/5 before advisor readiness, or
pretending Full-Agent is an outbound GPT Pro API.
```

Close verification:

```text
full_agent_session_closed.
Tailscale Funnel: No serve config.
Port 8765: not listening.
Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5.
```

Round J:
The third capture-backed browser-automation product flow was run with the
ordinary-user usability and failure-message question.

Preparation:

```text
Advisor channel: browser-automation ready.
Allowed root: <allowed-project-root>.
Open-time preflight: ok.
Public health: stable preflight_passed=5/5.
Prompt preparation: copied.
Risk while open: 5/5.
```

ChatGPT Web used the attached Full-Agent connector and returned this result:

```text
Level 3 connector: worked for this bounded review path.
open_workspace: succeeded.
Read succeeded: README.md, docs/security-public.md,
docs/conversation-product-mode.md.
Read failed: none.
No shell, write, edit, or unrelated file reads were used.
```

Captured answer:

```text
decision-inbox/level3-consultations/level3-live-capture-20260624-round3/advice/2026-06-24T09-17-16Z-chatgpt-web-full-agent.md
```

Advisor verdict:

```text
Adopt: call Level 3 "short-window user-web/browser-automation usable"; the
trigger, advisor-channel gate, and failure wording are directionally correct.
Ask: keep the maturity wording bounded and verify all wrapper exits use the
new failure message.
Reject: calling it fully autonomous, enabling browser automation by default, or
opening 5/5 before advisor readiness.
Smallest fixes: hard confirmation before browser automation controls the
computer, and a shared failure sentence: "GPT Pro has not been consulted yet;
the system is still preparing or waiting."
```

Close verification:

```text
full_agent_session_closed.
Tailscale Funnel: No serve config.
Port 8765: not listening.
Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5.
```

## Product Implication

After the three capture-backed ChatGPT Web rounds, Level 3 should report:

```text
Current state: usable_short_window_browser_automation
Requested mode: full-agent
Full-Agent session: three_capture_backed_browser_automation_rounds_verified
Risk if opened: 5/5
Reason: ChatGPT Web can use the connector, repeated compact rounds have
succeeded, and three capture-backed browser-automation rounds completed end to
end. The public endpoint still must pass health checks immediately before each
task window, and browser automation still occupies the user's computer while it
runs.
Next options: keep docs/security-public.md as the default safety input, keep
short connector-only rounds as the default, classify returned advice as
Adopt / Ask / Reject, and avoid "fully autonomous/no-friction" wording.
```

Do not describe account-side connector smoke tests as GPT Pro consultation.
Do not describe successful short-window ChatGPT Web rounds as a mature
always-on or background Level 3 product.

Implemented follow-up:

- `scripts/conversation_product_gate.py` is a side-effect-free product gate.
- It returns `waiting_for_advisor_channel` when the requested tier is
  Full-Agent but ChatGPT Web is blank, timed out, unavailable, or unknown.
- It can report `advisor-health=needs-browser-restart` for the recovery path
  that requires user confirmation before restarting Chrome.
- It returns `ready_to_open_full_agent` only after the advisor channel is
  explicitly marked `ready`.
- Product docs now require this health gate before opening a `5/5` Full-Agent
  public window.
- `scripts/level3_status.py` is a side-effect-free combined readiness command
  that reports the Level 3 gate, Full-Agent session state, and Tailscale Funnel
  state together.
- `docs/security-public.md` is the sanitized safety summary for web-advisor
  reads.
- `scripts/level3_consultation_prompt.py` renders the default short
  connector-only prompt for Level 3 web consultations.
- The default Level 3 prompt now uses a compact three-file safe set:
  `README.md`, `docs/security-public.md`, and
  `docs/conversation-product-mode.md`. Use `--deep` only for a second,
  targeted review when the first round proves the connector is working. This
  change directly addresses the observed Web run where a five-file prompt was
  only partially followed.
- `scripts/full_agent_session.py open` now prints a compact product-readiness
  summary that separates connector preflight from advisor-channel verification:
  `connector_tools_verified`, `advisor_channel_verified`, `session_online`, and
  `risk=5/5`.
- `scripts/level3_consultation_flow.py` is the default product wrapper for
  future Level 3 runs so Codex does not have to hand-compose `gate`, `open`,
  `status`, `prompt`, and `close` commands for every consultation.
- The wrapper now defaults to `advisor-channel=unknown` and
  `advisor-health=unknown`. Codex must explicitly mark `user-web`,
  `browser-automation`, or `direct-tool` as ready before the `5/5` Full-Agent
  window opens. Successful preparation prints a plain user handoff: open
  ChatGPT Web with GPT-5.5 Thinking selected and the Full-Agent connector,
  paste/send the copied prompt, and paste the answer back into Codex for
  Adopt / Ask / Reject classification.
- The wrapper now treats a first `Public health: intermittent` result as a
  recoverable warmup signal and runs one extra full health check. It proceeds
  only if the recovery check is `stable`; otherwise it closes the `5/5` window.
  A `failed` public health result still closes immediately.
- `scripts/level3_consultation_flow.py capture` now provides the product
  returned-answer path for Level 3. It wraps `scripts/level3_capture_advice.py`,
  stores pasted ChatGPT Web advice under `decision-inbox/level3-consultations/`,
  renders a review-only gate, refuses to store obvious secret material, and
  refreshes the 20-minute idle window by default. It does not execute advisor
  instructions or edit project files.
- `scripts/conversation_product_gate.py` now prints an explicit not-consulted
  notice for `waiting_for_advisor_channel` states:
  `GPT Pro has not been consulted yet; the system is still preparing or waiting.`
- `scripts/level3_consultation_flow.py prepare` now repeats that not-consulted
  notice on local-side failures before a real advisor answer, and prints a
  browser-automation warning before the Web step:
  the browser automation will temporarily control the user's computer UI, and
  the user should not use the mouse or keyboard during that Web step.

## Verification Commands

Local regression after lifecycle fix:

```bash
python3 -m unittest tests.test_full_agent_session tests.test_decision_inbox_tunnel_window
```

Observed:

```text
Ran 13 tests
OK
```

Full suite:

```bash
python3 -m unittest discover -s tests
```

Observed:

```text
Ran 137 tests
OK
```

Latest full-suite verification after Round J and product-message fixes:

```text
python3 -m unittest discover -s tests
Ran 138 tests in 20.539s
OK
```

Latest close verification after tests:

```text
full_agent_session_closed.
Tailscale Funnel: No serve config.
Port 8765: not listening.
Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5.
```
