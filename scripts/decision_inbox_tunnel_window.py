#!/usr/bin/env python3
"""Bounded Tailscale Funnel lifecycle helper for Decision Inbox MCP.

This helper manages the local public window only. It does not create or edit the
ChatGPT account-side connector.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts" / "decision_inbox_preflight.py"
DEFAULT_TAILSCALE_SOCKET = "/tmp/tailscaled-decision-inbox.sock"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open, check, or close a short Tailscale Funnel MCP connector window."
    )
    parser.add_argument("action", choices=["open", "status", "close"])
    parser.add_argument("--mode", default=os.environ.get("AGENT_BRIDGE_MODE", "auto-mcp"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--public-base-url",
        default=os.environ.get("DECISION_INBOX_PUBLIC_BASE_URL"),
        help="Public HTTPS origin, without /mcp.",
    )
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--tailscale-bin", default="tailscale")
    parser.add_argument("--socket", default=DEFAULT_TAILSCALE_SOCKET)
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Open Funnel without running the connector preflight.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.action == "open":
        return open_window(args)
    if args.action == "status":
        return run_tailscale(args, ["funnel", "status"])
    if args.action == "close":
        return close_window(args)
    raise AssertionError(args.action)


def open_window(args: argparse.Namespace) -> int:
    if not args.public_base_url:
        print("Current state: tunnel_window_failed")
        print("Risk coefficient: 4/5")
        print("Config error: --public-base-url or DECISION_INBOX_PUBLIC_BASE_URL is required")
        return 2
    print("Current state: opening_tunnel_window")
    print(f"Mode: {args.mode}")
    print(f"Risk coefficient while open: {risk_coefficient(args.mode)}")
    print(f"Public MCP URL: {args.public_base_url.rstrip('/')}/mcp")
    result = run_tailscale(args, ["funnel", "--bg", "--yes", str(args.port)])
    if result != 0:
        return result
    if args.skip_preflight:
        print("Preflight: skipped")
        return 0
    return run_preflight(args)


def close_window(args: argparse.Namespace) -> int:
    print("Current state: closing_tunnel_window")
    result = run_tailscale(args, ["funnel", "reset"])
    if result == 0:
        print("Risk coefficient after close: 1/5 if no persistent OAuth state remains; 2/5 if OAuth state remains on disk.")
    return result


def run_preflight(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(PREFLIGHT),
        "--mode",
        args.mode,
        "--public-base-url",
        args.public_base_url,
        "--timeout",
        str(args.timeout),
        "--require-public",
    ]
    if args.task_id:
        command.extend(["--task-id", args.task_id])
    return run_command(command)


def run_tailscale(args: argparse.Namespace, tail_args: List[str]) -> int:
    command = [args.tailscale_bin, "--socket", args.socket, *tail_args]
    return run_command(command)


def risk_coefficient(mode: str) -> str:
    if mode == "full-agent":
        return "5/5"
    if mode == "read-only-project":
        return "4/5"
    return "3/5"


def run_command(command: List[str]) -> int:
    print(f"Running: {redacted_command(command)}")
    completed = subprocess.run(command, text=True, env=network_direct_env())
    return completed.returncode


def redacted_command(command: List[str]) -> str:
    # Command line contains no token values by design; keep this function for one
    # place to redact later if more providers are added.
    return " ".join(command)


def network_direct_env() -> dict[str, str]:
    env = os.environ.copy()
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    return env


if __name__ == "__main__":
    raise SystemExit(main())
