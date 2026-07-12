# Connected Agent User Flow

This is the non-technical product flow for Connected Agent consultations.

## What The User Says

```text
Use Connected Agent to consult ChatGPT Web about: <question>
```

Codex should treat this as `Connected Agent`, not as Ask First.

If the user explicitly wants GPT Pro deep reasoning and no connector, use Ask
First instead.

## What Codex Does

1. Reports that Connected Agent is risk `3/5-5/5` while online; Danger Auto is
   fixed risk `5/5`.
2. Uses the current project as the allowed root only after the user has clearly
   asked for Connected Agent.
3. Checks that an advisor channel is available:
   - `user-web`: the user will send the prompt in ChatGPT Web,
   - `browser-automation`: Codex is allowed to operate ChatGPT Web and will
     occupy the visible browser while it runs,
   - `direct-tool`: Codex has a callable advisor tool.
4. Opens a short Connected Agent session only after the advisor channel is ready.
5. Runs the fast public health check before asking ChatGPT Web to use the connector.
6. On the newer Colleagues or embedded ChatGPT surface, discovers the exact
   user-created connector display name, then tells the user to type `@` and
   select that exact connector in the composer. For the default connector in
   this project, the name is `Agent Decision Bridge Connected Agent`. The UI
   may render the selection as a `plugin://...` reference; users should not
   hand-type or reconstruct account-specific plugin IDs. A plain-text connector
   name does not attach tools. Codex confirms that the connector reference and
   tools are visible before continuing. If they are not visible, Codex should
   stop at `waiting_for_advisor_channel` or fall back to Ask First.
   For the current Connected Agent release, Codex must verify the complete tool
   contract before project inspection. If any tool is missing, it reopens the
   local short-lived session, starts a fresh web conversation, reattaches the
   exact connector through `@`, and checks again. If the fresh conversation is
   still incomplete, it stops with `connector_contract_incomplete` and asks the
   user to update/re-publish or reinstall the connector. It must not silently
   continue with a partial schema.
7. Gives ChatGPT Web a compact prompt that opens the workspace deterministically:
   call `open_default_workspace` when visible; otherwise call
   `open_workspace` exactly once with path `"default"`. The compatibility alias
   is mandatory for a stale schema, needs no absolute path or extra user
   confirmation, and must not be misreported as a missing server feature.
   The prompt then inspects context first, lets the
   advisor choose task-relevant files under the allowed root, and hard-blocks
   high-risk credential paths at the server.
   Whole-file `read` returns the UTF-8 body in both the MCP text content block
   and `structuredContent.content` for ChatGPT Connector compatibility. Use
   `read_lines` for bounded excerpts and large source files.
8. Allows write/edit/bash through one-action approval by default: the tool
   returns `approval_id`, ChatGPT asks the user to approve that exact action,
   calls `grant_action_approval`, and retries once. The hidden danger switch
   starts only if the user types `dangerously trust connected agent`, and
   server policy still blocks unsafe commands and sensitive paths.
9. Imports the returned advice.
10. Classifies recommendations as `Adopt`, `Adapt`, `Reject`, or `Need info`.
11. Keeps the session open after capture and lets the idle watchdog close it 20
   minutes after the last Connected Agent use.

If the advisor channel is not ready or local preparation fails before a real
answer returns, Codex should say:

```text
GPT Pro has not been consulted yet; the system is still preparing or waiting.
```

For the user, the status card should answer:

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
1. Keep ChatGPT Web open with a tool-capable chat mode selected and the Connected Agent connector attached.
2. Let Codex paste/send the prompt and copy the answer.
3. Wait for Codex to capture the answer, refresh the 20-minute idle window, and
   report the result.
```

In the safer `user-web` fallback, the user only needs to:

```text
1. Open ChatGPT Web with a tool-capable chat mode selected. Type @ and select the exact user-created connector name shown in the connector detail; for the default setup, select Agent Decision Bridge Connected Agent.
2. Paste and send the prompt that Codex copied/prepared.
3. Paste ChatGPT's answer back into Codex.
```

The user should not need to run backend commands.

## Fast Product Default

For normal Connected Agent use, Codex should prefer the product-name wrapper:

```bash
python3 scripts/connected_agent_flow.py prepare \
  --allowed-root "$PWD" \
  --public-base-url "https://your-public-host.example.com" \
  --advisor-channel user-web \
  --advisor-health ready \
  "<question>"
```

The default wrapper profile is `--speed fast --output compact`. It should show
the compact status card above and one next action, not a long explanation of the
whole safety model. Use `--speed safe --output verbose` only for connector
verification, tunnel debugging, or a known unstable public endpoint.

## What Codex Runs After The Answer Comes Back

When the user pastes the ChatGPT answer back, Codex captures it as external
advice data:

```bash
python3 scripts/connected_agent_flow.py capture \
  --advisor chatgpt-web-connected-agent \
  "<original question>"
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

Adapt:
- ...

Reject:
- ...

Need info:
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
  predecessor workspace connector, local capture, and clean close verification.

Still not fully frictionless:

- Browser automation occupies the user's visible browser; the user should not
  operate the computer while it runs.
- Tailscale Funnel can be intermittent; it must pass health checks before each
  Connected Agent task window.
- Cloudflare Named Tunnel is not configured until Cloudflare login/origin
  certificate setup is complete.
