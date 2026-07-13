#!/usr/bin/env python3
"""Connected Agent MCP backend with explicit workspace roots and approval gates."""

import argparse
import difflib
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "agent-decision-bridge-connected-agent"
SERVER_VERSION = "0.4.2"
TOOL_CONTRACT_VERSION = "2.1"
MAX_COMMAND_SECONDS = 30
MAX_COMMAND_OUTPUT_BYTES = 200_000
MAX_READ_FILE_BYTES = 1_000_000
MAX_READ_LINES = 500
PROFILE_FULL_AGENT = "full-agent"
PROFILE_READ_ONLY_PROJECT = "read-only-project"
PROFILE_CONNECTED_AGENT = "connected-agent"
VALID_PROFILES = {PROFILE_FULL_AGENT, PROFILE_READ_ONLY_PROJECT, PROFILE_CONNECTED_AGENT}
DANGER_AUTO_PHRASE = "dangerously trust connected agent"
DANGER_AUTO_IDLE_SECONDS = 1200
ACTION_APPROVAL_IDLE_SECONDS = 1200
PATCH_PREVIEW_IDLE_SECONDS = 1200
PREPARED_ACTION_IDLE_SECONDS = 1200
PERMISSION_APPROVAL = "approval"
PERMISSION_CONTROLLED_AUTO = "controlled_auto"
PERMISSION_DANGER_AUTO = "danger_auto"
VALID_PERMISSION_MODES = {
    PERMISSION_APPROVAL,
    PERMISSION_CONTROLLED_AUTO,
    PERMISSION_DANGER_AUTO,
}
CONTROLLED_AUTO_TOOLS = {"apply_patch", "commit_action", "run_task"}
APPROVAL_CONFIRMATION_MARKERS = (
    "确认",
    "同意",
    "可以",
    "批准",
    "允许",
    "执行",
    "继续",
    "是的",
    "好的",
    "没问题",
    "行",
    "可",
    "准",
    "yes",
    "y",
    "ok",
    "okay",
    "approve",
    "approved",
    "confirm",
    "confirmed",
    "proceed",
    "go ahead",
)
APPROVAL_REJECTION_MARKERS = (
    "不要",
    "不行",
    "不可以",
    "不可",
    "不同意",
    "否",
    "拒绝",
    "取消",
    "停止",
    "no",
    "not",
    "deny",
    "denied",
    "cancel",
    "stop",
)
SENSITIVE_PATH_SEGMENTS = {
    ".env",
    ".git",
    ".gnupg",
    ".ssh",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    ".docker",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SENSITIVE_FILENAMES = {
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
    "token.json",
    "oauth-state.json",
    "oauth-owner-token",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "authorized_keys",
    "known_hosts",
}
SENSITIVE_COMMAND_MARKERS = (
    ".env",
    ".git",
    ".ssh",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    ".docker",
    "id_rsa",
    "id_ed25519",
    "oauth-state.json",
    "oauth-owner-token",
    "credentials.json",
    "token.json",
)
NETWORK_OR_REMOTE_COMMANDS = {
    "curl",
    "wget",
    "http",
    "https",
    "ssh",
    "scp",
    "rsync",
    "nc",
    "ncat",
    "telnet",
    "ftp",
    "sftp",
    "dig",
    "nslookup",
    "ping",
    "traceroute",
    "tailscale",
    "cloudflared",
    "ngrok",
}
GUI_OR_CLIPBOARD_COMMANDS = {
    "open",
    "osascript",
    "pbcopy",
    "pbpaste",
    "screencapture",
    "xclip",
    "xsel",
    "xdg-open",
}
GIT_REMOTE_COMMANDS = {"push", "pull", "fetch", "clone", "remote", "submodule"}
PACKAGE_INSTALL_COMMANDS = {"install", "add", "i"}
APPROVAL_COMMANDS = {
    "rm",
    "rmdir",
    "mv",
    "chmod",
    "chown",
    "chgrp",
    "sudo",
    "su",
    "launchctl",
}


class ApprovalRequired(Exception):
    """Raised when Connected Agent needs explicit user approval."""

    def __init__(self, message: str, structured: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.structured = structured or {}


class AccessDenied(Exception):
    """Raised when a request escapes the configured workspace boundary."""


class WorkspaceNotFound(Exception):
    """Raised when a workspace id has not been opened."""


class FullAgentWorkspaceManager:
    def __init__(
        self,
        allowed_roots: List[Path],
        profile: str = PROFILE_FULL_AGENT,
        allowed_tasks: Optional[Dict[str, str]] = None,
        trust_host_confirmation_for_previewed_patches: bool = False,
        initial_permission_mode: str = PERMISSION_APPROVAL,
    ):
        if profile not in VALID_PROFILES:
            raise ValueError(f"Unknown workspace profile: {profile}")
        self.profile = profile
        self.allowed_roots = validate_allowed_roots(allowed_roots)
        self.allowed_tasks = validate_allowed_tasks(allowed_tasks or {})
        self.trust_host_confirmation_for_previewed_patches = bool(
            trust_host_confirmation_for_previewed_patches
        )
        normalized_initial_mode = initial_permission_mode.strip().lower()
        if normalized_initial_mode not in {
            PERMISSION_APPROVAL,
            PERMISSION_CONTROLLED_AUTO,
        }:
            raise ValueError(
                "initial_permission_mode must be approval or controlled_auto"
            )
        self.base_permission_mode = normalized_initial_mode
        self.session_allowed_roots: List[Path] = []
        self.workspaces: Dict[str, Path] = {}
        self.permission_mode = self.base_permission_mode
        self.session_last_activity = time.time()
        self.pending_action_approvals: Dict[str, Dict[str, Any]] = {}
        self.granted_action_approvals: Dict[str, Dict[str, Any]] = {}
        self.pending_patch_previews: Dict[str, Dict[str, Any]] = {}
        self.pending_prepared_actions: Dict[str, Dict[str, Any]] = {}

    @property
    def danger_auto_enabled(self) -> bool:
        """Backward-compatible view of the session permission mode."""
        return self.permission_mode == PERMISSION_DANGER_AUTO

    @danger_auto_enabled.setter
    def danger_auto_enabled(self, enabled: bool) -> None:
        self.permission_mode = (
            PERMISSION_DANGER_AUTO if enabled else self.base_permission_mode
        )

    @property
    def risk_level(self) -> str:
        if self.profile == PROFILE_FULL_AGENT:
            return "5/5"
        if self.profile == PROFILE_CONNECTED_AGENT:
            if self.permission_mode == PERMISSION_DANGER_AUTO:
                return "5/5"
            if self.permission_mode == PERMISSION_CONTROLLED_AUTO:
                return "4/5-5/5"
            return "3/5-5/5"
        return "3/5-4/5"

    @property
    def tool_names(self) -> List[str]:
        return [tool["name"] for tool in tool_definitions(self.profile)]

    @property
    def previewed_patch_confirmation(self) -> str:
        if self.trust_host_confirmation_for_previewed_patches:
            return "host_native_once"
        return "server_one_action_approval"

    @property
    def prepared_action_confirmation(self) -> str:
        if self.trust_host_confirmation_for_previewed_patches:
            return "host_native_once"
        return "server_one_action_approval"

    def open_default_workspace(self) -> Dict[str, Any]:
        self.touch()
        if len(self.allowed_roots) != 1:
            raise AccessDenied(
                "open_default_workspace requires exactly one configured allowed root; "
                "ask Codex or the user to disambiguate the authorized workspace "
                "instead of guessing or passing a local absolute path"
            )
        return self._open_resolved_workspace(self.allowed_roots[0])

    def open_workspace(self, path_value: str) -> Dict[str, Any]:
        self.touch()
        requested = self._resolve_requested_workspace(path_value)
        return self._open_resolved_workspace(requested)

    def _open_resolved_workspace(self, requested: Path) -> Dict[str, Any]:
        workspace_id = f"ws-{uuid.uuid4().hex}"
        self.workspaces[workspace_id] = requested
        if self.profile == PROFILE_READ_ONLY_PROJECT:
            warning = (
                "Read-Only Project Advisor mode exposes project listing, reading, "
                "glob, and grep only. It cannot write files or run shell commands. "
                "Protected credential-like paths are blocked by the server."
            )
        elif self.profile == PROFILE_CONNECTED_AGENT:
            warning = (
                "Connected Agent exposes two user-facing permission choices: "
                "Controlled Auto and Danger Auto. Controlled Auto may run only "
                "previewed patches, immutable prepared actions, and owner-configured "
                "tasks automatically. Use prepare_action then commit_action for one "
                "host-native confirmation; raw write/edit/bash remain compatibility tools. "
                "Protected credential-like paths and unsafe commands remain blocked."
                if self.base_permission_mode == PERMISSION_CONTROLLED_AUTO
                else "Connected Agent is running in the low-level server approval "
                "fallback. Direct clients must explicitly enter Controlled Auto; "
                "protected credential-like paths and unsafe commands remain blocked."
            )
        else:
            warning = (
                "Full-Agent mode exposes file read/write/edit/search and shell "
                "execution inside this workspace. Shell commands run with the "
                "local user account, not a security sandbox. Protected "
                "credential-like paths are blocked by default, but bash is still "
                "high risk."
            )
        return {
            "workspace_id": workspace_id,
            "root": str(requested),
            "profile": self.profile,
            "contract_version": TOOL_CONTRACT_VERSION,
            "permission_mode": self.permission_mode,
            "visible_permission_modes": [
                PERMISSION_CONTROLLED_AUTO,
                PERMISSION_DANGER_AUTO,
            ],
            "server_approval_fallback_active": self.permission_mode
            == PERMISSION_APPROVAL,
            "previewed_patch_confirmation": self.previewed_patch_confirmation,
            "prepared_action_confirmation": self.prepared_action_confirmation,
            "tools": self.tool_names,
            "risk_level": self.risk_level,
            "warning": warning,
        }

    def list_directory(self, workspace_id: str, path_value: str = ".") -> List[Dict[str, Any]]:
        self.touch()
        path_value = _normalize_optional_workspace_location(path_value, "path")
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not target.is_dir():
            raise AccessDenied("ls target must be a directory")
        entries: List[Dict[str, Any]] = []
        for path in sorted(target.iterdir(), key=lambda item: item.name):
            if self._is_protected_path(path):
                continue
            entries.append(
                {
                    "name": path.name,
                    "type": "directory" if path.is_dir() else "file",
                    "size": path.stat().st_size if path.is_file() else None,
                }
            )
        return entries

    def read_file(self, workspace_id: str, path_value: str) -> str:
        self.touch()
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not target.is_file():
            raise AccessDenied("read target must be a file")
        self._assert_read_allowed(target)
        if target.stat().st_size > MAX_READ_FILE_BYTES:
            raise AccessDenied("read target is too large for advisor exposure")
        return target.read_text(encoding="utf-8")

    def read_lines(
        self,
        workspace_id: str,
        path_value: str,
        start_line: int,
        end_line: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.touch()
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not target.is_file():
            raise AccessDenied("read_lines target must be a file")
        self._assert_read_allowed(target)
        if not isinstance(start_line, int) or start_line < 1:
            raise AccessDenied("start_line must be a positive integer")
        if end_line is not None and (not isinstance(end_line, int) or end_line < start_line):
            raise AccessDenied("end_line must be an integer greater than or equal to start_line")
        requested_end = end_line if end_line is not None else start_line + MAX_READ_LINES - 1
        capped_end = min(requested_end, start_line + MAX_READ_LINES - 1)
        lines: List[Dict[str, Any]] = []
        with target.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line_number < start_line:
                    continue
                if line_number > capped_end:
                    break
                lines.append({"line": line_number, "text": line.rstrip("\n")})
        actual_end = lines[-1]["line"] if lines else start_line - 1
        return {
            "path": self.relative_path(workspace_id, target),
            "start_line": start_line,
            "end_line": actual_end,
            "requested_end_line": requested_end,
            "max_lines": MAX_READ_LINES,
            "truncated": requested_end > capped_end,
            "lines": lines,
        }

    def file_info(self, workspace_id: str, path_value: str) -> Dict[str, Any]:
        """Return stable metadata that can be used for optimistic write checks."""
        self.touch()
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        self._assert_not_protected(target)
        relative = self.relative_path(workspace_id, target)
        stat = target.stat()
        result: Dict[str, Any] = {
            "path": relative,
            "type": "directory" if target.is_dir() else "file",
            "bytes": stat.st_size if target.is_file() else None,
            "modified_at_unix": stat.st_mtime,
            "sha256": None,
        }
        if target.is_file():
            if stat.st_size > MAX_READ_FILE_BYTES:
                raise AccessDenied("file_info target is too large for content hashing")
            try:
                content = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise AccessDenied("file_info target must be a UTF-8 text file") from exc
            result["sha256"] = _sha256_text(content)
        return result

    def preview_patch(
        self,
        workspace_id: str,
        path_value: str,
        new_content: str,
        expected_sha256: str,
    ) -> Dict[str, Any]:
        """Build a single-use whole-file patch preview without changing the file."""
        self.touch()
        self._require_connected_agent_tool("preview_patch")
        self._expire_patch_previews()
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not target.is_file():
            raise AccessDenied("preview_patch target must be an existing file")
        self._assert_not_protected(target)
        if target.stat().st_size > MAX_READ_FILE_BYTES:
            raise AccessDenied("preview_patch target is too large")
        if len(new_content.encode("utf-8")) > MAX_READ_FILE_BYTES:
            raise AccessDenied("preview_patch result is too large")
        original = target.read_text(encoding="utf-8")
        base_sha256 = _sha256_text(original)
        if expected_sha256.strip().lower() != base_sha256:
            raise AccessDenied(
                "expected_sha256 does not match the current file; read file_info and preview again"
            )
        if original == new_content:
            raise ValueError("preview_patch contains no changes")
        relative = self.relative_path(workspace_id, target)
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
        preview_id = f"patch-{uuid.uuid4().hex}"
        result_sha256 = _sha256_text(new_content)
        self.pending_patch_previews[preview_id] = {
            "preview_id": preview_id,
            "workspace_id": workspace_id,
            "path": relative,
            "base_sha256": base_sha256,
            "result_sha256": result_sha256,
            "new_content": new_content,
            "diff": diff,
            "created_at": time.time(),
        }
        return {
            "preview_id": preview_id,
            "path": relative,
            "base_sha256": base_sha256,
            "result_sha256": result_sha256,
            "diff": diff,
            "expires_after_idle_seconds": PATCH_PREVIEW_IDLE_SECONDS,
            "commit_token": preview_id,
            "commit_confirmation": self.previewed_patch_confirmation,
            "applied": False,
        }

    def apply_patch(
        self,
        workspace_id: str,
        preview_id: str,
        approval_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply exactly one previously previewed result after policy checks."""
        self.touch()
        self._require_connected_agent_tool("apply_patch")
        self._expire_patch_previews()
        preview = self.pending_patch_previews.get(preview_id)
        if not preview:
            raise AccessDenied("preview_id is unknown, expired, or already used")
        if preview["workspace_id"] != workspace_id:
            raise AccessDenied("preview_id does not belong to this workspace")
        target = self.resolve_workspace_path(workspace_id, preview["path"], must_exist=True)
        self._assert_not_protected(target)
        current = target.read_text(encoding="utf-8")
        if _sha256_text(current) != preview["base_sha256"]:
            raise AccessDenied("file changed after preview; create a new preview before applying")
        action = {
            "tool_name": "apply_patch",
            "workspace_id": workspace_id,
            "preview_id": preview_id,
            "path": preview["path"],
            "base_sha256": preview["base_sha256"],
            "result_sha256": preview["result_sha256"],
            "diff_sha256": _sha256_text(preview["diff"]),
            "diff": preview["diff"],
        }
        if not self.trust_host_confirmation_for_previewed_patches:
            self._require_connected_action_approval("apply_patch", action, approval_id)
        new_content = preview["new_content"]
        target.write_text(new_content, encoding="utf-8")
        del self.pending_patch_previews[preview_id]
        return {
            "preview_id": preview_id,
            "path": preview["path"],
            "bytes": len(new_content.encode("utf-8")),
            "sha256": preview["result_sha256"],
            "confirmation": self.previewed_patch_confirmation,
            "applied": True,
        }

    def prepare_action(
        self,
        workspace_id: str,
        action_type: str,
        *,
        path_value: Optional[str] = None,
        content: Optional[str] = None,
        find: Optional[str] = None,
        replace: Optional[str] = None,
        expected_replacements: Optional[int] = None,
        command: Optional[str] = None,
        cwd: str = ".",
        timeout_seconds: int = MAX_COMMAND_SECONDS,
    ) -> Dict[str, Any]:
        """Store an immutable write/edit/bash action without executing it."""
        self.touch()
        self._require_connected_agent_tool("prepare_action")
        self._expire_prepared_actions()
        if not isinstance(action_type, str):
            raise ValueError("action_type must be one of: write, edit, bash")
        normalized_type = action_type.strip().lower()
        if normalized_type == "write":
            prepared = self._prepare_file_write(
                workspace_id,
                path_value,
                content,
            )
        elif normalized_type == "edit":
            prepared = self._prepare_file_edit(
                workspace_id,
                path_value,
                find,
                replace,
                expected_replacements,
            )
        elif normalized_type == "bash":
            prepared = self._prepare_bash_action(
                workspace_id,
                command,
                cwd,
                timeout_seconds,
            )
        else:
            raise ValueError("action_type must be one of: write, edit, bash")
        action_id = f"action-{uuid.uuid4().hex}"
        prepared["action_id"] = action_id
        prepared["created_at"] = time.time()
        prepared["fingerprint"] = _action_fingerprint(prepared["action"])
        self.pending_prepared_actions[action_id] = prepared
        result = {
            "status": "prepared",
            "action_id": action_id,
            "commit_token": action_id,
            "action_type": prepared["action_type"],
            "action": prepared["action"],
            "fingerprint": prepared["fingerprint"],
            "expires_after_idle_seconds": PREPARED_ACTION_IDLE_SECONDS,
            "commit_confirmation": self.prepared_action_confirmation,
            "single_use": True,
            "committed": False,
        }
        if prepared.get("diff") is not None:
            result["diff"] = prepared["diff"]
        return result

    def commit_action(
        self,
        workspace_id: str,
        action_id: str,
        approval_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute one immutable prepared action using only its bound token."""
        self.touch()
        self._require_connected_agent_tool("commit_action")
        self._expire_prepared_actions()
        prepared = self.pending_prepared_actions.get(action_id)
        if not prepared:
            raise AccessDenied("action_id is unknown, expired, or already used")
        if prepared["workspace_id"] != workspace_id:
            raise AccessDenied("action_id does not belong to this workspace")
        approval_action = {
            "tool_name": "commit_action",
            "workspace_id": workspace_id,
            "action_id": action_id,
            "prepared_fingerprint": prepared["fingerprint"],
        }
        if not self.trust_host_confirmation_for_previewed_patches:
            self._require_connected_action_approval(
                "commit_action",
                approval_action,
                approval_id,
            )
        del self.pending_prepared_actions[action_id]
        if prepared["action_type"] in {"write", "edit"}:
            result = self._commit_prepared_file(prepared)
        elif prepared["action_type"] == "bash":
            result = self._commit_prepared_bash(prepared)
        else:
            raise AccessDenied("prepared action type is no longer supported")
        return {
            "status": "committed",
            "action_id": action_id,
            "action_type": prepared["action_type"],
            "confirmation": self.prepared_action_confirmation,
            "single_use": True,
            "committed": True,
            "result": result,
        }

    def _prepare_file_write(
        self,
        workspace_id: str,
        path_value: Optional[str],
        content: Optional[str],
    ) -> Dict[str, Any]:
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("write preparation requires path")
        if not isinstance(content, str):
            raise ValueError("write preparation requires string content")
        if len(content.encode("utf-8")) > MAX_READ_FILE_BYTES:
            raise AccessDenied("prepared write content is too large")
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=False)
        self._assert_not_protected(target)
        relative = self.relative_path(workspace_id, target)
        original = ""
        base_sha256: Optional[str] = None
        target_state = "absent"
        if target.exists():
            if not target.is_file():
                raise AccessDenied("prepared write target must be a file or absent")
            if target.stat().st_size > MAX_READ_FILE_BYTES:
                raise AccessDenied("prepared write target is too large")
            try:
                original = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise AccessDenied("prepared write target must be a UTF-8 text file") from exc
            base_sha256 = _sha256_text(original)
            target_state = "existing"
        if original == content and target_state == "existing":
            raise ValueError("prepared write contains no changes")
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{relative}" if target_state == "existing" else "/dev/null",
                tofile=f"b/{relative}",
            )
        )
        result_sha256 = _sha256_text(content)
        action = {
            "tool_name": "write",
            "workspace_id": workspace_id,
            "path": relative,
            "target_state": target_state,
            "base_sha256": base_sha256,
            "content_sha256": result_sha256,
            "content_bytes": len(content.encode("utf-8")),
            "diff_sha256": _sha256_text(diff),
        }
        return {
            "workspace_id": workspace_id,
            "action_type": "write",
            "action": action,
            "path": relative,
            "target_state": target_state,
            "base_sha256": base_sha256,
            "result_sha256": result_sha256,
            "new_content": content,
            "diff": diff,
        }

    def _prepare_file_edit(
        self,
        workspace_id: str,
        path_value: Optional[str],
        find: Optional[str],
        replace: Optional[str],
        expected_replacements: Optional[int],
    ) -> Dict[str, Any]:
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("edit preparation requires path")
        if not isinstance(find, str) or not find:
            raise ValueError("edit preparation requires non-empty find text")
        if not isinstance(replace, str):
            raise ValueError("edit preparation requires string replace text")
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not target.is_file():
            raise AccessDenied("prepared edit target must be a file")
        self._assert_not_protected(target)
        if target.stat().st_size > MAX_READ_FILE_BYTES:
            raise AccessDenied("prepared edit target is too large")
        try:
            original = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AccessDenied("prepared edit target must be a UTF-8 text file") from exc
        count = original.count(find)
        if count == 0:
            raise ValueError("find text was not present")
        if expected_replacements is not None and count != expected_replacements:
            raise ValueError(
                f"expected {expected_replacements} replacement(s), found {count}"
            )
        new_content = original.replace(find, replace)
        if len(new_content.encode("utf-8")) > MAX_READ_FILE_BYTES:
            raise AccessDenied("prepared edit result is too large")
        relative = self.relative_path(workspace_id, target)
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
        base_sha256 = _sha256_text(original)
        result_sha256 = _sha256_text(new_content)
        action = {
            "tool_name": "edit",
            "workspace_id": workspace_id,
            "path": relative,
            "base_sha256": base_sha256,
            "result_sha256": result_sha256,
            "find_sha256": _sha256_text(find),
            "replace_sha256": _sha256_text(replace),
            "expected_replacements": expected_replacements,
            "actual_replacements": count,
            "diff_sha256": _sha256_text(diff),
        }
        return {
            "workspace_id": workspace_id,
            "action_type": "edit",
            "action": action,
            "path": relative,
            "target_state": "existing",
            "base_sha256": base_sha256,
            "result_sha256": result_sha256,
            "new_content": new_content,
            "replacements": count,
            "diff": diff,
        }

    def _prepare_bash_action(
        self,
        workspace_id: str,
        command: Optional[str],
        cwd: str,
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("bash preparation requires a non-empty command")
        timeout = max(1, min(int(timeout_seconds), MAX_COMMAND_SECONDS))
        cwd = _normalize_optional_workspace_location(cwd, "cwd")
        cwd_path = self.resolve_workspace_path(workspace_id, cwd, must_exist=True)
        if not cwd_path.is_dir():
            raise AccessDenied("prepared bash cwd must be a directory")
        self._assert_not_protected(cwd_path)
        forced_reason = self._assert_connected_bash_allowed(command)
        if forced_reason:
            raise AccessDenied(
                "prepare_action accepts only ordinary project-local bash; "
                f"separately high-risk command detected: {forced_reason}"
            )
        relative_cwd = self.relative_path(workspace_id, cwd_path)
        action = {
            "tool_name": "bash",
            "workspace_id": workspace_id,
            "cwd": relative_cwd,
            "command": command,
            "timeout_seconds": timeout,
        }
        return {
            "workspace_id": workspace_id,
            "action_type": "bash",
            "action": action,
            "command": command,
            "cwd": relative_cwd,
            "timeout_seconds": timeout,
        }

    def _commit_prepared_file(self, prepared: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = prepared["workspace_id"]
        target = self.resolve_workspace_path(
            workspace_id,
            prepared["path"],
            must_exist=False,
        )
        self._assert_not_protected(target)
        if prepared["target_state"] == "absent":
            if target.exists():
                raise AccessDenied(
                    "prepared create target now exists; prepare a new action before committing"
                )
        else:
            if not target.is_file():
                raise AccessDenied(
                    "prepared file target changed type or disappeared; prepare again"
                )
            if target.stat().st_size > MAX_READ_FILE_BYTES:
                raise AccessDenied("prepared file target is now too large")
            try:
                current = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise AccessDenied("prepared file target is no longer UTF-8 text") from exc
            if _sha256_text(current) != prepared["base_sha256"]:
                raise AccessDenied(
                    "file changed after action preparation; prepare a new action"
                )
        new_content = prepared["new_content"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
        return {
            "path": prepared["path"],
            "bytes": len(new_content.encode("utf-8")),
            "sha256": prepared["result_sha256"],
            "replacements": prepared.get("replacements"),
        }

    def _commit_prepared_bash(self, prepared: Dict[str, Any]) -> Dict[str, Any]:
        workspace_id = prepared["workspace_id"]
        cwd_path = self.resolve_workspace_path(
            workspace_id,
            prepared["cwd"],
            must_exist=True,
        )
        if not cwd_path.is_dir():
            raise AccessDenied("prepared bash cwd is no longer a directory")
        self._assert_not_protected(cwd_path)
        forced_reason = self._assert_connected_bash_allowed(prepared["command"])
        if forced_reason:
            raise AccessDenied(
                "prepared bash became separately high risk and cannot be committed: "
                + forced_reason
            )
        completed = subprocess.run(
            prepared["command"],
            cwd=cwd_path,
            shell=True,
            text=True,
            capture_output=True,
            timeout=prepared["timeout_seconds"],
        )
        stdout = completed.stdout.encode("utf-8", errors="replace")[:MAX_COMMAND_OUTPUT_BYTES]
        stderr = completed.stderr.encode("utf-8", errors="replace")[:MAX_COMMAND_OUTPUT_BYTES]
        return {
            "cwd": str(cwd_path),
            "command": prepared["command"],
            "returncode": completed.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    def write_file(
        self,
        workspace_id: str,
        path_value: str,
        content: str,
        approval_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.touch()
        self._require_full_agent_tool("write")
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=False)
        self._assert_not_protected(target)
        action = {
            "tool_name": "write",
            "workspace_id": workspace_id,
            "path": self.relative_path(workspace_id, target),
            "content_sha256": _sha256_text(content),
            "content_bytes": len(content.encode("utf-8")),
        }
        self._require_connected_action_approval("write", action, approval_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": self.relative_path(workspace_id, target), "bytes": len(content.encode("utf-8"))}

    def edit_file(
        self,
        workspace_id: str,
        path_value: str,
        find: str,
        replace: str,
        expected_replacements: Optional[int] = None,
        approval_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.touch()
        self._require_full_agent_tool("edit")
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not target.is_file():
            raise AccessDenied("edit target must be a file")
        self._assert_not_protected(target)
        action = {
            "tool_name": "edit",
            "workspace_id": workspace_id,
            "path": self.relative_path(workspace_id, target),
            "find_sha256": _sha256_text(find),
            "replace_sha256": _sha256_text(replace),
            "expected_replacements": expected_replacements,
        }
        self._require_connected_action_approval("edit", action, approval_id)
        original = target.read_text(encoding="utf-8")
        count = original.count(find)
        if count == 0:
            raise ValueError("find text was not present")
        if expected_replacements is not None and count != expected_replacements:
            raise ValueError(
                f"expected {expected_replacements} replacement(s), found {count}"
            )
        target.write_text(original.replace(find, replace), encoding="utf-8")
        return {"path": self.relative_path(workspace_id, target), "replacements": count}

    def glob_paths(self, workspace_id: str, pattern: str) -> List[str]:
        self.touch()
        workspace = self.workspace(workspace_id)
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError("pattern must be a non-empty string")
        if "\x00" in pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise AccessDenied("glob pattern must be relative to the workspace")
        results: List[str] = []
        for path in workspace.glob(pattern):
            resolved = path.resolve(strict=False)
            self._assert_under_workspace(workspace, resolved)
            if self._is_protected_path(resolved):
                continue
            results.append(resolved.relative_to(workspace).as_posix())
        return sorted(results)

    def grep(self, workspace_id: str, pattern: str, path_value: str = ".") -> List[Dict[str, Any]]:
        self.touch()
        path_value = _normalize_optional_workspace_location(path_value, "path")
        root = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("pattern must be a non-empty string")
        files = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        matches: List[Dict[str, Any]] = []
        workspace = self.workspace(workspace_id)
        for file_path in files:
            self._assert_under_workspace(workspace, file_path.resolve(strict=False))
            if self._is_protected_path(file_path):
                continue
            if file_path.stat().st_size > MAX_READ_FILE_BYTES:
                continue
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(lines, 1):
                if pattern in line:
                    matches.append(
                        {
                            "path": file_path.relative_to(workspace).as_posix(),
                            "line": number,
                            "text": line,
                        }
                    )
        return matches

    def run_bash(
        self,
        workspace_id: str,
        command: str,
        cwd: str = ".",
        timeout_seconds: int = MAX_COMMAND_SECONDS,
        approval_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.touch()
        self._require_full_agent_tool("bash")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be a non-empty string")
        timeout = max(1, min(int(timeout_seconds), MAX_COMMAND_SECONDS))
        cwd = _normalize_optional_workspace_location(cwd, "cwd")
        cwd_path = self.resolve_workspace_path(workspace_id, cwd, must_exist=True)
        if not cwd_path.is_dir():
            raise AccessDenied("bash cwd must be a directory")
        self._assert_not_protected(cwd_path)
        if self.profile == PROFILE_CONNECTED_AGENT:
            forced_approval_reason = self._assert_connected_bash_allowed(command)
            action = {
                "tool_name": "bash",
                "workspace_id": workspace_id,
                "cwd": self.relative_path(workspace_id, cwd_path),
                "command": command,
                "timeout_seconds": timeout,
            }
            self._require_connected_action_approval(
                "bash",
                action,
                approval_id,
                force=forced_approval_reason is not None,
                reason=forced_approval_reason,
            )
        else:
            self._assert_bash_command_allowed(command)
        completed = subprocess.run(
            command,
            cwd=cwd_path,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        stdout = completed.stdout.encode("utf-8", errors="replace")[:MAX_COMMAND_OUTPUT_BYTES]
        stderr = completed.stderr.encode("utf-8", errors="replace")[:MAX_COMMAND_OUTPUT_BYTES]
        return {
            "cwd": str(cwd_path),
            "returncode": completed.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "risk_level": "5/5",
        }

    def list_tasks(self, workspace_id: str) -> Dict[str, Any]:
        """List commands explicitly allowlisted by the local session owner."""
        self.touch()
        self._require_connected_agent_tool("list_tasks")
        self.workspace(workspace_id)
        return {
            "tasks": [
                {"name": name, "command": command, "cwd": "."}
                for name, command in sorted(self.allowed_tasks.items())
            ],
            "count": len(self.allowed_tasks),
            "source": "local_session_configuration",
        }

    def run_task(
        self,
        workspace_id: str,
        task_name: str,
        approval_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run one exact owner-configured task; arbitrary arguments are not accepted."""
        self.touch()
        self._require_connected_agent_tool("run_task")
        command = self.allowed_tasks.get(task_name)
        if command is None:
            raise AccessDenied("task_name is not in the local session allowlist")
        forced_reason = self._assert_connected_bash_allowed(command)
        if forced_reason:
            raise AccessDenied(
                "owner-configured tasks must not contain destructive, install, privileged, "
                f"or Git remote operations: {forced_reason}"
            )
        workspace = self.workspace(workspace_id)
        action = {
            "tool_name": "run_task",
            "workspace_id": workspace_id,
            "task_name": task_name,
            "command": command,
            "cwd": ".",
        }
        self._require_connected_action_approval("run_task", action, approval_id)
        completed = subprocess.run(
            command,
            cwd=workspace,
            shell=True,
            text=True,
            capture_output=True,
            timeout=MAX_COMMAND_SECONDS,
        )
        stdout = completed.stdout.encode("utf-8", errors="replace")[:MAX_COMMAND_OUTPUT_BYTES]
        stderr = completed.stderr.encode("utf-8", errors="replace")[:MAX_COMMAND_OUTPUT_BYTES]
        return {
            "task_name": task_name,
            "command": command,
            "cwd": ".",
            "returncode": completed.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "permission_mode": self.permission_mode,
        }

    def set_permission_mode(self, mode: str, confirmation: str = "") -> Dict[str, Any]:
        """Enter Controlled Auto; approval remains an internal compatibility fallback."""
        self._require_connected_agent_tool("set_permission_mode")
        self.touch()
        normalized = mode.strip().lower()
        if normalized not in {PERMISSION_APPROVAL, PERMISSION_CONTROLLED_AUTO}:
            raise AccessDenied(
                "set_permission_mode exposes only controlled_auto; Danger Auto uses "
                "its separate exact-phrase tool, while approval is reserved for "
                "internal direct-client compatibility"
            )
        if normalized == PERMISSION_CONTROLLED_AUTO and not _looks_like_affirmative_confirmation(
            confirmation
        ):
            raise AccessDenied(
                "controlled_auto requires a clear affirmative confirmation from the user"
            )
        self.permission_mode = normalized
        self.session_last_activity = time.time()
        return self.permission_mode_status()

    def permission_mode_status(self) -> Dict[str, Any]:
        self._require_connected_agent_tool("permission_mode_status")
        self._expire_idle_session()
        remaining = max(
            0,
            int(DANGER_AUTO_IDLE_SECONDS - (time.time() - self.session_last_activity)),
        )
        return {
            "profile": self.profile,
            "permission_mode": self.permission_mode,
            "base_permission_mode": self.base_permission_mode,
            "visible_permission_modes": [
                PERMISSION_CONTROLLED_AUTO,
                PERMISSION_DANGER_AUTO,
            ],
            "server_approval_fallback_active": self.permission_mode
            == PERMISSION_APPROVAL,
            "risk_level": self.risk_level,
            "previewed_patch_confirmation": self.previewed_patch_confirmation,
            "prepared_action_confirmation": self.prepared_action_confirmation,
            "host_confirmed_tools": (
                ["apply_patch", "commit_action"]
                if self.trust_host_confirmation_for_previewed_patches
                else []
            ),
            "automatic_tools": (
                sorted(CONTROLLED_AUTO_TOOLS)
                if self.permission_mode == PERMISSION_CONTROLLED_AUTO
                else (
                    [
                        "write",
                        "edit",
                        "apply_patch",
                        "commit_action",
                        "bash",
                        "run_task",
                    ]
                    if self.permission_mode == PERMISSION_DANGER_AUTO
                    else []
                )
            ),
            "raw_write_edit_bash_require_approval": self.permission_mode
            != PERMISSION_DANGER_AUTO,
            "prepared_action_flow": "prepare_action -> commit_action",
            "hard_blocks_remain": [
                "protected credential paths",
                "network commands",
                "browser, desktop, and clipboard commands",
                "out-of-workspace paths",
            ],
            "idle_timeout_seconds": DANGER_AUTO_IDLE_SECONDS,
            "seconds_until_idle_close": remaining,
            "configured_tasks": sorted(self.allowed_tasks),
        }

    def enable_danger_auto(self, phrase: str) -> Dict[str, Any]:
        self._require_connected_agent_tool("enable_danger_auto")
        self.touch()
        if phrase.strip() != DANGER_AUTO_PHRASE:
            raise AccessDenied(
                "Danger Auto phrase was not accepted. The user must type the exact phrase."
            )
        self.permission_mode = PERMISSION_DANGER_AUTO
        self.session_last_activity = time.time()
        return self.danger_auto_status()

    def danger_auto_status(self) -> Dict[str, Any]:
        self._require_connected_agent_tool("danger_auto_status")
        status = self.permission_mode_status()
        status.update(
            {
                "danger_auto_enabled": self.danger_auto_enabled,
                "danger_phrase": DANGER_AUTO_PHRASE,
                "risk_level": self.risk_level,
            }
        )
        status.update({
            "temporary_allowed_roots": [str(root) for root in self.session_allowed_roots],
            "pending_action_approvals": len(self.pending_action_approvals),
            "granted_action_approvals": len(self.granted_action_approvals),
            "pending_prepared_actions": len(self.pending_prepared_actions),
        })
        return status

    def disable_danger_auto(self) -> Dict[str, Any]:
        self._require_connected_agent_tool("disable_danger_auto")
        self.touch()
        if self.permission_mode == PERMISSION_DANGER_AUTO:
            self.permission_mode = self.base_permission_mode
        return self.danger_auto_status()

    def grant_action_approval(self, approval_id: str, confirmation: str) -> Dict[str, Any]:
        self._require_connected_agent_tool("grant_action_approval")
        self.touch()
        self._expire_action_approvals()
        if not isinstance(approval_id, str) or not approval_id.strip():
            raise ValueError("approval_id must be a non-empty string")
        if not _looks_like_affirmative_confirmation(confirmation):
            raise AccessDenied(
                "confirmation must contain a clear affirmative phrase from the user"
            )
        pending = self.pending_action_approvals.get(approval_id)
        if not pending:
            raise AccessDenied("approval_id is unknown or expired")
        granted = dict(pending)
        granted["status"] = "granted"
        granted["granted_at"] = time.time()
        self.granted_action_approvals[approval_id] = granted
        return {
            "status": "granted",
            "approval_id": approval_id,
            "tool_name": pending["action"]["tool_name"],
            "action": pending["action"],
            "single_use": True,
            "message": (
                "Retry the original tool call once with this approval_id. "
                "Do not reuse the approval for a different action."
            ),
        }

    def request_workspace_access(self, path_value: str, reason: str, access: str = "read") -> Dict[str, Any]:
        self._require_connected_agent_tool("request_workspace_access")
        self.touch()
        requested = self._resolve_grantable_root(path_value)
        return {
            "status": "approval_required",
            "path": str(requested),
            "access": self._normalize_access(access),
            "reason": reason,
            "risk_level": "5/5",
            "message": (
                "Ask the user in chat to confirm temporary workspace access. "
                "After the user confirms, call grant_workspace_access with the same path."
            ),
        }

    def grant_workspace_access(
        self,
        path_value: str,
        access: str = "read",
        approval_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._require_connected_agent_tool("grant_workspace_access")
        self.touch()
        requested = self._resolve_grantable_root(path_value)
        normalized_access = self._normalize_access(access)
        action = {
            "tool_name": "grant_workspace_access",
            "path": str(requested),
            "access": normalized_access,
            "temporary": True,
        }
        self._require_connected_action_approval(
            "grant_workspace_access",
            action,
            approval_id,
            force=True,
            reason="expanding the current session beyond its configured allowed roots",
        )
        if not any(_is_relative_to(requested, root) for root in self.allowed_roots + self.session_allowed_roots):
            self.session_allowed_roots.append(requested)
        return {
            "status": "granted",
            "path": str(requested),
            "access": normalized_access,
            "risk_level": "5/5",
            "temporary": True,
            "expires_after_idle_seconds": DANGER_AUTO_IDLE_SECONDS,
        }

    def touch(self) -> None:
        self._expire_idle_session()
        self.session_last_activity = time.time()

    def workspace(self, workspace_id: str) -> Path:
        workspace = self.workspaces.get(workspace_id)
        if not workspace:
            raise WorkspaceNotFound(f"Unknown workspace_id: {workspace_id}")
        return workspace

    def resolve_workspace_path(
        self, workspace_id: str, path_value: str, must_exist: bool
    ) -> Path:
        workspace = self.workspace(workspace_id)
        if not isinstance(path_value, str) or not path_value.strip():
            raise AccessDenied("path must be a non-empty string")
        if "\x00" in path_value:
            raise AccessDenied("path contains unsupported characters")
        raw = Path(path_value)
        if raw.is_absolute():
            raise AccessDenied("workspace file paths must be relative")
        if ".." in raw.parts:
            raise AccessDenied("parent-directory traversal is not allowed")
        target = (workspace / raw).resolve(strict=must_exist)
        self._assert_under_workspace(workspace, target)
        return target

    def relative_path(self, workspace_id: str, path: Path) -> str:
        return path.resolve(strict=False).relative_to(self.workspace(workspace_id)).as_posix()

    def _resolve_requested_workspace(self, path_value: str) -> Path:
        if not isinstance(path_value, str) or not path_value.strip():
            raise AccessDenied("workspace path must be a non-empty string")
        alias = path_value.strip().lower()
        if self.profile == PROFILE_CONNECTED_AGENT and alias in {
            "default",
            "default_workspace",
            "authorized_workspace",
        }:
            if len(self.allowed_roots) != 1:
                raise AccessDenied(
                    "default workspace alias requires exactly one configured allowed root; "
                    "ask Codex or the user to disambiguate the authorized workspace "
                    "instead of guessing or passing a local absolute path"
                )
            return self.allowed_roots[0]
        requested = Path(path_value).expanduser().resolve(strict=True)
        if not requested.is_dir():
            raise AccessDenied("workspace path must be a directory")
        if not any(_is_relative_to(requested, root) for root in self._current_allowed_roots()):
            raise AccessDenied(
                "workspace path is outside configured allowed roots; call "
                "request_workspace_access first, then grant_workspace_access only "
                "after the user confirms in chat"
            )
        return requested

    def _assert_under_workspace(self, workspace: Path, path: Path) -> None:
        if not _is_relative_to(path, workspace):
            raise AccessDenied("path escapes the opened workspace")

    def _require_full_agent_tool(self, tool_name: str) -> None:
        if self.profile not in {PROFILE_FULL_AGENT, PROFILE_CONNECTED_AGENT}:
            raise AccessDenied(f"{tool_name} is not available in read-only-project mode")

    def _require_connected_agent_tool(self, tool_name: str) -> None:
        if self.profile != PROFILE_CONNECTED_AGENT:
            raise AccessDenied(f"{tool_name} is only available in connected-agent mode")

    def _require_connected_action_approval(
        self,
        tool_name: str,
        action: Dict[str, Any],
        approval_id: Optional[str],
        *,
        force: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        if self.profile != PROFILE_CONNECTED_AGENT:
            return
        automatic = self.permission_mode == PERMISSION_DANGER_AUTO or (
            self.permission_mode == PERMISSION_CONTROLLED_AUTO
            and tool_name in CONTROLLED_AUTO_TOOLS
        )
        if automatic and not force:
            return
        self._expire_action_approvals()
        fingerprint = _action_fingerprint(action)
        if approval_id:
            granted = self.granted_action_approvals.get(approval_id)
            if not granted:
                raise ApprovalRequired(
                    f"{tool_name} requires a granted one-action approval_id in Connected Agent default mode",
                    {
                        "error": "approval_required",
                        "tool_name": tool_name,
                        "reason": "approval_id was not granted or has expired",
                    },
                )
            if granted["fingerprint"] != fingerprint:
                raise AccessDenied("approval_id does not match this exact action")
            del self.granted_action_approvals[approval_id]
            self.pending_action_approvals.pop(approval_id, None)
            return
        approval_id = f"approval-{uuid.uuid4().hex}"
        pending = {
            "approval_id": approval_id,
            "fingerprint": fingerprint,
            "action": action,
            "created_at": time.time(),
            "expires_after_idle_seconds": ACTION_APPROVAL_IDLE_SECONDS,
            "status": "pending",
        }
        self.pending_action_approvals[approval_id] = pending
        raise ApprovalRequired(
            (
                f"{tool_name} requires one-action user approval in Connected Agent default mode. "
                "Ask the user to approve this exact action, then call grant_action_approval "
                "with approval_id and the user's affirmative confirmation. Retry the original "
                "tool call once with the same approval_id."
            ),
            {
                "error": "approval_required",
                "approval_kind": "one_action",
                "approval_id": approval_id,
                "tool_name": tool_name,
                "action": action,
                "reason": reason or "this permission mode requires one-action approval",
                "single_use": True,
                "expires_after_idle_seconds": ACTION_APPROVAL_IDLE_SECONDS,
                "next_step": (
                    "Ask the user to confirm this exact action. If confirmed, call "
                    "grant_action_approval, then retry the original tool call with approval_id."
                ),
            },
        )

    def _assert_read_allowed(self, path: Path) -> None:
        self._assert_not_protected(path)

    def _assert_not_protected(self, path: Path) -> None:
        if self._is_protected_path(path):
            raise AccessDenied("path is protected from connector exposure")

    def _assert_bash_command_allowed(self, command: str) -> None:
        lowered = command.lower()
        if any(marker in lowered for marker in SENSITIVE_COMMAND_MARKERS):
            raise AccessDenied(
                "bash command appears to reference protected credential-like material"
            )

    def _assert_connected_bash_allowed(self, command: str) -> Optional[str]:
        self._assert_bash_command_allowed(command)
        lowered = command.lower()
        if "http://" in lowered or "https://" in lowered:
            raise AccessDenied("Connected Agent blocks bash commands that reference network URLs")
        if any(marker in lowered for marker in ("$home", "${home}", "~/", " ~", "../", "/..")):
            raise AccessDenied("Connected Agent blocks bash commands with obvious path escape markers")
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            raise AccessDenied(f"bash command could not be parsed safely: {exc}") from exc
        lowered_tokens = [token.lower() for token in tokens]
        command_names = {
            Path(token).name.lower()
            for token in lowered_tokens
            if token and not token.startswith("-") and token not in {"&&", "||", ";", "|"}
        }
        blocked = sorted(command_names.intersection(NETWORK_OR_REMOTE_COMMANDS | GUI_OR_CLIPBOARD_COMMANDS))
        if blocked:
            raise AccessDenied(
                "Connected Agent blocks network, browser/desktop, and clipboard commands: "
                + ", ".join(blocked)
            )
        approval_reasons: List[str] = []
        if command_names.intersection(APPROVAL_COMMANDS):
            approval_reasons.append(
                "deletion, moves, permission changes, or privileged commands"
            )
        if self._needs_install_approval(lowered_tokens):
            approval_reasons.append("dependency installation")
        if self._needs_git_remote_approval(lowered_tokens):
            approval_reasons.append("Git remote operations")
        if "-delete" in lowered_tokens:
            approval_reasons.append("find -delete style operations")
        for token in tokens:
            path_token = token.strip("'\"")
            if not path_token.startswith("/"):
                continue
            resolved = Path(path_token).expanduser().resolve(strict=False)
            if not any(_is_relative_to(resolved, root) for root in self._current_allowed_roots()):
                raise AccessDenied(
                    "Connected Agent blocks bash commands that reference absolute paths outside allowed roots"
                )
        if approval_reasons:
            return "; ".join(approval_reasons)
        return None

    def _needs_install_approval(self, tokens: List[str]) -> bool:
        for index, token in enumerate(tokens):
            command = Path(token).name
            following = tokens[index + 1 :]
            if command in {"npm", "pnpm", "yarn"} and following:
                if following[0] in PACKAGE_INSTALL_COMMANDS:
                    return True
            if command in {"pip", "pip3"} and following:
                if following[0] == "install":
                    return True
            if command in {"python", "python3"} and len(following) >= 3:
                if following[:3] in (["-m", "pip", "install"], ["-m", "uv", "pip"]):
                    return True
            if command == "uv" and following:
                if following[0] in {"add", "pip", "sync"}:
                    return True
            if command == "poetry" and following:
                if following[0] in {"add", "install"}:
                    return True
            if command == "brew" and following:
                if following[0] in {"install", "upgrade"}:
                    return True
            if command == "cargo" and following:
                if following[0] == "install":
                    return True
            if command == "go" and following:
                if following[0] in {"get", "install"}:
                    return True
            if command == "gem" and following:
                if following[0] == "install":
                    return True
        return False

    def _needs_git_remote_approval(self, tokens: List[str]) -> bool:
        for index, token in enumerate(tokens):
            if Path(token).name != "git":
                continue
            for item in tokens[index + 1 :]:
                if item.startswith("-"):
                    continue
                return item in GIT_REMOTE_COMMANDS
        return False

    def _is_protected_path(self, path: Path) -> bool:
        lowered_parts = [part.lower() for part in path.parts]
        lowered_name = path.name.lower()
        if lowered_name in SENSITIVE_FILENAMES:
            return True
        if lowered_name.startswith(".env"):
            return True
        if path.suffix.lower() in SENSITIVE_SUFFIXES:
            return True
        return any(segment in lowered_parts for segment in SENSITIVE_PATH_SEGMENTS)

    def _current_allowed_roots(self) -> List[Path]:
        return self.allowed_roots + self.session_allowed_roots

    def _expire_idle_session(self) -> None:
        if time.time() - self.session_last_activity <= DANGER_AUTO_IDLE_SECONDS:
            self._expire_action_approvals()
            self._expire_patch_previews()
            self._expire_prepared_actions()
            return
        self.permission_mode = self.base_permission_mode
        self.session_allowed_roots.clear()
        self.pending_action_approvals.clear()
        self.granted_action_approvals.clear()
        self.pending_patch_previews.clear()
        self.pending_prepared_actions.clear()

    def _expire_action_approvals(self) -> None:
        cutoff = time.time() - ACTION_APPROVAL_IDLE_SECONDS
        self.pending_action_approvals = {
            approval_id: approval
            for approval_id, approval in self.pending_action_approvals.items()
            if float(approval.get("created_at", 0)) >= cutoff
        }
        self.granted_action_approvals = {
            approval_id: approval
            for approval_id, approval in self.granted_action_approvals.items()
            if float(approval.get("granted_at", approval.get("created_at", 0))) >= cutoff
        }

    def _expire_patch_previews(self) -> None:
        cutoff = time.time() - PATCH_PREVIEW_IDLE_SECONDS
        self.pending_patch_previews = {
            preview_id: preview
            for preview_id, preview in self.pending_patch_previews.items()
            if float(preview.get("created_at", 0)) >= cutoff
        }

    def _expire_prepared_actions(self) -> None:
        cutoff = time.time() - PREPARED_ACTION_IDLE_SECONDS
        self.pending_prepared_actions = {
            action_id: prepared
            for action_id, prepared in self.pending_prepared_actions.items()
            if float(prepared.get("created_at", 0)) >= cutoff
        }

    def _resolve_grantable_root(self, path_value: str) -> Path:
        if not isinstance(path_value, str) or not path_value.strip():
            raise AccessDenied("workspace access path must be a non-empty string")
        requested = Path(path_value).expanduser().resolve(strict=True)
        if not requested.is_dir():
            raise AccessDenied("workspace access path must be a directory")
        if self._is_protected_path(requested):
            raise AccessDenied("workspace access path is protected from connector exposure")
        validate_allowed_roots([requested])
        return requested

    def _normalize_access(self, value: str) -> str:
        access = (value or "read").strip().lower()
        if access not in {"read", "write", "execute"}:
            raise ValueError("access must be one of: read, write, execute")
        return access


def validate_allowed_roots(roots: List[Path]) -> List[Path]:
    if not roots:
        raise ValueError("Connected Agent workspace mode requires at least one --allowed-root")
    home = Path.home().resolve()
    normalized: List[Path] = []
    for root in roots:
        resolved = root.expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError(f"Allowed root is not a directory: {root}")
        if resolved == home:
            raise ValueError("Allowed root must be narrower than the home directory")
        if resolved == Path(resolved.anchor).resolve():
            raise ValueError("Allowed root must not be a filesystem root")
        normalized.append(resolved)
    return normalized


def validate_allowed_tasks(tasks: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for raw_name, raw_command in tasks.items():
        name = raw_name.strip().lower()
        command = raw_command.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", name):
            raise ValueError(
                "Allowed task names must use 1-32 lowercase letters, numbers, hyphens, or underscores"
            )
        if not command:
            raise ValueError(f"Allowed task command is empty: {name}")
        normalized[name] = command
    return normalized


def parse_allowed_tasks(values: Optional[List[str]]) -> Dict[str, str]:
    tasks: Dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError("--allowed-task must use NAME=COMMAND")
        name, command = value.split("=", 1)
        tasks[name] = command
    return validate_allowed_tasks(tasks)


def tool_definitions(profile: str = PROFILE_FULL_AGENT) -> List[Dict[str, Any]]:
    open_default_workspace_tool = {
        "name": "open_default_workspace",
        "title": "Open Default Workspace",
        "description": (
            "Open the single configured allowed-root workspace without passing a "
            "local filesystem path. Use this first in Connected Agent mode when "
            "one allowed root is configured."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": _read_only_annotations(idempotent=False),
    }
    base_tools = [
        {
            "name": "open_workspace",
            "title": "Open Workspace",
            "description": (
                "Open a configured allowed-root workspace and return a workspace_id. "
                "In Connected Agent mode, when exactly one allowed root is configured, "
                'path "default" opens that root without passing a local filesystem path.'
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(idempotent=False),
        },
        _path_tool("ls", "List Directory", "List files and directories in an opened workspace."),
        _path_tool("read", "Read File", "Read a UTF-8 file in an opened workspace."),
        {
            "name": "read_lines",
            "title": "Read Lines",
            "description": (
                "Read a bounded 1-based line range from a UTF-8 file in an opened "
                "workspace. Use this for large task-relevant text files instead of "
                "reading the whole file."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["workspace_id", "path", "start_line"],
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(),
        },
    ]
    if profile == PROFILE_CONNECTED_AGENT:
        base_tools = [open_default_workspace_tool] + base_tools
    search_tools = [
        {
            "name": "grep",
            "title": "Grep",
            "description": "Search text in files under an opened workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                },
                "required": ["workspace_id", "pattern"],
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "glob",
            "title": "Glob",
            "description": "List workspace paths matching a relative glob pattern.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "pattern": {"type": "string"},
                },
                "required": ["workspace_id", "pattern"],
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(),
        },
    ]
    if profile == PROFILE_READ_ONLY_PROJECT:
        return base_tools + search_tools
    execution_tools = [
        {
            "name": "write",
            "title": "Write File",
            "description": (
                "Directly write a UTF-8 file. In Controlled Auto, prefer the read-only "
                "prepare_action then bound commit_action flow; this raw compatibility "
                "tool retains legacy server approval."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "approval_id": {"type": "string"},
                },
                "required": ["workspace_id", "path", "content"],
                "additionalProperties": False,
            },
            "annotations": _write_annotations(destructive=True),
        },
        {
            "name": "edit",
            "title": "Edit File",
            "description": (
                "Directly replace exact text. In Controlled Auto, prefer the read-only "
                "prepare_action then bound commit_action flow; this raw compatibility "
                "tool retains legacy server approval."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "path": {"type": "string"},
                    "find": {"type": "string"},
                    "replace": {"type": "string"},
                    "expected_replacements": {"type": "integer"},
                    "approval_id": {"type": "string"},
                },
                "required": ["workspace_id", "path", "find", "replace"],
                "additionalProperties": False,
            },
            "annotations": _write_annotations(destructive=True),
        },
    ]
    structured_execution_tools = [
        {
            "name": "prepare_action",
            "title": "Prepare Bound Action",
            "description": (
                "Validate and store one immutable write, edit, or ordinary project-local "
                "bash action without executing it. Show the returned action and diff, "
                "then call commit_action once with only its action_id."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "action_type": {
                        "type": "string",
                        "enum": ["write", "edit", "bash"],
                    },
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "find": {"type": "string"},
                    "replace": {"type": "string"},
                    "expected_replacements": {"type": "integer"},
                    "command": {"type": "string"},
                    "cwd": {"type": "string", "default": "."},
                    "timeout_seconds": {"type": "integer"},
                },
                "required": ["workspace_id", "action_type"],
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(idempotent=False),
        },
        {
            "name": "commit_action",
            "title": "Commit Prepared Action",
            "description": (
                "Commit exactly one unexpired prepare_action result using only its "
                "bound action_id. The bounded product session uses one host-native "
                "confirmation; direct clients retain server one-action approval."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "action_id": {"type": "string"},
                    "approval_id": {"type": "string"},
                },
                "required": ["workspace_id", "action_id"],
                "additionalProperties": False,
            },
            "annotations": _write_annotations(destructive=True),
        },
        {
            "name": "file_info",
            "title": "File Info",
            "description": (
                "Return file type, size, modification time, and SHA-256 for a small "
                "task-relevant file. Use the hash before preview_patch."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["workspace_id", "path"],
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "preview_patch",
            "title": "Preview Patch",
            "description": (
                "Preview an exact whole-file replacement for an existing UTF-8 file. "
                "Returns a single-use preview_id and unified diff without writing."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "path": {"type": "string"},
                    "new_content": {"type": "string"},
                    "expected_sha256": {"type": "string"},
                },
                "required": [
                    "workspace_id",
                    "path",
                    "new_content",
                    "expected_sha256",
                ],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
        {
            "name": "apply_patch",
            "title": "Apply Previewed Patch",
            "description": (
                "Apply exactly one unexpired preview_patch result after showing its diff. "
                "The session reports whether commit confirmation is handled by a server "
                "one-action approval or one ChatGPT host-native write confirmation."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "preview_id": {"type": "string"},
                    "approval_id": {"type": "string"},
                },
                "required": ["workspace_id", "preview_id"],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
        {
            "name": "list_tasks",
            "title": "List Allowed Tasks",
            "description": (
                "List bounded local test, lint, build, or other check commands "
                "explicitly configured by the session owner."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_id": {"type": "string"}},
                "required": ["workspace_id"],
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "run_task",
            "title": "Run Allowed Task",
            "description": (
                "Run one exact owner-configured, non-destructive local check without "
                "arbitrary arguments. Network, install, privileged, Git remote, and "
                "destructive commands remain blocked. The default Controlled Auto "
                "product session may run it with host confirmation; low-level direct "
                "clients retain the hidden server approval fallback."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "task_name": {"type": "string"},
                    "approval_id": {"type": "string"},
                },
                "required": ["workspace_id", "task_name"],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
    ]
    bash_tool = {
        "name": "bash",
        "title": "Run Bash",
        "description": (
            "Directly run a shell command in an opened workspace. This is not a "
            "sandbox. In Controlled Auto, prefer prepare_action then commit_action "
            "for ordinary project-local commands; raw bash retains legacy approval."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "command": {"type": "string"},
                "cwd": {"type": "string", "default": "."},
                "timeout_seconds": {"type": "integer"},
                "approval_id": {"type": "string"},
            },
            "required": ["workspace_id", "command"],
            "additionalProperties": False,
        },
        "annotations": _write_annotations(destructive=True),
    }
    connected_tools = [
        {
            "name": "set_permission_mode",
            "title": "Set Permission Mode",
            "description": (
                "Enter bounded Controlled Auto from a low-level server approval "
                "fallback. Product sessions already start in Controlled Auto; "
                "Danger Auto uses its separate exact-phrase tool."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": [PERMISSION_CONTROLLED_AUTO],
                    },
                    "confirmation": {"type": "string"},
                },
                "required": ["mode"],
                "additionalProperties": False,
            },
            "annotations": _write_annotations(
                destructive=False,
                idempotent=True,
            ),
        },
        {
            "name": "permission_mode_status",
            "title": "Permission Mode Status",
            "description": "Return the current internal Connected Agent permission mode and hard boundaries.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "enable_danger_auto",
            "title": "Enable Danger Auto",
            "description": (
                "Enable session-only Connected Agent Danger Auto after the user typed "
                "the exact danger phrase. The model must not fabricate this phrase."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"phrase": {"type": "string"}},
                "required": ["phrase"],
                "additionalProperties": False,
            },
            "annotations": _write_annotations(
                destructive=True,
                idempotent=True,
            ),
        },
        {
            "name": "danger_auto_status",
            "title": "Danger Auto Status",
            "description": "Return Connected Agent Danger Auto status and idle timeout.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "disable_danger_auto",
            "title": "Disable Danger Auto",
            "description": "Disable Connected Agent Danger Auto for this session.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "annotations": _write_annotations(
                destructive=False,
                idempotent=True,
            ),
        },
        {
            "name": "grant_action_approval",
            "title": "Grant Action Approval",
            "description": (
                "Grant one pending side-effect or workspace-expansion action after the user clearly "
                "approves it in chat. Single-use; retry the original tool call "
                "with the returned approval_id."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "approval_id": {"type": "string"},
                    "confirmation": {"type": "string"},
                },
                "required": ["approval_id", "confirmation"],
                "additionalProperties": False,
            },
            "annotations": _write_annotations(destructive=True),
        },
        {
            "name": "request_workspace_access",
            "title": "Request Workspace Access",
            "description": (
                "Prepare a user-visible request for temporary access to a project "
                "directory outside the configured allowed roots."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "reason": {"type": "string"},
                    "access": {"type": "string", "enum": ["read", "write", "execute"]},
                },
                "required": ["path", "reason"],
                "additionalProperties": False,
            },
            "annotations": _read_only_annotations(idempotent=False),
        },
        {
            "name": "grant_workspace_access",
            "title": "Grant Workspace Access",
            "description": (
                "Temporarily add a confirmed project directory to this session's "
                "allowed roots. This always requires a single-use action approval, "
                "including in Controlled Auto or Danger Auto."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "access": {"type": "string", "enum": ["read", "write", "execute"]},
                    "approval_id": {"type": "string"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            "annotations": _write_annotations(destructive=True),
        },
    ]
    if profile == PROFILE_CONNECTED_AGENT:
        return (
            base_tools
            + structured_execution_tools
            + execution_tools
            + search_tools
            + [bash_tool]
            + connected_tools
        )
    return base_tools + execution_tools + search_tools + [bash_tool]


def handle_request(
    request: Dict[str, Any], manager: FullAgentWorkspaceManager
) -> Optional[Dict[str, Any]]:
    request_id = request.get("id")
    method = request.get("method")
    try:
        if method == "initialize":
            return _response(request_id, _initialize_result(request, manager))
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return _response(request_id, {"tools": tool_definitions(manager.profile)})
        if method == "tools/call":
            return _response(request_id, _call_tool(request.get("params") or {}, manager))
        return _error(request_id, -32601, f"Method not found: {method}")
    except Exception as exc:
        return _error(request_id, -32603, f"Internal error: {exc}")


def _call_tool(params: Dict[str, Any], manager: FullAgentWorkspaceManager) -> Dict[str, Any]:
    if not isinstance(params, dict):
        return _tool_error("Invalid tool call params: expected object")
    name = params.get("name")
    try:
        arguments = _arguments_dict(params.get("arguments"))
        if name not in manager.tool_names:
            return _tool_error(f"Tool is not available in {manager.profile} mode: {name}")
        if name == "open_default_workspace":
            result = manager.open_default_workspace()
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "open_workspace":
            result = manager.open_workspace(_required_string(arguments, "path"))
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "ls":
            result = {"entries": manager.list_directory(_required_string(arguments, "workspace_id"), arguments.get("path", "."))}
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "read":
            content = manager.read_file(
                _required_string(arguments, "workspace_id"),
                _required_string(arguments, "path"),
            )
            return _tool_result(
                content,
                {
                    "path": arguments["path"],
                    "bytes": len(content.encode("utf-8")),
                    "content": content,
                },
            )
        if name == "read_lines":
            result = manager.read_lines(
                _required_string(arguments, "workspace_id"),
                _required_string(arguments, "path"),
                _required_int(arguments, "start_line"),
                _optional_int(arguments, "end_line"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "prepare_action":
            result = manager.prepare_action(
                _required_string(arguments, "workspace_id"),
                _required_string(arguments, "action_type"),
                path_value=arguments.get("path"),
                content=arguments.get("content"),
                find=arguments.get("find"),
                replace=arguments.get("replace"),
                expected_replacements=_optional_int(
                    arguments,
                    "expected_replacements",
                ),
                command=arguments.get("command"),
                cwd=arguments.get("cwd", "."),
                timeout_seconds=arguments.get(
                    "timeout_seconds",
                    MAX_COMMAND_SECONDS,
                ),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "commit_action":
            result = manager.commit_action(
                _required_string(arguments, "workspace_id"),
                _required_string(arguments, "action_id"),
                arguments.get("approval_id"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "file_info":
            result = manager.file_info(
                _required_string(arguments, "workspace_id"),
                _required_string(arguments, "path"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "preview_patch":
            _require_strings(
                arguments,
                ["workspace_id", "path", "new_content", "expected_sha256"],
                allow_empty={"new_content"},
            )
            result = manager.preview_patch(
                arguments["workspace_id"],
                arguments["path"],
                arguments["new_content"],
                arguments["expected_sha256"],
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "apply_patch":
            result = manager.apply_patch(
                _required_string(arguments, "workspace_id"),
                _required_string(arguments, "preview_id"),
                arguments.get("approval_id"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "write":
            _require_strings(arguments, ["workspace_id", "path", "content"])
            result = manager.write_file(
                arguments["workspace_id"],
                arguments["path"],
                arguments["content"],
                arguments.get("approval_id"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "edit":
            _require_strings(arguments, ["workspace_id", "path", "find", "replace"])
            result = manager.edit_file(
                arguments["workspace_id"],
                arguments["path"],
                arguments["find"],
                arguments["replace"],
                arguments.get("expected_replacements"),
                arguments.get("approval_id"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "grep":
            result = {"matches": manager.grep(_required_string(arguments, "workspace_id"), _required_string(arguments, "pattern"), arguments.get("path", "."))}
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "glob":
            result = {"paths": manager.glob_paths(_required_string(arguments, "workspace_id"), _required_string(arguments, "pattern"))}
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "bash":
            result = manager.run_bash(
                _required_string(arguments, "workspace_id"),
                _required_string(arguments, "command"),
                arguments.get("cwd", "."),
                arguments.get("timeout_seconds", MAX_COMMAND_SECONDS),
                arguments.get("approval_id"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "list_tasks":
            result = manager.list_tasks(_required_string(arguments, "workspace_id"))
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "run_task":
            result = manager.run_task(
                _required_string(arguments, "workspace_id"),
                _required_string(arguments, "task_name"),
                arguments.get("approval_id"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "set_permission_mode":
            result = manager.set_permission_mode(
                _required_string(arguments, "mode"),
                arguments.get("confirmation", ""),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "permission_mode_status":
            result = manager.permission_mode_status()
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "enable_danger_auto":
            result = manager.enable_danger_auto(_required_string(arguments, "phrase"))
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "danger_auto_status":
            result = manager.danger_auto_status()
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "disable_danger_auto":
            result = manager.disable_danger_auto()
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "grant_action_approval":
            result = manager.grant_action_approval(
                _required_string(arguments, "approval_id"),
                _required_string(arguments, "confirmation"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "request_workspace_access":
            result = manager.request_workspace_access(
                _required_string(arguments, "path"),
                _required_string(arguments, "reason"),
                arguments.get("access", "read"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "grant_workspace_access":
            result = manager.grant_workspace_access(
                _required_string(arguments, "path"),
                arguments.get("access", "read"),
                arguments.get("approval_id"),
            )
            return _tool_result(json.dumps(result, indent=2), result)
        return _tool_error(f"Unknown tool: {name}")
    except ApprovalRequired as exc:
        structured = {"error": "approval_required", "reason": str(exc)}
        structured.update(getattr(exc, "structured", {}) or {})
        return _tool_error(f"Approval required: {exc}", structured)
    except (AccessDenied, WorkspaceNotFound, FileNotFoundError) as exc:
        return _tool_error(f"Access denied: {exc}", {"error": "access_denied", "reason": str(exc)})
    except (ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        return _tool_error(str(exc))


def _initialize_result(
    request: Dict[str, Any], manager: FullAgentWorkspaceManager
) -> Dict[str, Any]:
    requested_version = (request.get("params") or {}).get("protocolVersion")
    protocol_version = (
        requested_version if requested_version == PROTOCOL_VERSION else PROTOCOL_VERSION
    )
    return {
        "protocolVersion": protocol_version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": SERVER_NAME,
            "title": (
                "Agent Decision Bridge Full-Agent"
                if manager.profile == PROFILE_FULL_AGENT
                else (
                    "Agent Decision Bridge Connected Agent"
                    if manager.profile == PROFILE_CONNECTED_AGENT
                    else "Agent Decision Bridge Read-Only Project Advisor"
                )
            ),
            "version": SERVER_VERSION,
            "description": (
                "High-risk local coding MCP server with file and shell tools. "
                "Protected credential-like paths are blocked by default."
                if manager.profile == PROFILE_FULL_AGENT
                else (
                    "Connected Agent MCP server with project tools, approval gates, "
                    "Danger Auto, and protected path filtering."
                    if manager.profile == PROFILE_CONNECTED_AGENT
                    else "Read-only project advisor MCP server with protected path filtering."
                )
            ),
        },
        "instructions": (
            "Full-Agent mode can read, write, edit, search, and run shell commands "
            "inside opened workspaces under configured allowed roots. Risk level is "
            "5/5. Protected credential-like paths are blocked by default, but shell "
            "commands run as the local user, not in a security sandbox."
            if manager.profile == PROFILE_FULL_AGENT
            else (
                "Connected Agent mode can read and search opened workspaces under "
                "configured allowed roots by default. If one allowed root is "
                "configured, call open_default_workspace first to avoid passing a "
                "local absolute path through the web advisor. If the client has a "
                "stale schema without open_default_workspace, call open_workspace "
                "with path exactly \"default\" instead of a /Users/... path. Whole-file "
                "read accepts task-relevant UTF-8 source files up to 1 MB; use "
                "targeted grep plus read_lines for larger source files, and skip "
                "node_modules, build outputs, sourcemaps, image galleries, and "
                "dependency artifacts unless the task explicitly requires them. "
                "Connected Agent exposes two user-facing permission choices: "
                "controlled_auto and danger_auto. The bounded product helper starts in "
                "controlled_auto; low-level direct clients may retain an internal "
                "server approval fallback that is not a user-facing mode. "
                + (
                    "This session uses one host-native confirmation for bounded commits. "
                    "For existing-file whole replacements, show preview_patch then call "
                    "apply_patch once with preview_id. For write, edit, or ordinary "
                    "project-local bash, call prepare_action, show its action/diff, then "
                    "call commit_action once with only action_id. Do not request or grant "
                    "a second approval_id for either bounded path. "
                    if manager.trust_host_confirmation_for_previewed_patches
                    else "In the server approval fallback, apply_patch returns a "
                    "one-action approval_id; "
                    "ask the user to approve that exact patch in chat, call "
                    "grant_action_approval, then retry it once with approval_id. "
                )
                + "Raw write, edit, and bash are legacy compatibility tools and retain "
                "the old one-action approval retry. Do not use that fragile path for "
                "ordinary Controlled Auto work; use prepare_action -> commit_action. "
                "In the low-level server approval fallback, bounded commits and run_task "
                "still require server approval. Do not suggest the "
                f"`{DANGER_AUTO_PHRASE}` phrase for ordinary one-off writes, "
                "edits, or bash commands. That phrase is only a hidden high-risk "
                "automation switch typed by the user. Server policy still blocks "
                "credential paths, network commands, GUI/clipboard commands, "
                "path escapes, Git remote operations, dependency installs, and "
                "broad destructive commands unless explicitly allowed by policy."
                if manager.profile == PROFILE_CONNECTED_AGENT
                else "Read-Only Project Advisor mode can list, read, glob, and grep "
                "opened workspaces under configured allowed roots. It cannot write files "
                "or run shell commands. Protected credential-like paths are blocked."
            )
        ),
        "allowed_roots": [str(root) for root in manager.allowed_roots],
        "temporary_allowed_roots": [str(root) for root in manager.session_allowed_roots],
        "profile": manager.profile,
        "contract_version": TOOL_CONTRACT_VERSION,
        "permission_mode": manager.permission_mode,
        "visible_permission_modes": [
            PERMISSION_CONTROLLED_AUTO,
            PERMISSION_DANGER_AUTO,
        ],
        "server_approval_fallback_active": manager.permission_mode
        == PERMISSION_APPROVAL,
        "previewed_patch_confirmation": manager.previewed_patch_confirmation,
        "prepared_action_confirmation": manager.prepared_action_confirmation,
        "tools": manager.tool_names,
        "risk_level": manager.risk_level,
    }


def _path_tool(name: str, title: str, description: str) -> Dict[str, Any]:
    path_schema: Dict[str, Any] = {"type": "string"}
    if name == "ls":
        path_schema["default"] = "."
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "path": path_schema,
            },
            "required": ["workspace_id", "path"] if name == "read" else ["workspace_id"],
            "additionalProperties": False,
        },
        "annotations": _read_only_annotations(),
    }


def _normalize_optional_workspace_location(value: Any, field_name: str) -> str:
    """Map an omitted or blank optional root path/CWD to the workspace root."""
    if value is None:
        return "."
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value if value.strip() else "."


def _read_only_annotations(*, idempotent: bool = True) -> Dict[str, bool]:
    """Describe tools that do not change the authorized project or outside world."""
    return {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


def _write_annotations(
    *, destructive: bool, idempotent: bool = False
) -> Dict[str, bool]:
    """Describe tools that mutate project data or session authorization state."""
    return {
        "readOnlyHint": False,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


def _required_string(arguments: Dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required string argument: {name}")
    return value


def _required_int(arguments: Dict[str, Any], name: str) -> int:
    value = arguments.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Missing required integer argument: {name}")
    return value


def _optional_int(arguments: Dict[str, Any], name: str) -> Optional[int]:
    value = arguments.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Optional argument must be an integer: {name}")
    return value


def _arguments_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON string for tool arguments: {exc.msg}") from exc
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Tool arguments JSON string must decode to an object")
    raise TypeError("Tool arguments must be an object")


def _require_strings(
    arguments: Dict[str, Any],
    names: List[str],
    allow_empty: Optional[set[str]] = None,
) -> None:
    allowed_empty = allow_empty or set()
    missing = [
        name
        for name in names
        if not isinstance(arguments.get(name), str)
        or (name not in allowed_empty and not arguments.get(name, "").strip())
    ]
    if missing:
        raise ValueError(f"Missing required string argument(s): {', '.join(missing)}")


def _tool_result(text: str, structured: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
        "isError": False,
    }


def _tool_error(message: str, structured: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {"isError": True, "content": [{"type": "text", "text": message}]}
    if structured is not None:
        payload["structuredContent"] = structured
    return payload


def _response(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _action_fingerprint(action: Dict[str, Any]) -> str:
    payload = json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _looks_like_affirmative_confirmation(value: str) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    if not lowered:
        return False
    if _contains_approval_marker(lowered, APPROVAL_REJECTION_MARKERS):
        return False
    return _contains_approval_marker(lowered, APPROVAL_CONFIRMATION_MARKERS)


def _contains_approval_marker(text: str, markers: Iterable[str]) -> bool:
    ascii_tokens = " ".join(
        "".join(char if char.isascii() and char.isalnum() else " " for char in text).split()
    )
    padded_ascii_tokens = f" {ascii_tokens} "
    ascii_words = set(ascii_tokens.split())
    for marker in markers:
        marker_lower = marker.lower()
        if marker_lower.isascii():
            normalized = " ".join(
                "".join(
                    char if char.isascii() and char.isalnum() else " "
                    for char in marker_lower
                ).split()
            )
            if not normalized:
                continue
            if " " in normalized:
                if f" {normalized} " in padded_ascii_tokens:
                    return True
            elif normalized in ascii_words:
                return True
        elif marker_lower in text:
            return True
    return False


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def run_stdio(manager: FullAgentWorkspaceManager, lines: Iterable[str]) -> int:
    for line in lines:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"Parse error: {exc.msg}")
        else:
            response = handle_request(request, manager)
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Connected Agent workspace MCP over stdio.")
    parser.add_argument("--allowed-root", type=Path, action="append", required=True)
    parser.add_argument(
        "--allowed-task",
        action="append",
        default=[],
        metavar="NAME=COMMAND",
        help="Allow one exact local task command for list_tasks/run_task.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(VALID_PROFILES),
        default=PROFILE_FULL_AGENT,
    )
    parser.add_argument(
        "--initial-permission-mode",
        choices=[PERMISSION_APPROVAL, PERMISSION_CONTROLLED_AUTO],
        default=PERMISSION_APPROVAL,
        help=(
            "Initial Connected Agent permission mode. Direct clients default to the "
            "hidden approval fallback; product helpers explicitly choose controlled_auto."
        ),
    )
    parser.add_argument(
        "--trust-host-confirmation-for-previewed-patches",
        action="store_true",
        help=(
            "Treat the MCP host's native write confirmation as the sole user-facing "
            "approval for single-use apply_patch and commit_action calls. Direct "
            "clients default to the server approval_id flow."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    return run_stdio(
        FullAgentWorkspaceManager(
            args.allowed_root,
            profile=args.profile,
            allowed_tasks=parse_allowed_tasks(args.allowed_task),
            trust_host_confirmation_for_previewed_patches=(
                args.trust_host_confirmation_for_previewed_patches
            ),
            initial_permission_mode=args.initial_permission_mode,
        ),
        sys.stdin,
    )


if __name__ == "__main__":
    raise SystemExit(main())
