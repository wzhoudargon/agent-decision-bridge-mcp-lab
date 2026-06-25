#!/usr/bin/env python3
"""Preflight checks for Agent Decision Bridge MCP connectors.

This script is intentionally read-only. It does not start tunnels, change
ChatGPT connector settings, or print secret token values.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.decision_inbox_http_server import (  # noqa: E402
    DEFAULT_FULL_AGENT_STATE_FILE,
    MODE_AUTO_MCP,
    MODE_FULL_AGENT,
    MODE_READ_ONLY_PROJECT,
    VALID_MODES,
    normalize_mode,
    normalize_public_base_url,
    public_mcp_url,
)
from server.decision_inbox_server import AUTO_MCP_TOOL_NAMES  # noqa: E402


DEFAULT_LOCAL_MCP_URL = "http://127.0.0.1:8765/mcp"
DEFAULT_TOKEN_FILE = Path("/tmp/decision-inbox-mcp-token")
DEFAULT_AUTO_MCP_STATE_FILE = Path.home() / ".local/share/decision-inbox-mcp-lab/oauth-state.json"
FULL_AGENT_TOOL_NAMES = [
    "open_workspace",
    "ls",
    "read",
    "write",
    "edit",
    "grep",
    "glob",
    "bash",
]
READ_ONLY_PROJECT_TOOL_NAMES = [
    "open_workspace",
    "ls",
    "read",
    "grep",
    "glob",
]
DISALLOWED_AUTO_MCP_TOOLS = {
    "request_local_fact_check",
    "open_workspace",
    "read",
    "write",
    "edit",
    "grep",
    "glob",
    "ls",
    "bash",
    "run_shell",
    "git",
    "install_dependencies",
}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run read-only preflight checks before using a ChatGPT MCP connector."
    )
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default=os.environ.get("AGENT_BRIDGE_MODE", MODE_AUTO_MCP),
    )
    parser.add_argument("--local-url", default=DEFAULT_LOCAL_MCP_URL)
    parser.add_argument(
        "--public-base-url",
        default=os.environ.get("DECISION_INBOX_PUBLIC_BASE_URL"),
        help="Public HTTPS origin, without /mcp.",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help="Explicit public MCP URL. Prefer --public-base-url for normal runs.",
    )
    parser.add_argument("--task-id", default=None)
    parser.add_argument(
        "--token-env",
        default="DECISION_INBOX_MCP_TOKEN",
        help="Bearer-token environment variable. The value is never printed.",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_FILE,
        help="Bearer-token file. The value is never printed.",
    )
    parser.add_argument(
        "--oauth-state-file",
        type=Path,
        default=None,
        help="OAuth state file to inspect for a non-expired access token. Token values are never printed.",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--require-public",
        action="store_true",
        help="Fail if no public MCP URL is configured.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        lines, ok = build_report(args)
    except ValueError as exc:
        print("Current state: preflight_failed")
        print("Risk coefficient: 4/5")
        print(f"Config error: {exc}")
        return 2
    print("\n".join(lines))
    return 0 if ok else 1


def build_report(args: argparse.Namespace) -> Tuple[List[str], bool]:
    mode = normalize_mode(args.mode)
    expected_scope = expected_oauth_scope(mode)
    expected_tools = expected_tool_names(mode)
    risk = risk_coefficient(mode)
    public_url = resolve_public_mcp_url(args.public_base_url, args.mcp_url)
    oauth_state_file = args.oauth_state_file or default_oauth_state_file(mode)
    token, token_source = load_bearer_token(args.token_env, args.token_file)
    if not token:
        token, token_source = load_oauth_access_token(oauth_state_file, expected_scope)

    lines = [
        "Current state: preflight",
        f"Mode: {mode}",
        f"Expected connector scope: {expected_scope}",
        f"Expected connector tools: {', '.join(expected_tools)}",
        f"Risk coefficient if public window is open: {risk}/5",
        f"Local MCP URL: {args.local_url}",
        f"Public MCP URL: {public_url or 'none'}",
        f"Authenticated tool probe credential: {credential_status(token, token_source)}",
    ]
    failures: List[str] = []

    local_status = probe_unauthenticated_mcp(args.local_url, expected_scope, args.timeout)
    lines.append(f"Local unauthenticated MCP challenge: {local_status}")
    if not local_status.startswith("ok "):
        failures.append("local MCP endpoint is not reachable or not challenging as expected")

    if args.require_public and not public_url:
        failures.append("public MCP URL is required but not configured")

    if public_url:
        metadata_status = probe_public_metadata(public_url, expected_scope, args.timeout)
        lines.append(f"Public OAuth metadata: {metadata_status}")
        if not metadata_status.startswith("ok "):
            failures.append("public OAuth metadata is not reachable")

        public_status = probe_unauthenticated_mcp(public_url, expected_scope, args.timeout)
        lines.append(f"Public unauthenticated MCP challenge: {public_status}")
        if not public_status.startswith("ok "):
            failures.append("public MCP endpoint is not reachable or not challenging as expected")
    else:
        lines.append("Public OAuth metadata: skipped_no_public_url")
        lines.append("Public unauthenticated MCP challenge: skipped_no_public_url")

    tool_probe_url = public_url or args.local_url
    if token:
        tool_status, tool_names = probe_tools(tool_probe_url, token, expected_tools, args.timeout)
        lines.append(f"Authenticated tools/list: {tool_status}")
        if tool_names:
            lines.append(f"Observed tools: {', '.join(tool_names)}")
        if not tool_status.startswith("ok "):
            observed = ", ".join(tool_names) if tool_names else "none"
            failures.append(
                "authenticated tools/list did not match the expected connector surface"
                f" ({tool_status}; observed={observed})"
            )
        if mode == MODE_AUTO_MCP:
            disallowed = sorted(DISALLOWED_AUTO_MCP_TOOLS.intersection(tool_names))
            if disallowed:
                lines.append(f"Auto MCP disallowed tool check: failed found={', '.join(disallowed)}")
                failures.append("Auto MCP exposes disallowed execution or fact-check tools")
            else:
                lines.append("Auto MCP disallowed tool check: ok none_found")
        if args.task_id and tool_status.startswith("ok "):
            status_check = probe_task(tool_probe_url, token, args.task_id, args.timeout)
            lines.append(f"Task package/status probe: {status_check}")
            if not status_check.startswith("ok "):
                failures.append("task package/status probe failed")
    else:
        lines.append("Authenticated tools/list: skipped_no_bearer_or_oauth_access_token")
        if mode == MODE_AUTO_MCP:
            lines.append("Auto MCP disallowed tool check: skipped_no_authenticated_tools_probe")
        if args.task_id:
            lines.append("Task package/status probe: skipped_no_authenticated_tools_probe")

    if failures:
        lines.append("Preflight result: failed")
        for item in failures:
            lines.append(f"- {item}")
        return lines, False

    lines.append("Preflight result: ok")
    return lines, True


def resolve_public_mcp_url(public_base_url: Optional[str], mcp_url: Optional[str]) -> Optional[str]:
    if public_base_url:
        return public_mcp_url(normalize_public_base_url(public_base_url))
    if not mcp_url:
        return None
    parsed = urlparse(mcp_url.strip())
    if parsed.scheme != "https":
        raise ValueError("Public MCP URL must use https")
    if parsed.path.rstrip("/") != "/mcp":
        raise ValueError("Public MCP URL must end with /mcp")
    if parsed.query or parsed.fragment:
        raise ValueError("Public MCP URL must not include query strings or fragments")
    return mcp_url.strip().rstrip("/")


def default_oauth_state_file(mode: str) -> Path:
    if mode in {MODE_READ_ONLY_PROJECT, MODE_FULL_AGENT}:
        return DEFAULT_FULL_AGENT_STATE_FILE
    return DEFAULT_AUTO_MCP_STATE_FILE


def expected_oauth_scope(mode: str) -> str:
    if mode == MODE_FULL_AGENT:
        return "full-agent"
    if mode == MODE_READ_ONLY_PROJECT:
        return "read-only-project"
    return "decision-inbox"


def expected_tool_names(mode: str) -> List[str]:
    if mode == MODE_FULL_AGENT:
        return FULL_AGENT_TOOL_NAMES
    if mode == MODE_READ_ONLY_PROJECT:
        return READ_ONLY_PROJECT_TOOL_NAMES
    return AUTO_MCP_TOOL_NAMES


def risk_coefficient(mode: str) -> str:
    if mode == MODE_FULL_AGENT:
        return "5"
    if mode == MODE_READ_ONLY_PROJECT:
        return "3-4"
    return "3"


def load_bearer_token(env_name: str, token_file: Optional[Path]) -> Tuple[Optional[str], str]:
    env_token = os.environ.get(env_name, "").strip()
    if env_token:
        return env_token, f"env:{env_name}"
    if token_file and token_file.expanduser().is_file():
        token = token_file.expanduser().read_text(encoding="utf-8").strip()
        if token:
            return token, f"file:{token_file.expanduser()}"
    return None, "none"


def load_oauth_access_token(state_file: Optional[Path], expected_scope: str) -> Tuple[Optional[str], str]:
    if not state_file or not state_file.expanduser().is_file():
        return None, "none"
    path = state_file.expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, f"oauth_state_unreadable:{path}"
    tokens = payload.get("oauth_access_tokens")
    if not isinstance(tokens, dict):
        return None, f"oauth_state_no_access_tokens:{path}"
    now = time.time()
    for token, record in tokens.items():
        if not isinstance(token, str) or not isinstance(record, dict):
            continue
        scopes = record.get("scopes") or []
        expires_at = record.get("expires_at")
        if expected_scope in scopes and isinstance(expires_at, (int, float)) and expires_at > now:
            return token, f"oauth_state_access_token:{path}"
    return None, f"oauth_state_no_valid_access_token:{path}"


def credential_status(token: Optional[str], source: str) -> str:
    if not token:
        return f"absent source={source}"
    return f"present source={source} length={len(token)} value=redacted"


def probe_public_metadata(mcp_url: str, expected_scope: str, timeout: float) -> str:
    origin = origin_from_mcp_url(mcp_url)
    protected_status, _, protected_body = http_request(
        "GET", f"{origin}/.well-known/oauth-protected-resource/mcp", None, None, timeout
    )
    if protected_status != 200:
        return f"failed protected_resource_status={protected_status}{error_detail(protected_body)}"
    oauth_status, _, oauth_body = http_request(
        "GET", f"{origin}/.well-known/oauth-authorization-server", None, None, timeout
    )
    if oauth_status != 200:
        return f"failed authorization_server_status={oauth_status}{error_detail(oauth_body)}"
    try:
        protected = json.loads(protected_body.decode("utf-8"))
        oauth = json.loads(oauth_body.decode("utf-8"))
    except json.JSONDecodeError:
        return "failed invalid_json_metadata"
    scopes = protected.get("scopes_supported") or oauth.get("scopes_supported") or []
    if expected_scope not in scopes:
        return f"failed expected_scope_missing scope={expected_scope}"
    resource = protected.get("resource", "")
    if not isinstance(resource, str) or not resource.endswith("/mcp"):
        return "failed protected_resource_not_mcp"
    return f"ok scope={expected_scope}"


def probe_unauthenticated_mcp(mcp_url: str, expected_scope: str, timeout: float) -> str:
    status, headers, body = http_request(
        "POST",
        mcp_url,
        {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout,
    )
    if status == 401:
        challenge = headers.get("www-authenticate", "")
        if expected_scope in challenge:
            return f"ok oauth_challenge scope={expected_scope}"
        if "Bearer" in challenge:
            return "ok bearer_challenge"
        return "failed missing_bearer_challenge"
    if status == 200:
        return "failed unprotected_200"
    return f"failed http_status={status}{error_detail(body)}"


def probe_tools(
    mcp_url: str,
    token: str,
    expected_tools: List[str],
    timeout: float,
) -> Tuple[str, List[str]]:
    status, _, body = http_request(
        "POST",
        mcp_url,
        {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
            "MCP-Protocol-Version": "2025-11-25",
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        timeout,
    )
    if status != 200:
        return f"failed http_status={status}", []
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return "failed invalid_json_response", []
    tools = payload.get("result", {}).get("tools")
    if not isinstance(tools, list):
        return "failed missing_tools", []
    names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
    names = [name for name in names if isinstance(name, str)]
    if names != expected_tools:
        return "failed tool_allowlist_mismatch", names
    return "ok expected_allowlist", names


def probe_task(mcp_url: str, token: str, task_id: str, timeout: float) -> str:
    for name in ("get_task_status", "get_decision_package"):
        status, _, body = http_request(
            "POST",
            mcp_url,
            {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {token}",
                "MCP-Protocol-Version": "2025-11-25",
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": {"task_id": task_id}},
            },
            timeout,
        )
        if status != 200:
            return f"failed {name} http_status={status}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return f"failed {name} invalid_json_response"
        result = payload.get("result", {})
        if result.get("isError"):
            text = (result.get("content") or [{}])[0].get("text", "unknown")
            return f"failed {name} tool_error={text}"
    return f"ok task_id={task_id}"


def http_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]],
    json_payload: Optional[Dict[str, Any]],
    timeout: float,
) -> Tuple[int, Dict[str, str], bytes]:
    data = None if json_payload is None else json.dumps(json_payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers=headers or {})
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, lower_headers(dict(response.headers.items())), response.read()
    except HTTPError as exc:
        return exc.code, lower_headers(dict(exc.headers.items())), exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        fallback = curl_fallback_request(method, url, headers, data, timeout)
        if fallback is not None:
            return fallback
        return 0, {}, f"{exc.__class__.__name__}: {exc}".encode("utf-8", errors="replace")


def curl_fallback_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]],
    data: Optional[bytes],
    timeout: float,
) -> Optional[Tuple[int, Dict[str, str], bytes]]:
    if not url.startswith("https://"):
        return None
    if not curl_fallback_is_safe(headers):
        return None
    if not shutil.which("curl"):
        return None
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--include",
        "--max-time",
        str(max(1.0, timeout)),
        "-X",
        method,
    ]
    for key, value in (headers or {}).items():
        command.extend(["-H", f"{key}: {value}"])
    if data is not None:
        command.extend(["--data-binary", "@-"])
    command.append(url)
    try:
        completed = subprocess.run(
            command,
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=network_direct_env(),
            check=False,
        )
    except OSError as exc:
        return 0, {}, f"{exc.__class__.__name__}: {exc}".encode("utf-8", errors="replace")
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        return 0, {}, f"curl exit {completed.returncode}: {error}".encode(
            "utf-8", errors="replace"
        )
    return parse_curl_response(completed.stdout)


def curl_fallback_is_safe(headers: Optional[Dict[str, str]]) -> bool:
    for key in (headers or {}):
        if key.lower() == "authorization":
            return False
    return True


def network_direct_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    return env


def parse_curl_response(raw: bytes) -> Tuple[int, Dict[str, str], bytes]:
    separator = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
    parts = raw.split(separator)
    status = 0
    headers: Dict[str, str] = {}
    body_parts: List[bytes] = []
    consumed_headers = False
    for index, part in enumerate(parts):
        if part.startswith(b"HTTP/"):
            consumed_headers = True
            lines = part.decode("iso-8859-1", errors="replace").splitlines()
            status = parse_status_line(lines[0]) if lines else 0
            headers = parse_header_lines(lines[1:])
            continue
        body_parts = parts[index:]
        break
    if consumed_headers and not body_parts:
        body_parts = []
    return status, lower_headers(headers), separator.join(body_parts)


def parse_status_line(line: str) -> int:
    pieces = line.split()
    if len(pieces) < 2:
        return 0
    try:
        return int(pieces[1])
    except ValueError:
        return 0


def parse_header_lines(lines: List[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def error_detail(body: bytes) -> str:
    if not body:
        return ""
    text = body.decode("utf-8", errors="replace")
    text = " ".join(text.split())
    if len(text) > 160:
        text = f"{text[:157]}..."
    return f" error={text}"


def lower_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def origin_from_mcp_url(mcp_url: str) -> str:
    parsed = urlparse(mcp_url)
    return f"{parsed.scheme}://{parsed.netloc}"


if __name__ == "__main__":
    raise SystemExit(main())
