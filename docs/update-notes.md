# Update Notes

## 2026-07-14: Skill 1.0.0 Release Identity

### What Changed

- Declared `agent-decision-bridge` Skill release `1.0.0` in the reusable Skill
  and public project documentation.
- Kept the independently versioned Connected Agent server at `0.4.2` and the
  25-tool connector contract at `2.1`.
- Added an explicit version identity table so Skill, server, and connector
  contract releases are not confused with one another.

### Validation

- Runtime and repository Skill copies are byte-identical.
- Skill structure validation passes without adding unsupported YAML frontmatter.
- Existing server and contract version assertions remain unchanged.

## 2026-07-13: Token-Only Prepared Action Commits

### What Changed

- Released server `0.4.2` with a more precise `run_task` impact annotation.
  Owner-configured checks remain non-read-only and host-confirmable, but are no
  longer advertised as destructive. The server still blocks network, install,
  privileged, Git remote, and destructive command classes and still accepts
  only an exact task returned by `list_tasks`.
- Kept Connected Agent contract `2.1` and all 25 tool names unchanged. Connector
  hosts must refresh the app metadata or start a fresh conversation to observe
  the updated annotation and description.
- Released server `0.4.1` as a contract-preserving compatibility fix. Optional
  root `path`/`cwd` values for `ls`, `grep`, prepared bash, and raw bash now
  normalize omitted, null, or blank host serialization to `.`. Required file
  paths remain non-empty and keep all traversal/protected-path checks.
- Added explicit `default: "."` metadata for those optional schema fields so
  Connector hosts have a deterministic root value. The tool contract remains
  `2.1` with the same 25 tool names; no connector re-publication is required
  for the server-side behavior fix.
- Advanced the Connected Agent tool contract to `2.1` with 25 tools by adding
  `prepare_action` and `commit_action`.
- Replaced the normal Controlled Auto raw write/edit/bash approval replay with a
  bound two-step flow. `prepare_action` validates and stores the complete
  immutable action; `commit_action` carries only the same workspace id and an
  expiring, single-use action id.
- Extended the bounded ChatGPT session's host-native confirmation trust to the
  write-annotated `commit_action`. The user sees one native connector dialog,
  and the model does not regenerate file content, replacement text, or command
  arguments after approval.
- Kept direct HTTP/stdio clients conservative: their small token-only commit
  call retains the hidden server one-action approval fallback.
- Kept raw `write`, `edit`, and `bash` as legacy compatibility tools rather than
  removing them from old clients.
- Preserved protected-path, workspace, network/GUI/clipboard, dependency,
  remote-Git, permission, and destructive-command boundaries. Prepared file
  actions are base-state/hash-bound, and prepared bash accepts only ordinary
  project-local commands.
- Updated the OAuth authorization warning to describe the bounded host-native
  commit path separately from legacy raw write/edit/bash approval.

### Validation

- Added regression coverage for write/create, edit, and bash prepared commits;
  token replay, expiry, cross-workspace use, file drift, direct-client fallback,
  protected paths, high-risk commands, HTTP wiring, and MCP annotations.
- Targeted Connected Agent suite: `91 tests OK`.
- Full Python suite in an isolated working-tree copy: `207 tests OK`.
- Repository Skill validation: `Skill is valid!`.

## 2026-07-13: Two Visible Connected Agent Permission Choices

### What Changed

- Simplified the user-facing Connected Agent permission model to two choices:
  `controlled_auto` by default and the explicit `danger_auto` switch.
- Treated the user's act of opening the bounded second-tier session as consent
  for Controlled Auto. Only previewed patches and owner-configured tasks become
  automatic.
- Kept Approval as a hidden enforcement fallback rather than a visible mode:
  raw write/edit/bash still require one-action approval, workspace expansion
  remains separately approved, and direct HTTP/stdio clients remain conservative.
- Made Danger Auto disable and idle expiry return to the session's base mode;
  product sessions return to Controlled Auto, direct fallback sessions return
  to Approval.
- Made the session helper detect stale or mismatched permission configuration,
  close the old session, and reopen it with the requested default instead of
  silently reusing an older Approval process.
- Updated the default online risk label to `4/5-5/5`; Danger Auto remains `5/5`.
- Kept all 23 tool names and the `2.0` contract identifier stable while narrowing
  the visible `set_permission_mode` schema to `controlled_auto`.
- Added explicit MCP annotations to all 23 tools so read/search/status operations
  are not misclassified as writes, while file, command, and permission mutations
  remain host-confirmable operations.
- Synchronized the repository's versioned `agent-decision-bridge` Skill and eval
  cases with the two-choice model. The installed runtime Skill remains a separate
  promotion step under the project's explicit-confirmation policy.

### Validation

- Added regression coverage for the product-session default, hidden direct-client
  fallback, Danger Auto return mode, visible-mode metadata, 23-tool schema, and
  read/write annotations.
- Targeted Connected Agent suite: `120 tests OK`.
- Full Python suite: `200 tests OK`.
- Repository Skill validation: `Skill is valid!`.

## 2026-07-13: Single Native Confirmation For Previewed Patches

### What Changed

- Kept direct MCP clients conservative: `apply_patch` still uses the server's
  one-action `approval_id` flow unless the session owner explicitly enables host
  confirmation trust.
- Made the bounded ChatGPT session helper enable that trust by default. After
  `preview_patch` shows the diff, ChatGPT's native write confirmation is the sole
  user prompt and `apply_patch` is called once with the single-use `preview_id`.
- Bound the commit token to workspace, path, base/result hashes, diff, expiry,
  and single use; stale files, cross-workspace use, and replay remain rejected.
- Added explicit read/write MCP annotations for `preview_patch` and `apply_patch`.
- Left raw `write`, `edit`, `bash`, `run_task`, workspace expansion, protected
  paths, and high-risk command gates unchanged.

### Validation

- Added regression coverage for host-confirmed commits, default direct-client
  approval, cross-workspace rejection, stale-file rejection, replay rejection,
  raw-write approval retention, HTTP wiring, session defaults, and MCP annotations.
- Full Python suite: `194 tests OK`.

## 2026-07-13: Codex Chat Dialog Terminology Correction

### What Changed

- Removed a mistaken product-surface label introduced by voice transcription.
- Standardized user-facing instructions on **the Codex built-in ChatGPT
  dialog**, or another ChatGPT surface that actually exposes Connector/App
  tools.
- Kept Connector availability conditional: the connector chip/reference and
  callable tools must be visible before the workflow continues.
- Updated the runtime/public Skill wording, user documentation, generated
  connector prompt, evaluation case, and regression test name.
- No permission, workspace, or server capability changed in this correction.

## 2026-07-13: Controlled Project Executor Contract 2.0

### What Changed

- Kept the public product model at two tiers: **Ask First** and **Connected
  Agent**. Added three clearly nested permission choices inside Connected
  Agent: `approval`, `controlled_auto`, and `danger_auto`.
- Made `approval` the default: raw side effects use the existing single-use
  `approval_id` flow. The later native-confirmation refinement applies only to
  an already previewed `apply_patch` in an explicitly configured host session.
- Added `file_info`, `preview_patch`, and `apply_patch`. A patch is bound to the
  current file hash, stored server-side, expires, and can be applied only once.
- Added `list_tasks` and `run_task`. Only exact commands configured by the local
  session owner with `--allowed-task NAME=COMMAND` can appear or run; arbitrary
  arguments are not accepted.
- Limited Controlled Auto to `apply_patch` and `run_task`. Raw write, edit, and
  bash remain approval-gated.
- Added `set_permission_mode` and `permission_mode_status` and returned
  `contract_version`, current permission mode, and the canonical tool list when
  opening a workspace.
- Removed duplicated tool allowlists from the prompt generator and preflight;
  both now derive the Connected Agent contract from the server schema.
- Fixed the Danger Auto high-risk-command path so its separate approval is now
  grantable and single-use instead of returning an approval error without an
  `approval_id`.
- Closed a workspace-expansion gap: `grant_workspace_access` now always uses a
  grantable single-use approval, including in Controlled Auto and Danger Auto.
- Kept credential paths, network commands, browser/desktop control, clipboard,
  and path escapes blocked. No new Git remote, network, secret, or desktop
  capability was added.

### Validation

- Added regression coverage for preview/apply hash binding, single-use patch
  IDs, Controlled Auto boundaries, locally allowlisted tasks, contract
  consistency, and grantable high-risk approvals.
- Full Python suite: `189 tests OK`.
- Runtime, public GitHub, legacy upload, and sanitized mirror Skill packages all
  pass `quick_validate.py`.

## 2026-07-12: Codex Chat Connector Attachment And Read Compatibility

### What Changed

- Added the Codex built-in ChatGPT dialog and other tool-capable ChatGPT
  attachment flow: discover the exact user-created connector display name,
  type `@`, select it from the UI, and verify that its tools are mounted before
  sending workspace instructions.
- Documented the default connector display name as
  `Agent Decision Bridge Connected Agent`.
- Clarified that a plain-text connector name does not attach tools and that
  account-specific `plugin://...` identifiers must be generated by the UI, not
  guessed or hard-coded.
- Updated the Connected Agent prompt generator and regression tests to include
  the exact-name `@` attachment gate.
- Added a mandatory complete-tool-contract gate before project inspection.
  Missing tools now trigger session reopen, fresh-chat reattachment, and then
  `connector_contract_incomplete` instead of silent degraded execution.
- Added `structuredContent.content` to whole-file `read` results so ChatGPT
  connector surfaces that prioritize structured output can see file contents.

### Validation

- Runtime and sanitized mirror skill folders pass `quick_validate.py`.
- Targeted prompt/server suite: `30 tests OK`.
- Full Python suite: `179 tests OK`.

## 2026-07-12: Phase 1 Contract Consistency

This update aligns the runtime skill, Ask First helper, current product docs,
and regression coverage without starting the larger Phase 2 runbook split.

### What Changed

- Standardized recommendation review on
  `Adopt / Adapt / Reject / Need info`.
- Added explicit first-tier aliases and clarified that package readiness is not
  proof that GPT Pro or another advisor was consulted.
- Changed `prepare_consultation.py` to default to Ask First, limited its CLI to
  package-producing modes, added automatic Chinese/English templates, and made
  the manual handoff require the complete package instead of a local task id.
- Replaced stale runtime helper names with the canonical Connected Agent
  helpers and scoped the public MCP guardrail explicitly to Decision Inbox.
- Added eight routing golden cases plus product-contract consistency tests.
- Refreshed the skill UI metadata to describe both Ask First and Connected
  Agent.
- Made workspace opening deterministic across current and stale connector
  schemas: call `open_default_workspace` when visible; otherwise call
  `open_workspace("default")` exactly once. The compatibility path no longer
  permits asking for an absolute path or incorrectly proposing a server change.
- Added prompt-level regression coverage for the deterministic fallback,
  authorized-root verification, and no-absolute-path boundary.

### Validation

- Runtime skill folder passes `quick_validate.py`.
- Full Python suite: `178 tests OK`.
- Phase 2 progressive-disclosure work remains intentionally deferred.

## 2026-07-09: Connected Agent Documentation Refresh

This update makes the current Agent Decision Bridge product language consistent
across the repository.

### What Changed

- Consolidated the public product description around two modes:
  **Ask First** and **Connected Agent**.
- Added `docs/user-guide.md` as the main user-facing guide.
- Renamed the non-technical Connected Agent flow to
  `docs/connected-agent-user-flow.md`.
- Removed superseded multi-tier drafts and older live-verification notes from
  the public repository.
- Removed platform-upload packaging and promotional card assets from repository
  tracking so the GitHub repository stays focused on Agent Decision Bridge.
- Removed stale model/version wording from current docs and user-visible
  helper output.
- Added the `scripts/connected_agent_flow.py` product wrapper as the preferred
  consultation entry point.
- Updated Connected Agent tooling docs and tests for:
  `open_default_workspace`, bounded `read_lines`, and normal source-file reads
  up to 1 MB.

### Current User-Facing Model

- **Ask First**: Codex prepares a focused package for manual advisor review. No
  public connector exposure. Risk `1/5`.
- **Connected Agent**: ChatGPT Web connects to an allowed project window through
  Apps/MCP connector tools. Read/search/list are automatic; write/edit/bash use
  one-action approval by default. Risk `3/5-5/5`.

Older compatibility names remain only where they are needed to explain legacy
CLI modes, test coverage, or migration behavior. They are not current product
documentation.

### Validation

- Current public docs scan clean for superseded model/version wording.
- Checked Markdown links in the current entry documents.
- Ran the full Python test suite:
  `python3 -m unittest discover -s tests`
  result: `170 tests OK`.
