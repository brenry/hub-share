# shellcheck shell=bash
# Shared by install-hub.sh, install-engine.sh and uninstall.sh. Sourced, never run on its own.
#
# The record: every folder, file, service, setting and firewall rule an install makes is written, as it
# happens, to a ".installed" file. uninstall.sh undoes exactly those entries, newest first, and nothing else.
# If an install stops with an error, what that run did is undone the same way, and anything it had moved
# aside (an earlier version) is put back.

# shellcheck disable=SC2034 # the variables below are used by the scripts that source this file
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REL=$(dirname -- "$HERE")
CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
UNIT_DIR=$CONFIG_HOME/systemd/user
WANTS_DIR=$UNIT_DIR/default.target.wants
SAFE_PATH='^/[A-Za-z0-9._/+-]+$'

if [ -t 1 ]; then C=$'\033[1;36m' Y=$'\033[1;33m' R=$'\033[1;31m' N=$'\033[0m'; else C='' Y='' R='' N=''; fi
say()  { printf '%s==>%s %s\n' "$C" "$N" "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '%s !!%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '%s xx%s %s\n' "$R" "$N" "$*" >&2; exit 1; }

ASSUME_YES=0
ask() { # question: true for yes. Without a terminal (and without --yes) the answer is no.
  local answer
  [ "$ASSUME_YES" -eq 0 ] || return 0
  [ -t 0 ] || return 1
  read -r -p "$C??$N $1 [Y/n] " answer || return 1
  case "$answer" in '' | y | Y | yes | Yes | YES) return 0 ;; *) return 1 ;; esac
}

need_user() { # HUB_INSTALL_TEST=1: the installers' own tests, which run as root in a sandbox
  [ "$(id -u)" -ne 0 ] || [ "${HUB_INSTALL_TEST:-}" = 1 ] || die "Run this as your normal user, without sudo."
  command -v systemctl >/dev/null || die "systemd was not found; this installer needs a systemd Linux."
  systemctl --user show-environment >/dev/null 2>&1 ||
    die "Your user services are not reachable. Run this from a normal login (a desktop terminal or ssh), not su."
}

find_python() { # [file]: sets PY and PYVER to a system Python 3.13 or 3.14
  PY=${1:-}
  if [ -z "$PY" ] && [ -x /usr/bin/python3 ]; then PY=/usr/bin/python3; fi
  if [ -z "$PY" ]; then PY=$(command -v python3 || true); fi
  [ -n "$PY" ] && [ -x "$PY" ] || die "python3 was not found. This computer needs Python 3.13 or 3.14."
  PYVER=$("$PY" -I -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || die "$PY does not start."
  case "$PYVER" in 3.13 | 3.14) ;; *) die "Found Python $PYVER ($PY). The hub needs Python 3.13 or 3.14." ;; esac
  "$PY" -I -c 'import venv, ensurepip' 2>/dev/null || die "$PY cannot make Python environments (venv is missing)."
}

find_prefix() { # sets PREFIX when it is empty: the install this computer's `hub` launcher points at, else $HOME/hub
  [ -n "${PREFIX:-}" ] && return 0
  local launcher=$HOME/.local/bin/hub found=''
  if [ -f "$launcher" ]; then
    found=$(sed -n 's|^HUB_DATA=.* exec \(.*\)/venv/bin/python .*$|\1|p' "$launcher" | head -n 1)
  fi
  PREFIX=${found:-$HOME/hub}
}
check_path() { [[ "$1" =~ $SAFE_PATH ]] || die "Use a folder path with only letters, digits and . _ - + / (no spaces): $1"; }

check_target() { # folder, names...: refuse to write over those names in a folder this installer did not make
  local dir=$1 name
  shift
  [ ! -f "$dir/.installed" ] || return 0
  for name in "$@"; do
    [ ! -e "$dir/$name" ] || die "$dir/$name already exists and was not made by this installer. Move it away first."
  done
}

ours() { [ -n "$RECORD" ] && [ -f "$RECORD" ] && grep -qxF -- "file"$'\t'"$1" "$RECORD"; } # file: in our record?

RECORD=''      # the .installed file of this install
RECORD_BASE=0  # its line count before this run; -1 when this run made it
RUN=()         # "P|T<TAB>entry" for everything this run did, oldest first (P: kept in the record, T: run only)
FINISHED=0
KEPT=()
UNITS_CHANGED=0
STAGE=''

entry() { local IFS=$'\t'; printf '%s' "$*"; }
did() { # kind args...: made by this run; recorded so uninstall.sh can remove it
  RUN+=("P"$'\t'"$(entry "$@")")
  if [ -n "$RECORD" ]; then printf '%s\n' "$(entry "$@")" >>"$RECORD"; fi
}
did_temp() { RUN+=("T"$'\t'"$(entry "$@")"); } # kind args...: undone only if this run fails

open_record() { # file label
  local item
  RECORD=$1
  if [ -f "$RECORD" ]; then
    RECORD_BASE=$(wc -l <"$RECORD")
    return 0
  fi
  RECORD_BASE=-1
  (umask 077 && printf '# Hub installer record (%s): uninstall.sh removes these, newest first.\n' "$2" >"$RECORD")
  for item in "${RUN[@]}"; do
    if [ "${item%%$'\t'*}" = P ]; then printf '%s\n' "${item#*$'\t'}" >>"$RECORD"; fi
  done
}

make_dir() { # folder: make it and any missing parents, recording each one made
  local p=$1 missing=()
  while [ ! -e "$p" ]; do missing=("$p" "${missing[@]}") && p=$(dirname -- "$p"); done
  [ -d "$p" ] || die "$p is not a folder."
  for p in "${missing[@]}"; do
    mkdir -- "$p" 2>/dev/null || die "Cannot create $p (no permission?)."
    did dir "$p"
  done
}

new_stage() { # folder for this run's scratch and for earlier versions moved aside
  STAGE=$1
  rm -rf -- "$STAGE"
  mkdir -p -- "$STAGE/old"
  did_temp tree "$STAGE"
}

replace_dir() { # folder [kind]: move an earlier version aside (put back if this run fails), or record a new one
  local old
  if [ -e "$1" ]; then
    old=$STAGE/old/$(printf '%s' "$1" | sha256sum | cut -c1-16)
    mv -- "$1" "$old"
    did_temp swap "$1" "$old"
  else
    did "${2:-tree}" "$1"
  fi
}

put_file() { # file, content on stdin: write it, recording a new file or keeping the old one for a rollback
  local new old
  new=$(mktemp -p "$STAGE")
  cat >"$new"
  if [ -e "$1" ] && cmp -s -- "$new" "$1"; then rm -f -- "$new" && return 0; fi
  if [ -e "$1" ]; then
    old=$(mktemp -p "$STAGE") && cp -p -- "$1" "$old"
    did_temp swap "$1" "$old"
  else
    did file "$1"
  fi
  chmod 644 -- "$new"
  mv -f -- "$new" "$1"
}

copy_tree() { # source folder, new destination folder (code only: no tests or caches)
  mkdir -p -- "$2"
  tar -C "$1" --exclude=__pycache__ --exclude='*.pyc' --exclude=tests --exclude=.pytest_cache -cf - . |
    tar -C "$2" -xf - || die "Copying $1 failed."
}

build_venv() { # venv folder, lock file, folder for the .pth: remade only when the lock or the Python changed
  local venv=$1 lock=$2 stamp site
  stamp="$(sha256sum <"$lock" | cut -c1-64) python$PYVER"
  if [ -x "$venv/bin/python" ] && [ "$(cat -- "$venv/.hub-lock" 2>/dev/null)" = "$stamp" ]; then return 0; fi
  replace_dir "$venv"
  "$PY" -I -m venv "$venv" || die "Could not make the Python environment in $venv."
  PIP_CONFIG_FILE=/dev/null "$venv/bin/python" -I -m pip install --quiet --no-index --find-links "$REL/wheels" \
    --require-hashes --only-binary=:all: --no-cache-dir --disable-pip-version-check --no-input -r "$lock" ||
    die "Installing the bundled Python packages failed (see the lines above)."
  PIP_CONFIG_FILE=/dev/null "$venv/bin/python" -I -m pip uninstall --quiet --yes --disable-pip-version-check pip ||
    die "Could not tidy the Python environment."
  site=$("$venv/bin/python" -I -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
  printf '%s\n' "$3" >"$site/hub-app.pth"
  printf '%s\n' "$stamp" >"$venv/.hub-lock"
}

unit_active() { systemctl --user is-active --quiet "$1" 2>/dev/null; }

stop_service() { # unit: stop it for this run; a failed run starts the earlier one again
  if unit_active "$1"; then
    did_temp service "$1" active
    systemctl --user stop "$1"
  else
    did_temp service "$1" inactive
  fi
}

install_unit() { # unit name, content on stdin; refuses to replace a unit the hub did not make
  local file=$UNIT_DIR/$1
  if [ -e "$file" ] && ! ours "$file"; then die "$file already exists and was not made by this installer."; fi
  make_dir "$UNIT_DIR"
  put_file "$file"
}

enable_unit() { # unit: enable it to start at boot or login, recording what enabling made
  local had_wants=1
  [ -d "$WANTS_DIR" ] || had_wants=0
  systemctl --user daemon-reload
  if ! systemctl --user is-enabled --quiet "$1" 2>/dev/null; then
    systemctl --user enable --quiet "$1"
    if [ "$had_wants" -eq 0 ] && [ -d "$WANTS_DIR" ]; then did dir "$WANTS_DIR"; fi
    did enable "$1"
  fi
}

firewall() { sudo firewall-cmd --quiet "$@"; }

undo() { # mode (rollback|uninstall|purge) kind args...
  local mode=$1 kind=$2
  shift 2
  case "$kind" in
    dir) rmdir -- "$1" 2>/dev/null || [ ! -e "$1" ] || KEPT+=("$(entry dir "$1")") ;;
    tree) rm -rf -- "$1" ;;
    data | uninstaller) if [ "$mode" = uninstall ]; then KEPT+=("$(entry "$kind" "$1")"); else rm -rf -- "$1"; fi ;;
    file) rm -f -- "$1" && if [[ "$1" == "$UNIT_DIR"/* ]]; then UNITS_CHANGED=1; fi ;;
    swap) rm -rf -- "$1" && mv -- "$2" "$1" && UNITS_CHANGED=1 ;;
    enable) systemctl --user disable --now --quiet "$1" >/dev/null 2>&1 || true ;;
    service)
      systemctl --user daemon-reload >/dev/null 2>&1
      if [ "$2" = active ]; then systemctl --user restart "$1"; else systemctl --user stop "$1"; fi >/dev/null 2>&1 ;;
    linger)
      if [ "$mode" != rollback ] && [ -n "$(ls -A -- "$WANTS_DIR" 2>/dev/null)" ]; then
        note "Left 'start at boot' (linger) on: other services of yours use it."
      else
        loginctl disable-linger "$1" >/dev/null 2>&1 || warn "Could not turn linger off. To do it: loginctl disable-linger"
      fi ;;
    settings | restore | basepython) undo_engine "$mode" "$kind" "$@" ;;
    firewall)
      if [ "$FIREWALL_UNDO" = yes ]; then
        firewall --zone="$1" --remove-rich-rule="$2" >/dev/null 2>&1
        firewall --permanent --zone="$1" --remove-rich-rule="$2" >/dev/null 2>&1 || warn "Could not remove firewall rule: $2"
      fi ;;
  esac
  return 0
}

# The engine's entries (install-engine.sh): the scripts that write them set these first.
HUBPY='' DATA='' # the Hub's Python and data folder, for hub_engine
hub_engine() { "$HUBPY" -I -m hub engine "$1" --data "$DATA" "${@:2}"; } # action args...: the hub's engine command
undo_engine() { # mode kind args...: undo one of the engine installer's entries; what cannot be undone is kept
  local mode=$1 kind=$2
  shift 2
  case "$kind" in
    settings) # file: the engine settings the install replaced, put back (the model and LoRA folders stay as now);
      if [ ! -f "$1" ]; then :                       # none written: the run stopped before it changed them
      elif hub_engine restore --before "$1" >/dev/null; then rm -f -- "$1"; else
        warn "Could not put the old engine settings back (they are in $1)."
        KEPT+=("$(entry settings "$1")")
      fi ;;
    restore) # file copy: a file the install replaced though it did not make it, put back from its copy
      if [ ! -f "$2" ]; then :
      elif [ "$mode" = purge ]; then rm -f -- "$2"
      else mv -f -- "$2" "$1" || { warn "Could not put $1 back (it is in $2)."; KEPT+=("$(entry restore "$1" "$2")"); }
      fi ;;
    basepython) # undo file: the engine Python copied in beside its environment
      if [ "$mode" = rollback ]; then
        [ ! -f "$1" ] || python3 -I "$HERE/helpers.py" base-python-undo "$1" || warn "Could not put the engine's Python back."
        rm -f -- "$1"
      elif [ "$mode" = purge ]; then
        rm -f -- "$1"
      else
        KEPT+=("$(entry basepython "$1")")
      fi ;;
  esac
  return 0
}

FIREWALL_UNDO=yes
undo_record() { # record file, mode: undo every entry, newest first; keep a record of anything left on purpose
  local file=$1 mode=$2 lines fields i saved=("${KEPT[@]}")
  mapfile -t lines < <(grep -v '^#' -- "$file")
  rm -f -- "$file"
  KEPT=()
  for ((i = ${#lines[@]} - 1; i >= 0; i--)); do
    [ -n "${lines[i]}" ] || continue
    IFS=$'\t' read -r -a fields <<<"${lines[i]}"
    undo "$mode" "${fields[@]}"
  done
  if [ "${#KEPT[@]}" -gt 0 ] && [ -d "$(dirname -- "$file")" ]; then
    printf '# Hub installer record (kept): uninstall.sh --purge removes these.\n' >"$file"
    for ((i = ${#KEPT[@]} - 1; i >= 0; i--)); do printf '%s\n' "${KEPT[i]}" >>"$file"; done
  fi
  KEPT=("${saved[@]}" "${KEPT[@]}")
}

rollback() {
  local i fields
  set +e
  if [ "$RECORD_BASE" -lt 0 ]; then
    rm -f -- "$RECORD"
  elif [ -n "$RECORD" ] && [ -f "$RECORD" ]; then
    (umask 077 && head -n "$RECORD_BASE" -- "$RECORD" >"$RECORD.tmp") && mv -f -- "$RECORD.tmp" "$RECORD"
  fi
  KEPT=()
  for ((i = ${#RUN[@]} - 1; i >= 0; i--)); do
    IFS=$'\t' read -r -a fields <<<"${RUN[i]#*$'\t'}"
    undo rollback "${fields[@]}"
  done
  if [ "${#KEPT[@]}" -gt 0 ] && [ -n "$RECORD" ] && [ -d "$(dirname -- "$RECORD")" ]; then
    [ -f "$RECORD" ] || (umask 077 && printf '# Hub installer record (left by an undone run).\n' >"$RECORD")
    for ((i = ${#KEPT[@]} - 1; i >= 0; i--)); do printf '%s\n' "${KEPT[i]}" >>"$RECORD"; done
  fi
  if [ "$UNITS_CHANGED" -eq 1 ]; then systemctl --user daemon-reload >/dev/null 2>&1; fi
}

on_exit() {
  local status=$?
  trap - EXIT
  if [ "$status" -ne 0 ] && [ "$FINISHED" -eq 0 ] && [ "${#RUN[@]}" -gt 0 ]; then
    warn "Stopped. Undoing what this run changed..."
    rollback
    if [ "${#KEPT[@]}" -eq 0 ]; then
      say "Undone: this computer is as it was before this run."
    else
      warn "Undone, except what is named above: it stays as it is, written in $RECORD."
    fi
  fi
  exit "$status"
}

start_run() {
  trap on_exit EXIT
  trap 'exit 130' INT TERM HUP
}

finish_run() { # the install is complete: drop the scratch folder and earlier versions
  FINISHED=1
  rm -rf -- "$STAGE"
}
