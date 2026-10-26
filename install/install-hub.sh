#!/usr/bin/env bash
# Installs the Hub on this server: its own Python environment, the app and a user service that starts at boot.
# Run it as your normal user (not sudo). Running it again repairs or updates the install. Nothing is downloaded.
# If anything fails, everything this run did is undone.
#
#   bash install/install-hub.sh [--prefix DIR] [--bind IP] [--engine-root DIR] [--engine-python FILE]
#                               [--lora-folder DIR]... [--python FILE] [--no-firewall] [--yes]
#   --prefix defaults to the install the `hub` command on this computer points at, else $HOME/hub.
#
# The engine is the Hub's own, in <prefix>/engine (install-engine.sh puts it there); a first install without one writes
# empty engine settings and says how to add it. A repair keeps the settings as they are.
set -euo pipefail
# shellcheck source=install/common.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

PREFIX=''
BIND='' ENGINE_ROOT='' ENGINE_PY='' PYTHON='' FIREWALL=ask
LORAS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX=${2:?}; shift ;;
    --bind) BIND=${2:?}; shift ;;
    --engine-root) ENGINE_ROOT=${2:?}; shift ;;
    --engine-python) ENGINE_PY=${2:?}; shift ;;
    --lora-folder) LORAS+=("${2:?}"); shift ;;
    --python) PYTHON=${2:?}; shift ;;
    --no-firewall) FIREWALL=no ;;
    --yes) ASSUME_YES=1 ;;
    *) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
  esac
  shift
done
find_prefix
PREFIX=${PREFIX%/}
DATA=$PREFIX/data
LAUNCHER=$HOME/.local/bin/hub

say "Checking this computer"
need_user
find_python "$PYTHON"
for f in hub/__main__.py web/dist/index.html requirements/controller.lock deploy/hub.service; do
  [ -f "$REL/$f" ] || die "This release is incomplete: $f is missing. Unzip the whole release again."
done
check_path "$PREFIX"
check_target "$PREFIX" venv hub web install data
GIVEN=${ENGINE_ROOT:+yes}
ENGINE_ROOT=${ENGINE_ROOT:-$PREFIX/engine/app}
ENGINE_PY=${ENGINE_PY:-$PREFIX/engine/env/bin/python}
if [ -f "$ENGINE_ROOT/wgp.py" ]; then
  [ -x "$ENGINE_PY" ] || die "The engine's Python was not found at $ENGINE_PY. Use --engine-python <file>."
  "$ENGINE_PY" -I -B -S -c '' 2>/dev/null || die "The engine's Python ($ENGINE_PY) does not start."
  case "$(realpath -m -- "$PREFIX")/" in "$(realpath -m -- "$ENGINE_ROOT")"/*) die "Choose a --prefix outside $ENGINE_ROOT." ;; esac
elif [ -n "$GIVEN" ]; then
  die "The image engine was not found in $ENGINE_ROOT. Use --engine-root <folder with wgp.py>."
else
  ENGINE_ROOT='' ENGINE_PY=''
fi
if [ "${#LORAS[@]}" -eq 0 ] && [ -n "$ENGINE_ROOT" ] && [ -d "$ENGINE_ROOT/loras" ]; then LORAS=("$(realpath -- "$ENGINE_ROOT/loras")"); fi
for d in "${LORAS[@]}"; do [ -d "$d" ] || die "LoRA folder not found: $d"; done
LAN=$("$PY" -I "$HERE/helpers.py" lan ${BIND:+"$BIND"} 2>&1) || die "$LAN"
read -r LAN_IP LAN_NET LAN_IF <<<"$LAN"
note "Python $PYVER · engine ${ENGINE_ROOT:-none yet} · this server is $LAN_IP on $LAN_NET"

say "Installing the hub in $PREFIX"
make_dir "$PREFIX"
open_record "$PREFIX/.installed" hub
start_run
new_stage "$PREFIX/.stage"
stop_service hub.service
build_venv "$PREFIX/venv" "$REL/requirements/controller.lock" "$PREFIX"
replace_dir "$PREFIX/hub"
copy_tree "$REL/hub" "$PREFIX/hub"
replace_dir "$PREFIX/web"
copy_tree "$REL/web/dist" "$PREFIX/web/dist"
replace_dir "$PREFIX/install" uninstaller
copy_tree "$REL/install" "$PREFIX/install"
hub_cmd() { "$PREFIX/venv/bin/python" -I -m hub "$@"; }

if [ -f "$DATA/settings.json" ]; then
  note "Keeping your settings and images in $DATA"
else
  [ -e "$DATA" ] || did data "$DATA"
  args=(init --data "$DATA" --bind "$LAN_IP")
  if [ -n "$ENGINE_ROOT" ]; then args+=(--engine-root "$ENGINE_ROOT" --engine-python "$ENGINE_PY"); fi
  for d in "${LORAS[@]}"; do args+=(--lora-folder "$d"); done
  hub_cmd "${args[@]}" >/dev/null || die "The hub could not write its first settings (see the line above)."
fi
SERVER=$("$PY" -I -c 'import json, sys
s = json.load(open(sys.argv[1]))["server"]
print(int(s["port"]), ([a for a in s["bind"] if not a.startswith("127.")] or s["bind"])[0])' "$DATA/settings.json") ||
  die "The hub's settings could not be read: $DATA/settings.json"
read -r PORT ADDR <<<"$SERVER"

if [ -e "$LAUNCHER" ] && ! ours "$LAUNCHER"; then
  warn "$LAUNCHER already exists, so the 'hub' command is: HUB_DATA=$DATA $PREFIX/venv/bin/python -m hub"
else
  make_dir "$(dirname -- "$LAUNCHER")"
  put_file "$LAUNCHER" < <(printf '#!/bin/sh\n# The hub command (made by the Hub installer).\nHUB_DATA=%s exec %s/venv/bin/python -I -m hub "$@"\n' "$DATA" "$PREFIX")
  chmod 755 "$LAUNCHER"
fi

say "Starting the hub service"
install_unit hub.service < <(sed -e "s#@PREFIX@#$PREFIX#g" -e "s#@DATA@#$DATA#g" "$REL/deploy/hub.service")
if [ "$(loginctl show-user "$(id -u)" -p Linger --value 2>/dev/null)" != yes ]; then
  if loginctl enable-linger "$(id -u)" >/dev/null 2>&1; then
    did linger "$(id -u)"
  else
    warn "The hub starts when you log in. To start it at boot without a login, run once: sudo loginctl enable-linger $USER"
  fi
fi
enable_unit hub.service
if ss -Hltn "sport = :$PORT" 2>/dev/null | grep -q .; then
  die "Port $PORT is already in use by another program. Stop it, or change the hub's port: hub network set --port <n>"
fi
systemctl --user start hub.service
for _ in $(seq 60); do
  if ss -Hltn "sport = :$PORT" 2>/dev/null | grep -q .; then break; fi
  unit_active hub.service || break
  sleep 0.5
done
ss -Hltn "sport = :$PORT" 2>/dev/null | grep -q . ||
  die "The hub did not start. Its last lines: journalctl --user -u hub -n 20"
note "The hub is running at http://$ADDR:$PORT"
if [ "$ADDR" != "$LAN_IP" ]; then
  warn "This server's address is now $LAN_IP, but the hub still uses $ADDR. To switch: hub network reset"
fi

if [ "$FIREWALL" = ask ] && command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
  say "Firewall"
  zone=$(firewall-cmd --get-zone-of-interface="$LAN_IF" 2>/dev/null || firewall-cmd --get-default-zone 2>/dev/null || true)
  rules=("rule priority=\"-20\" family=\"ipv4\" source address=\"$LAN_NET\" port port=\"$PORT\" protocol=\"tcp\" accept"
    "rule priority=\"-19\" family=\"ipv4\" port port=\"$PORT\" protocol=\"tcp\" reject")
  todo=()
  for rule in "${rules[@]}"; do grep -qxF -- "firewall"$'\t'"$zone"$'\t'"$rule" "$RECORD" || todo+=("$rule"); done
  if [ -z "$zone" ]; then
    note "No active firewall zone found; no rules added."
  elif [ "${#todo[@]}" -eq 0 ]; then
    note "Port $PORT is open to $LAN_NET only (zone $zone)."
  elif ask "Allow only your home network ($LAN_NET) to reach the hub on port $PORT? (2 firewall rules; asks for your password)"; then
    for rule in "${todo[@]}"; do
      if firewall --zone="$zone" --add-rich-rule="$rule" && firewall --permanent --zone="$zone" --add-rich-rule="$rule"; then
        did firewall "$zone" "$rule"
      else
        warn "The firewall rule was not added: $rule"
      fi
    done
    note "Port $PORT is open to $LAN_NET only (zone $zone)."
  else
    note "Firewall unchanged. To be asked again, run this installer again."
  fi
fi
finish_run

link=$(hub_cmd pair --data "$DATA" --name Desk) || link="(not made; run: hub pair --name Desk)"
say "Done. The hub is running at http://$ADDR:$PORT"
cat <<EOF

  Pair the desk's screens. In HocusPocus Desktop choose New Instance, name it Hub, and use this
  address (it works once, within 10 minutes):

    $link

  New link: hub pair --name Desk
  Remove the hub: bash $PREFIX/install/uninstall.sh

EOF
if [ -z "$("$PY" -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["engine"]["root"])' "$DATA/settings.json")" ]; then
  warn "The hub has no image engine yet. Add it: bash $PREFIX/install/install-engine.sh"
fi
