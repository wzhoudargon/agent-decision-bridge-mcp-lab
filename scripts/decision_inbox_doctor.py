#!/usr/bin/env python3
"""Local connector diagnostics for Decision Inbox MCP.

This script prints safe status only. It never prints token values, starts tunnels,
or changes ChatGPT connector settings.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.decision_inbox_http_server import (
    DEFAULT_FULL_AGENT_OWNER_TOKEN_FILE,
    DEFAULT_FULL_AGENT_STATE_FILE,
    MODE_ASK_FIRST,
    MODE_AUTO_MCP,
    MODE_CONNECTED_AGENT,
    MODE_FULL_AGENT,
    MODE_READ_ONLY_PROJECT,
    VALID_MODES,
    normalize_mode,
    normalize_public_base_url,
    public_mcp_url,
)


DEFAULT_LOCAL_URL = "http://127.0.0.1:8765/mcp"
DEFAULT_TOKEN_FILE = Path("/tmp/decision-inbox-mcp-token")
DEFAULT_OWNER_TOKEN_FILE = Path("/tmp/decision-inbox-oauth-owner-token")
DEFAULT_PERSISTENT_STATE_FILE = (
    Path.home() / ".local/share/decision-inbox-mcp-lab/oauth-state.json"
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check local Decision Inbox MCP connector readiness without exposing secrets."
    )
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default=os.environ.get("AGENT_BRIDGE_MODE", MODE_AUTO_MCP),
        help="Connector mode to evaluate. Defaults to auto-mcp.",
    )
    parser.add_argument("--local-url", default=DEFAULT_LOCAL_URL)
    parser.add_argument(
        "--public-base-url",
        default=os.environ.get("DECISION_INBOX_PUBLIC_BASE_URL"),
        help="Public HTTPS origin, without /mcp. May also use DECISION_INBOX_PUBLIC_BASE_URL.",
    )
    parser.add_argument(
        "--token-env",
        default="DECISION_INBOX_MCP_TOKEN",
        help="Environment variable that may contain the MCP bearer token.",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_FILE,
        help="Optional token file to inspect. The token value is never printed.",
    )
    parser.add_argument(
        "--oauth-owner-token-env",
        default="DECISION_INBOX_OAUTH_OWNER_TOKEN",
        help="Environment variable that may contain the OAuth Owner password.",
    )
    parser.add_argument(
        "--oauth-owner-token-file",
        type=Path,
        default=None,
        help="Optional Owner password file to inspect. The value is never printed.",
    )
    parser.add_argument(
        "--oauth-state-file",
        type=Path,
        default=None,
        help=(
            "Optional OAuth state file to inspect for presence and permissions only. "
            "Secret token values are never read or printed."
        ),
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help="Only validate config and risk, without probing the local MCP endpoint.",
    )
    return parser.parse_args(argv)


def load_token(env_name: str, token_file: Optional[Path]) -> Tuple[Optional[str], str]:
    env_token = os.environ.get(env_name)
    if env_token:
        return env_token.strip(), f"env:{env_name}"
    if token_file and token_file.is_file():
        return token_file.read_text(encoding="utf-8").strip(), f"file:{token_file}"
    return None, "none"


def token_status(token: Optional[str], source: str) -> str:
    if not token:
        return "absent"
    return f"present source={source} length={len(token)} value=redacted"


def secret_file_status(path: Optional[Path]) -> str:
    if not path:
        return "disabled"
    expanded = path.expanduser()
    if not expanded.exists():
        return f"absent path={expanded}"
    if not expanded.is_file():
        return f"invalid_not_file path={expanded}"
    mode = expanded.stat().st_mode & 0o777
    permission_status = "ok" if mode == 0o600 else "warn_expected_0600"
    return f"present path={expanded} mode={mode:04o} permissions={permission_status} value=not_read"


def estimate_risk(
    public_base_url: Optional[str],
    token: Optional[str],
    local_url: str,
    oauth_owner_token: Optional[str] = None,
    oauth_state_file_present: bool = False,
    mode: str = MODE_AUTO_MCP,
) -> Tuple[int, str]:
    if mode == MODE_ASK_FIRST:
        return (1, "Ask First uses package/advice files and does not expose an MCP server")
    if mode == MODE_CONNECTED_AGENT:
        return (
            5 if public_base_url else 4,
            "connected-agent exposes local project read/search and can request write/edit/bash; Danger Auto is session-only and server-filtered",
        )
    if mode == MODE_FULL_AGENT:
        return (
            5,
            "full-agent exposes local file read/write/edit/search and shell execution to the connected MCP client",
        )
    if mode == MODE_READ_ONLY_PROJECT:
        return (
            4 if public_base_url else 3,
            "read-only-project exposes protected project listing, file reads, glob, and grep to the connected MCP client",
        )
    has_auth = bool(token or oauth_owner_token or oauth_state_file_present)
    if public_base_url and has_auth:
        suffix = "; persistent OAuth state file present" if oauth_state_file_present else ""
        return (
            3,
            "public tunnel/reverse proxy configured; endpoint is internet-reachable if tunnel is running"
            + suffix,
        )
    if public_base_url and not has_auth:
        return 4, "public URL configured without bearer-token or OAuth owner-password auth"
    if oauth_state_file_present:
        return 2, "local-only or non-public endpoint with bearer-equivalent OAuth state stored on disk"
    if local_url.startswith("http://127.0.0.1") or local_url.startswith("http://localhost"):
        return 1, "local-only endpoint"
    return 2, "non-local endpoint without public URL metadata"


def probe_local_endpoint(
    local_url: str,
    token: Optional[str],
    timeout: float,
    oauth_owner_token: Optional[str] = None,
) -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        local_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if (
            oauth_owner_token
            and exc.code == 401
            and "oauth-protected-resource" in (exc.headers.get("WWW-Authenticate") or "")
        ):
            return "ok oauth_challenge"
        return f"failed http_status={exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        return f"unavailable reason={exc.__class__.__name__}"
    except json.JSONDecodeError:
        return "failed invalid_json_response"

    server_info = body.get("result", {}).get("serverInfo", {})
    name = server_info.get("name", "unknown")
    return f"ok server={name}"


def build_report(args: argparse.Namespace) -> List[str]:
    mode = normalize_mode(getattr(args, "mode", MODE_AUTO_MCP))
    owner_token_file = getattr(args, "oauth_owner_token_file", None) or default_owner_token_file(mode)
    oauth_state_file = getattr(args, "oauth_state_file", None) or default_state_file(mode)
    token, token_source = load_token(args.token_env, args.token_file)
    owner_token, owner_token_source = load_token(
        args.oauth_owner_token_env, owner_token_file
    )
    normalized_public_base_url = normalize_public_base_url(args.public_base_url)
    oauth_state_file_present = bool(oauth_state_file and oauth_state_file.is_file())
    risk, risk_reason = estimate_risk(
        normalized_public_base_url,
        token,
        args.local_url,
        owner_token,
        oauth_state_file_present,
        mode,
    )
    probe = (
        "skipped"
        if args.skip_probe
        else probe_local_endpoint(args.local_url, token, args.timeout, owner_token)
    )

    public_url = public_mcp_url(normalized_public_base_url) or "none"
    next_action = "start local server only" if normalized_public_base_url is None else "use stable public URL or reconnect ChatGPT connector when the tunnel URL changes"

    return [
        "Current state: connector_diagnostic",
        f"Mode: {mode}",
        f"Product tier: {product_tier(mode)}",
        f"Risk coefficient: {risk}/5",
        f"Risk reason: {risk_reason}",
        f"Local MCP URL: {args.local_url}",
        f"Public MCP URL: {public_url}",
        f"Token status: {token_status(token, token_source)}",
        f"OAuth Owner password status: {token_status(owner_token, owner_token_source)}",
        f"OAuth Owner password file status: {secret_file_status(owner_token_file)}",
        f"OAuth state file status: {secret_file_status(oauth_state_file)}",
        f"Local probe: {probe}",
        "Connector split note: current product uses Ask First plus Connected Agent. Legacy package-only Auto MCP, Read-Only Project Advisor, and Full-Agent are deprecated aliases.",
        "ChatGPT connector note: changing a temporary public URL usually requires updating or reconnecting the ChatGPT app-side connector.",
        "Preflight command: python3 scripts/decision_inbox_preflight.py --mode "
        f"{mode}"
        + (
            f" --public-base-url {normalized_public_base_url}"
            if normalized_public_base_url
            else ""
        ),
        f"Recommended next action: {next_action}",
    ]


def default_owner_token_file(mode: str) -> Path:
    if mode in {MODE_FULL_AGENT, MODE_CONNECTED_AGENT}:
        return DEFAULT_FULL_AGENT_OWNER_TOKEN_FILE
    return DEFAULT_OWNER_TOKEN_FILE


def product_tier(mode: str) -> str:
    if mode == MODE_ASK_FIRST:
        return "Ask First"
    if mode == MODE_CONNECTED_AGENT:
        return "Connected Agent"
    if mode == MODE_FULL_AGENT:
        return "Full-Agent"
    if mode == MODE_READ_ONLY_PROJECT:
        return "Read-Only Project Advisor"
    if mode == "manual":
        return "Ask First"
    return "Legacy Auto MCP Package"


def default_state_file(mode: str) -> Path:
    if mode in {MODE_READ_ONLY_PROJECT, MODE_FULL_AGENT, MODE_CONNECTED_AGENT}:
        return DEFAULT_FULL_AGENT_STATE_FILE
    if os.environ.get("DECISION_INBOX_OAUTH_STATE_FILE"):
        return Path(os.environ["DECISION_INBOX_OAUTH_STATE_FILE"])
    return DEFAULT_PERSISTENT_STATE_FILE


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        lines = build_report(args)
    except ValueError as exc:
        print("Current state: connector_diagnostic", file=sys.stderr)
        print("Risk coefficient: 4/5", file=sys.stderr)
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
