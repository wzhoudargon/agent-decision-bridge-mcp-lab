#!/usr/bin/env python3
"""Render a safe ChatGPT Web prompt for a Level 3 consultation."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAFE_FILES = [
    "README.md",
    "docs/security-public.md",
    "docs/conversation-product-mode.md",
]
DEEP_REVIEW_FILES = [
    *DEFAULT_SAFE_FILES,
    "PROJECT_CONTEXT.md",
    "docs/phase-5-full-agent-live-verification.md",
]
HARD_DENY_PARTS = {
    ".env",
    ".git",
    ".ssh",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    ".docker",
    ".gnupg",
}
HARD_DENY_FILENAMES = {
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
    "token.json",
    "oauth-state.json",
    "oauth-owner-token",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
HARD_DENY_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
PROTECTED_BOUNDARY = [
    ".env and .env.* files",
    ".git directories and Git internals",
    ".ssh, .aws, .azure, .gcloud, .kube, .docker, and .gnupg directories",
    "private-key material such as .pem, .key, .p12, and .pfx files",
    "known credential files such as .npmrc, .pypirc, .netrc, token.json, credentials.json, oauth-state.json, and oauth-owner-token",
    "browser data, cookies, keychains, and unrelated user files unless the current Codex user explicitly allows them",
]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a copyable prompt for ChatGPT Web when the Full-Agent "
            "connector is already attached to the conversation."
        )
    )
    parser.add_argument("question", help="User's Level 3 consultation question.")
    parser.add_argument(
        "--allowed-root",
        default=str(ROOT),
        help="Workspace root the Full-Agent connector should open.",
    )
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        default=[],
        help=(
            "Safe relative file to request. If omitted, the prompt asks the "
            "advisor to inspect task-relevant files under the allowed root."
        ),
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help=(
            "Use the larger product-review file set. Default is self-directed "
            "task-relevant inspection."
        ),
    )
    parser.add_argument(
        "--advisor-name",
        default="Agent Decision Bridge Full-Agent Live",
        help="Visible ChatGPT connector name to call out in the prompt.",
    )
    parser.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy the rendered prompt to the local clipboard when pbcopy is available.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        prompt = render_prompt(
            question=args.question,
            allowed_root=args.allowed_root,
            files=args.files if args.files else (DEEP_REVIEW_FILES if args.deep else None),
            advisor_name=args.advisor_name,
        )
    except ValueError as exc:
        print(f"level3_consultation_prompt: {exc}", file=sys.stderr)
        return 1
    print("Current state: level3_prompt_ready")
    print("Risk if opened: 5/5")
    exit_code = 0
    if args.clipboard:
        try:
            copy_to_clipboard(prompt)
        except RuntimeError as exc:
            print(f"Clipboard: failed ({exc})", file=sys.stderr)
            exit_code = 1
        else:
            print("Clipboard: copied")
    print("Prompt:")
    print(prompt)
    return exit_code


def render_prompt(
    question: str,
    allowed_root: str,
    files: Optional[Iterable[str]] = None,
    advisor_name: str = "Agent Decision Bridge Full-Agent Live",
) -> str:
    clean_question = " ".join(question.strip().split())
    if not clean_question:
        raise ValueError("question must be non-empty")
    root = str(Path(allowed_root).expanduser())
    safe_files = validate_files(files) if files is not None else []
    file_instruction = render_file_instruction(safe_files)
    protected_list = "\n".join(f"- {item}" for item in PROTECTED_BOUNDARY)
    return f"""Model requirement:
Use GPT-5.5 Thinking, not GPT-5.5 Pro. GPT-5.5 Pro does not expose ChatGPT Apps/MCP connector tools. If this conversation cannot see the attached connector tools, stop and ask the user to switch to GPT-5.5 Thinking with the connector attached.

Use only the attached {advisor_name} connector. Do not answer from chat memory.

Task:
{clean_question}

Connector steps:
1. Open this workspace root:
   {root}
2. {file_instruction}
3. Use only connector tools. For context inspection, use ls, glob, grep, and read. For write, edit, or bash, follow the approval rule in step 5. Do not use Python, browser file checks, uploads, screenshots, or chat-only guesses.
4. Protected boundary. Do not read, search, write, edit, or run commands against:
{protected_list}
5. Inspect first. For any write, edit, or bash action, first ask the user for approval of the exact file or command, the intended change, and the risk. Only call that tool after the user approves that specific action.
6. If protected information seems necessary, stop and ask for a sanitized summary instead of trying to access it.

Reply in Chinese with:
1. whether the Level 3 connector truly worked,
2. exactly which files were listed, searched, read, denied, or failed,
3. `Adopt`, `Ask`, and `Reject` recommendations,
4. the two smallest fixes needed for smoother user use,
5. any remaining risk, including the fact that Level 3 is 5/5 while online.
"""


def render_file_instruction(files: List[str]) -> str:
    if files:
        file_list = "\n".join(f"   - {item}" for item in files)
        return (
            f"Read exactly these {len(files)} files through the connector, "
            f"then stop file inspection unless the task clearly requires more:\n{file_list}"
        )
    return (
        "Inspect only task-relevant project files through the connector. Start "
        "with a concise directory listing and targeted glob/grep searches, then "
        "read the smallest set of files needed to answer the task."
    )


def validate_files(files: Iterable[str]) -> List[str]:
    safe: List[str] = []
    for raw in files:
        value = raw.strip()
        if not value:
            continue
        path = Path(value)
        if path.is_absolute():
            raise ValueError(f"file must be relative: {value}")
        parts = {part.lower() for part in path.parts}
        name = path.name.lower()
        if ".." in path.parts:
            raise ValueError(f"parent traversal is not allowed: {value}")
        if parts & HARD_DENY_PARTS:
            raise ValueError(f"protected path is not allowed: {value}")
        if name.startswith(".env"):
            raise ValueError(f"protected path is not allowed: {value}")
        if name in HARD_DENY_FILENAMES:
            raise ValueError(f"protected path is not allowed: {value}")
        if path.suffix.lower() in HARD_DENY_SUFFIXES:
            raise ValueError(f"protected path is not allowed: {value}")
        safe.append(value)
    if not safe:
        raise ValueError("at least one safe file is required")
    return safe


def copy_to_clipboard(text: str) -> None:
    if not shutil.which("pbcopy"):
        raise RuntimeError("pbcopy is not available on this system")
    completed = subprocess.run(["pbcopy"], input=text, text=True)
    if completed.returncode != 0:
        raise RuntimeError("pbcopy failed")


if __name__ == "__main__":
    raise SystemExit(main())
