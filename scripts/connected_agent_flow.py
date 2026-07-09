#!/usr/bin/env python3
"""Product-name alias for the Connected Agent consultation wrapper."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.level3_consultation_flow import main as level3_main  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    return level3_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
