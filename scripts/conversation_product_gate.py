#!/usr/bin/env python3
"""Side-effect-free product gate for conversation advisor workflows."""

import argparse
import sys
from typing import List, Optional


MODES = {"manual", "ask-first", "connected-agent", "read-only-project", "full-agent"}
ADVISOR_CHANNELS = {"unknown", "manual", "user-web", "browser-automation", "direct-tool"}
ADVISOR_HEALTH = {"unknown", "ready", "blank", "timeout", "unavailable", "needs-browser-restart"}
NOT_CONSULTED_NOTICE = (
    "GPT Pro has not been consulted yet; the system is still preparing or waiting."
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether a conversation product workflow may proceed."
    )
    parser.add_argument("--mode", choices=sorted(MODES), required=True)
    parser.add_argument(
        "--advisor-channel",
        choices=sorted(ADVISOR_CHANNELS),
        default="unknown",
    )
    parser.add_argument(
        "--advisor-health",
        choices=sorted(ADVISOR_HEALTH),
        default="unknown",
        help="Observed advisor surface health. Use ready only after a real prompt box/tool is available.",
    )
    parser.add_argument(
        "--session-state",
        default="not_open",
        help="Observed Full-Agent session state for reporting only.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    result = evaluate_gate(
        mode=args.mode,
        advisor_channel=args.advisor_channel,
        advisor_health=args.advisor_health,
        session_state=args.session_state,
    )
    print(result["message"])
    return int(result["exit_code"])


def evaluate_gate(
    mode: str,
    advisor_channel: str,
    advisor_health: str,
    session_state: str = "not_open",
) -> dict[str, object]:
    if mode not in MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    if advisor_channel not in ADVISOR_CHANNELS:
        raise ValueError(f"Unsupported advisor channel: {advisor_channel}")
    if advisor_health not in ADVISOR_HEALTH:
        raise ValueError(f"Unsupported advisor health: {advisor_health}")

    if mode in {"manual", "ask-first"}:
        return status(
            current_state="manual_package_available",
            requested_mode=mode,
            session_state="not_required",
            risk="1/5",
            reason="Manual Package does not require a live advisor connector.",
            next_step="Create package and wait for returned advice.",
            exit_code=0,
        )

    if mode in {"read-only-project", "connected-agent"}:
        risk = "3/5-5/5" if mode == "connected-agent" else "3/5-4/5"
        if advisor_ready(advisor_channel, advisor_health):
            return status(
                current_state=(
                    "ready_to_open_connected_agent"
                    if mode == "connected-agent"
                    else "ready_to_open_read_only_project"
                ),
                requested_mode=mode,
                session_state=session_state,
                risk=risk,
                reason="A usable advisor channel is available.",
                next_step=(
                    "Open the Connected Agent connector window."
                    if mode == "connected-agent"
                    else "Open the read-only project connector window."
                ),
                exit_code=0,
            )
        return waiting(
            mode=mode,
            session_state=session_state,
            risk=risk,
            reason=advisor_blocker_reason(advisor_channel, advisor_health),
        )

    if advisor_ready(advisor_channel, advisor_health):
        return status(
            current_state="ready_to_open_full_agent",
            requested_mode=mode,
            session_state=session_state,
            risk="5/5",
            reason="A usable advisor channel is available.",
            next_step="Open Full-Agent only for the active consultation window.",
            exit_code=0,
        )

    return waiting(
        mode=mode,
        session_state=session_state,
        risk="5/5",
        reason=advisor_blocker_reason(advisor_channel, advisor_health),
    )


def advisor_ready(advisor_channel: str, advisor_health: str) -> bool:
    if advisor_channel == "direct-tool":
        return advisor_health == "ready"
    if advisor_channel == "browser-automation":
        return advisor_health == "ready"
    if advisor_channel == "user-web":
        return advisor_health == "ready"
    return False


def advisor_blocker_reason(advisor_channel: str, advisor_health: str) -> str:
    if advisor_channel in {"unknown", "manual"}:
        return "Codex does not currently have a live web advisor channel."
    if advisor_health == "blank":
        return "ChatGPT Web is open but rendered blank, so no advisor prompt is available."
    if advisor_health == "timeout":
        return "Browser automation timed out before a usable advisor prompt was available."
    if advisor_health == "unavailable":
        return "The advisor channel is unavailable."
    if advisor_health == "needs-browser-restart":
        return "Browser automation cannot access ChatGPT Web; restart the browser after user confirmation."
    return "Advisor channel health is unknown."


def waiting(mode: str, session_state: str, risk: str, reason: str) -> dict[str, object]:
    return status(
        current_state="waiting_for_advisor_channel",
        requested_mode=mode,
        session_state=session_state,
        risk=risk,
        reason=reason,
        next_step=(
            "Restore or manually open ChatGPT Web, authorize browser automation, "
            "confirm browser restart if needed, or fall back to Manual Package."
        ),
        exit_code=2,
    )


def status(
    current_state: str,
    requested_mode: str,
    session_state: str,
    risk: str,
    reason: str,
    next_step: str,
    exit_code: int,
) -> dict[str, object]:
    message = "\n".join(
        [
            f"Current state: {current_state}",
            f"Requested mode: {requested_mode}",
            f"Session state: {session_state}",
            f"Risk if opened: {risk}",
            f"Reason: {reason}",
            f"Next step: {next_step}",
        ]
    )
    if current_state == "waiting_for_advisor_channel":
        message = "\n".join([message, NOT_CONSULTED_NOTICE])
    return {"message": message, "exit_code": exit_code}


if __name__ == "__main__":
    raise SystemExit(main())
