# Test Workspace

This folder is for safe MCP access tests.

Use only synthetic files here. Do not put real project files, secrets, customer data, private documents, or credentials in this folder.

## Purpose

Phase 1 uses this folder to test whether ChatGPT Web can connect to a local MCP server and read allowlisted local files.

## Success Criteria

- ChatGPT Web can read an allowed synthetic file.
- ChatGPT Web cannot access files outside the configured allowlist.
- The test documents what connector, tunnel, and permissions were used.

## Suggested Synthetic Files

Small fake files are available under `synthetic-project/`:

- `sample-project-notes.md`
- `sample-file-tree.txt`
- `sample-open-question.md`

These files should be safe to paste publicly.
