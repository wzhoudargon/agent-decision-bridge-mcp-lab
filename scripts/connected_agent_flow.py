#!/usr/bin/env python3
"""Product-name alias for the Connected Agent consultation wrapper."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.connected_agent_consultation_flow import main as connected_agent_main  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    return connected_agent_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
