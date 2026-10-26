"""Which of the Hub's saved engine arguments upstream WanGP takes. Run by the engine's own Python from its folder:

    cd <app> && <env>/bin/python -I -B <this file> <app> ARGS...

Upstream refuses the whole start on an argument it does not know (its parser's `parse_args`,
shared/cli_args.py) or an attention mode it does not have (wgp.py:3464-3470). So each option, with the values that
follow it, is kept only when upstream's own parser takes it beside those already kept. Prints the kept arguments as a
JSON list; each one left out is named on stderr.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys

ATTENTION = ("auto", "sdpa", "sage", "sage2", "flash", "xformers")      # wgp.py:3465
CONFIG = "wgp_config.json"


def groups(args: list[str]) -> list[list[str]]:
    out: list[list[str]] = []
    for arg in args:
        if arg.startswith("-") or not out:
            out.append([arg])
        else:
            out[-1].append(arg)
    return out


def takes(parse, args: list[str]) -> bool:
    try:
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            parsed = parse(CONFIG, args)
    except SystemExit:
        return False
    return not getattr(parsed, "attention", "") or parsed.attention in ATTENTION


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    sys.path.insert(0, argv[0])
    from shared.cli_args import parse_wgp_args
    kept: list[str] = []
    for group in groups(argv[1:]):
        if takes(parse_wgp_args, [*kept, *group]):
            kept += group
        else:
            print(f"Left out of the engine's arguments: {' '.join(group)} (upstream does not take it)",
                  file=sys.stderr)
    print(json.dumps(kept))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
