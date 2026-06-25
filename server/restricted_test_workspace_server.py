#!/usr/bin/env python3
"""Minimal read-only MCP server for Phase 1 synthetic workspace testing."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "agent-decision-bridge-synthetic-workspace"
SERVER_VERSION = "0.1.0"


class AccessDenied(Exception):
    """Raised when a requested path is outside the synthetic allowlist."""


class RestrictedWorkspace:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError(f"Workspace root is not a directory: {root}")

    def list_files(self) -> List[str]:
        return sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_file() and not path.name.startswith(".")
        )

    def read_file(self, requested_path: str) -> str:
        resolved = self._resolve_allowed_file(requested_path)
        if not resolved.exists():
            raise FileNotFoundError(Path(requested_path).name)
        if not resolved.is_file():
            raise AccessDenied("Only regular files in the synthetic root are allowed")
        return resolved.read_text(encoding="utf-8")

    def _resolve_allowed_file(self, requested_path: str) -> Path:
        if not isinstance(requested_path, str) or not requested_path.strip():
            raise AccessDenied("Path must be a non-empty string")
        if "\x00" in requested_path or "\\" in requested_path:
            raise AccessDenied("Path contains unsupported characters")

        raw = Path(requested_path)
        if raw.is_absolute():
            raise AccessDenied("Absolute paths are not allowed")
        if any(part in ("", ".", "..") or part.startswith(".") for part in raw.parts):
            raise AccessDenied("Hidden paths and parent-directory traversal are not allowed")
        if len(raw.parts) != 1:
            raise AccessDenied("Only files directly under the synthetic root are allowed")

        resolved = (self.root / raw).resolve(strict=False)
        if resolved.parent != self.root:
            raise AccessDenied("Path escapes the synthetic root")
        return resolved


def tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "name": "list_synthetic_files",
            "title": "List Synthetic Files",
            "description": "List read-only files available in the synthetic test workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "read_synthetic_file",
            "title": "Read Synthetic File",
            "description": "Read one allowlisted synthetic file by file name.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File name under the synthetic workspace root.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    ]


def handle_request(
    request: Dict[str, Any], workspace: RestrictedWorkspace
) -> Optional[Dict[str, Any]]:
    request_id = request.get("id")
    method = request.get("method")

    try:
        if method == "initialize":
            return _response(request_id, _initialize_result(request))
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return _response(request_id, {"tools": tool_definitions()})
        if method == "tools/call":
            return _response(request_id, _call_tool(request.get("params") or {}, workspace))
        return _error(request_id, -32601, f"Method not found: {method}")
    except Exception as exc:
        return _error(request_id, -32603, f"Internal error: {exc}")


def _initialize_result(request: Dict[str, Any]) -> Dict[str, Any]:
    requested_version = (request.get("params") or {}).get("protocolVersion")
    protocol_version = (
        requested_version if requested_version == PROTOCOL_VERSION else PROTOCOL_VERSION
    )
    return {
        "protocolVersion": protocol_version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": SERVER_NAME,
            "title": "Agent Decision Bridge Synthetic Workspace",
            "version": SERVER_VERSION,
            "description": "Read-only MCP server for synthetic Phase 1 access tests.",
        },
        "instructions": (
            "This server exposes only synthetic test files. It cannot read real "
            "projects, write files, run shell commands, inspect Git, or install "
            "dependencies."
        ),
    }


def _call_tool(params: Dict[str, Any], workspace: RestrictedWorkspace) -> Dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}

    if name == "list_synthetic_files":
        files = workspace.list_files()
        return _tool_result(
            text="\n".join(files),
            structured={"files": files},
        )

    if name == "read_synthetic_file":
        path = arguments.get("path")
        try:
            content = workspace.read_file(path)
        except AccessDenied as exc:
            return _tool_error(f"Access denied: {exc}")
        except FileNotFoundError:
            return _tool_error(f"File not found: {Path(str(path)).name}")
        return _tool_result(
            text=content,
            structured={"path": path, "content": content},
        )

    return _tool_error(f"Unknown tool: {name}")


def _tool_result(text: str, structured: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
    }


def _tool_error(message: str) -> Dict[str, Any]:
    return {
        "isError": True,
        "content": [{"type": "text", "text": message}],
    }


def _response(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def run_stdio(workspace: RestrictedWorkspace, lines: Iterable[str]) -> int:
    for line in lines:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"Parse error: {exc.msg}")
        else:
            response = handle_request(request, workspace)
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0


def default_workspace_root() -> Path:
    return Path(__file__).resolve().parents[1] / "test-workspace" / "synthetic-project"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Phase 1 synthetic read-only MCP server over stdio."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_workspace_root(),
        help="Synthetic workspace root. Defaults to test-workspace/synthetic-project.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    workspace = RestrictedWorkspace(args.root)
    return run_stdio(workspace, sys.stdin)


if __name__ == "__main__":
    raise SystemExit(main())
