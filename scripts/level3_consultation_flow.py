#!/usr/bin/env python3
"""Product wrapper for a bounded Level 3 ChatGPT Web consultation.

The helper does not operate ChatGPT Web. It prepares the local side of the
workflow: advisor gate, short Full-Agent session, public health check, and safe
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
FULL_AGENT_SESSION = ROOT / "scripts" / "full_agent_session.py"
LEVEL3_PROMPT = ROOT / "scripts" / "level3_consultation_prompt.py"
LEVEL3_CAPTURE = ROOT / "scripts" / "level3_capture_advice.py"
DEFAULT_PUBLIC_WARMUP_SECONDS = 30.0
DEFAULT_PREFLIGHT_TIMEOUT_SECONDS = 30.0
DEFAULT_PREFLIGHT_ATTEMPTS = 6
DEFAULT_PREFLIGHT_RETRY_SECONDS = 8.0
DEFAULT_HEALTH_ATTEMPTS = 5
DEFAULT_HEALTH_RETRY_SECONDS = 4.0
DEFAULT_HEALTH_RECOVERY_ATTEMPTS = 1
DEFAULT_IDLE_TIMEOUT_SECONDS = 1200
NOT_CONSULTED_NOTICE = (
    "GPT Pro has not been consulted yet; the system is still preparing or waiting."
)
BROWSER_AUTOMATION_NOTICE = (
    "Browser automation warning: 浏览器自动化会临时控制你的电脑 UI，请不要操作鼠标键盘；"
    "如果不方便，改用 user-web 手动粘贴。"
)
MODEL_SELECTION_NOTICE = (
    "Model selection: use GPT-5.5 Thinking for MCP/App connector calls. "
    "Do not use GPT-5.5 Pro for this step because Pro models do not expose "
    "ChatGPT Apps/MCP tools."
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or close a bounded Level 3 consultation window."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    prepare = subparsers.add_parser("prepare", help="Open the session and copy a safe prompt.")
    prepare.add_argument("question", help="User's Level 3 consultation request.")
    prepare.add_argument("--allowed-root", required=True, help="Workspace root to expose.")
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
    prepare.add_argument("--public-warmup-seconds", type=float, default=DEFAULT_PUBLIC_WARMUP_SECONDS)
    prepare.add_argument("--preflight-timeout", type=float, default=DEFAULT_PREFLIGHT_TIMEOUT_SECONDS)
    prepare.add_argument("--preflight-attempts", type=int, default=DEFAULT_PREFLIGHT_ATTEMPTS)
    prepare.add_argument("--preflight-retry-seconds", type=float, default=DEFAULT_PREFLIGHT_RETRY_SECONDS)
    prepare.add_argument("--health-attempts", type=int, default=DEFAULT_HEALTH_ATTEMPTS)
    prepare.add_argument("--health-retry-seconds", type=float, default=DEFAULT_HEALTH_RETRY_SECONDS)
    prepare.add_argument(
        "--health-recovery-attempts",
        type=int,
        default=DEFAULT_HEALTH_RECOVERY_ATTEMPTS,
        help="Extra full health checks to run only after an intermittent first result.",
    )
    prepare.add_argument("--no-clipboard", action="store_true", help="Print prompt only.")
    prepare.add_argument("--deep", action="store_true", help="Use the larger safe review set.")

    capture = subparsers.add_parser(
        "capture",
        help="Capture returned advice and refresh the Level 3 idle window by default.",
    )
    capture.add_argument("question", help="Original Level 3 consultation request.")
    capture.add_argument("--advisor", default="chatgpt-web-full-agent")
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
        help="Close the Level 3 session immediately after capture instead of waiting for idle shutdown.",
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
    print("Current state: level3_flow_starting")
    print("Requested mode: full-agent")
    print("Risk if opened: 5/5")

    if not args.public_base_url:
        print("Current state: level3_flow_failed")
        print("Config error: --public-base-url or DECISION_INBOX_PUBLIC_BASE_URL is required.")
        print(NOT_CONSULTED_NOTICE)
        return 2

    gate = evaluate_gate(
        mode="full-agent",
        advisor_channel=args.advisor_channel,
        advisor_health=args.advisor_health,
        session_state="not_open",
    )
    print("Advisor gate:")
    print(indent(str(gate["message"])))
    if int(gate["exit_code"]) != 0:
        return int(gate["exit_code"])

    print("Opening Full-Agent session and public tunnel...")
    open_result = run_command(build_open_command(args))
    print("Open session:")
    print(indent(open_result.stdout.strip()))
    if open_result.returncode != 0:
        print("Current state: level3_flow_failed")
        print(NOT_CONSULTED_NOTICE)
        return open_result.returncode

    health_result = check_public_health_with_recovery(args)
    if not health_is_stable(health_result):
        print("Current state: level3_flow_failed")
        print("Reason: public health is not stable; closing the 5/5 window.")
        close()
        print(NOT_CONSULTED_NOTICE)
        return 1

    print("Generating compact ChatGPT Web prompt...")
    prompt_result = run_command(build_prompt_command(args))
    print("Prompt preparation:")
    print(indent(prompt_result.stdout.strip()))
    if prompt_result.stderr.strip():
        print("Prompt stderr:")
        print(indent(prompt_result.stderr.strip()))
    if prompt_result.returncode != 0:
        print("Current state: level3_flow_failed")
        print("Reason: prompt generation failed; closing the 5/5 window before retrying.")
        close()
        print(NOT_CONSULTED_NOTICE)
        return prompt_result.returncode

    print("Current state: level3_flow_ready_for_advisor")
    print("Risk while session remains open: 5/5")
    print(render_handoff(args.advisor_channel))
    print("Close command: python3 scripts/level3_consultation_flow.py close")
    return 0


def check_public_health_with_recovery(args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    print("Checking public Full-Agent health...")
    result = run_command(build_health_command(args))
    print("Public health:")
    print(indent(result.stdout.strip()))
    if health_is_stable(result) or not health_is_intermittent(result):
        return result

    attempts = max(0, int(args.health_recovery_attempts))
    for attempt in range(1, attempts + 1):
        print(f"Public health was intermittent; running recovery check {attempt}/{attempts}...")
        result = run_command(build_health_command(args))
        print("Public health recovery:")
        print(indent(result.stdout.strip()))
        if health_is_stable(result) or not health_is_intermittent(result):
            return result
    return result


def health_is_stable(result: subprocess.CompletedProcess[str]) -> bool:
    return result.returncode == 0 and "Public health: stable" in result.stdout


def health_is_intermittent(result: subprocess.CompletedProcess[str]) -> bool:
    return "Public health: intermittent" in result.stdout


def close() -> int:
    close_result = run_command([sys.executable, str(FULL_AGENT_SESSION), "close"])
    status_result = run_command(
        [
            sys.executable,
            str(FULL_AGENT_SESSION),
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
    print("Current state: level3_flow_capturing_advice")
    print("Requested mode: full-agent")
    print("Risk while session may still be open: 5/5")
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
        print("Current state: level3_flow_failed")
        print("Reason: advice capture failed.")
        return capture_result.returncode

    close_status = 0
    should_close = bool(args.close_after_capture)
    if should_close:
        print("Closing Level 3 session after advice capture because --close-after-capture was set...")
        close_status = close()
    else:
        refresh_idle_window()
    if close_status != 0:
        print("Current state: level3_flow_failed")
        print("Reason: close verification failed.")
        return close_status

    print("Current state: level3_flow_review_ready")
    if should_close:
        print("Risk after close: 2/5 if persistent OAuth state remains, otherwise 1/5")
    else:
        print("Risk after capture: 5/5 until idle shutdown closes the session.")
        print(f"Idle shutdown: {DEFAULT_IDLE_TIMEOUT_SECONDS} seconds after last Level 3 use.")
    print("Next step: classify captured advice as Adopt / Ask / Reject.")
    return 0


def refresh_idle_window() -> subprocess.CompletedProcess[str]:
    touch_result = run_command([sys.executable, str(FULL_AGENT_SESSION), "touch"])
    print("Idle window refresh:")
    print(indent(touch_result.stdout.strip()))
    if touch_result.stderr.strip():
        print("Idle window refresh stderr:")
        print(indent(touch_result.stderr.strip()))
    return touch_result


def build_open_command(args: argparse.Namespace) -> List[str]:
    return [
        sys.executable,
        str(FULL_AGENT_SESSION),
        "open",
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


def build_health_command(args: argparse.Namespace) -> List[str]:
    return [
        sys.executable,
        str(FULL_AGENT_SESSION),
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
        str(LEVEL3_PROMPT),
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
        str(LEVEL3_CAPTURE),
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
                "  Send the copied prompt in ChatGPT Web using the attached Full-Agent connector.",
                "  If browser automation cannot type or send reliably, switch to user-web handoff or close the 5/5 window.",
                "  After advice returns, classify it locally as Adopt / Ask / Reject.",
            ]
        )
    if advisor_channel == "direct-tool":
        return "\n".join(
            [
                MODEL_SELECTION_NOTICE,
                "Next step for Codex:",
                "  Call the available advisor channel with the copied prompt.",
                "  After advice returns, classify it locally as Adopt / Ask / Reject.",
            ]
        )
    return "\n".join(
        [
            MODEL_SELECTION_NOTICE,
            "Next step for the user:",
            "  Open a ChatGPT Web conversation using GPT-5.5 Thinking with the Full-Agent connector attached.",
            "  Paste and send the copied prompt.",
            "  When ChatGPT finishes, paste the answer back into Codex.",
            "  Codex will classify the advice as Adopt / Ask / Reject and close the loop.",
        ]
    )


def indent(value: str) -> str:
    if not value:
        return "  <empty>"
    return "\n".join(f"  {line}" for line in value.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
