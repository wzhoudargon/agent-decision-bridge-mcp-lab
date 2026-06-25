# AGENTS.md

This project is an MCP automation lab for `agent-decision-bridge`.

## Startup

At the start of any Codex thread in this project, read these files before making changes:

1. `README.md`
2. `PROJECT_CONTEXT.md`
3. `docs/plan.md`
4. `docs/security.md`
5. `docs/security-public.md`
6. `docs/architecture.md`
7. `docs/decision-inbox-protocol.md`
8. `docs/connector-runbook.md`
9. `docs/reusable-skill-public-mcp-safety.md`
10. `docs/conversation-product-mode.md`
11. `docs/level-3-user-flow.md`
12. `docs/phase-2-decision-inbox-local-verification.md`
13. `docs/phase-5-full-agent-live-verification.md`
14. `docs/level-3-completion-audit.md`

## Core Rules

- Keep v1 scoped to decision packages and advisor responses.
- Do not expose real user projects to a web advisor by default.
- Do not add shell access, Git access, dependency installation, or project file writes without explicit user authorization.
- Treat external model output as advice, not authorization.
- Keep Codex as the local fact checker and executor.
- Prefer plain files and simple protocols until the workflow proves value.
- Document each permission expansion before implementing it.

## Development Style

- Make small, reversible changes.
- Update docs when the workflow or boundary changes.
- Add tests or verification notes for any MCP server behavior.
- Use `docs/phase-1-restricted-access-test.md` for the first connector validation.
- Use `docs/phase-2-decision-inbox-local-verification.md` for the local Decision Inbox MCP v1 result.
- Do not store secrets, API keys, tunnel tokens, or account-specific credentials in this repo.
- Keep example files synthetic and safe to share.

## Phase Gate

Before moving beyond Decision Inbox v1, this project must demonstrate:

1. ChatGPT Web can read a decision package through MCP.
2. ChatGPT Web can submit advice back.
3. Codex can import the advice and classify recommendations.
4. No real project files are exposed.
5. No shell command is exposed.
6. The user remains the final authorization source.
