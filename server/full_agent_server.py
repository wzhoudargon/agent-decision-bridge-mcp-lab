#!/usr/bin/env python3
"""Full-Agent MCP backend with explicit workspace roots and shell access."""

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "agent-decision-bridge-full-agent"
SERVER_VERSION = "0.1.0"
MAX_COMMAND_SECONDS = 30
MAX_COMMAND_OUTPUT_BYTES = 200_000
MAX_READ_FILE_BYTES = 200_000
PROFILE_FULL_AGENT = "full-agent"
PROFILE_READ_ONLY_PROJECT = "read-only-project"
VALID_PROFILES = {PROFILE_FULL_AGENT, PROFILE_READ_ONLY_PROJECT}
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


class AccessDenied(Exception):
    """Raised when a request escapes the configured Full-Agent boundary."""


class WorkspaceNotFound(Exception):
    """Raised when a workspace id has not been opened."""


class FullAgentWorkspaceManager:
    def __init__(self, allowed_roots: List[Path], profile: str = PROFILE_FULL_AGENT):
        if profile not in VALID_PROFILES:
            raise ValueError(f"Unknown workspace profile: {profile}")
        self.profile = profile
        self.allowed_roots = validate_allowed_roots(allowed_roots)
        self.workspaces: Dict[str, Path] = {}

    @property
    def risk_level(self) -> str:
        return "5/5" if self.profile == PROFILE_FULL_AGENT else "3/5-4/5"

    @property
    def tool_names(self) -> List[str]:
        if self.profile == PROFILE_READ_ONLY_PROJECT:
            return ["open_workspace", "ls", "read", "grep", "glob"]
        return ["open_workspace", "ls", "read", "write", "edit", "grep", "glob", "bash"]

    def open_workspace(self, path_value: str) -> Dict[str, Any]:
        requested = self._resolve_requested_workspace(path_value)
        workspace_id = f"ws-{uuid.uuid4().hex}"
        self.workspaces[workspace_id] = requested
        if self.profile == PROFILE_READ_ONLY_PROJECT:
            warning = (
                "Read-Only Project Advisor mode exposes project listing, reading, "
                "glob, and grep only. It cannot write files or run shell commands. "
                "Protected credential-like paths are blocked by the server."
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
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not target.is_file():
            raise AccessDenied("read target must be a file")
        self._assert_read_allowed(target)
        if target.stat().st_size > MAX_READ_FILE_BYTES:
            raise AccessDenied("read target is too large for advisor exposure")
        return target.read_text(encoding="utf-8")

    def write_file(self, workspace_id: str, path_value: str, content: str) -> Dict[str, Any]:
        self._require_full_agent_tool("write")
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=False)
        self._assert_not_protected(target)
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
    ) -> Dict[str, Any]:
        self._require_full_agent_tool("edit")
        target = self.resolve_workspace_path(workspace_id, path_value, must_exist=True)
        if not target.is_file():
            raise AccessDenied("edit target must be a file")
        self._assert_not_protected(target)
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
    ) -> Dict[str, Any]:
        self._require_full_agent_tool("bash")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be a non-empty string")
        timeout = max(1, min(int(timeout_seconds), MAX_COMMAND_SECONDS))
        cwd_path = self.resolve_workspace_path(workspace_id, cwd, must_exist=True)
        if not cwd_path.is_dir():
            raise AccessDenied("bash cwd must be a directory")
        self._assert_not_protected(cwd_path)
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
        requested = Path(path_value).expanduser().resolve(strict=True)
        if not requested.is_dir():
            raise AccessDenied("workspace path must be a directory")
        if not any(_is_relative_to(requested, root) for root in self.allowed_roots):
            raise AccessDenied("workspace path is outside configured allowed roots")
        return requested

    def _assert_under_workspace(self, workspace: Path, path: Path) -> None:
        if not _is_relative_to(path, workspace):
            raise AccessDenied("path escapes the opened workspace")

    def _require_full_agent_tool(self, tool_name: str) -> None:
        if self.profile != PROFILE_FULL_AGENT:
            raise AccessDenied(f"{tool_name} is not available in read-only-project mode")

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


def validate_allowed_roots(roots: List[Path]) -> List[Path]:
    if not roots:
        raise ValueError("Full-Agent mode requires at least one --allowed-root")
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
    base_tools = [
        {
            "name": "open_workspace",
            "title": "Open Workspace",
            "description": "Open a configured allowed-root workspace and return a workspace_id.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        _path_tool("ls", "List Directory", "List files and directories in an opened workspace."),
        _path_tool("read", "Read File", "Read a UTF-8 file in an opened workspace."),
    ]
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
            },
            "required": ["workspace_id", "command"],
            "additionalProperties": False,
        },
    }
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
            return _tool_result(content, {"content": content, "path": arguments["path"]})
        if name == "write":
            _require_strings(arguments, ["workspace_id", "path", "content"])
            result = manager.write_file(arguments["workspace_id"], arguments["path"], arguments["content"])
            return _tool_result(json.dumps(result, indent=2), result)
        if name == "edit":
            _require_strings(arguments, ["workspace_id", "path", "find", "replace"])
            result = manager.edit_file(
                arguments["workspace_id"],
                arguments["path"],
                arguments["find"],
                arguments["replace"],
                arguments.get("expected_replacements"),
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
            )
            return _tool_result(json.dumps(result, indent=2), result)
        return _tool_error(f"Unknown tool: {name}")
    except (AccessDenied, WorkspaceNotFound, FileNotFoundError) as exc:
        return _tool_error(f"Access denied: {exc}")
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
                else "Agent Decision Bridge Read-Only Project Advisor"
            ),
            "version": SERVER_VERSION,
            "description": (
                "High-risk local coding MCP server with file and shell tools. "
                "Protected credential-like paths are blocked by default."
                if manager.profile == PROFILE_FULL_AGENT
                else "Read-only project advisor MCP server with protected path filtering."
            ),
        },
        "instructions": (
            "Full-Agent mode can read, write, edit, search, and run shell commands "
            "inside opened workspaces under configured allowed roots. Risk level is "
            "5/5. Protected credential-like paths are blocked by default, but shell "
            "commands run as the local user, not in a security sandbox."
            if manager.profile == PROFILE_FULL_AGENT
            else "Read-Only Project Advisor mode can list, read, glob, and grep "
            "opened workspaces under configured allowed roots. It cannot write files "
            "or run shell commands. Protected credential-like paths are blocked."
        ),
        "allowed_roots": [str(root) for root in manager.allowed_roots],
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


def _tool_error(message: str) -> Dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def _response(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


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
    parser = argparse.ArgumentParser(description="Run Full-Agent MCP over stdio.")
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
