# Implementation Plan

This plan keeps the implementation history, but the current user-facing product
language is consolidated in [`docs/user-guide.md`](user-guide.md).

Current public modes:

- **Ask First**: Codex prepares a focused review package for manual advisor
  review. No connector exposure. Risk `1/5`.
- **Connected Agent**: ChatGPT Web connects to a short-lived allowed project
  window through Apps/MCP connector tools. Read/search/list are automatic;
  write/edit/bash use one-action approval by default. Risk `3/5-5/5`.

Older tiered names and separate read-only/full-access connector names are
historical implementation names or compatibility aliases. Do not use them as
primary product copy for new users.

## Goal

Reduce manual copy-paste between Codex and web advisor models while preserving the `agent-decision-bridge` safety model.

## Current Product Model

Status: implemented locally.

- **Ask First**: package/advice only, no MCP exposure, risk `1/5`.
- **Connected Agent**: ChatGPT Web connects to allowed project roots through
  `--mode connected-agent`; read/search/list are automatic, while
  write/edit/bash use one-action approval by default.
- **Danger Auto** is a Connected Agent sub-mode. It starts only when the user
  typed `dangerously trust connected agent` in ChatGPT Web and the connector
  calls `enable_danger_auto`. It is session-only, fixed risk `5/5`, and still
  server-blocks secret paths, network commands, GUI/clipboard commands, path
  escapes, dependency installs, Git remote operations, permission changes, and
  broad destructive operations.
- Legacy `auto-mcp`, `read-only-project`, and `full-agent` remain only as
  compatibility aliases for existing tests/connectors.

## Phase 0: Project Scaffold

Status: complete.

Deliverables:

- `README.md`
- `PROJECT_CONTEXT.md`
- `AGENTS.md`
- `docs/plan.md`
- `docs/security.md`
- `docs/security-public.md`
- `docs/architecture.md`
- `docs/decision-inbox-protocol.md`
- `docs/phase-1-local-verification.md`
- `docs/phase-1-restricted-access-test.md`
- `docs/phase-2-decision-inbox-local-verification.md`
- `docs/phase-2-external-connector-verification.md`
- `decision-inbox/README.md`
- `decision-inbox/tasks/README.md`
- `decision-inbox/tasks/_template/`
- `decision-inbox/tasks/phase-1-package-only-mcp-review/`
- `test-workspace/README.md`
- `test-workspace/synthetic-project/`
- `server/README.md`

Exit criteria:

- A new Codex thread can read the project files and understand the current goal without seeing the original long conversation.
- The inbox has a concrete package/advice/fact-check folder shape that does not expose real project files.
- The test workspace contains only synthetic files.

## Phase 1: Restricted MCP Access Test

Status: local stdio server implemented. External ChatGPT Web connector validation was deferred in favor of the narrower Phase 2 Decision Inbox connector test.

Purpose:

Verify whether ChatGPT Web can use an MCP connector to access a restricted local test workspace.

Scope:

- Use only `test-workspace/`.
- Use synthetic files only.
- No secrets.
- No real project data.
- No shell execution unless explicitly isolated and approved.
- Document the connector path, tunnel/auth requirements, and negative access tests before using the connection for real decisions.

Candidate options:

- A tiny local MCP server with read-only synthetic tools. Current local implementation: `server/restricted_test_workspace_server.py`.
- DevSpace against `test-workspace/`, only if the user explicitly chooses that connector path and keeps the allowlist synthetic.

Exit criteria:

- ChatGPT Web can list or read an allowed synthetic file.
- ChatGPT Web cannot access files outside the allowlisted test workspace.
- The connection requirements are documented.
- Codex records the result in a local verification note before Phase 2 implementation begins.

## Phase 2: Decision Inbox MCP v1

Status: local stdio/HTTP implementation and ChatGPT Web external connector verification complete.

Purpose:

Replace manual copy-paste with a narrow inbox protocol.

MCP tools to consider:

- `list_decision_tasks`
- `get_decision_package`
- `submit_advice`
- `get_task_status`

Implemented local files:

- `server/decision_inbox_store.py`
- `server/decision_inbox_server.py`
- `server/decision_inbox_http_server.py`
- `scripts/decision_inbox_doctor.py`
- `scripts/decision_inbox_preflight.py`
- `scripts/decision_inbox_tunnel_window.py`
- `scripts/import_advice_review.py`

Allowed storage:

- `decision-inbox/tasks/<task-id>/package.md`
- `decision-inbox/tasks/<task-id>/metadata.json`
- `decision-inbox/tasks/<task-id>/advice/<timestamp>-<advisor>.md`
- `decision-inbox/tasks/<task-id>/fact-check-requests/<timestamp>.md`

Explicitly disallowed in v1:

- reading arbitrary project files,
- writing arbitrary project files,
- running shell commands,
- changing Git state,
- installing dependencies,
- exposing secrets.

Exit criteria:

- Codex can create a task package. Local complete.
- Local MCP stdio and HTTP smoke can read a package and submit advice. Complete.
- ChatGPT Web can read it through MCP. Complete on 2026-06-21 through `Decision Inbox Lab Temp`.
- ChatGPT Web can submit advice. Complete; advice file `2026-06-21T00-00-00Z-chatgpt-web-external-connector-test.md` was written under the task advice folder.
- Codex can import the submitted advice and run `agent-decision-bridge` Import Mode. Complete in review-only mode; material recommendations were classified locally.

## Phase 3: End-To-End Decision Loop

Status: complete for the synthetic package-only task.

Purpose:

Prove the loop works on a realistic but safe decision.

Test scenario:

- Codex writes a decision package about whether to add read-only project context to the MCP server.
- ChatGPT Web reads the package.
- ChatGPT Web submits advice.
- Codex imports the advice.
- Codex classifies items as `Adopt`, `Adapt`, `Reject`, or `Need info`.
- Codex recommends stop or one targeted follow-up round.

Observed result on 2026-06-21:

- No manual copy-paste of the package or advice was needed after connector setup.
- Positive test succeeded: ChatGPT Web listed the task, read the package, and submitted advice.
- Negative test succeeded: `../README` and `.env` were rejected, and no shell/Git/arbitrary file/dependency tools were available.
- Codex imported the advice in review-only mode and kept advisor output as advice, not authorization.

Exit criteria:

- No manual copy-paste of package/advice is needed after initial connector setup.
- Codex does not treat external advice as authorization.
- User can inspect files under `decision-inbox/`.

## Phase 3.1: Repeatable Connector Hygiene

Status: Tailscale Funnel stable public URL verified locally. Current
project-aware review uses Connected Agent. Legacy Auto MCP remains available for
package-only compatibility.

Purpose:

Borrow the useful DevSpace connector pattern while keeping endpoint setup,
OAuth state, and project access boundaries explicit.

Implemented:

- public base URL validation for the HTTP server,
- Host header allowlist derived from local host plus public base URL,
- OAuth Owner password approval for stable ChatGPT connector runs,
- optional explicit OAuth state persistence outside the repo for repeated
  connector runs,
- local auth reset helper for deleting persisted OAuth state and Owner password
  files,
- explicit legacy workspace-connector default auth paths can also be reset,
- local connector doctor that reports token presence, local probe status, and
  risk coefficient without printing secrets,
- `docs/connector-runbook.md` for temporary and stable URL runs,
- `docs/tailscale-funnel-verification.md` for the no-owned-domain stable URL path.

Non-goals:

- no project writes in the older read-only compatibility connector,
- no shell, Git, dependency install, or arbitrary write tools,
- no automatic ChatGPT account-side connector edits.

2026-06-23 historical scope update:

- the implementation temporarily used the names `Manual Package`,
  `Read-Only Project Advisor`, and `Full-Agent Execution`,
- the read-only and full-agent compatibility connectors used separate ChatGPT
  connectors and separate OAuth scopes,
- legacy Auto MCP public tool surface is restricted to package read, advice
  writeback, task listing, and task status,
- `request_local_fact_check` remains a local file protocol concept but is not
  exposed as a default Auto MCP web tool,
- `submit_advice` now validates advisor identity, timestamp handling, and an
  explicit non-authorization marker before writing advice,
- preflight and Tailscale Funnel lifecycle helpers are part of the repeatable
  connector workflow.

Exit criteria:

- `python3 scripts/decision_inbox_doctor.py` gives a clear local/tunnel risk state.
- HTTP tests cover Host allowlisting and public URL validation.
- Repeated ChatGPT connector tests can use a stable public URL or an explicit
  reconnect flow instead of relying on an editable app endpoint.
- The Tailscale Funnel endpoint rejects unauthenticated access and exposes only
  the Auto MCP package/advice/status tools with OAuth or bearer-token authentication.
- Optional OAuth state persistence survives local server restart, keeps state
  outside the repo, uses `0600` file permissions, and can be revoked locally.

## Phase 4: Optional Read-Only Project Context

Purpose:

Decide whether web advisors should read selected project facts directly.

Possible design:

- Only allow configured read-only roots.
- Require a per-task allowlist.
- Redact or deny secret-like paths.
- Prefer summaries over full files.

Exit criteria:

- Security review passes.
- User explicitly chooses to expand from package-only mode.

## Phase 5: Optional Controlled Execution

Status: implemented locally and folded into the current Connected Agent product
model.

Purpose:

Support a DevSpace-like coding workflow only when the user explicitly chooses a
project-aware Connected Agent session with approval gates.

Implemented:

- `--mode connected-agent` on the HTTP MCP server for the current product,
- legacy `--mode full-agent` and `--mode read-only-project` compatibility
  aliases on the HTTP MCP server,
- `--allowed-root` required, with home and filesystem roots rejected,
- Connected Agent backend tools: `open_workspace`, `read`, `write`, `edit`,
  `grep`, `glob`, `ls`, and `bash`,
- default OAuth Owner password and state files under
  `~/.local/share/agent-decision-bridge/`,
- `--oauth-state-file none` to disable OAuth persistence,
- doctor fixed `5/5` risk when the hidden danger switch is active,
- reset helper support for default OAuth state,
- `scripts/full_agent_session.py` legacy session-window helper:
  start the workspace connector, open public window, run preflight, keep the
  session alive during active Codex work, and close after idle timeout,
- `scripts/prepare_consultation.py` Manual Package / legacy package helper:
  create a package-ready task from a natural-language user request. It must not
  be used for Connected Agent.
- `docs/security-public.md`: sanitized safety summary for ChatGPT Web reads
  when raw `docs/security.md` would trigger platform tool-safety blocking.
- `scripts/connected_agent_flow.py`: product-name alias for the Connected Agent
  consultation wrapper. It defaults to a fast compact startup path for repeated
  user-facing use, while `--speed safe --output verbose` keeps the older
  conservative tunnel-verification profile.

Constraints:

- Ask First is the safest manual package mode.
- Legacy Auto MCP remains available for package-only compatibility.
- Connected Agent is not a sandbox.
- Bash runs with the local user account.
- The hidden danger switch is always fixed risk `5/5`.
- Idle shutdown reduces exposure duration only; online Connected Agent risk
  remains non-trivial while the connector is open.
- Connected Agent is inbound from ChatGPT Web to local tools; it is not an
  outbound GPT Pro API for Codex.
- ChatGPT Web connector runs should use a chat mode where Apps/MCP connector
  tools are visible. If connector tools are unavailable, use Ask First for
  manual GPT Pro review.
- Codex must not claim a GPT Pro consultation happened unless advice was
  actually returned through MCP, browser automation, a direct advisor tool, or
  pasted user evidence.

## Current Next Action

Use the current English documentation as the canonical product description:
`README.md` for overview, `docs/user-guide.md` for user workflow, and
`docs/connector-runbook.md` for setup. For product validation, run repeated
short ChatGPT Web Connected Agent consultations with connector tools visible and
the compact prompt helper. Verify that the advisor can choose task-relevant
files, avoid high-risk credential paths, return advice, and let Codex classify
recommendations as `Adopt / Ask / Reject`. Keep the failure path: when no
advisor channel is visible, the product reports `waiting_for_advisor_channel`
instead of creating a manual package and implying that GPT Pro reviewed it.
