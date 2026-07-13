#!/usr/bin/env python3
"""Render a safe ChatGPT Web prompt for a Connected Agent consultation."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.connected_agent_server import (  # noqa: E402
    PROFILE_CONNECTED_AGENT,
    TOOL_CONTRACT_VERSION,
    tool_definitions,
)
DEFAULT_SAFE_FILES = [
    "README.md",
    "docs/security-public.md",
    "docs/conversation-product-mode.md",
]
DEEP_REVIEW_FILES = [
    *DEFAULT_SAFE_FILES,
    "PROJECT_CONTEXT.md",
    "docs/architecture.md",
]

CURRENT_CONNECTED_AGENT_TOOLS = [
    tool["name"] for tool in tool_definitions(PROFILE_CONNECTED_AGENT)
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
            "Create a copyable prompt for ChatGPT Web when the Connected Agent "
            "connector is already attached to the conversation."
        )
    )
    parser.add_argument("question", help="User's Connected Agent consultation question.")
    parser.add_argument(
        "--allowed-root",
        default=str(ROOT),
        help="Workspace root the Connected Agent connector should open.",
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
        default="Agent Decision Bridge Connected Agent",
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
        print(f"connected_agent_consultation_prompt: {exc}", file=sys.stderr)
        return 1
    print("Current state: connected_agent_prompt_ready")
    print("Risk if opened: 3/5-5/5")
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
    advisor_name: str = "Agent Decision Bridge Connected Agent",
) -> str:
    clean_question = " ".join(question.strip().split())
    if not clean_question:
        raise ValueError("question must be non-empty")
    safe_files = validate_files(files) if files is not None else []
    file_instruction = render_file_instruction(safe_files)
    protected_list = "\n".join(f"- {item}" for item in PROTECTED_BOUNDARY)
    required_tools = ", ".join(CURRENT_CONNECTED_AGENT_TOOLS)
    return f"""ChatGPT Web requirement:
In the Codex built-in ChatGPT dialog, or another ChatGPT surface that actually exposes Connector/App tools, type @ and select the user-created connector whose exact display name is `{advisor_name}` before sending this prompt. Let the UI create the connector chip or plugin reference; do not hand-type or reconstruct a plugin:// identifier. Writing the connector name as plain text does not attach its tools.
Use a chat mode where Apps/MCP connector tools are visible. Before starting the task, confirm that the selected `{advisor_name}` connector reference is present and that the complete current tool contract is visible:
{required_tools}
This is Connected Agent tool contract {TOOL_CONTRACT_VERSION}. If any listed tool is missing, do not inspect the project and do not continue with a degraded tool set. Stop with `connector_contract_incomplete`; ask the user to start a fresh conversation in a tool-capable ChatGPT mode, attach the exact connector again through @, and update/re-publish or reinstall it if the fresh conversation is still incomplete.

Use only the attached {advisor_name} connector. Do not answer from chat memory.
Do not fabricate the Danger Auto phrase. Only call enable_danger_auto if the user typed this exact phrase in ChatGPT Web: dangerously trust connected agent

Task:
{clean_question}

Connector steps:
1. Apply this deterministic workspace-open rule; do not ask the user to choose an entry point. If open_default_workspace is visible, call it with no arguments. Otherwise, if open_workspace is visible, call it exactly once with path "default". The "default" alias is the required legacy-schema compatibility path, not an optional suggestion, and needs neither confirmation nor a local absolute path. Never claim that a server change or explicit filesystem path is required merely because open_default_workspace is absent. After opening, verify that the returned root is the currently authorized workspace. Report failure only if the applicable visible entry point actually returns an error. Never guess or request a /Users/... path.
2. {file_instruction}
3. Use only connector tools. For context inspection, use ls, glob, grep, read, read_lines, and file_info. Prefer source files over generated assets: skip node_modules, dist/build outputs, image galleries, sourcemaps, and lockfile-sized dependency artifacts unless Codex explicitly asks for them. Whole-file read is intended for task-relevant UTF-8 files up to the server limit; for larger source files, use grep to locate relevant symbols and read_lines for bounded 1-based line ranges. Do not use Python, browser file checks, uploads, screenshots, or chat-only guesses.
4. Protected boundary. Do not read, search, write, edit, or run commands against:
{protected_list}
5. Connected Agent is the second product tier and has three internal permission modes, not three product tiers:
   - approval: the default; every side-effectful write, edit, apply_patch, bash, or run_task needs one-action approval.
   - controlled_auto: only a patch already shown by preview_patch and a task returned by list_tasks may run automatically. Raw write, edit, and bash still need approval. Call set_permission_mode only after the user clearly confirms this mode in the current chat.
   - danger_auto: the hidden 5/5 switch described below.
6. Prefer the controlled executor path for project changes: call file_info, then preview_patch, show the diff, then apply_patch. For tests, lint, or builds, call list_tasks and use run_task only for an exact returned task name. Never invent a task or add arbitrary arguments. In approval mode, if a side-effectful tool returns approval_id, show the exact action, impact, and approval_id; wait for the user's explicit approval; call grant_action_approval; retry the exact original call once with the same approval_id.
7. Danger Auto: if and only if the user typed `dangerously trust connected agent`, call enable_danger_auto with that phrase. Danger Auto may auto-run project-local write/edit and safe local bash, but server policy still blocks network commands, GUI/desktop control, clipboard access, secret paths, path escapes, and keeps dependency installs, Git remote operations, and broad destructive actions separately approval-gated.
8. If protected information seems necessary, stop and ask for a sanitized summary instead of trying to access it.

Reply in Chinese with:
1. whether the Connected Agent connector truly worked,
2. exactly which files were listed, searched, read, denied, or failed,
3. `Adopt`, `Adapt`, `Reject`, and `Need info` recommendations,
4. the two smallest fixes needed for smoother user use,
5. any remaining risk, including the fact that Connected Agent is 3/5-5/5 while online and Danger Auto is 5/5.
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
