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

There are two current product modes that must not be confused:

1. Ask First:
   - Codex writes package/advice files.
   - The user copy-pastes manually.
   - Any side-effectful decision remains explicitly user-approved.
   - This is safest and risk `1/5`.

2. Connected Agent:
   - ChatGPT Web can read and search configured project roots directly.
   - It does not require Codex to generate a decision package.
   - It hard-blocks high-risk credential paths such as `.env*`, `.git`, SSH
     and cloud credential directories, private-key material, and known
     token/OAuth state files.
   - Other task-relevant project files can be selected by the web advisor.
   - It can request writes, edits, and bash under allowed roots.
   - Default mode uses one-action approval for write, edit, and bash:
     return `approval_id`, confirm that exact action in chat, call
     `grant_action_approval`, then retry once with the same `approval_id`.
   - The hidden danger switch starts only after the user types
     `dangerously trust connected agent`; it is session-only and fixed risk
     `5/5`.
   - The hidden danger switch still blocks network, browser/desktop, clipboard, secret-path,
     path-escape, dependency install, Git remote, and broad destructive command
     classes.
   - Codex remains the local verifier and executor.
   - This is the default advisor mode when the user wants ChatGPT Web to inspect project context.
   - Connector runs should use GPT-5.5 Thinking, not GPT-5.5 Pro, because Pro
     models do not expose ChatGPT Apps/MCP tools.

Legacy `read-only-project` and `full-agent` modes remain as deprecated aliases
for old ChatGPT connectors/tests. New project-aware review should use
`connected-agent` scope. The old package-only Auto MCP connector remains as
legacy compatibility, not the product Level 2.

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
6. Connected Agent is implemented as the product second tier with approval
   gates and a session-only hidden danger switch.
7. Legacy Read-Only Project Advisor and Full-Agent remain only as compatibility
   aliases.

## Current Scaffold

- `docs/decision-inbox-protocol.md` defines the package/advice/fact-check file protocol.
- `docs/connector-runbook.md` defines repeatable connector hygiene borrowed from DevSpace without expanding v1 permissions.
- `docs/reusable-skill-public-mcp-safety.md` defines the safety rules for turning this lab into reusable behavior for other users.
- `docs/phase-1-restricted-access-test.md` defines the restricted MCP connector validation plan.
- `docs/phase-2-decision-inbox-local-verification.md` records the local Decision Inbox MCP v1 test result.
- `docs/conversation-product-mode.md` defines the conversation-first product behavior and the required distinction between inbound Connected Agent connector access and outbound advisor invocation.
- `docs/level-3-completion-audit.md` records the earlier workspace connector maturity audit:
  short-window `user-web` is usable, but fully autonomous browser/product
  maturity is not yet verified.
- `decision-inbox/tasks/_template/` is the reusable task skeleton.
- `decision-inbox/tasks/phase-1-package-only-mcp-review/` is the first package-only advisor review task.
- `test-workspace/synthetic-project/` contains only synthetic files for the first access test.
- `server/decision_inbox_server.py` exposes package/advice/status Auto MCP tools over stdio.
- `server/full_agent_server.py` exposes Connected Agent workspace tools,
  approval gates, the hidden danger switch, and legacy Full-Agent/read-only profiles.
- `server/decision_inbox_http_server.py` exposes legacy Auto MCP by default,
  Connected Agent with `--mode connected-agent`, and deprecated workspace
  aliases with `--mode read-only-project` / `--mode full-agent`; it also handles bearer-token auth, OAuth Owner
  password approval, Origin checks, Host allowlisting, and mode-aware OAuth
  persistence.
- `scripts/decision_inbox_doctor.py` checks connector readiness, public URL shape, bearer-token/Owner-password presence, OAuth state files, mode, and risk coefficient without printing token values.
- `scripts/decision_inbox_preflight.py` runs read-only local/public endpoint checks before ChatGPT Web is asked to call MCP tools.
- `scripts/decision_inbox_tunnel_window.py` opens, checks, reports, and closes a bounded Tailscale Funnel window.
- `scripts/prepare_consultation.py` creates an Ask First / legacy package-only
  Auto MCP task from a natural-language user request. It must not be used for
  Connected Agent.
- `scripts/import_advice_review.py` renders a review-only Codex import gate for submitted advice.
- `scripts/level3_consultation_flow.py capture` captures returned Connected Agent
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

- Should legacy Auto MCP remain package-only as a compatibility boundary?
- How much default approval friction should Connected Agent keep before users
  opt into the hidden danger switch?
- What is the minimum useful status UI for the user?
- Should the next ChatGPT Web connector run verify Auto MCP only, or also run
  a separate explicitly approved Full-Agent connector test?

## Default Answers Until Overridden

- Use plain files first.
- Use Markdown for human review and JSON only for task metadata.
- Use Connected Agent for project-aware review; default write/edit/bash use
  one-action approval.
- Treat the hidden danger switch and legacy Full-Agent as explicit `5/5` risk whenever used.
- Do not claim Codex has consulted GPT Pro unless a real advisor channel returned advice.
- For ChatGPT Web connector calls, use GPT-5.5 Thinking rather than GPT-5.5 Pro.
- Treat the current Connected Agent state as connector-tools verified and ChatGPT Web
  verified for bounded short-window consultations. Earlier rounds used a fixed
  safe file set; the current prompt should let the advisor choose
  task-relevant files under the allowed root while the server hard-blocks
  high-risk credential paths.
- Prefer narrow, reversible changes.
- Prefer one external advisor round, with one extra targeted round only when needed.
