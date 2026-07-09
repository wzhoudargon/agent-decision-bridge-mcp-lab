#!/usr/bin/env python3
"""Connected Agent MCP backend with explicit workspace roots and approval gates."""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "agent-decision-bridge-connected-agent"
SERVER_VERSION = "0.1.0"
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
    def __init__(self, allowed_roots: List[Path], profile: str = PROFILE_FULL_AGENT):
        if profile not in VALID_PROFILES:
            raise ValueError(f"Unknown workspace profile: {profile}")
        self.profile = profile
        self.allowed_roots = validate_allowed_roots(allowed_roots)
        self.session_allowed_roots: List[Path] = []
        self.workspaces: Dict[str, Path] = {}
        self.danger_auto_enabled = False
        self.session_last_activity = time.time()
        self.pending_action_approvals: Dict[str, Dict[str, Any]] = {}
        self.granted_action_approvals: Dict[str, Dict[str, Any]] = {}

    @property
    def risk_level(self) -> str:
        if self.profile == PROFILE_FULL_AGENT:
            return "5/5"
        if self.profile == PROFILE_CONNECTED_AGENT:
            return "5/5" if self.danger_auto_enabled else "3/5-5/5"
        return "3/5-4/5"

    @property
    def tool_names(self) -> List[str]:
        if self.profile == PROFILE_READ_ONLY_PROJECT:
            return ["open_workspace", "ls", "read", "read_lines", "grep", "glob"]
        if self.profile == PROFILE_CONNECTED_AGENT:
            return [
                "open_default_workspace",
                "open_workspace",
                "ls",
                "read",
                "read_lines",
                "write",
                "edit",
                "grep",
                "glob",
                "bash",
                "enable_danger_auto",
                "danger_auto_status",
                "disable_danger_auto",
                "grant_action_approval",
                "request_workspace_access",
                "grant_workspace_access",
            ]
        return ["open_workspace", "ls", "read", "read_lines", "write", "edit", "grep", "glob", "bash"]

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
                "Connected Agent exposes project read/search tools by default. "
                "Write, edit, and bash require one-action approval by default. "
                "Protected credential-like paths and unsafe commands are blocked "
                "by the server."
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
            "risk_level": self.risk_level,
            "warning": warning,
        }

    def list_directory(self, workspace_id: str, path_value: str = ".") -> List[Dict[str, Any]]:
        self.touch()
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
        cwd_path = self.resolve_workspace_path(workspace_id, cwd, must_exist=True)
        if not cwd_path.is_dir():
            raise AccessDenied("bash cwd must be a directory")
        self._assert_not_protected(cwd_path)
        if self.profile == PROFILE_CONNECTED_AGENT:
            self._assert_connected_bash_allowed(command)
            action = {
                "tool_name": "bash",
                "workspace_id": workspace_id,
                "cwd": self.relative_path(workspace_id, cwd_path),
                "command": command,
                "timeout_seconds": timeout,
            }
            self._require_connected_action_approval("bash", action, approval_id)
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

    def enable_danger_auto(self, phrase: str) -> Dict[str, Any]:
        self._require_connected_agent_tool("enable_danger_auto")
        self.touch()
        if phrase.strip() != DANGER_AUTO_PHRASE:
            raise AccessDenied(
                "Danger Auto phrase was not accepted. The user must type the exact phrase."
            )
        self.danger_auto_enabled = True
        self.session_last_activity = time.time()
        return self.danger_auto_status()

    def danger_auto_status(self) -> Dict[str, Any]:
        self._require_connected_agent_tool("danger_auto_status")
        self._expire_idle_session()
        remaining = max(0, int(DANGER_AUTO_IDLE_SECONDS - (time.time() - self.session_last_activity)))
        return {
            "profile": self.profile,
            "danger_auto_enabled": self.danger_auto_enabled,
            "risk_level": "5/5" if self.danger_auto_enabled else "3/5-5/5",
            "idle_timeout_seconds": DANGER_AUTO_IDLE_SECONDS,
            "seconds_until_idle_close": remaining,
            "temporary_allowed_roots": [str(root) for root in self.session_allowed_roots],
            "pending_action_approvals": len(self.pending_action_approvals),
            "granted_action_approvals": len(self.granted_action_approvals),
            "danger_phrase": DANGER_AUTO_PHRASE,
        }

    def disable_danger_auto(self) -> Dict[str, Any]:
        self._require_connected_agent_tool("disable_danger_auto")
        self.touch()
        self.danger_auto_enabled = False
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

    def grant_workspace_access(self, path_value: str, access: str = "read") -> Dict[str, Any]:
        self._require_connected_agent_tool("grant_workspace_access")
        self.touch()
        requested = self._resolve_grantable_root(path_value)
        if not any(_is_relative_to(requested, root) for root in self.allowed_roots + self.session_allowed_roots):
            self.session_allowed_roots.append(requested)
        return {
            "status": "granted",
            "path": str(requested),
            "access": self._normalize_access(access),
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
    ) -> None:
        if self.profile != PROFILE_CONNECTED_AGENT or self.danger_auto_enabled:
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

    def _assert_connected_bash_allowed(self, command: str) -> None:
        self._assert_bash_command_allowed(command)
        lowered = command.lower()
        if "http://" in lowered or "https://" in lowered:
            raise AccessDenied("Connected Agent blocks bash commands that reference network URLs")
        if any(marker in lowered for marker in ("$home", "${home}", "~/", " ~", "../", "/..")):
            raise AccessDenied("Connected Agent blocks bash commands with obvious path escape markers")
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            raise ApprovalRequired(f"bash command needs explicit approval: could not parse shell tokens ({exc})") from exc
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
        if self.danger_auto_enabled:
            if command_names.intersection(APPROVAL_COMMANDS):
                raise ApprovalRequired(
                    "The hidden danger switch still requires explicit one-action approval for deletion, moves, permission changes, or privileged commands"
                )
            if self._needs_install_approval(lowered_tokens):
                raise ApprovalRequired("The hidden danger switch still requires explicit one-action approval before installing dependencies")
            if self._needs_git_remote_approval(lowered_tokens):
                raise ApprovalRequired("The hidden danger switch still requires explicit one-action approval for Git remote operations")
            if "-delete" in lowered_tokens:
                raise ApprovalRequired("The hidden danger switch still requires explicit one-action approval for find -delete style operations")
        for token in tokens:
            path_token = token.strip("'\"")
            if not path_token.startswith("/"):
                continue
            resolved = Path(path_token).expanduser().resolve(strict=False)
            if not any(_is_relative_to(resolved, root) for root in self._current_allowed_roots()):
                raise AccessDenied(
                    "Connected Agent blocks bash commands that reference absolute paths outside allowed roots"
                )

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
            return
        self.danger_auto_enabled = False
        self.session_allowed_roots.clear()
        self.pending_action_approvals.clear()
        self.granted_action_approvals.clear()

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
                    "path": {"type": "string"},
                },
                "required": ["workspace_id", "pattern"],
                "additionalProperties": False,
            },
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
        },
    ]
    if profile == PROFILE_READ_ONLY_PROJECT:
        return base_tools + search_tools
    execution_tools = [
        {
            "name": "write",
            "title": "Write File",
            "description": "Write a UTF-8 file in an opened workspace.",
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
        },
        {
            "name": "edit",
            "title": "Edit File",
            "description": "Replace exact text in a UTF-8 file in an opened workspace.",
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
        },
    ]
    bash_tool = {
        "name": "bash",
        "title": "Run Bash",
        "description": (
            "Run a shell command in an opened workspace. This is not a sandbox; "
            "commands run with the local user account."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
                "approval_id": {"type": "string"},
            },
            "required": ["workspace_id", "command"],
            "additionalProperties": False,
        },
    }
    connected_tools = [
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
        },
        {
            "name": "grant_action_approval",
            "title": "Grant Action Approval",
            "description": (
                "Grant one pending write/edit/bash action after the user clearly "
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
        },
        {
            "name": "grant_workspace_access",
            "title": "Grant Workspace Access",
            "description": (
                "Temporarily add a confirmed project directory to this session's "
                "allowed roots. Use only after the user confirms in chat."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "access": {"type": "string", "enum": ["read", "write", "execute"]},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    ]
    if profile == PROFILE_CONNECTED_AGENT:
        return base_tools + execution_tools + search_tools + [bash_tool] + connected_tools
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
                "dependency artifacts unless the task explicitly requires them. In default mode, "
                "write, edit, and bash return a one-action approval_id; ask the "
                "user to approve that exact action in chat, call "
                "grant_action_approval, then retry the original tool call once "
                "with approval_id. Do not suggest the "
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
        "risk_level": manager.risk_level,
    }


def _path_tool(name: str, title: str, description: str) -> Dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["workspace_id", "path"] if name == "read" else ["workspace_id"],
            "additionalProperties": False,
        },
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


def _require_strings(arguments: Dict[str, Any], names: List[str]) -> None:
    missing = [
        name
        for name in names
        if not isinstance(arguments.get(name), str) or not arguments.get(name, "").strip()
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
        "--profile",
        choices=sorted(VALID_PROFILES),
        default=PROFILE_FULL_AGENT,
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    return run_stdio(FullAgentWorkspaceManager(args.allowed_root, profile=args.profile), sys.stdin)


if __name__ == "__main__":
    raise SystemExit(main())
