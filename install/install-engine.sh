#!/usr/bin/env bash
# Switches the Hub to its own engine, upstream WanGP (Stage 10). The Stage 10 step 1 block already put its code in
# <prefix>/engine/app (a git checkout) and its Python environment in <prefix>/engine/env. This points the Hub at
# them, writes the app's config, and checks that the engine starts. The model and LoRA folders stay the ones set on
# the Hub's Settings screen: nothing in them is moved, copied or deleted. Run it as your normal user (not sudo).
# Nothing is downloaded or copied except the engine's base Python. If anything fails, this run is undone.
#
#   bash install/install-engine.sh [--prefix DIR] [--dry-run] [--yes]
#   bash install/uninstall.sh --engine [--purge]        undo: the Hub's engine settings as they were before
set -euo pipefail
# shellcheck source=install/common.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

PIN=${HUB_ENGINE_PIN:-af2ed29}                    # upstream WanGP v18.05: the commit captured and tested
UPSTREAM=https://github.com/deepbeepmeep/Wan2GP
SERVICE_PATH=/usr/local/bin:/usr/bin:/bin         # the PATH the Hub's service gives the engine (deploy/hub.service)
PREFIX='' DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX=${2:?}; shift ;;
    --dry-run) DRY=1 ;;
    --yes) ASSUME_YES=1 ;;
    *) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
  esac
  shift
done
if [ -z "$PREFIX" ]; then
  if [ -f "$REL/data/settings.json" ] && [ -f "$REL/hub/worker/main.py" ]; then PREFIX=$REL; else find_prefix; fi
fi
PREFIX=${PREFIX%/}
DATA=$PREFIX/data E=$PREFIX/engine
APP=$E/app ENV=$E/env BASE=$E/python BEFORE=$E/.settings-before.json KEPT_CONFIG=$E/.app-config-before.json
PYE=$ENV/bin/python HUBPY=$PREFIX/venv/bin/python
export PATH="$PATH:$HOME/.local/bin:/home/linuxbrew/.linuxbrew/bin"
lines() { "$PY" -I -c 'import json, sys; sys.stdout.write("".join(f"{a}\n" for a in json.loads(sys.argv[1])))' "$1"; }
setting() { # dotted key: the Hub's setting, as JSON
  "$PY" -I -c 'import json, sys
v = json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): v = v.get(k, {}) if isinstance(v, dict) else {}
print(json.dumps(v if v != {} else ""))' "$DATA/settings.json" "$1"
}

say "Checking this computer"
need_user
find_python
check_path "$PREFIX"
[ -f "$DATA/settings.json" ] || die "The Hub is not installed in $PREFIX (no data/settings.json). Install the Hub first."
[ -x "$HUBPY" ] && [ -f "$PREFIX/hub/worker/keep.py" ] ||
  die "The Hub in $PREFIX is older than this installer. Install the Hub from this release first: bash install/install-hub.sh"
[ -f "$APP/wgp.py" ] || die "No upstream WanGP in $APP. Run the Stage 10 step 1 block first."
[ "$(git -C "$APP" config --get remote.origin.url 2>/dev/null || true)" = "$UPSTREAM" ] ||
  die "$APP is not an upstream WanGP checkout. Move it away first."
head=$(git -C "$APP" rev-parse --short=7 HEAD)
[ "$head" = "$PIN" ] || die "$APP is at $head, not the tested $PIN. To go back to it: git -C $APP checkout --detach $PIN"
[ -z "$(git -C "$APP" status --porcelain --untracked-files=no)" ] || die "$APP has local changes. See: git -C $APP status"
"$PYE" -I -B -S -c '' 2>/dev/null || die "The engine's Python ($PYE) does not start."
extra=$(ls -A "$E" | grep -vxE 'app|env|env.lock|python|\.installed|\.stage|\.settings-before\.json|\.base-python\.json|\.app-config-before\.json' || true)
[ -z "$extra" ] || die "$E holds more than the engine: $(echo "$extra" | tr '\n' ' '). Move those away first."
RECORD_FILE=$E/.installed
OLD=$(lines "[$(setting engine.root)]")
FIRST=0                                           # the first switch: the settings it replaces are kept for the undo
if [ "$OLD" != "$APP" ] && ! grep -q $'^settings\t' -- "$RECORD_FILE" 2>/dev/null; then FIRST=1; fi
mapfile -t MODEL_FOLDERS < <(lines "$(setting engine.model_folders)")
mapfile -t LORA_FOLDERS < <(lines "$(setting modules.loras.folders)")
TEMPLATE=- SOURCE=$APP OTHER=()                   # the config the app's is written from: its settings are kept
if [ "$FIRST" -eq 1 ] && [ -n "$OLD" ] && [ -f "$OLD/wgp_config.json" ]; then
  TEMPLATE=$OLD/wgp_config.json SOURCE=$OLD OTHER=(--other-engine)
elif [ -f "$APP/wgp_config.json" ]; then TEMPLATE=$APP/wgp_config.json; fi
CC='' CXX=''
for c in gcc gcc-15 gcc-14 gcc-13; do if command -v "$c" >/dev/null; then CC=$(command -v "$c"); break; fi; done
for c in g++ g++-15 g++-14 g++-13; do if command -v "$c" >/dev/null; then CXX=$(command -v "$c"); break; fi; done
[ -n "$CC" ] && [ -n "$CXX" ] || die "gcc and g++ are needed (the engine's kernels build with them). Install them: brew install gcc"
if ! PATH=$SERVICE_PATH command -v ffmpeg >/dev/null || ! PATH=$SERVICE_PATH command -v ffprobe >/dev/null; then
  [ -x "$APP/ffmpeg_bins/ffmpeg" ] && [ -x "$APP/ffmpeg_bins/ffprobe" ] && ls "$APP"/ffmpeg_bins/libavdevice.so* >/dev/null 2>&1 ||
    die "ffmpeg and ffprobe are not in $SERVICE_PATH nor in $APP/ffmpeg_bins. Run the Stage 10 step 1 block again."
fi
ARGS_JSON=$("$PY" -I -c 'import json, sys; print(json.dumps(json.load(open(sys.argv[1]))["engine"].get("args", [])))' "$DATA/settings.json")
KEPT_ARGS=$ARGS_JSON
if [ "$ARGS_JSON" != "[]" ]; then
  mapfile -t old_args < <(lines "$ARGS_JSON")
  KEPT_ARGS=$(cd "$APP" && "$PYE" -I -B "$HERE/engineargs.py" "$APP" "${old_args[@]}") ||
    die "The engine's arguments could not be checked against upstream's (see above)."
fi
mapfile -t ENGINE_ARGS < <(lines "$KEPT_ARGS")

say "The plan"
note "The Hub ($PREFIX) and the engine code ($APP, $ENV) stay where they are."
note "The Hub's engine: ${OLD:-none} -> $APP (Python $PYE, compilers $CC and $CXX, arguments $KEPT_ARGS)."
note "Model folders (your Settings; unchanged, nothing in them is moved, copied or deleted):"
for f in "${MODEL_FOLDERS[@]}"; do note "  $f"; done
[ "${#MODEL_FOLDERS[@]}" -gt 0 ] || note "  none"
note "LoRA folders (your Settings; unchanged):"
for f in "${LORA_FOLDERS[@]}"; do note "  $f"; done
[ "${#LORA_FOLDERS[@]}" -gt 0 ] || note "  none"
note "The app's config: written from ${TEMPLATE/#-/upstream defaults}; its own ckpts only (never your folders); outputs of upstream's own page in $APP/outputs."
if [ "$FIRST" -eq 1 ]; then note "To undo: bash $PREFIX/install/uninstall.sh --engine (the Hub's engine goes back to ${OLD:-none})."; fi
if [ "$DRY" -eq 1 ]; then say "Dry run: nothing was changed."; exit 0; fi
if [ "$FIRST" -eq 1 ] && ! ask "Go ahead?"; then die "Stopped: nothing was changed."; fi

say "Installing the engine"
open_record "$RECORD_FILE" engine
start_run
new_stage "$E/.stage"
WAS_RUNNING=0
if unit_active hub.service; then WAS_RUNNING=1; fi
stop_service hub.service
[ -d "$APP/outputs" ] || { mkdir -- "$APP/outputs" && did dir "$APP/outputs"; }
did_temp basepython "$STAGE/base-python.json"           # undone only if this run made the copy and then failed
said=$("$PY" -I "$HERE/helpers.py" base-python "$ENV" "$BASE" "$STAGE/base-python.json") ||
  die "The engine's Python could not be made its own (see above)."
note "$said"
if [ -f "$STAGE/base-python.json" ]; then
  mv -f -- "$STAGE/base-python.json" "$E/.base-python.json"
  did basepython "$E/.base-python.json"
fi
set_args=(--root "$APP" --python "$PYE" --cc "$CC" --cxx "$CXX" --args "$KEPT_ARGS")
if [ "$FIRST" -eq 1 ]; then                              # recorded first: a stop at any point still puts them back
  rm -f -- "$BEFORE"
  did settings "$BEFORE"
  hub_engine set "${set_args[@]}" --before "$BEFORE" || die "The Hub's settings were not changed (see above)."
else
  did_temp settings "$STAGE/settings-before.json"
  hub_engine set "${set_args[@]}" --before "$STAGE/settings-before.json" || die "The Hub's settings were not changed (see above)."
fi
MODELS=$(setting engine.model_folders)
mapfile -t FOLDERS < <(lines "$("$PY" -I -c 'import json, sys
print(json.dumps([x for f in json.loads(sys.argv[1]) for x in ("--models", f)]))' "$MODELS")")
"$PY" -I "$HERE/helpers.py" config "$TEMPLATE" "$STAGE/wgp_config.json" --source "$SOURCE" --outputs "$APP/outputs" "${OTHER[@]}" ||
  die "The engine's config could not be written (see above)."
if [ -e "$APP/wgp_config.json" ] && ! ours "$APP/wgp_config.json" && [ ! -e "$KEPT_CONFIG" ]; then
  did restore "$APP/wgp_config.json" "$KEPT_CONFIG"     # a config the installer did not make: put back by the undo
  cp -p -- "$APP/wgp_config.json" "$KEPT_CONFIG"
fi
put_file "$APP/wgp_config.json" <"$STAGE/wgp_config.json"

say "Checking that the engine starts"
env -i PATH="$SERVICE_PATH" HOME="$HOME" "$CC" --version >/dev/null 2>&1 || die "$CC does not run in the engine's environment."
mkdir -p -- "$DATA/engine-home"
if ! env -i PATH="$SERVICE_PATH" HOME="$DATA/engine-home" LANG=C.UTF-8 CC="$CC" CXX="$CXX" \
  "$PYE" -B "$PREFIX/hub/worker/main.py" --root "$APP" "${FOLDERS[@]}" --dump-catalog "$STAGE/catalog.json" \
  -- "${ENGINE_ARGS[@]}" 2>"$STAGE/smoke.log"; then
  tail -n 5 -- "$STAGE/smoke.log" >&2
  die "The engine did not start (the lines above)."
fi
grep -h '^Kept ' -- "$STAGE/smoke.log" | sed 's/^/    /' || true
note "$("$PY" -I -c 'import json, sys
m = json.load(open(sys.argv[1]))["models"]
print("The engine answers: %d picture models and %d clip models." % (sum(e["kind"] == "image" for e in m), sum(e["kind"] == "video" for e in m)))' "$STAGE/catalog.json")"
finish_run
if [ "$WAS_RUNNING" -eq 1 ]; then systemctl --user start hub.service; fi
say "Done. The Hub's engine is $APP."
note "The weights it lacks: $PYE -B $PREFIX/hub/worker/main.py --root $APP ${FOLDERS[*]} --check-weights"
