#!/usr/bin/env python3
"""Report Connected Agent product readiness without opening a public session."""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from conversation_product_gate import evaluate_gate


ROOT = Path(__file__).resolve().parents[1]
FULL_AGENT_SESSION = ROOT / "scripts" / "full_agent_session.py"
DEFAULT_TAILSCALE_SOCKET = "/tmp/tailscaled-decision-inbox.sock"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Connected Agent product readiness without opening it."
    )
    parser.add_argument(
        "--advisor-channel",
        choices=["unknown", "manual", "user-web", "browser-automation", "direct-tool"],
        default="unknown",
    )
    parser.add_argument(
        "--advisor-health",
        choices=["unknown", "ready", "blank", "timeout", "unavailable", "needs-browser-restart"],
        default="unknown",
    )
    parser.add_argument("--tailscale-bin", default="tailscale")
    parser.add_argument("--socket", default=DEFAULT_TAILSCALE_SOCKET)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    session = run_status([sys.executable, str(FULL_AGENT_SESSION), "status"])
    funnel = run_status([args.tailscale_bin, "--socket", args.socket, "funnel", "status"])
    session_state = parse_session_state(session.stdout)
    gate = evaluate_gate(
        mode="connected-agent",
        advisor_channel=args.advisor_channel,
        advisor_health=args.advisor_health,
        session_state=session_state,
    )
    print(render_report(session, funnel, gate["message"]))
    return int(gate["exit_code"])


def run_status(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def parse_session_state(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("Current state:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def render_report(
    session: subprocess.CompletedProcess[str],
    funnel: subprocess.CompletedProcess[str],
    gate_message: str,
) -> str:
    summary = summarize_state(session.stdout, funnel.stdout, gate_message)
    sections = [
        "Connected Agent product status:",
        indent(summary),
        "",
        "Connected Agent readiness:",
        gate_message,
        "",
        "Connected Agent session status:",
        indent(session.stdout.strip() or f"command exited {session.returncode}"),
        "",
        "Tailscale Funnel status:",
        indent(funnel.stdout.strip() or f"command exited {funnel.returncode}"),
    ]
    return "\n".join(sections)


def summarize_state(session_output: str, funnel_output: str, gate_message: str) -> str:
    session_state = parse_session_state(session_output)
    session_closed = session_state == "full_agent_session_closed"
    funnel_closed = "No serve config" in funnel_output
    waiting_for_advisor = "Current state: waiting_for_advisor_channel" in gate_message
    ready_to_open = "Current state: ready_to_open_connected_agent" in gate_message

    lines = []
    if ready_to_open:
        lines.append("Can use now: yes, after opening the short Connected Agent task window.")
        lines.append("User step: keep ChatGPT Web ready with the Connected Agent connector attached.")
    elif waiting_for_advisor:
        lines.append("Can use now: not yet.")
        lines.append(
            "User step: open ChatGPT Web with the Connected Agent connector, or authorize browser automation."
        )
    else:
        lines.append("Can use now: check the detailed readiness state below.")

    if session_closed and funnel_closed:
        lines.append("Exposure now: closed.")
        lines.append("Risk now: 2/5 if OAuth state remains, otherwise 1/5.")
    elif not session_closed:
        lines.append("Exposure now: Connected Agent session may be open.")
        lines.append("Risk now: 3/5-5/5 until closed.")
    else:
        lines.append("Exposure now: session closed; inspect Funnel status below.")

    lines.append(
        "Normal flow: prepare -> ChatGPT Web with Connected Agent connector -> capture -> 20-minute idle close."
    )
    return "\n".join(lines)


def indent(value: str) -> str:
    return "\n".join(f"  {line}" for line in value.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
