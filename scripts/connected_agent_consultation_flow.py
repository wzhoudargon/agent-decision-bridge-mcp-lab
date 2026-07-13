#!/usr/bin/env python3
"""Product wrapper for a bounded Connected Agent ChatGPT Web consultation.

The helper does not operate ChatGPT Web. It prepares the local side of the
workflow: advisor gate, short Connected Agent session, public health check, and safe
connector prompt generation. Codex or the user can then paste the copied prompt
into ChatGPT Web.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

try:
    from conversation_product_gate import evaluate_gate
except ModuleNotFoundError:  # pragma: no cover - exercised by package imports.
    from scripts.conversation_product_gate import evaluate_gate


ROOT = Path(__file__).resolve().parents[1]
CONNECTED_AGENT_SESSION = ROOT / "scripts" / "connected_agent_session.py"
CONNECTED_AGENT_PROMPT = ROOT / "scripts" / "connected_agent_consultation_prompt.py"
CONNECTED_AGENT_CAPTURE = ROOT / "scripts" / "connected_agent_capture_advice.py"
DEFAULT_PUBLIC_WARMUP_SECONDS = 30.0
DEFAULT_PREFLIGHT_TIMEOUT_SECONDS = 30.0
DEFAULT_PREFLIGHT_ATTEMPTS = 6
DEFAULT_PREFLIGHT_RETRY_SECONDS = 8.0
DEFAULT_HEALTH_ATTEMPTS = 5
DEFAULT_HEALTH_RETRY_SECONDS = 4.0
DEFAULT_HEALTH_RECOVERY_ATTEMPTS = 1
FAST_PUBLIC_WARMUP_SECONDS = 5.0
FAST_PREFLIGHT_TIMEOUT_SECONDS = 12.0
FAST_PREFLIGHT_ATTEMPTS = 2
FAST_PREFLIGHT_RETRY_SECONDS = 3.0
FAST_HEALTH_ATTEMPTS = 1
FAST_HEALTH_RETRY_SECONDS = 0.0
FAST_HEALTH_RECOVERY_ATTEMPTS = 0
DEFAULT_IDLE_TIMEOUT_SECONDS = 1200
NOT_CONSULTED_NOTICE = (
    "GPT Pro has not been consulted yet; the system is still preparing or waiting."
)
BROWSER_AUTOMATION_NOTICE = (
    "Browser automation warning: 浏览器自动化会临时控制你的电脑 UI，请不要操作鼠标键盘；"
    "如果不方便，改用 user-web 手动粘贴。"
)
MODEL_SELECTION_NOTICE = (
    "ChatGPT Web setup: use a chat mode where Apps/MCP connector tools are "
    "visible. If the Connected Agent connector is not visible, switch to a "
    "tool-capable ChatGPT mode or use Ask First for manual GPT Pro review."
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or close a bounded Connected Agent consultation window."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    prepare = subparsers.add_parser("prepare", help="Open the session and copy a safe prompt.")
    prepare.add_argument("question", help="User's Connected Agent consultation request.")
    prepare.add_argument("--allowed-root", required=True, help="Workspace root to expose.")
    prepare.add_argument(
        "--allowed-task",
        action="append",
        default=[],
        metavar="NAME=COMMAND",
        help="Expose one exact local test/lint/build task to Controlled Auto.",
    )
    prepare.add_argument(
        "--public-base-url",
        default=os.environ.get("DECISION_INBOX_PUBLIC_BASE_URL"),
        help="Public HTTPS origin without /mcp.",
    )
    prepare.add_argument(
        "--advisor-channel",
        choices=["unknown", "user-web", "browser-automation", "direct-tool"],
        default="unknown",
    )
    prepare.add_argument(
        "--advisor-health",
        choices=["ready", "blank", "timeout", "unavailable", "needs-browser-restart", "unknown"],
        default="unknown",
    )
    prepare.add_argument("--idle-timeout-seconds", type=int, default=DEFAULT_IDLE_TIMEOUT_SECONDS)
    prepare.add_argument(
        "--speed",
        choices=["fast", "safe"],
        default="fast",
        help="fast is the product default; safe keeps the conservative repeated health probes.",
    )
    prepare.add_argument(
        "--output",
        choices=["compact", "verbose"],
        default="compact",
        help="compact prints a product status card; verbose includes helper command output.",
    )
    prepare.add_argument("--public-warmup-seconds", type=float)
    prepare.add_argument("--preflight-timeout", type=float)
    prepare.add_argument("--preflight-attempts", type=int)
    prepare.add_argument("--preflight-retry-seconds", type=float)
    prepare.add_argument("--health-attempts", type=int)
    prepare.add_argument("--health-retry-seconds", type=float)
    prepare.add_argument(
        "--health-recovery-attempts",
        type=int,
        default=None,
        help="Extra full health checks to run only after an intermittent first result.",
    )
    prepare.add_argument("--no-clipboard", action="store_true", help="Print prompt only.")
    prepare.add_argument("--deep", action="store_true", help="Use the larger safe review set.")

    capture = subparsers.add_parser(
        "capture",
        help="Capture returned advice and refresh the Connected Agent idle window by default.",
    )
    capture.add_argument("question", help="Original Connected Agent consultation request.")
    capture.add_argument("--advisor", default="chatgpt-web-connected-agent")
    capture.add_argument(
        "--source-channel",
        choices=["user-web", "browser-automation", "direct-tool"],
        default="user-web",
    )
    capture.add_argument("--run-id")
    capture.add_argument("--timestamp")
    capture.add_argument("--advice-file", type=Path)
    capture.add_argument("--consultations-root", type=Path)
    capture.add_argument(
        "--no-close",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    capture.add_argument(
        "--close-after-capture",
        action="store_true",
        help="Close the Connected Agent session immediately after capture instead of waiting for idle shutdown.",
    )

    subparsers.add_parser("close", help="Close the session and print close verification.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    enable_line_buffered_stdout()
    args = parse_args(argv)
    if args.action == "prepare":
        return prepare(args)
    if args.action == "capture":
        return capture_and_keep_open(args)
    if args.action == "close":
        return close()
    raise AssertionError(args.action)


def prepare(args: argparse.Namespace) -> int:
    apply_speed_profile(args)
    print_status_card(
        args,
        state="starting",
        current_step="advisor-gate",
        next_action="verify advisor channel before opening the task window",
    )

    if not args.public_base_url:
        print_failure(
            "connected_agent_flow_failed",
            "Config error: --public-base-url or DECISION_INBOX_PUBLIC_BASE_URL is required.",
        )
        print(NOT_CONSULTED_NOTICE)
        return 2

    gate = evaluate_gate(
        mode="connected-agent",
        advisor_channel=args.advisor_channel,
        advisor_health=args.advisor_health,
        session_state="not_open",
    )
    print_gate_result(args, gate)
    if int(gate["exit_code"]) != 0:
        return int(gate["exit_code"])

    print("Opening Connected Agent task window...")
    open_result = run_command(build_open_command(args))
    print_command_result(args, "Open session", open_result)
    if open_result.returncode != 0:
        print_failure("connected_agent_flow_failed", "Connected Agent session could not be opened.")
        print(NOT_CONSULTED_NOTICE)
        return open_result.returncode

    health_result = check_public_health_with_recovery(args)
    if not health_is_stable(health_result):
        print_failure(
            "connected_agent_flow_failed",
            "public health is not stable; closing the Connected Agent window.",
        )
        close()
        print(NOT_CONSULTED_NOTICE)
        return 1

    print("Generating compact ChatGPT Web prompt...")
    prompt_result = run_command(build_prompt_command(args))
    print_command_result(args, "Prompt preparation", prompt_result)
    if prompt_result.returncode != 0:
        print_failure(
            "connected_agent_flow_failed",
            "prompt generation failed; closing the Connected Agent window before retrying.",
        )
        close()
        print(NOT_CONSULTED_NOTICE)
        return prompt_result.returncode

    print_status_card(
        args,
        state="ready_for_advisor",
        current_step="web-consult",
        next_action=handoff_next_action(args.advisor_channel),
    )
    print(render_handoff(args.advisor_channel))
    print("Close command: python3 scripts/connected_agent_flow.py close")
    return 0


def check_public_health_with_recovery(args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    print("Checking public Connected Agent health...")
    result = run_command(build_health_command(args))
    print_command_result(args, "Public health", result, summary=public_health_summary(result.stdout))
    if health_is_stable(result) or not health_is_intermittent(result):
        return result

    attempts = max(0, int(args.health_recovery_attempts))
    for attempt in range(1, attempts + 1):
        print(f"Public health was intermittent; running recovery check {attempt}/{attempts}...")
        result = run_command(build_health_command(args))
        print_command_result(
            args,
            "Public health recovery",
            result,
            summary=public_health_summary(result.stdout),
        )
        if health_is_stable(result) or not health_is_intermittent(result):
            return result
    return result


def health_is_stable(result: subprocess.CompletedProcess[str]) -> bool:
    return result.returncode == 0 and "Public health: stable" in result.stdout


def health_is_intermittent(result: subprocess.CompletedProcess[str]) -> bool:
    return "Public health: intermittent" in result.stdout


def close() -> int:
    close_result = run_command([sys.executable, str(CONNECTED_AGENT_SESSION), "close"])
    status_result = run_command(
        [
            sys.executable,
            str(CONNECTED_AGENT_SESSION),
            "status",
            "--check-public-health",
            "--health-attempts",
            "1",
        ]
    )
    print("Close session:")
    print(indent(close_result.stdout.strip()))
    print("Close verification:")
    print(indent(status_result.stdout.strip()))
    if close_result.returncode != 0:
        return close_result.returncode
    return 0


def capture_and_keep_open(args: argparse.Namespace) -> int:
    print("Current state: connected_agent_flow_capturing_advice")
    print("Requested mode: connected-agent")
    print("Risk while session may still be open: 3/5-5/5")
    input_text = None
    if not args.advice_file:
        input_text = sys.stdin.read()
    capture_result = run_command(build_capture_command(args), input_text=input_text)
    print("Advice capture:")
    print(indent(capture_result.stdout.strip()))
    if capture_result.stderr.strip():
        print("Advice capture stderr:")
        print(indent(capture_result.stderr.strip()))

    if capture_result.returncode != 0:
        refresh_idle_window()
        print("Current state: connected_agent_flow_failed")
        print("Reason: advice capture failed.")
        return capture_result.returncode

    close_status = 0
    should_close = bool(args.close_after_capture)
    if should_close:
        print("Closing Connected Agent session after advice capture because --close-after-capture was set...")
        close_status = close()
    else:
        refresh_idle_window()
    if close_status != 0:
        print("Current state: connected_agent_flow_failed")
        print("Reason: close verification failed.")
        return close_status

    print("Current state: connected_agent_flow_review_ready")
    if should_close:
        print("Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5")
    else:
        print("Risk after capture: 3/5-5/5 until idle shutdown closes the session.")
        print(f"Idle shutdown: {DEFAULT_IDLE_TIMEOUT_SECONDS} seconds after last Connected Agent use.")
    print("Next step: classify captured advice as Adopt / Adapt / Reject / Need info.")
    return 0


def refresh_idle_window() -> subprocess.CompletedProcess[str]:
    touch_result = run_command([sys.executable, str(CONNECTED_AGENT_SESSION), "touch"])
    print("Idle window refresh:")
    print(indent(touch_result.stdout.strip()))
    if touch_result.stderr.strip():
        print("Idle window refresh stderr:")
        print(indent(touch_result.stderr.strip()))
    return touch_result


def build_open_command(args: argparse.Namespace) -> List[str]:
    command = [
        sys.executable,
        str(CONNECTED_AGENT_SESSION),
        "open",
        "--mode",
        "connected-agent",
        "--public-base-url",
        str(args.public_base_url),
        "--allowed-root",
        str(Path(args.allowed_root).expanduser()),
        "--idle-timeout-seconds",
        str(args.idle_timeout_seconds),
        "--public-warmup-seconds",
        str(args.public_warmup_seconds),
        "--preflight-timeout",
        str(args.preflight_timeout),
        "--preflight-attempts",
        str(args.preflight_attempts),
        "--preflight-retry-seconds",
        str(args.preflight_retry_seconds),
    ]
    for allowed_task in args.allowed_task:
        command.extend(["--allowed-task", allowed_task])
    return command


def apply_speed_profile(args: argparse.Namespace) -> None:
    if args.speed == "safe":
        defaults = {
            "public_warmup_seconds": DEFAULT_PUBLIC_WARMUP_SECONDS,
            "preflight_timeout": DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
            "preflight_attempts": DEFAULT_PREFLIGHT_ATTEMPTS,
            "preflight_retry_seconds": DEFAULT_PREFLIGHT_RETRY_SECONDS,
            "health_attempts": DEFAULT_HEALTH_ATTEMPTS,
            "health_retry_seconds": DEFAULT_HEALTH_RETRY_SECONDS,
            "health_recovery_attempts": DEFAULT_HEALTH_RECOVERY_ATTEMPTS,
        }
    else:
        defaults = {
            "public_warmup_seconds": FAST_PUBLIC_WARMUP_SECONDS,
            "preflight_timeout": FAST_PREFLIGHT_TIMEOUT_SECONDS,
            "preflight_attempts": FAST_PREFLIGHT_ATTEMPTS,
            "preflight_retry_seconds": FAST_PREFLIGHT_RETRY_SECONDS,
            "health_attempts": FAST_HEALTH_ATTEMPTS,
            "health_retry_seconds": FAST_HEALTH_RETRY_SECONDS,
            "health_recovery_attempts": FAST_HEALTH_RECOVERY_ATTEMPTS,
        }
    for key, value in defaults.items():
        if getattr(args, key) is None:
            setattr(args, key, value)


def print_status_card(
    args: argparse.Namespace,
    *,
    state: str,
    current_step: str,
    next_action: str,
) -> None:
    print(f"Current state: connected_agent_flow_{state}")
    print(f"Connected Agent: {state}")
    print(f"Advisor channel: {args.advisor_channel} / {args.advisor_health}")
    print(f"Workspace: {Path(args.allowed_root).expanduser()}")
    print("Risk while online: 3/5-5/5; Danger Auto 5/5")
    print(f"Speed profile: {args.speed}")
    print(f"Current step: {current_step}")
    print(f"Next action: {next_action}")


def print_failure(state: str, reason: str) -> None:
    print(f"Current state: {state}")
    print(f"Reason: {reason}")


def print_gate_result(args: argparse.Namespace, gate: dict[str, object]) -> None:
    message = str(gate["message"])
    if args.output == "verbose":
        print("Advisor gate:")
        print(indent(message))
        return
    if int(gate["exit_code"]) == 0:
        print("Advisor gate: ready")
        return

    lines = parse_status_lines(message)
    print(f"Advisor gate: {lines.get('Current state', 'blocked')}")
    if reason := lines.get("Reason"):
        print(f"Reason: {reason}")
    if next_step := lines.get("Next step"):
        print(f"Next action: {next_step}")
    if NOT_CONSULTED_NOTICE in message:
        print(NOT_CONSULTED_NOTICE)


def print_command_result(
    args: argparse.Namespace,
    title: str,
    result: subprocess.CompletedProcess[str],
    *,
    summary: Optional[str] = None,
) -> None:
    if summary and result.returncode == 0 and args.output == "compact":
        print(f"{title}: {summary}")
        return
    if result.returncode == 0 and args.output == "compact":
        print(f"{title}: ok")
        return
    print(f"{title}:")
    print(indent(result.stdout.strip()))
    if result.stderr.strip():
        print(f"{title} stderr:")
        print(indent(result.stderr.strip()))


def public_health_summary(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Public health:"):
            return stripped.split(":", 1)[1].strip()
    return "ok"


def parse_status_lines(message: str) -> dict[str, str]:
    parsed = {}
    for line in message.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def handoff_next_action(advisor_channel: str) -> str:
    if advisor_channel == "browser-automation":
        return "Codex sends the copied prompt in ChatGPT Web"
    if advisor_channel == "direct-tool":
        return "Codex calls the available advisor channel"
    return "user sends the copied prompt in ChatGPT Web"


def build_health_command(args: argparse.Namespace) -> List[str]:
    return [
        sys.executable,
        str(CONNECTED_AGENT_SESSION),
        "status",
        "--check-public-health",
        "--preflight-timeout",
        str(args.preflight_timeout),
        "--health-attempts",
        str(args.health_attempts),
        "--health-retry-seconds",
        str(args.health_retry_seconds),
    ]


def build_prompt_command(args: argparse.Namespace) -> List[str]:
    command = [
        sys.executable,
        str(CONNECTED_AGENT_PROMPT),
        "--allowed-root",
        str(Path(args.allowed_root).expanduser()),
    ]
    if args.deep:
        command.append("--deep")
    if not args.no_clipboard:
        command.append("--clipboard")
    command.append(args.question)
    return command


def build_capture_command(args: argparse.Namespace) -> List[str]:
    command = [
        sys.executable,
        str(CONNECTED_AGENT_CAPTURE),
        "--question",
        args.question,
        "--advisor",
        args.advisor,
        "--source-channel",
        args.source_channel,
    ]
    if args.run_id:
        command.extend(["--run-id", args.run_id])
    if args.timestamp:
        command.extend(["--timestamp", args.timestamp])
    if args.advice_file:
        command.extend(["--advice-file", str(args.advice_file)])
    if args.consultations_root:
        command.extend(["--consultations-root", str(args.consultations_root)])
    return command


def run_command(command: List[str], input_text: Optional[str] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def enable_line_buffered_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(line_buffering=True)


def render_handoff(advisor_channel: str) -> str:
    if advisor_channel == "browser-automation":
        return "\n".join(
            [
                BROWSER_AUTOMATION_NOTICE,
                MODEL_SELECTION_NOTICE,
                "Next step for Codex:",
                "  Send the copied prompt in ChatGPT Web using the attached Connected Agent connector.",
                "  If browser automation cannot type or send reliably, switch to user-web handoff or close the window.",
                "  After advice returns, classify it locally as Adopt / Adapt / Reject / Need info.",
            ]
        )
    if advisor_channel == "direct-tool":
        return "\n".join(
            [
                MODEL_SELECTION_NOTICE,
                "Next step for Codex:",
                "  Call the available advisor channel with the copied prompt.",
                "  After advice returns, classify it locally as Adopt / Adapt / Reject / Need info.",
            ]
        )
    return "\n".join(
        [
            MODEL_SELECTION_NOTICE,
            "Next step for the user:",
            "  Open a ChatGPT Web conversation where the Connected Agent connector is visible.",
            "  Paste and send the copied prompt.",
            "  When ChatGPT finishes, paste the answer back into Codex.",
            "  Codex will classify the advice as Adopt / Adapt / Reject / Need info and close the loop.",
        ]
    )


def indent(value: str) -> str:
    if not value:
        return "  <empty>"
    return "\n".join(f"  {line}" for line in value.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
