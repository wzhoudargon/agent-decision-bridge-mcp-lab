#!/usr/bin/env python3
"""Prepare a Decision Inbox consultation task from a conversational request."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS_ROOT = ROOT / "decision-inbox" / "tasks"
TASK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_RE = re.compile(r"[^a-z0-9]+")
VALID_MODES = {"ask-first", "auto-mcp", "read-only-project", "full-agent"}
PACKAGE_MODES = {"ask-first", "auto-mcp"}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a conversation-first Decision Inbox consultation package."
    )
    parser.add_argument("question", help="User consultation request.")
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default="auto-mcp",
        help="Product tier requested by the user.",
    )
    parser.add_argument("--title", default=None)
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--advisor", default="chatgpt-pro")
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    parser.add_argument(
        "--allowed-root",
        action="append",
        default=[],
        help="Allowed workspace root for Full-Agent consultations.",
    )
    parser.add_argument(
        "--advisor-channel",
        choices=["unknown", "manual", "user-web", "browser-automation", "direct-tool"],
        default="unknown",
        help="How Codex can reach the external advisor in the current environment.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = create_consultation_task(
            tasks_root=args.tasks_root,
            question=args.question,
            mode=args.mode,
            title=args.title,
            task_id=args.task_id,
            advisor=args.advisor,
            allowed_roots=args.allowed_root,
            advisor_channel=args.advisor_channel,
        )
    except Exception as exc:
        print(f"prepare_consultation: {exc}", file=sys.stderr)
        return 1
    print(render_status(result))
    return 0


def create_consultation_task(
    tasks_root: Path,
    question: str,
    mode: str,
    title: Optional[str] = None,
    task_id: Optional[str] = None,
    advisor: str = "chatgpt-pro",
    allowed_roots: Optional[List[str]] = None,
    advisor_channel: str = "unknown",
) -> Dict[str, Any]:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    if mode not in PACKAGE_MODES:
        raise ValueError(
            f"{mode} does not create a decision package. Use direct workspace MCP tools instead."
        )
    if not question.strip():
        raise ValueError("question must be non-empty")
    tasks_root.mkdir(parents=True, exist_ok=True)
    task_title = title or title_from_question(question)
    resolved_task_id = task_id or unique_task_id(tasks_root, task_title)
    validate_task_id(resolved_task_id)
    task_dir = tasks_root / resolved_task_id
    if task_dir.exists():
        raise FileExistsError(f"Task already exists: {resolved_task_id}")
    task_dir.mkdir()
    (task_dir / "advice").mkdir()
    (task_dir / "fact-check-requests").mkdir()

    now = utc_timestamp()
    normalized_allowed_roots = [str(Path(item).expanduser()) for item in (allowed_roots or [])]
    metadata = {
        "task_id": resolved_task_id,
        "title": task_title,
        "status": "package_ready",
        "created_at": now,
        "updated_at": now,
        "created_by": "codex",
        "advisor_rounds": 0,
        "product_mode": mode,
        "advisor": advisor,
        "advisor_channel": advisor_channel,
        "risk_level": risk_level(mode),
        "allowed_roots": normalized_allowed_roots,
        "allowed_inputs": ["metadata.json", "package.md", "advice/*.md"],
        "disallowed_inputs": disallowed_inputs(mode),
        "next_local_action": next_local_action(mode, advisor_channel, resolved_task_id),
    }
    (task_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
    )
    (task_dir / "package.md").write_text(
        render_package(
            title=task_title,
            question=question,
            mode=mode,
            advisor=advisor,
            allowed_roots=normalized_allowed_roots,
            advisor_channel=advisor_channel,
        ),
        encoding="utf-8",
    )
    return {
        "task_id": resolved_task_id,
        "task_dir": task_dir,
        "package_path": task_dir / "package.md",
        "metadata_path": task_dir / "metadata.json",
        "mode": mode,
        "advisor": advisor,
        "advisor_channel": advisor_channel,
        "risk_level": metadata["risk_level"],
        "next_local_action": metadata["next_local_action"],
    }


def render_package(
    title: str,
    question: str,
    mode: str,
    advisor: str,
    allowed_roots: List[str],
    advisor_channel: str,
) -> str:
    full_agent_notes = ""
    if mode == "full-agent":
        roots = "\n".join(f"- {root}" for root in allowed_roots) or "- Not provided yet"
        full_agent_notes = f"""
## Full-Agent Boundary

- Requested mode: Full-Agent.
- Risk while online: 5/5.
- Allowed roots:
{roots}
- Full-Agent may expose file read/write/edit/search and bash under configured allowed roots.
- Do not treat tool access as authorization to make destructive changes.
- External advice only. This is not authorization.
"""
    return f"""# {title}

## Instructions For The External Advisor

You are an external advisor. Use only the facts in this package unless a
separate Full-Agent connector is intentionally active in this same conversation.
Do not assume access to local files, screenshots, code, logs, Git state, shell
commands, browser data, or previous chat history that is not provided or exposed
through the active connector.

External advice only. This is not authorization.

## Product Mode

- Requested mode: {mode}
- Target advisor: {advisor}
- Advisor channel visible to Codex now: {advisor_channel}
- If no advisor tool/connector is visible in the current conversation, report
  that the workflow is waiting for an advisor channel instead of pretending that
  an advisor was called.

{full_agent_notes}
## User Question

{question.strip()}

## Current Facts

- Codex is the local fact checker and executor.
- External model output is advice, not authorization.
- The user wants a conversation-first product flow, not manual backend command handling.
- Material recommendations must be imported back into Codex and classified.

## Constraints

- Do not request secrets, credentials, browser data, full private dumps, or broad
  filesystem access.
- Do not ask Auto MCP to run shell, inspect Git, install dependencies, or edit files.
- Do not merge Auto MCP and Full-Agent scopes.
- If Full-Agent is used, keep the session short and close it after idle timeout.

## Please Output

1. Recommended approach
2. Why this approach
3. What should be adopted
4. What should be changed or asked about
5. What should be rejected
6. Concrete next steps for Codex
7. Verification or acceptance criteria
8. Main risks

When writing advice back through MCP, include the exact marker:

```text
External advice only. This is not authorization.
```
"""


def render_status(result: Dict[str, Any]) -> str:
    task_id = result["task_id"]
    mode = result["mode"]
    lines = [
        "Current state: consultation_package_ready",
        f"Mode: {mode}",
        f"Risk coefficient: {result['risk_level']}",
        f"Advisor channel: {result['advisor_channel']}",
        f"Task id: {task_id}",
        f"Package: {result['package_path']}",
        f"Next local action: {result['next_local_action']}",
    ]
    if result["advisor_channel"] in {"unknown", "manual", "user-web"}:
        lines.extend(
            [
                "",
                "Advisor prompt:",
                advisor_prompt(mode, task_id, result["advisor"]),
            ]
        )
    return "\n".join(lines)


def advisor_prompt(mode: str, task_id: str, advisor: str) -> str:
    if mode == "auto-mcp":
        return (
            f"Use the Auto MCP Controlled Advisor connector. Call get_decision_package "
            f"for task_id={task_id}, answer only from that package, then call "
            f"submit_advice with advisor={advisor}. Include: External advice only. "
            f"This is not authorization."
        )
    if mode == "full-agent":
        return (
            f"Use the separate Full-Agent connector only if it is visible in this "
            f"conversation. If available, inspect the allowed workspace only as needed, "
            f"then provide advice for task_id={task_id}. Do not make destructive "
            f"changes unless the current user explicitly authorizes them in Codex. "
            f"Include: External advice only. This is not authorization."
        )
    return (
        f"Review the package for task_id={task_id}. Return advice only; do not claim "
        f"local access. Include: External advice only. This is not authorization."
    )


def title_from_question(question: str) -> str:
    stripped = " ".join(question.strip().split())
    return stripped[:80] or "Advisor Consultation"


def unique_task_id(tasks_root: Path, title: str) -> str:
    base = slugify(title) or "advisor-consultation"
    candidate = base[:64].strip("-") or "advisor-consultation"
    if not (tasks_root / candidate).exists():
        return candidate
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{candidate[:48].strip('-')}-{suffix}"


def slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    return re.sub(r"-+", "-", slug)


def validate_task_id(task_id: str) -> None:
    if not TASK_ID_RE.fullmatch(task_id):
        raise ValueError("task_id must be a lowercase slug using letters, numbers, and hyphens")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def risk_level(mode: str) -> str:
    if mode == "ask-first":
        return "1/5"
    if mode == "auto-mcp":
        return "1/5 local-only or 3/5 while public Auto MCP tunnel is active"
    return "5/5 while Full-Agent session is open"


def disallowed_inputs(mode: str) -> List[str]:
    base = ["secrets", "credentials", "browser data", "automatic implementation"]
    if mode != "full-agent":
        base.extend(["real project files", "shell commands", "Git operations", "dependency installation"])
    return base


def next_local_action(mode: str, advisor_channel: str, task_id: str) -> str:
    if advisor_channel == "direct-tool":
        return f"Call the visible advisor tool/connector for task {task_id}, then import advice."
    if advisor_channel == "browser-automation":
        return f"Use authorized browser/computer automation to send task {task_id}, then import advice."
    if mode == "full-agent":
        return (
            f"Open Full-Agent session, then use a visible ChatGPT Full-Agent connector for task "
            f"{task_id}; if no advisor channel is visible, wait for user-web or automation authorization."
        )
    if mode == "auto-mcp":
        return (
            f"Open Auto MCP window, then ask ChatGPT Web to read task {task_id} and submit advice; "
            f"if Codex has no advisor channel, wait for user-web or automation authorization."
        )
    return f"Give package {task_id} to the user for manual advisor review, then import advice."


if __name__ == "__main__":
    raise SystemExit(main())
