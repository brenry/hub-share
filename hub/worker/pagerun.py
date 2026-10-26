"""Upstream WanGP's own page, run by hand with the Hub stopped, so the engine fetches what the weights lack
(Stage 10; on hold). Run by the engine's Python:

    <prefix>/engine/env/bin/python -B <prefix>/hub/worker/pagerun.py <prefix>/engine/app [wgp.py arguments]

It holds every file then under the app config's checkpoint roots for the whole run (`keep.hold`: the engine's import
never erases or renames a weight file; new downloads land), then runs `wgp.py` from the app as the page, with the
app's own config (`wgp_config.json`, written by install-engine.sh: the app's own `ckpts` as checkpoint folder,
outputs in `app/outputs`). Nothing of the Hub's offline guard is on: this fetch is the page's, not the Hub's.
"""
from __future__ import annotations

import json
import os
import runpy
import sys

try:
    from . import keep
except ImportError:  # run as a script by the engine's Python
    import keep

CONFIG = "wgp_config.json"
DEFAULT_ROOTS = ("ckpts", ".")          # upstream's own when the config names none (shared/utils/files_locator.py)
USAGE = "usage: pagerun.py <engine app folder> [wgp.py arguments]"


def roots(app: str) -> list[str]:
    """The checkpoint roots the page will search and write: the app config's `checkpoints_paths` (relative to the
    app), else upstream's defaults; plus the app's `ckpts`, which upstream reaches before it reads the config."""
    try:
        with open(os.path.join(app, CONFIG), encoding="utf-8") as f:
            listed = json.load(f).get("checkpoints_paths")
    except (OSError, ValueError, AttributeError):
        listed = None
    paths = [str(p) for p in listed] if isinstance(listed, list) and listed else list(DEFAULT_ROOTS)
    out = [os.path.normpath(os.path.join(app, p)) for p in [*paths, "ckpts"]]
    return [p for i, p in enumerate(out) if p not in out[:i] and p != os.path.normpath(app)]


def main(argv: list[str]) -> int:
    if not argv or not os.path.isfile(os.path.join(argv[0], "wgp.py")):
        sys.stderr.write(USAGE + "\n")
        return 2
    app = os.path.abspath(argv[0])
    os.chdir(app)
    held = roots(app)
    noted = keep.hold(held)
    sys.stderr.write(f"Holding {noted} weight files under {', '.join(held)}: none is removed or renamed.\n")
    sys.stderr.flush()
    here = os.path.dirname(os.path.abspath(__file__))       # the worker's folder: none of its modules is the page's
    sys.path[:] = [app, *(p for p in sys.path if os.path.abspath(p or os.curdir) not in (here, app))]
    sys.argv = [os.path.join(app, "wgp.py"), *argv[1:]]
    runpy.run_path(sys.argv[0], run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
