# Decision Inbox

This folder stores decision tasks exchanged between Codex and a web advisor through MCP.

It is intentionally separate from real project files.

## Intended v1 Task Structure

```text
tasks/
└── <task-id>/
    ├── metadata.json
    ├── package.md
    ├── advice/
    │   └── <timestamp>-<advisor>.md
    └── fact-check-requests/
        └── <timestamp>.md
```

Current scaffold:

```text
tasks/
├── README.md
├── _template/
│   ├── metadata.json
│   ├── package.md
│   ├── advice/
│   └── fact-check-requests/
└── phase-1-package-only-mcp-review/
    ├── metadata.json
    ├── package.md
    ├── advice/
    └── fact-check-requests/
```

## Rules

- Decision packages should be self-contained.
- Do not store secrets here.
- Do not store full private project dumps here.
- Advisor responses are not authorization.
- Codex must import and verify responses before any implementation.
- Use `docs/decision-inbox-protocol.md` as the source of truth for file names, statuses, and validation rules.

## First Test Task

The first real test task is:

```text
tasks/phase-1-package-only-mcp-review/
```

It asks the web advisor:

Should this lab implement package-only Decision Inbox MCP v1 before adding read-only project access?

Expected outcome:

- advisor gives recommendation,
- Codex classifies it,
- no files outside this lab are touched.
