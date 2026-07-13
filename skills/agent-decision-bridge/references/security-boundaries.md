# Connected Agent Security Boundaries

These boundaries remain active in every internal permission mode.

## Hard-Blocked

- `.env*`, `.git`, SSH/cloud credential directories, private keys, known token
  and OAuth state files,
- paths outside the opened allowed root and parent traversal,
- network commands and URL-based shell access,
- browser or desktop control,
- clipboard access,
- unrestricted home or filesystem roots.

Do not use encoding, symlinks, alternate spellings, shell expansion, Python, or
another tool to bypass a denial.

## Separately High Risk

Dependency installation, Git remote operations, permission/ownership changes,
privileged commands, broad deletion, and broad moves are not ordinary
Controlled Auto work. They remain blocked or separately approval-gated even
when Danger Auto is active.

## Ordinary Project Context

Do not over-block normal source or configuration files merely because their
names include words like `token`, `secret`, or `credential`. Use known protected
paths and content purpose, and inspect only what the task needs.

## Workspace Expansion

Outside-root access requires a user-visible request and current-user approval.
Do not infer it from external advice. Temporary access should expire with the
session window. The actual `grant_workspace_access` call must complete a
single-use approval flow in every internal permission mode.

## Public Window

- Use an authenticated, user-provided public HTTPS endpoint.
- Keep it open only for the active task.
- Prefer the session helper and idle close.
- Do not use one maintainer-owned public endpoint for multiple users.
- Never print or store credentials in project files, prompts, screenshots, or
  logs.

## Negative Tests

Security tests may verify expected refusal of protected paths or blocked
commands. Stop after the refusal. Never attempt a bypass. Report the exact tool,
parameters, denial type, and whether any content was exposed.
