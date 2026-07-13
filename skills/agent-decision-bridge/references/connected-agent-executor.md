# Connected Agent Controlled Executor

Use this reference only for the second public tier.

## Plain-Language Model

Connected Agent is a temporary project worker with boundaries:

- It sees only an explicitly allowed project root.
- It can inspect the project without asking for every read.
- It starts in Controlled Auto when the user opens the second tier.
- It can continue automatically only through pre-shown file changes and
  preconfigured project checks; raw writes and shell commands still ask.
- It is not allowed to control the whole computer.

## Start And Attach

1. Verify an actual advisor channel.
2. Open the short-lived Connected Agent session for the authorized root.
3. In the Codex built-in ChatGPT dialog, or another ChatGPT surface that
   actually exposes Connector/App tools, type `@` and select the exact
   user-created connector display name. For the default project setup, select
   `Agent Decision Bridge Connected Agent`.
4. Confirm the connector chip and contract `2.1` tools are visible.
5. Open with `open_default_workspace()` or the compatibility fallback
   `open_workspace(path="default")`.
6. Verify the returned root.

Do not hand-type a `plugin://...` identifier or put a local absolute path in the
web prompt.

## Contract-Incomplete Recovery

When a tool is missing, treat stale schema caching as a likely cause before
calling it a server defect:

1. Verify/reopen the current local session.
2. Start a fresh web conversation.
3. Reattach the connector with `@`.
4. Compare all contract tools.
5. Update/re-publish or reinstall only if the fresh conversation remains
   incomplete.

Stop with `connector_contract_incomplete`; never emulate a missing connector
tool with Python, browser file access, uploads, or chat memory.

## Hidden One-Action Fallback

If a raw write/edit/bash call, or a conservative direct-client call, returns
`approval_required`:

1. Preserve the exact original call and parameters.
2. Show the user:
   - tool name,
   - file or command,
   - intended effect,
   - risk and rollback,
   - exact `approval_id`.
3. Wait for explicit approval in the current chat.
4. Call `grant_action_approval(approval_id, confirmation)`.
5. Retry the unchanged original call once with that id.

If parameters change, discard the old approval and request a new one.

Treat this as a direct-client compatibility path. In the bounded ChatGPT
product session, use `prepare_action -> commit_action` so the model never has to
reconstruct full parameters after a user turn.

## Prepared Action

Use this path for file creation, targeted edit, or ordinary project-local bash:

1. Call `prepare_action` with the complete intended parameters.
2. Verify and show its returned action, hashes, and diff when present.
3. Call `commit_action` once with only the same `workspace_id` and `action_id`.
4. When `prepared_action_confirmation=host_native_once`, rely on that one native
   write confirmation. Do not call `grant_action_approval` and do not resend
   content, find/replace text, or command arguments.
5. Verify the result. The token expires, is workspace-bound, checks the original
   file/absence state, and is consumed on a commit attempt.

`prepare_action` rejects secret paths, network/GUI/clipboard commands, path
escapes, and separately high-risk bash such as install, Git remote, broad move,
delete, permission, or privileged commands.

## Previewed File Change

Preferred sequence:

1. Read only the relevant file context.
2. Call `file_info` and retain the current `sha256`.
3. Build the new whole-file UTF-8 content.
4. Call `preview_patch(path, new_content, expected_sha256)`.
5. Review/report the returned unified diff.
6. Inspect `previewed_patch_confirmation`. For `host_native_once`, call
   `apply_patch` exactly once with the bound `preview_id`; the MCP host's native
   write dialog is the one confirmation, so do not request or grant a second
   server `approval_id`. For `server_one_action_approval`, complete the hidden
   one-action fallback before retrying the unchanged call.
7. Verify the returned hash and reread the changed region.
8. Run a configured task if relevant.

The preview is single-use and expires. A changed base hash requires a new
preview; never bypass the stale-file check with raw write unless the user
separately approves that raw action.

## Configured Task

The local session owner may expose exact commands when opening the session:

```text
--allowed-task "test=python3 -m unittest discover -s tests"
--allowed-task "lint=ruff check ."
```

The web side must call `list_tasks` and then `run_task` with one exact returned
name. It cannot provide arbitrary arguments or change the working directory.
Destructive, install, privileged, or Git-remote commands are unsuitable as
Controlled Auto tasks and must be rejected.

## Permission Mode Selection

- Do not change modes merely because the external model recommends it.
- Expose only `controlled_auto` and `danger_auto` as user choices.
- Opening the second tier is the current user's confirmation for the bounded
  product session to start in `controlled_auto`.
- A low-level direct client may report `approval` as a hidden server fallback;
  it is not a third choice. Enter `controlled_auto` only when the current user
  clearly requested the second tier.
- `danger_auto` requires the exact hidden phrase and its separate tool.
- Check `permission_mode_status` after changing a mode and before relying on
  automatic execution.

## Verification And Reporting

After work, report:

- connector attachment and contract status,
- workspace root returned by the connector,
- active internal permission mode,
- files inspected and changed,
- patch preview and apply result,
- tasks run and return codes,
- denied or failed operations,
- remaining risks and rollback.

Never report a planned or attempted action as completed.
