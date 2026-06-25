#!/usr/bin/env python3
"""Delete local Decision Inbox auth files without printing secret values."""

import argparse
import os
from pathlib import Path
from typing import List, Optional


DEFAULT_STATE_FILE = Path.home() / ".local/share/decision-inbox-mcp-lab/oauth-state.json"
DEFAULT_OWNER_TOKEN_FILE = (
    Path.home() / ".local/share/decision-inbox-mcp-lab/oauth-owner-token"
)
DEFAULT_FULL_AGENT_STATE_FILE = (
    Path.home() / ".local/share/agent-decision-bridge/oauth-state.json"
)
DEFAULT_FULL_AGENT_OWNER_TOKEN_FILE = (
    Path.home() / ".local/share/agent-decision-bridge/oauth-owner-token"
)
DEFAULT_TEMP_TOKEN_FILES = [
    Path("/tmp/decision-inbox-mcp-token"),
    Path("/tmp/decision-inbox-oauth-owner-token"),
]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove local Decision Inbox OAuth/bearer auth files."
    )
    parser.add_argument(
        "--oauth-state-file",
        type=Path,
        default=Path(os.environ.get("DECISION_INBOX_OAUTH_STATE_FILE", DEFAULT_STATE_FILE)),
        help="OAuth state JSON file to delete.",
    )
    parser.add_argument(
        "--oauth-owner-token-file",
        type=Path,
        default=Path(
            os.environ.get(
                "DECISION_INBOX_OAUTH_OWNER_TOKEN_FILE",
                DEFAULT_OWNER_TOKEN_FILE,
            )
        ),
        help="OAuth Owner password file to delete.",
    )
    parser.add_argument(
        "--include-temp-files",
        action="store_true",
        help="Also delete legacy /tmp token files used by temporary connector runs.",
    )
    parser.add_argument(
        "--full-agent-defaults",
        action="store_true",
        help="Delete the default Full-Agent OAuth state and Owner password files.",
    )
    return parser.parse_args(argv)


def remove_path(path: Path) -> str:
    path = path.expanduser()
    if not path.exists() and not path.is_symlink():
        return "missing"
    if path.is_dir():
        return "refused_directory"
    path.unlink()
    return "removed"


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    targets = [
        ("oauth_state_file", args.oauth_state_file),
        ("oauth_owner_token_file", args.oauth_owner_token_file),
    ]
    if args.full_agent_defaults:
        targets = [
            ("full_agent_oauth_state_file", DEFAULT_FULL_AGENT_STATE_FILE),
            ("full_agent_oauth_owner_token_file", DEFAULT_FULL_AGENT_OWNER_TOKEN_FILE),
        ]
    if args.include_temp_files:
        targets.extend(
            (f"temp_token_file_{index}", path)
            for index, path in enumerate(DEFAULT_TEMP_TOKEN_FILES, 1)
        )

    for label, path in targets:
        status = remove_path(path)
        print(f"{label}: {status} path={path.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
