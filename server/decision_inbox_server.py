#!/usr/bin/env python3
"""Minimal Decision Inbox MCP v1 server over stdio JSON-RPC."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from server.decision_inbox_store import (
        AccessDenied,
        DecisionInboxError,
        DecisionInboxStore,
        TaskNotFound,
        default_tasks_root,
    )
except ModuleNotFoundError:
    from decision_inbox_store import (  # type: ignore
        AccessDenied,
        DecisionInboxError,
        DecisionInboxStore,
        TaskNotFound,
        default_tasks_root,
    )


PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "agent-decision-bridge-decision-inbox"
SERVER_VERSION = "0.1.0"
AUTO_MCP_TOOL_NAMES = [
    "list_decision_tasks",
    "get_decision_package",
    "submit_advice",
    "get_task_status",
]


def tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "name": "list_decision_tasks",
            "title": "List Decision Tasks",
            "description": "List package-only decision tasks and safe metadata fields.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "get_decision_package",
            "title": "Get Decision Package",
            "description": "Read package.md for one decision task.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Decision task id.",
                    }
                },
                "required": ["task_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "submit_advice",
            "title": "Submit Advice",
            "description": (
                "Write advisor Markdown under the task advice/ folder. The content "
                "must explicitly state that external advice is not authorization."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "advisor": {
                        "type": "string",
                        "description": "Stable advisor identifier, for example chatgpt-pro-review.",
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Complete advice Markdown. Must include a clear marker such as "
                            "'External advice only; this is not authorization.'"
                        ),
                    },
                    "timestamp": {
                        "type": "string",
                        "description": "Optional deterministic timestamp YYYY-MM-DDTHH-MM-SSZ.",
                    },
                },
                "required": ["task_id", "advisor", "content"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_task_status",
            "title": "Get Task Status",
            "description": "Read task metadata and count advice/fact-check files.",
            "inputSchema": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
                "additionalProperties": False,
            },
        },
    ]


def handle_request(
    request: Dict[str, Any], store: DecisionInboxStore
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
            return _response(request_id, _call_tool(request.get("params") or {}, store))
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
            "title": "Agent Decision Bridge Auto MCP Controlled Advisor",
            "version": SERVER_VERSION,
            "description": "Package-only MCP server for decision package exchange.",
        },
        "instructions": (
            "This Auto MCP Controlled Advisor exposes only decision packages, advisor "
            "writeback, and task status. It cannot read real projects, write outside "
            "decision-inbox/tasks, run shell commands, inspect Git, install "
            "dependencies, request local fact checks, or authorize execution."
        ),
    }


def _call_tool(params: Dict[str, Any], store: DecisionInboxStore) -> Dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    try:
        if name == "list_decision_tasks":
            tasks = store.list_decision_tasks()
            return _tool_result(
                text=json.dumps({"tasks": tasks}, indent=2, ensure_ascii=False),
                structured={"tasks": tasks},
            )
        if name == "get_decision_package":
            task_id = _required_string(arguments, "task_id")
            package = store.get_decision_package(task_id)
            return _tool_result(
                text=package,
                structured={"task_id": task_id, "package": package},
            )
        if name == "submit_advice":
            _require_strings(arguments, ["task_id", "advisor", "content"])
            result = store.submit_advice(
                task_id=arguments["task_id"],
                advisor=arguments["advisor"],
                content=arguments["content"],
                timestamp=arguments.get("timestamp"),
            )
            return _tool_result(
                text=f"Advice stored at {result['relative_path']}",
                structured=result,
            )
        if name == "get_task_status":
            task_id = _required_string(arguments, "task_id")
            status = store.get_task_status(task_id)
            return _tool_result(
                text=json.dumps(status, indent=2, ensure_ascii=False),
                structured=status,
            )
        return _tool_error(f"Unknown tool: {name}")
    except AccessDenied as exc:
        return _tool_error(f"Access denied: {exc}")
    except TaskNotFound as exc:
        return _tool_error(f"Task not found: {exc}")
    except (DecisionInboxError, FileExistsError, ValueError, TypeError) as exc:
        return _tool_error(str(exc))


def _required_string(arguments: Dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required string argument: {name}")
    return value


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


def run_stdio(store: DecisionInboxStore, lines: Iterable[str]) -> int:
    for line in lines:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"Parse error: {exc.msg}")
        else:
            response = handle_request(request, store)
        if response is not None:
            print(json.dumps(response, separators=(",", ":"), ensure_ascii=False), flush=True)
    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Decision Inbox MCP v1 server over stdio."
    )
    parser.add_argument(
        "--tasks-root",
        type=Path,
        default=default_tasks_root(),
        help="Decision inbox tasks root. Defaults to decision-inbox/tasks.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    store = DecisionInboxStore(args.tasks_root)
    return run_stdio(store, sys.stdin)


if __name__ == "__main__":
    raise SystemExit(main())
