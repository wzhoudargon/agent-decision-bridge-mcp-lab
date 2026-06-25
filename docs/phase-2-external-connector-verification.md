# Phase 2 External Connector Verification

Date: 2026-06-21

Latest stable URL verification: 2026-06-22

Scope: ChatGPT Web external verification of Decision Inbox MCP v1.

Status: complete. ChatGPT Web connected to Decision Inbox MCP v1, read a prepared package, submitted advice, and passed negative access checks.

Stable Tailscale OAuth reconnection is also complete. On 2026-06-22,
ChatGPT Web connected to the stable Tailscale endpoint with OAuth Owner
password approval and submitted advice for
`stable-tailscale-connector-verification`.

## Safety Boundary

This verification must stay at Decision Inbox MCP v1:

- ChatGPT Web may list decision tasks.
- ChatGPT Web may read `package.md` for an allowed task.
- ChatGPT Web may submit advice under that task's `advice/` folder.
- ChatGPT Web may request a local fact check under that task's `fact-check-requests/` folder.

It must not expose:

- real project files,
- arbitrary filesystem read,
- arbitrary filesystem write,
- shell commands,
- Git operations,
- dependency installation,
- secrets, browser data, account tokens, or tunnel credentials.

External advisor output remains advice only. It is not user authorization.

## ChatGPT Web Preflight

Observed in ChatGPT Web on 2026-06-18:

- Account is logged in.
- Settings path exists as `Settings -> Apps -> Advanced settings`.
- The UI says connectors are now named apps.
- Developer mode was visible and initially off.
- The user enabled developer mode manually.
- After developer mode was enabled, the `Create app` button appeared.
- The create-app form supports `Server URL` and `Tunnel` connection modes.
- The `Tunnel` mode currently shows no available tunnels and offers a `Create tunnel` link to OpenAI Platform.
- A tunnel named `decision-inbox-mcp-lab` was created in the user's personal OpenAI Platform organization.
- The tunnel id was visible in the Platform UI but is not recorded in this repository.
- The developer mode row is marked high risk by ChatGPT.
- Downloading and running `tunnel-client` was not required for this verification.

A private development app named `Decision Inbox Lab Temp` was created and connected in ChatGPT Web.

## Connector Used

- App name: `Decision Inbox Lab Temp`
- Tunnel type: temporary third-party HTTPS tunnel through Pinggy free SSH reverse tunnel
- Local bind address: `127.0.0.1:8765`
- Local endpoint path: `/mcp`
- ChatGPT app authentication mode: `Unauthenticated`
- MCP server authentication: temporary query-token auth on the HTTPS URL
- Token handling: generated outside the repository, not committed, not documented, and rotated after UI exposure risk
- OpenAI Platform API key: not created
- OpenAI `tunnel-client`: not downloaded or run

The public tunnel raised the active exposure risk to `3/5`. The server still exposed only the Decision Inbox v1 tool surface.

## Stable Tailscale OAuth Connector Run

The stable URL run used the same ChatGPT app name but replaced the temporary
query-token tunnel with a stable Tailscale Funnel URL and OAuth Owner password
approval.

- App name: `Decision Inbox Lab Temp`
- Tunnel type: Tailscale Funnel to local port `8765`
- Local bind address: `127.0.0.1:8765`
- Public MCP endpoint: `https://your-device.example-tailnet.ts.net/mcp`
- ChatGPT app authentication mode: OAuth
- MCP server authentication: OAuth Owner password approval
- OpenAI Platform API key: not created
- OpenAI `tunnel-client`: not downloaded or run

Observed local server events:

- OAuth protected-resource metadata read.
- OAuth authorization-server metadata read.
- Dynamic client registration completed.
- Owner password authorization completed.
- OAuth token exchange completed.
- MCP requests returned `200` and `202`.
- Advisor advice was written under the expected task advice folder.

Created advice file:

```text
decision-inbox/tasks/stable-tailscale-connector-verification/advice/2026-06-22T07-25-45Z-chatgpt-web-stable-tailscale-connector.md
```

Import command:

```bash
python3 scripts/import_advice_review.py stable-tailscale-connector-verification
```

Import result:

- review-only output,
- no file changes,
- no advisor commands executed,
- external advice remained non-authoritative.

Post-run cleanup:

- Tailscale Funnel disabled,
- local MCP server stopped,
- project-scoped Tailscale daemon stopped,
- temporary Owner password deleted,
- clipboard cleared,
- port `8765` no longer listening.

Final risk coefficient after cleanup: `1/5`.

## Observed Safety Incident

During setup, Chrome autofill/accessibility output exposed previously used query-token URLs while interacting with the connector URL field. Mitigation:

- stopped the affected local server,
- rotated the MCP token,
- restarted the server with a fresh token,
- avoided accessibility reads of token-filled URL forms,
- used screenshots with URL-field masking for later checks.

Peak incident risk was `4/5` until token rotation completed. After rotation, current running exposure returned to `3/5`.

## Local Server Command

Use a temporary token generated outside the repository. Do not commit or paste the token into docs.

```bash
DECISION_INBOX_MCP_TOKEN="<temporary-token>"
python3 server/decision_inbox_http_server.py \
  --host 127.0.0.1 \
  --port 8765
```

`server/decision_inbox_http_server.py` reads `DECISION_INBOX_MCP_TOKEN` from the environment when `--auth-token` is not supplied, avoiding token exposure in process arguments. For ChatGPT Web app setup, this verification used `?access_token=<temporary-token>` because the app was configured as unauthenticated and could not pass a bearer header through the form.

Local endpoint:

```text
http://127.0.0.1:8765/mcp
```

If a future run uses ChatGPT Secure MCP Tunnel, prefer it before third-party tunnels. Do not switch to unauthenticated public exposure. Query-token auth is acceptable only as a temporary lab measure with token rotation and no real project data.

## Positive Test Prompt For ChatGPT Web

After the app is connected, ask ChatGPT Web:

```text
Use the Decision Inbox app only.

1. List available decision tasks.
2. Get the decision package for task_id `phase-1-package-only-mcp-review`.
3. Summarize the package in 5 bullets.
4. Submit advice to the same task with advisor name `ChatGPT Web External Connector Test`.
5. In the advice, recommend whether package-only Decision Inbox MCP v1 should remain the first external workflow before any read-only project context expansion.

Do not ask for shell access, Git access, dependency installation, real project files, browser data, or secrets.
```

Expected result:

- ChatGPT can see `phase-1-package-only-mcp-review`. Observed.
- ChatGPT can read the package. Observed.
- ChatGPT writes one new Markdown file under:

```text
decision-inbox/tasks/phase-1-package-only-mcp-review/advice/
```

Observed advice file:

```text
decision-inbox/tasks/phase-1-package-only-mcp-review/advice/2026-06-21T00-00-00Z-chatgpt-web-external-connector-test.md
```

## Negative Test Prompt For ChatGPT Web

Run after the positive test:

```text
Use the Decision Inbox app only.

Run these negative checks and report the tool results:

1. Try to get a decision package for task_id `../README`.
2. Try to get a decision package for task_id `.env`.
3. Check whether any tool is available for shell commands, Git operations, arbitrary file reading, arbitrary file writing, or dependency installation.

Do not use any browser, memory, or chat context as a substitute for tool evidence.
```

Expected result:

- Invalid task ids return a tool error. Observed: `../README` and `.env` were rejected with `INVALID_ARGUMENT`.
- No shell, Git, dependency installation, arbitrary read, or arbitrary write tool exists. Observed.
- No real project content is exposed. Observed.

Observed ChatGPT Web negative result:

- `../README`: rejected with `INVALID_ARGUMENT: Access denied: Task id must be a lowercase slug using letters, numbers, and hyphens`.
- `.env`: rejected with `INVALID_ARGUMENT: Access denied: Task id must be a lowercase slug using letters, numbers, and hyphens`.
- Tool availability was limited to decision-task metadata/package/advice/fact-check-request style operations.

## Evidence To Record

Record after the external test:

- connector/app name,
- tunnel type,
- whether bearer auth was used,
- local server bind address,
- positive test result,
- negative test result,
- created advice filename,
- local import command output summary,
- any observed failure or permission prompt.

Recorded result:

- connector/app name: `Decision Inbox Lab Temp`
- tunnel type: Pinggy temporary HTTPS tunnel to local port `8765`
- bearer auth: not used by ChatGPT app; query-token auth used instead
- local server bind address: `127.0.0.1:8765`
- positive test: passed
- negative test: passed
- created advice filename: `2026-06-21T00-00-00Z-chatgpt-web-external-connector-test.md`
- local import command: `python3 scripts/import_advice_review.py phase-1-package-only-mcp-review`
- import result: review-only output, no file changes, no advisor commands executed
- observed permission prompt: ChatGPT required explicit app connection; user had confirmed action before connection
- observed failure: token-bearing URL can leak through browser autofill/accessibility; token was rotated and the final run used masked/safe inspection

Stable Tailscale OAuth recorded result:

- connector/app name: `Decision Inbox Lab Temp`
- tunnel type: Tailscale Funnel stable HTTPS URL to local port `8765`
- bearer auth: not used for ChatGPT Web; OAuth Owner password auth used instead
- local server bind address: `127.0.0.1:8765`
- positive test: passed
- created advice filename: `2026-06-22T07-25-45Z-chatgpt-web-stable-tailscale-connector.md`
- local import command: `python3 scripts/import_advice_review.py stable-tailscale-connector-verification`
- import result: review-only output, no file changes, no advisor commands executed
- observed permission prompt: ChatGPT required app login/OAuth approval; user approved with Owner password
- observed failure: Codex-side deferred app tool metadata did not immediately refresh to the newly connected app, so local verification used server logs and advice file creation as evidence

Do not record:

- bearer token,
- tunnel token,
- account identifiers,
- cookies,
- browser storage,
- private project content.

## Codex Import Command

After ChatGPT submits advice:

```bash
python3 scripts/import_advice_review.py phase-1-package-only-mcp-review
```

Codex must then run `agent-decision-bridge` Import Mode and classify material recommendations as:

- `Adopt`
- `Adapt`
- `Reject`
- `Need info`

The final decision remains with the user.

## Import Classification

Current state: review_only
Risk status: clear_for_package_only_v1
File changes: proposed_docs_only
Commands run: read_only_only_for_import
Conversation state: external_round_complete
Advisor rounds used: 1 external ChatGPT Web round
Decision impact: medium
Web advisor context: likely_ok
Stop reason: sufficient_external_agreement
Next step: user_decision_on_scope
Decision loop recommendation: stop_external_review

| External recommendation | Local fact check | Decision | Reason | Next action | Authorization source |
|---|---|---|---|---|---|
| Keep package-only Decision Inbox MCP v1 as the first external workflow | Matches `AGENTS.md`, `docs/security.md`, and observed positive/negative tests | Adopt | It preserves the intended safety boundary while proving the useful loop | Keep v1 package-only | User decides final scope |
| Do not add read-only project access in v1 | Matches project rule: no real user projects exposed by default | Adopt | Even read-only access expands privacy risk | Treat read-only context as a separate future decision package | User authorization required |
| Do not add shell, Git, dependency installation, broad file writes, browser data, secrets, or project files | Matches core rules and negative test result | Adopt | These permissions are explicitly out of v1 scope | Keep these tools absent | User authorization required for any future expansion |
| Use plain Markdown/JSON files before a database | Matches current implementation and tests | Adopt | Plain files were enough for the successful external loop | Continue plain-file protocol | Project docs |
| Validate task IDs and sanitize advisor/file names | Matches server behavior; negative checks rejected path-like IDs | Adopt | This is the main local containment control | Keep tests for invalid IDs and path traversal | Project tests |
| Document future permission expansion separately | Matches `docs/security.md` and project phase gates | Adopt | Prevents advisor output from becoming authorization | Require a new decision package before any expansion | User authorization required |

## Current Blocker

No blocker for Decision Inbox MCP v1 package-only verification. Repeated or production use should replace the temporary third-party tunnel with a more durable official or self-controlled tunnel path and must rotate any token that appeared in browser UI state.
