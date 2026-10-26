"""Lay out a full-stack run in a temp folder: a fake engine root. Prints the paths as JSON."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tests.engine.helpers import make_engine_root  # noqa: E402


def main(base: Path) -> None:
    print(json.dumps({"engine": str(make_engine_root(base, "upstream"))}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
