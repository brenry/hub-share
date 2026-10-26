#!/bin/bash
# SessionStart hook (.claude/settings.json) and a command to run by hand: makes the dev tools ready in a cloud
# session. Builds .venv from the two hash-pinned locks and installs web/node_modules, skipping each when the lock it
# was built from is unchanged. Outside a cloud session it does nothing unless given --force. Never exits non-zero: a
# failure is reported on stdout, where the session reads it, and the session goes on.
set -u
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${1:-}" != "--force" ]; then
  exit 0
fi
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
cd "$ROOT" 2>/dev/null || { echo "session-start: no repository root found"; exit 0; }

status=""
PY_STAMP=.venv/.locks.sha256
if ! { [ -x .venv/bin/ruff ] && [ -x .venv/bin/python ] && [ -f "$PY_STAMP" ] && sha256sum -c --quiet "$PY_STAMP" >/dev/null 2>&1; }; then
  if python3 -m venv .venv \
     && .venv/bin/python -m pip install -q --disable-pip-version-check --require-hashes -r requirements/controller.lock -r requirements/dev.lock \
     && sha256sum requirements/controller.lock requirements/dev.lock > "$PY_STAMP"; then
    status="$status .venv built;"
  else
    rm -f "$PY_STAMP"
    status="$status .venv FAILED (run: python3 -m venv .venv && .venv/bin/python -m pip install --require-hashes -r requirements/controller.lock -r requirements/dev.lock);"
  fi
else
  status="$status .venv current;"
fi

WEB_STAMP=web/node_modules/.lock.sha256
if ! { [ -d web/node_modules ] && [ -f "$WEB_STAMP" ] && sha256sum -c --quiet "$WEB_STAMP" >/dev/null 2>&1; }; then
  if (cd web && npm ci --no-audit --no-fund --silent) && sha256sum web/package-lock.json > "$WEB_STAMP"; then
    status="$status web/node_modules installed;"
  else
    rm -f "$WEB_STAMP"
    status="$status web/node_modules FAILED (run: cd web && npm ci);"
  fi
else
  status="$status web/node_modules current;"
fi

echo "Dev tools:$status ruff/pytest at .venv/bin, web tests via npm in web/."
exit 0
