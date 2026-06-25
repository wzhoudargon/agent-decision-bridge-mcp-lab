# Phase 1 Local Verification

Date: 2026-06-18

Scope: local-only validation of the synthetic read-only MCP server. This does not prove ChatGPT Web connector access yet.

## Implemented Local Server

```text
server/restricted_test_workspace_server.py
```

Transport shape:

- stdio
- newline-delimited JSON-RPC
- MCP methods implemented: `initialize`, `notifications/initialized`, `tools/list`, `tools/call`

Tools:

- `list_synthetic_files`
- `read_synthetic_file`

Allowed root:

```text
test-workspace/synthetic-project/
```

## Local Unit Test

Command:

```bash
python3 -m unittest tests/test_restricted_test_workspace_server.py
```

Expected result:

```text
Ran 12 tests
OK
```

Observed local result on 2026-06-18:

```text
Ran 12 tests in 0.001s
OK
```

Covered behavior:

- list only synthetic files,
- read allowed synthetic files,
- reject parent-directory traversal,
- reject absolute paths,
- reject hidden path segments,
- reject unknown tools,
- return tool errors as data instead of executing anything,
- declare only the MCP `tools` capability.

## Stdio Smoke Test

Run the server and send JSON-RPC lines for:

1. `initialize`
2. `tools/list`
3. `tools/call` with `list_synthetic_files`
4. `tools/call` with `read_synthetic_file`
5. `tools/call` with denied path `../README.md`

Expected result:

- allowed calls return text content and structured content,
- denied path returns `isError: true`,
- no file outside the synthetic root is read.

Observed local result on 2026-06-18:

- `initialize` returned protocol version `2025-11-25` and only the `tools` capability.
- `tools/list` returned `list_synthetic_files` and `read_synthetic_file`.
- `list_synthetic_files` returned the three synthetic files.
- `read_synthetic_file` returned `sample-project-notes.md`.
- `read_synthetic_file` with `../README.md` returned `isError: true`.

## External Connector Status

Pending.

The next step is to connect this local server through the user's chosen MCP connector path and run the positive and negative checks in `docs/phase-1-restricted-access-test.md`.
