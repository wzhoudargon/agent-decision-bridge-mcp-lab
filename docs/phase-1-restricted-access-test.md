# Phase 1 Restricted Access Test

This plan validates that a web advisor can use MCP to read only synthetic local test files before this lab builds the Decision Inbox MCP server.

## Goal

Prove the connector path and allowlist behavior with harmless files under:

```text
test-workspace/synthetic-project/
```

Do not use real project files for this phase.

## Allowed Test Files

- `sample-project-notes.md`
- `sample-file-tree.txt`
- `sample-open-question.md`

## Required Setup Notes

Before running the test, record:

- connector path used,
- whether a tunnel is used,
- authentication method,
- allowed local root,
- server process command, if any,
- start and stop procedure,
- where logs are written.

Do not store tunnel tokens, API keys, account IDs, or credentials in this repo.

## Local Test Server

The local stdio test server is:

```text
server/restricted_test_workspace_server.py
```

It exposes only:

- `list_synthetic_files`
- `read_synthetic_file`

It does not expose write, shell, Git, dependency installation, secret inspection, or real project file access.

## Positive Checks

The web advisor should be able to:

1. List the three synthetic files.
2. Read `sample-project-notes.md`.
3. Read `sample-open-question.md`.
4. Summarize the fake decision without claiming access to other files.

## Negative Checks

The web advisor or MCP tool should be unable to:

1. Read files outside `test-workspace/synthetic-project/`.
2. Read `../README.md`.
3. Read `.env` or any hidden file.
4. Run shell commands.
5. Write files.
6. Access Git state.
7. Install dependencies.

## Evidence To Capture

Record a short verification note with:

- date,
- connector used,
- positive checks result,
- negative checks result,
- observed failures,
- whether the setup is safe enough to inform Phase 2.

The note should not contain secrets, account-specific credentials, tunnel tokens, cookies, or private project content.

Local-only verification is recorded in `docs/phase-1-local-verification.md`. External connector verification should be added separately after the user configures the connector path.

## Exit Decision

Move to Phase 2 only if:

- all positive checks pass,
- all negative checks are blocked,
- the user understands any tunnel exposure risk,
- the next server design remains package-only by default.
