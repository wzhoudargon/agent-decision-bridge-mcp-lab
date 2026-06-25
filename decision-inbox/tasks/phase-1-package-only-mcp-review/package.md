# Package-only Decision Inbox MCP v1 Review Package

## Instructions For The External Advisor

You are an external advisor. Use only the facts in this package. Do not assume access to local files, tools, logs, Git state, shell commands, browser data, or previous chat history.

## Goal

- Decide whether this lab should implement package-only Decision Inbox MCP v1 before adding any read-only project access.

## Verified Facts

- The lab is for automating the existing Agent Decision Bridge workflow.
- Codex is the local fact checker and executor.
- Web advisors can provide recommendations, alternatives, and risk review.
- Advisor output is not user authorization.
- v1 is intentionally scoped to decision packages and advisor responses.
- The current scaffold uses plain files under `decision-inbox/tasks/`.
- The current safe test workspace contains only synthetic files.

## Assumptions

- A web advisor can access a local MCP server only after the user sets up the connector or tunnel.
- The first useful automation value is reducing copy-paste, not giving a web model broad workspace access.
- Plain files are easier to inspect and rollback than a database during this lab phase.

## Constraints And Privacy Boundary

- Do not expose real user projects to the web advisor by default.
- Do not add shell access in v1.
- Do not add Git operations in v1.
- Do not add dependency installation in v1.
- Do not add project file writes in v1.
- Do not store secrets, API keys, tunnel tokens, credentials, private emails, browser data, or full proprietary documents in the inbox.
- Codex must import and classify material advice as `Adopt`, `Adapt`, `Reject`, or `Need info` before any execution.
- Only the current user can authorize file edits, commands, publishing, sending, or permission expansion.

## Settled Decisions

- Keep the automation lab separate from the runtime `agent-decision-bridge` skill.
- Use package-only exchange as the default v1 direction.
- Use synthetic test data before any real workflow.
- Prefer Markdown packages and small JSON metadata.
- Document each permission expansion before implementing it.

## Open Questions Only

1. Should package-only Decision Inbox MCP v1 be built before any read-only project access?
2. What is the minimum server tool set needed for that package-only v1?
3. What negative tests are required before connecting a web advisor?

## Do Not Re-Litigate

- Do not propose full DevSpace-style read/write/shell access as the first version unless you identify a critical flaw in the package-only plan.
- Do not treat the web advisor as an executor or authorization source.
- Do not require a database unless plain files create a concrete blocker.

## Please Output

1. Recommended approach
2. Why this approach
3. What not to do
4. Missing information, if any
5. Concrete steps for Codex or the local executor
6. Verification or acceptance criteria
7. Main risks
