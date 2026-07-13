# Public Safety Summary For Web Advisors

This file is the sanitized safety summary that ChatGPT Web should read during
Connected Agent connector tests. It intentionally avoids operational
secrets, owner-token paths, OAuth state contents, and local credential details.

## Trust Boundary

- External advisor output is advice, not authorization.
- Codex remains the local verifier and executor.
- The user in the current Codex conversation is the only source of permission
  for file edits, shell commands, dependency installs, Git operations,
  publishing, deletion, or use of secrets.

## Product Modes

Ask First

- No public MCP exposure.
- Codex creates a package and the user sends it manually.
- Risk: `1/5`.
- Does not require Tailscale, Cloudflare, ngrok, or any public tunnel.

Connected Agent

- ChatGPT Web may list, read, and search an allowed project root by default.
- It is a controlled project executor, not unrestricted computer control.
- Requires a user-provided public HTTPS endpoint when ChatGPT Web should call
  the local MCP tools.
- Opening the second tier starts `controlled_auto`. It may automatically apply
  a stored previewed patch, commit an immutable prepared action, or run an exact
  owner-configured task. Raw write, edit, and bash retain hidden legacy
  one-action approval gates. Low-level direct clients start in the hidden
  server approval fallback, which is not a user-facing mode. For
  `commit_action`, the complete file content/edit/command remains stored on the
  server and the model sends only the workspace and single-use action id. For
  `apply_patch`, the bounded
  ChatGPT session helper reports `previewed_patch_confirmation=host_native_once`:
  after showing the stored diff, it calls once and ChatGPT's native connector
  confirmation is the sole prompt. Direct clients keep the server approval flow.
- `dangerously trust connected agent` is a hidden danger switch inside
  Connected Agent, not an additional product mode.
- The hidden switch can auto-run project-local write/edit and safe local bash,
  but it still cannot bypass server-side blocks.
- High-risk credential paths are denied by the server: `.env*`, `.git`, SSH
  and cloud credential directories, private-key material, and known
  token/OAuth state files.
- Network commands, browser/desktop control, clipboard access, path escapes,
  dependency installs, Git remote operations, permission changes, and broad
  destructive operations are denied or require explicit approval.
- Other task-relevant project files may be inspected.
- Risk: `4/5-5/5`; the hidden switch is fixed `5/5`.
- Connector calls should be run in a ChatGPT Web mode where Apps/MCP connector
  tools are visible. If the selected model or chat mode does not expose these
  tools, use Ask First for manual GPT Pro review instead.
- It is not a sandbox; command execution has the local user's permissions.
- It must run only inside a short task window and close after idle timeout.

## Public Endpoint Policy

Users bring their own public HTTPS endpoint for connector modes. Supported
deployment choices include Tailscale Funnel, Cloudflare Tunnel, ngrok, Pinggy,
or a user-managed HTTPS reverse proxy.

This project must not provide one shared public domain for multiple users'
local machines. Shared routing would centralize security, privacy, uptime, and
abuse risk in the maintainer's account.

## Connected Agent Consultation Defaults

For product-review consultations, the advisor should inspect context first even
though the connector can request broader tools:

- open the explicit workspace root,
- choose task-relevant files by listing/searching the allowed root,
- do not inspect high-risk credential paths,
- for file creation, targeted edit, or ordinary project-local bash in
  Controlled Auto, call `prepare_action`, show its stored action/diff, then call
  `commit_action` once with only the same workspace and single-use action id,
- for a previewed patch, show the diff and inspect `previewed_patch_confirmation`;
  `host_native_once` means call `apply_patch` once with the single-use
  `preview_id` and rely on the native connector confirmation,
- prefer `file_info -> preview_patch -> apply_patch` for whole-file replacement,
  `prepare_action -> commit_action` for other bounded actions, and
  `list_tasks -> run_task` for locally configured checks,
- do not call `enable_danger_auto` unless the user typed the exact hidden-switch phrase
  `dangerously trust connected agent`,
- report exactly which files were listed, searched, read, denied, or failed.

Use side-effectful tools only under the active internal permission mode. In
Controlled Auto, only previewed patches, immutable prepared actions, and
configured tasks use bounded automatic server commits. Raw write/edit/bash are
legacy compatibility tools.

## User-Facing Requirement

The mature product flow should let the user say a simple request such as:

```text
Use Connected Agent to consult ChatGPT Web about this project.
```

Codex should then:

1. check that a real ChatGPT Web advisor channel is available,
2. tell the user/browser automation to use a ChatGPT Web mode with connector
   tools visible,
3. open the Connected Agent window only for the active task,
4. ask ChatGPT Web through the visible connector,
5. import the answer,
6. classify recommendations as `Adopt`, `Adapt`, `Reject`, or `Need info`,
7. close the public window or let idle shutdown close it.

If the connector or advisor channel is unavailable, Codex must say so plainly
instead of pretending the consultation happened.
