#!/usr/bin/env bash
# Removes the Hub from this computer: exactly what the installers recorded, and nothing else.
# Your images and settings (the hub's data folder) are kept unless you add --purge.
# --engine undoes only what install-engine.sh did: the Hub's engine settings go back to what they were before it
# (the model and LoRA folders stay as they are now). --purge also removes the engine's code, its Python and its
# environment.
#
#   bash uninstall.sh [--prefix DIR] [--purge]
#   bash uninstall.sh --engine [--prefix DIR] [--purge]
set -euo pipefail
# shellcheck source=install/common.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

PREFIX='' MODE=uninstall ENGINE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX=${2:?}; shift ;;
    --purge) MODE=purge ;;
    --engine) ENGINE=1 ;;
    *) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
  esac
  shift
done
need_user
if [ "$ENGINE" -eq 1 ]; then
  if [ -z "$PREFIX" ]; then
    if [ -f "$REL/engine/.installed" ]; then PREFIX=$REL; else find_prefix; fi
  fi
  PREFIX=${PREFIX%/} E=${PREFIX%/}/engine DATA=${PREFIX%/}/data HUBPY=${PREFIX%/}/venv/bin/python
  [ -f "$E/.installed" ] || { say "No engine installed by install-engine.sh in $PREFIX."; exit 0; }
  if [ "$MODE" = purge ]; then                # a Settings folder inside what --purge removes: nothing is changed
    inside=$(python3 -I -c 'import json, os, sys
s = json.load(open(sys.argv[1]))
folders = s.get("engine", {}).get("model_folders", []) + s.get("modules", {}).get("loras", {}).get("folders", [])
gone = [os.path.realpath(p) for p in sys.argv[2:]]
print("\n".join(f for f in folders if any(os.path.commonpath([os.path.realpath(f), g]) == g for g in gone)))' \
      "$DATA/settings.json" "$E/app" "$E/env" "$E/python") || die "Could not read $DATA/settings.json: nothing was changed."
    [ -z "$inside" ] || die "A folder in your Settings is inside the engine: $(echo "$inside" | tr '\n' ' ')Take it out of Settings first: nothing was changed."
  fi
  running=0
  if unit_active hub.service; then running=1 && systemctl --user stop hub.service; fi
  say "Removing the Hub's engine"
  rm -rf -- "$E/.stage"
  undo_record "$E/.installed" "$MODE"
  if [ "$MODE" = purge ]; then
    rm -rf -- "$E/app" "$E/env" "$E/python" "$E/env.lock"
    note "Removed the engine's code, Python and environment."
  else
    note "Kept the engine's code and environment in $E (to remove them too: add --purge)."
  fi
  if [ "$running" -eq 1 ]; then systemctl --user start hub.service; fi
  if printf '%s\n' "${KEPT[@]}" | grep -q $'^settings\t'; then
    warn "The Hub's engine settings were not put back (named above)."
  else
    say "Done: the Hub's engine settings are as they were before install-engine.sh."
  fi
  exit 0
fi
if [ -n "$PREFIX" ]; then
  [ -f "${PREFIX%/}/.installed" ] || die "Nothing from the hub is installed in $PREFIX."
  candidates=("${PREFIX%/}/.installed")
else
  find_prefix
  candidates=("$REL/.installed" "${PREFIX%/}/.installed")
fi
records=()
for f in "${candidates[@]}"; do
  [ -f "$f" ] || continue
  f=$(realpath -- "$f")
  if [ "${#records[@]}" -eq 0 ] || ! printf '%s\n' "${records[@]}" | grep -qxF -- "$f"; then records+=("$f"); fi
done
[ "${#records[@]}" -gt 0 ] || { say "Nothing from the hub is installed here."; exit 0; }

if cat -- "${records[@]}" | grep -q "^firewall"$'\t'; then
  say "Removing the hub's firewall rules (asks for your password)"
  if ! sudo -v; then
    FIREWALL_UNDO=no
    note "Firewall unchanged. To remove the hub's rules yourself:"
    while IFS=$'\t' read -r _ zone rule; do
      note "sudo firewall-cmd --zone=$zone --remove-rich-rule='$rule'"
      note "sudo firewall-cmd --permanent --zone=$zone --remove-rich-rule='$rule'"
    done < <(grep -h "^firewall"$'\t' -- "${records[@]}")
  fi
fi
for f in "${records[@]}"; do
  if [ -f "$f" ]; then
    say "Removing $(dirname -- "$f")"
    rm -rf -- "$(dirname -- "$f")/.stage"
    undo_record "$f" "$MODE"
  fi
done
systemctl --user daemon-reload >/dev/null 2>&1 || true
for item in "${KEPT[@]}"; do
  case "$item" in
    data$'\t'*) note "Kept your images and settings in ${item#*$'\t'}" ;;
    uninstaller$'\t'*) note "To remove those too: bash ${item#*$'\t'}/uninstall.sh --purge" ;;
  esac
done
say "The hub is removed."
