# Project Context

## Why This Exists

The original `agent-decision-bridge` skill solved a manual cross-model collaboration problem:

- Codex gathers local facts and creates a self-contained decision package.
- The user sends that package to ChatGPT Pro, Claude, Gemini, or another advisor model.
- The advisor returns recommendations.
- Codex imports the recommendations, verifies them against local facts, and blocks execution until the user explicitly authorizes it.

This worked, but the copy-paste loop is repetitive. The next experiment is to reduce that manual transfer without losing the safety boundary.

## Current Question

Can ChatGPT Web, especially a stronger Pro-style web model, participate in this workflow through MCP so that it can read a decision package and submit advice back without the user manually copying text both ways?

## Important Distinction

There are three different modes that must not be confused:

1. Ask First:
   - Codex writes package/advice files.
   - The user copy-pastes manually.
   - Any side-effectful decision remains explicitly user-approved.
   - This is safest and risk `1/5`.

2. Read-Only Project Advisor:
   - ChatGPT Web can read and search configured project roots directly.
   - It does not require Codex to generate a decision package.
   - It hard-blocks high-risk credential paths such as `.env*`, `.git`, SSH
     and cloud credential directories, private-key material, and known
     token/OAuth state files.
   - Other task-relevant project files can be selected by the web advisor.
   - It cannot edit real project files.
   - It cannot run shell commands.
   - Codex remains the local verifier and executor.
   - This is the default advisor mode when the user wants ChatGPT Web to inspect project context.
   - Connector runs should use GPT-5.5 Thinking, not GPT-5.5 Pro, because Pro
     models do not expose ChatGPT Apps/MCP tools.

3. Full-Agent, like DevSpace:
   - ChatGPT Web can read files.
   - It may edit files.
   - It may run shell commands.
   - It requires `--mode full-agent` and `--allowed-root`.
   - This is powerful but risk `5/5`.

Read-Only Project Advisor is the normal advisor mode for project-aware review.
Full-Agent is explicit. They must be separate ChatGPT connectors:
`read-only-project` scope for Read-Only Project Advisor, `full-agent` scope for
Full-Agent. The old package-only Auto MCP connector remains as legacy
compatibility, not the product Level 2.

## Current Skill Baseline

The runtime skill is:

`~/.codex/skills/agent-decision-bridge/SKILL.md`

A pre-automation rollback snapshot exists at:

`~/.codex/skill-backups/agent-decision-bridge/2026-06-18-pre-automation/`

That snapshot should be treated as the rollback point if later automation changes make the skill too complicated or unsafe.

## Key Product Principle

External advisor models can suggest, but they do not authorize.

Only the user, in the current Codex conversation, can authorize:

- file edits,
- shell commands,
- deletion or moving,
- dependency installation,
- Git operations,
- publishing,
- sending messages,
- use of secrets,
- execution of an external model's plan.

## Current Decision

Do not directly expand the runtime skill into a large automation system.

Instead, keep this as a separate lab project:

- experiment safely,
- document architecture,
- build a narrow MCP prototype,
- test against fake workspace data,
- only then decide whether to promote stable behavior back into the skill.

## Current Phases

1. Create durable project context. Complete.
2. Validate local restricted MCP access on a synthetic test workspace. Local complete; external connector deferred because the narrower Phase 2 Decision Inbox connector test succeeded first.
3. Build Decision Inbox MCP v1. Local and ChatGPT Web external connector verification complete.
4. Run an end-to-end decision package loop. Complete with a synthetic package-only advisor round.
5. Keep Manual Package as the safest first tier.
6. Full DevSpace-style write/shell access is implemented as explicit
   Full-Agent mode, not as the default.
7. Add Read-Only Project Advisor as the product second tier.

## Current Scaffold

- `docs/decision-inbox-protocol.md` defines the package/advice/fact-check file protocol.
- `docs/connector-runbook.md` defines repeatable connector hygiene borrowed from DevSpace without expanding v1 permissions.
- `docs/reusable-skill-public-mcp-safety.md` defines the safety rules for turning this lab into reusable behavior for other users.
- `docs/phase-1-restricted-access-test.md` defines the restricted MCP connector validation plan.
- `docs/phase-2-decision-inbox-local-verification.md` records the local Decision Inbox MCP v1 test result.
- `docs/conversation-product-mode.md` defines the conversation-first product behavior and the required distinction between inbound Full-Agent connector access and outbound advisor invocation.
- `docs/level-3-completion-audit.md` records the current Level 3 maturity audit:
  short-window `user-web` is usable, but fully autonomous browser/product
  maturity is not yet verified.
- `decision-inbox/tasks/_template/` is the reusable task skeleton.
- `decision-inbox/tasks/phase-1-package-only-mcp-review/` is the first package-only advisor review task.
- `test-workspace/synthetic-project/` contains only synthetic files for the first access test.
- `server/decision_inbox_server.py` exposes package/advice/status Auto MCP tools over stdio.
- `server/full_agent_server.py` exposes explicit high-risk Full-Agent workspace and bash tools.
- `server/decision_inbox_http_server.py` exposes legacy Auto MCP by default,
  Read-Only Project Advisor with `--mode read-only-project`, and Full-Agent
  with `--mode full-agent`; it also handles bearer-token auth, OAuth Owner
  password approval, Origin checks, Host allowlisting, and mode-aware OAuth
  persistence.
- `scripts/decision_inbox_doctor.py` checks connector readiness, public URL shape, bearer-token/Owner-password presence, OAuth state files, mode, and risk coefficient without printing token values.
- `scripts/decision_inbox_preflight.py` runs read-only local/public endpoint checks before ChatGPT Web is asked to call MCP tools.
- `scripts/decision_inbox_tunnel_window.py` opens, checks, reports, and closes a bounded Tailscale Funnel window.
- `scripts/prepare_consultation.py` creates a Manual Package / legacy package-only Auto MCP task from a natural-language user request. It must not be used for Level 2 or Level 3.
- `scripts/import_advice_review.py` renders a review-only Codex import gate for submitted advice.
- `scripts/level3_consultation_flow.py capture` captures returned Level 3
  ChatGPT Web advice as external advice data, renders the review-only gate, and
  closes the session by default. It wraps the lower-level
  `scripts/level3_capture_advice.py` helper.
- `docs/phase-2-external-connector-verification.md` records the successful ChatGPT Web connector test.
- `docs/tailscale-funnel-verification.md` records the stable no-owned-domain Tailscale Funnel verification result.

## What A New Codex Thread Should Do First

When opening this project in a new Codex thread:

1. Read `README.md`.
2. Read this file.
3. Read `docs/plan.md`.
4. Read `docs/security.md`.
5. Read `docs/security-public.md`.
6. Read `docs/architecture.md`.
7. Read `docs/decision-inbox-protocol.md`.
8. Read `docs/connector-runbook.md`.
9. Read `docs/reusable-skill-public-mcp-safety.md`.
10. Read `docs/conversation-product-mode.md`.
11. Read `docs/level-3-user-flow.md`.
12. Read `docs/phase-2-decision-inbox-local-verification.md`.
13. Read `docs/phase-5-full-agent-live-verification.md`.
14. Read `docs/level-3-completion-audit.md`.
15. Check `decision-inbox/` for active packages or advisor responses.
16. Continue the smallest next phase rather than redesigning the whole project.

## Current Open Questions

- Should Auto MCP remain package-only as the default production boundary?
- Is a separate read-only project context phase worth designing after the package-only loop has proven useful?
- What is the minimum useful status UI for the user?
- Should the next ChatGPT Web connector run verify Auto MCP only, or also run
  a separate explicitly approved Full-Agent connector test?

## Default Answers Until Overridden

- Use plain files first.
- Use Markdown for human review and JSON only for task metadata.
- Avoid shell access and project writes in Read-Only Project Advisor.
- Treat Full-Agent as explicit `5/5` risk whenever used.
- Do not claim Codex has consulted GPT Pro unless a real advisor channel returned advice.
- For ChatGPT Web connector calls, use GPT-5.5 Thinking rather than GPT-5.5 Pro.
- Treat the current Level 3 state as connector-tools verified and ChatGPT Web
  verified for bounded short-window consultations. Earlier rounds used a fixed
  safe file set; the current prompt should let the advisor choose
  task-relevant files under the allowed root while the server hard-blocks
  high-risk credential paths.
- Prefer narrow, reversible changes.
- Prefer one external advisor round, with one extra targeted round only when needed.
