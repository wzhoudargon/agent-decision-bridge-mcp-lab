#!/usr/bin/env python3
"""Session-level lifecycle helper for the high-risk Full-Agent connector.

This helper starts the Full-Agent MCP server, optionally opens Tailscale Funnel,
runs preflight, and starts a watchdog that closes the public window after a
short idle period. It intentionally stores process metadata only; OAuth tokens
stay in the HTTP server's normal state file outside the repo.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server" / "decision_inbox_http_server.py"
PREFLIGHT = ROOT / "scripts" / "decision_inbox_preflight.py"
DEFAULT_STATE_DIR = Path.home() / ".local/share/agent-decision-bridge/full-agent-session"
DEFAULT_STATE_FILE = DEFAULT_STATE_DIR / "session.json"
DEFAULT_SERVER_LOG = DEFAULT_STATE_DIR / "server.log"
DEFAULT_WATCHDOG_LOG = DEFAULT_STATE_DIR / "watchdog.log"
DEFAULT_TAILSCALE_SOCKET = os.environ.get(
    "TAILSCALE_SOCKET", "/tmp/tailscaled-decision-inbox.sock"
)
DEFAULT_IDLE_TIMEOUT_SECONDS = 1200
DEFAULT_PUBLIC_WARMUP_SECONDS = 10.0
DEFAULT_PREFLIGHT_TIMEOUT_SECONDS = 10.0
DEFAULT_PREFLIGHT_ATTEMPTS = 3
DEFAULT_PREFLIGHT_RETRY_SECONDS = 5.0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open, touch, inspect, or close a short Full-Agent MCP session."
    )
    parser.add_argument("action", choices=["open", "touch", "status", "sweep", "watch", "close"])
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--public-base-url",
        default=os.environ.get("DECISION_INBOX_PUBLIC_BASE_URL"),
        help="Public HTTPS origin, without /mcp. Required unless --local-only is set.",
    )
    parser.add_argument(
        "--allowed-root",
        dest="allowed_roots",
        action="append",
        default=[],
        help="Workspace root Full-Agent may open. Required for open.",
    )
    parser.add_argument("--tailscale-bin", default="tailscale")
    parser.add_argument("--socket", default=DEFAULT_TAILSCALE_SOCKET)
    parser.add_argument(
        "--idle-timeout-seconds",
        type=int,
        default=DEFAULT_IDLE_TIMEOUT_SECONDS,
        help="Close the session after this many seconds without touch.",
    )
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--startup-timeout", type=float, default=10.0)
    parser.add_argument("--preflight-timeout", type=float, default=DEFAULT_PREFLIGHT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--public-warmup-seconds",
        type=float,
        default=DEFAULT_PUBLIC_WARMUP_SECONDS,
        help="Seconds to wait after opening Funnel before public preflight.",
    )
    parser.add_argument(
        "--preflight-attempts",
        type=int,
        default=DEFAULT_PREFLIGHT_ATTEMPTS,
        help="Number of connector preflight attempts before failing.",
    )
    parser.add_argument(
        "--preflight-retry-seconds",
        type=float,
        default=DEFAULT_PREFLIGHT_RETRY_SECONDS,
        help="Seconds to wait between failed preflight attempts.",
    )
    parser.add_argument("--server-log", type=Path, default=DEFAULT_SERVER_LOG)
    parser.add_argument("--watchdog-log", type=Path, default=DEFAULT_WATCHDOG_LOG)
    parser.add_argument("--oauth-state-file", default=None)
    parser.add_argument("--oauth-owner-token-file", default=None)
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Do not open Tailscale Funnel; expose only the local endpoint.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Start the session without running read-only connector preflight.",
    )
    parser.add_argument(
        "--check-public-health",
        action="store_true",
        help="For status, run repeated read-only preflight probes against the active public endpoint.",
    )
    parser.add_argument(
        "--health-attempts",
        type=int,
        default=3,
        help="Number of status health probes to classify the active public endpoint.",
    )
    parser.add_argument(
        "--health-retry-seconds",
        type=float,
        default=2.0,
        help="Seconds to wait between status health probes.",
    )
    parser.add_argument(
        "--no-watchdog",
        action="store_true",
        help="Do not start the idle shutdown watchdog. Intended for tests/debugging.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.action == "open":
        return open_session(args)
    if args.action == "touch":
        return touch_session(args)
    if args.action == "status":
        return status_session(args)
    if args.action == "sweep":
        return sweep_session(args)
    if args.action == "watch":
        return watch_session(args)
    if args.action == "close":
        return close_session(args)
    raise AssertionError(args.action)


def open_session(args: argparse.Namespace) -> int:
    if not args.allowed_roots:
        print("Current state: full_agent_session_failed")
        print("Risk coefficient: 5/5 if opened")
        print("Config error: --allowed-root is required for Full-Agent.")
        return 2
    if not args.local_only and not args.public_base_url:
        print("Current state: full_agent_session_failed")
        print("Risk coefficient: 5/5 if opened")
        print("Config error: --public-base-url or DECISION_INBOX_PUBLIC_BASE_URL is required.")
        return 2
    if args.idle_timeout_seconds < 60:
        print("Current state: full_agent_session_failed")
        print("Risk coefficient: 5/5 if opened")
        print("Config error: --idle-timeout-seconds must be at least 60.")
        return 2

    existing = load_state(args.state_file)
    if existing and is_pid_running(existing.get("server_pid")):
        existing["idle_timeout_seconds"] = args.idle_timeout_seconds
        update_last_activity(args.state_file, existing)
        print("Current state: full_agent_session_already_open")
        print("Risk coefficient while open: 5/5")
        print(f"Idle shutdown: {existing.get('idle_timeout_seconds')} seconds after last touch")
        print(f"Public MCP URL: {mcp_url(existing) or 'local-only'}")
        return 0

    ensure_private_dir(args.state_file.parent)
    ensure_private_dir(args.server_log.parent)
    ensure_private_dir(args.watchdog_log.parent)
    local_mcp_url = f"http://{args.host}:{args.port}/mcp"
    server_log = args.server_log.open("ab")
    try:
        server_proc = subprocess.Popen(
            build_server_command(args),
            cwd=str(ROOT),
            env=server_env(),
            stdout=server_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        server_log.close()
        print("Current state: full_agent_session_failed")
        print("Risk coefficient: 5/5 if opened")
        print(f"Server start error: {exc}")
        return 1
    server_log.close()

    now = time.time()
    state = {
        "version": 1,
        "mode": "full-agent",
        "server_pid": server_proc.pid,
        "watchdog_pid": None,
        "host": args.host,
        "port": args.port,
        "local_mcp_url": local_mcp_url,
        "public_base_url": normalize_public_base_url(args.public_base_url),
        "allowed_roots": [str(Path(item).expanduser()) for item in args.allowed_roots],
        "tailscale_bin": None if args.local_only else args.tailscale_bin,
        "tailscale_socket": None if args.local_only else args.socket,
        "idle_timeout_seconds": args.idle_timeout_seconds,
        "opened_at": now,
        "last_activity": now,
        "server_log": str(args.server_log),
        "watchdog_log": str(args.watchdog_log),
    }
    save_state(args.state_file, state)

    try:
        wait_for_local_server(local_mcp_url, args.startup_timeout)
        if not args.local_only:
            run_tailscale(args, ["funnel", "--bg", "--yes", str(args.port)])
            flush_dns_cache_best_effort()
            wait_for_public_warmup(args.public_warmup_seconds)
        preflight_ran = not args.skip_preflight
        if preflight_ran:
            run_preflight_with_retries(args, local_mcp_url)
        if not args.no_watchdog:
            state["watchdog_pid"] = start_watchdog(args)
            save_state(args.state_file, state)
    except Exception as exc:
        print("Current state: full_agent_session_failed")
        print("Risk coefficient while cleanup is running: 5/5")
        print(f"Failure: {exc}")
        close_session(args)
        return 1

    print("Current state: full_agent_session_open")
    print("Mode: full-agent")
    print(product_readiness_summary(preflight_ran=not args.skip_preflight))
    print("Risk coefficient while open: 5/5")
    print(f"Idle shutdown: {args.idle_timeout_seconds} seconds after last touch")
    print(f"Public MCP URL: {mcp_url(state) or 'local-only'}")
    print(f"State file: {args.state_file}")
    print(f"Server log: {args.server_log}")
    print("Use `python3 scripts/full_agent_session.py touch` after each Full-Agent consult step.")
    return 0


def touch_session(args: argparse.Namespace) -> int:
    state = load_state(args.state_file)
    if not state:
        print("Current state: full_agent_session_closed")
        print("Risk coefficient now: 2/5 if persistent OAuth state remains, otherwise 1/5")
        return 1
    if not is_pid_running(state.get("server_pid")):
        print("Current state: full_agent_session_stale")
        remove_state(args.state_file)
        print("Risk coefficient now: 2/5 if persistent OAuth state remains, otherwise 1/5")
        return 1
    update_last_activity(args.state_file, state)
    print("Current state: full_agent_session_touched")
    print("Risk coefficient while open: 5/5")
    print(f"Public MCP URL: {mcp_url(state) or 'local-only'}")
    return 0


def status_session(args: argparse.Namespace) -> int:
    state = load_state(args.state_file)
    if not state:
        print("Current state: full_agent_session_closed")
        print("Risk coefficient now: 2/5 if persistent OAuth state remains, otherwise 1/5")
        if args.check_public_health:
            print("Public health: skipped_session_not_open")
        return 1
    alive = is_pid_running(state.get("server_pid"))
    idle = int(time.time() - float(state.get("last_activity", 0)))
    print(f"Current state: {'full_agent_session_open' if alive else 'full_agent_session_stale'}")
    print(f"Risk coefficient while open: {'5/5' if alive else 'not_open'}")
    print(f"Idle seconds: {idle}")
    print(f"Idle shutdown: {state.get('idle_timeout_seconds')} seconds after last touch")
    print(f"Public MCP URL: {mcp_url(state) or 'local-only'}")
    print(f"Server PID: {state.get('server_pid')}")
    print(f"Watchdog PID: {state.get('watchdog_pid')}")
    final_alive = alive
    if args.check_public_health:
        print(public_health_report(args, state, alive=alive))
        final_alive = session_still_alive(args.state_file, state)
        if alive and not final_alive:
            print("Current state after health check: full_agent_session_closed_or_stale")
            print("Risk coefficient now: 2/5 if persistent OAuth state remains, otherwise 1/5")
    return 0 if final_alive else 1


def sweep_session(args: argparse.Namespace) -> int:
    state = load_state(args.state_file)
    if not state:
        print("Current state: full_agent_session_closed")
        return 0
    if not is_pid_running(state.get("server_pid")):
        print("Current state: full_agent_session_stale")
        remove_state(args.state_file)
        return 0
    idle = time.time() - float(state.get("last_activity", 0))
    timeout = float(state.get("idle_timeout_seconds", args.idle_timeout_seconds))
    if idle < timeout:
        print("Current state: full_agent_session_open")
        print("Risk coefficient while open: 5/5")
        print(f"Idle seconds: {int(idle)}")
        return 0
    print("Current state: full_agent_session_idle_expired")
    print("Risk coefficient while closing: 5/5")
    return close_session(args, from_watchdog=True)


def watch_session(args: argparse.Namespace) -> int:
    while True:
        state = load_state(args.state_file)
        if not state:
            return 0
        if not is_pid_running(state.get("server_pid")):
            remove_state(args.state_file)
            return 0
        idle = time.time() - float(state.get("last_activity", 0))
        timeout = float(state.get("idle_timeout_seconds", args.idle_timeout_seconds))
        if idle >= timeout:
            print("Current state: full_agent_session_idle_expired")
            print("Risk coefficient while closing: 5/5")
            return close_session(args, from_watchdog=True)
        time.sleep(max(1.0, min(args.poll_seconds, timeout - idle)))


def session_still_alive(state_file: Path, state: Dict[str, Any]) -> bool:
    latest = load_state(state_file)
    if not latest:
        return False
    if latest.get("server_pid") != state.get("server_pid"):
        return False
    return is_pid_running(latest.get("server_pid"))


def close_session(args: argparse.Namespace, from_watchdog: bool = False) -> int:
    state = load_state(args.state_file)
    if not state:
        print("Current state: full_agent_session_closed")
        print("Risk coefficient now: 2/5 if persistent OAuth state remains, otherwise 1/5")
        return 0

    result = 0
    if state.get("tailscale_socket"):
        result = run_tailscale_from_state(args, state, ["funnel", "reset"])
    terminate_pid(state.get("server_pid"))
    if not from_watchdog:
        terminate_pid(state.get("watchdog_pid"))
    remove_state(args.state_file)
    print("Current state: full_agent_session_closed")
    print("Risk coefficient now: 2/5 if persistent OAuth state remains, otherwise 1/5")
    return result


def build_server_command(args: argparse.Namespace) -> List[str]:
    command = [
        sys.executable,
        str(SERVER),
        "--mode",
        "full-agent",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.public_base_url:
        command.extend(["--public-base-url", normalize_public_base_url(args.public_base_url)])
    for allowed_root in args.allowed_roots:
        command.extend(["--allowed-root", str(Path(allowed_root).expanduser())])
    if args.oauth_state_file:
        command.extend(["--oauth-state-file", args.oauth_state_file])
    if args.oauth_owner_token_file:
        command.extend(["--oauth-owner-token-file", args.oauth_owner_token_file])
    command.extend(["--session-activity-file", str(args.state_file)])
    return command


def product_readiness_summary(preflight_ran: bool) -> str:
    connector_state = "verified_by_preflight" if preflight_ran else "not_verified_preflight_skipped"
    return (
        "Product readiness: "
        f"connector_tools_verified={connector_state}; "
        "advisor_channel_verified=not_checked_by_session_helper; "
        "session_online=yes; "
        "risk=5/5"
    )


def run_preflight(args: argparse.Namespace, local_mcp_url: str) -> None:
    command = [
        sys.executable,
        str(PREFLIGHT),
        "--mode",
        "full-agent",
        "--local-url",
        local_mcp_url,
        "--timeout",
        str(args.preflight_timeout),
    ]
    if args.public_base_url:
        command.extend(["--public-base-url", normalize_public_base_url(args.public_base_url)])
    if not args.local_only:
        command.append("--require-public")
    run_command(command, env=network_direct_env())


def run_preflight_for_state(args: argparse.Namespace, state: Dict[str, Any]) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(PREFLIGHT),
        "--mode",
        "full-agent",
        "--local-url",
        str(state.get("local_mcp_url") or f"http://{state.get('host', '127.0.0.1')}:{state.get('port', 8765)}/mcp"),
        "--timeout",
        str(args.preflight_timeout),
    ]
    public_base_url = state.get("public_base_url")
    if isinstance(public_base_url, str) and public_base_url:
        command.extend(["--public-base-url", normalize_public_base_url(public_base_url)])
        command.append("--require-public")
    return subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=network_direct_env(),
        check=False,
    )


def public_health_report(args: argparse.Namespace, state: Dict[str, Any], alive: bool) -> str:
    if not alive:
        return "Public health: skipped_session_not_open"
    if not mcp_url(state):
        return "Public health: skipped_local_only"

    attempts = max(1, int(args.health_attempts))
    passed = 0
    latest_failure = ""
    for attempt in range(1, attempts + 1):
        completed = run_preflight_for_state(args, state)
        if completed.returncode == 0:
            passed += 1
        else:
            latest_failure = summarize_preflight_failure(completed.stdout)
        if attempt < attempts and args.health_retry_seconds > 0:
            time.sleep(args.health_retry_seconds)

    if passed == attempts:
        return f"Public health: stable preflight_passed={passed}/{attempts}"
    if passed > 0:
        return (
            f"Public health: intermittent preflight_passed={passed}/{attempts}"
            f" latest_failure={latest_failure or 'unknown'}"
        )
    return (
        f"Public health: failed preflight_passed=0/{attempts}"
        f" latest_failure={latest_failure or 'unknown'}"
    )


def summarize_preflight_failure(output: str) -> str:
    reasons = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            reasons.append(stripped[2:])
    if reasons:
        return "; ".join(reasons)
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return "no preflight output"


def run_preflight_with_retries(args: argparse.Namespace, local_mcp_url: str) -> None:
    attempts = max(1, int(args.preflight_attempts))
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            run_preflight(args, local_mcp_url)
            return
        except RuntimeError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            print(f"Preflight attempt {attempt}/{attempts} failed; retrying after {args.preflight_retry_seconds:g}s.")
            if args.preflight_retry_seconds > 0:
                time.sleep(args.preflight_retry_seconds)
    if last_error is not None:
        raise last_error


def run_tailscale(args: argparse.Namespace, tail_args: List[str]) -> None:
    command = [args.tailscale_bin, "--socket", args.socket, *tail_args]
    run_command(command, env=network_direct_env())


def wait_for_public_warmup(seconds: float) -> None:
    if seconds <= 0:
        return
    time.sleep(seconds)


def flush_dns_cache_best_effort() -> None:
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            ["dscacheutil", "-flushcache"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        pass


def run_tailscale_from_state(
    args: argparse.Namespace, state: Dict[str, Any], tail_args: List[str]
) -> int:
    command = [
        str(state.get("tailscale_bin") or args.tailscale_bin),
        "--socket",
        str(state.get("tailscale_socket")),
        *tail_args,
    ]
    completed = subprocess.run(command, text=True, env=network_direct_env())
    return completed.returncode


def run_command(command: List[str], env: Optional[Dict[str, str]] = None) -> None:
    print(f"Running: {redacted_command(command)}")
    completed = subprocess.run(command, text=True, env=env)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed with exit code {completed.returncode}: {command[0]}")


def start_watchdog(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "watch",
        "--state-file",
        str(args.state_file),
        "--poll-seconds",
        str(args.poll_seconds),
    ]
    ensure_private_dir(args.watchdog_log.parent)
    watchdog_log = args.watchdog_log.open("ab")
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=watchdog_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        watchdog_log.close()
    return proc.pid


def wait_for_local_server(local_mcp_url: str, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error: Optional[str] = None
    while time.time() < deadline:
        try:
            probe_unauthenticated(local_mcp_url)
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.2)
    raise RuntimeError(f"local Full-Agent endpoint did not become ready: {last_error}")


def probe_unauthenticated(url: str) -> None:
    payload = b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=2.0) as response:
            if response.status in {200, 202, 401}:
                return
            raise RuntimeError(f"unexpected HTTP status {response.status}")
    except HTTPError as exc:
        if exc.code in {401, 403}:
            return
        raise
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def load_state(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid Full-Agent session state file: {exc}") from exc


def save_state(path: Path, state: Dict[str, Any]) -> None:
    ensure_private_dir(path.parent)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def remove_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def update_last_activity(path: Path, state: Dict[str, Any]) -> None:
    state["last_activity"] = time.time()
    save_state(path, state)


def ensure_private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def is_pid_running(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_pid(pid: Any) -> None:
    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return
    if not is_pid_running(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not is_pid_running(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def normalize_public_base_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.rstrip("/")


def mcp_url(state: Dict[str, Any]) -> Optional[str]:
    public_base_url = state.get("public_base_url")
    if isinstance(public_base_url, str) and public_base_url:
        return f"{public_base_url.rstrip('/')}/mcp"
    return None


def server_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return env


def network_direct_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("ALL_PROXY", None)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    env.pop("all_proxy", None)
    return env


def redacted_command(command: List[str]) -> str:
    return " ".join(command)


if __name__ == "__main__":
    raise SystemExit(main())
