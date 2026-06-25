# Advice: Package-only Decision Inbox MCP v1

## 1. Recommended approach

Keep package-only Decision Inbox MCP v1 as the first external workflow before any read-only project context expansion.

The v1 should support a narrow, auditable loop: list decision tasks, read a prepared decision package, submit advisor Markdown, and optionally expose task status or advice counts. It should not expose project files, shell access, Git state, dependency installation, browser data, secrets, or write access outside the decision inbox.

## 2. Why this approach

Package-only exchange directly solves the first automation value: reducing copy-paste in the existing Agent Decision Bridge workflow. It preserves the current trust model where Codex remains the local fact checker and executor, while web advisors provide recommendations, alternatives, and risk review only.

This scope also keeps privacy and authorization boundaries crisp. Advisor output is not execution authority, and Codex must still classify material advice as `Adopt`, `Adapt`, `Reject`, or `Need info` before anything happens locally. Plain Markdown packages plus small JSON metadata are sufficient for the lab phase and easier to inspect, diff, rollback, and test than a database.

## 3. What not to do

Do not add read-only project access in v1. Even read-only access changes the threat model because real project files can contain proprietary material, secrets, private context, stale assumptions, or information the user did not intend to send to a web advisor.

Do not add shell access, Git operations, dependency installation, project file writes, browser data, private email access, tunnel tokens, API keys, credentials, or full proprietary documents to the inbox.

Do not treat advisor advice as user authorization. The web advisor should never become an executor, approver, or permission-expansion source.

Do not require a database unless plain files create a concrete blocker. The package states no such blocker.

## 4. Missing information

No blocking missing information for v1. The current package contains enough to recommend proceeding with package-only MCP first.

Useful non-blocking details before implementation would be: the exact naming convention for task folders, the expected metadata schema, whether submitted advice needs deterministic filenames, and how Codex will import/classify advice after submission.

## 5. Concrete steps for Codex or the local executor

1. Implement the minimum MCP server tool set for package-only v1: list decision tasks, get decision package, submit advisor advice, and get task status.
2. Keep storage as plain files under the decision inbox task folders, with package Markdown, small metadata JSON, and an advice folder.
3. Validate task IDs against known package-only task directories to prevent path traversal or accidental access outside the inbox.
4. Sanitize or reject advisor names and generated filenames that could create unsafe paths.
5. Add explicit documentation that v1 has no local project access and no execution authority.
6. Build the first synthetic test flow end to end: create package, expose package to advisor, receive advice, import advice locally, classify advice, and require user authorization before execution.
7. Document any future permission expansion as a separate decision package before implementation.

## 6. Verification or acceptance criteria

- A web advisor can list only safe task metadata, not local project files.
- A web advisor can read only prepared package Markdown for a selected task.
- A web advisor can submit Markdown advice only into that task advice folder.
- The server cannot read or write outside the decision inbox task scope.
- Synthetic tests pass before any real workflow is connected.
- Submitted advice is visible to Codex for local import and classification.
- No shell, Git, dependency installation, browser data, secrets, credentials, private emails, or project file writes are exposed.
- Any later read-only expansion requires a new documented decision and explicit user authorization.

## 7. Main risks

The main risk is scope creep: read-only project context may sound harmless but would prematurely widen the privacy boundary. Another risk is advisory confusion, where web model output is mistaken for permission to act. A smaller implementation risk is unsafe file handling around task IDs, advisor names, and advice filenames. These risks are manageable if v1 remains package-only, synthetic-first, and explicitly non-executing.

## Final recommendation

Yes: package-only Decision Inbox MCP v1 should remain the first external workflow. It is the right first step because it automates the useful part of external review while preserving local control, privacy boundaries, and user authorization.