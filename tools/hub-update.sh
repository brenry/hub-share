#!/usr/bin/env bash
# Updates the Hub from the newest release zip beside this script. Run it from the download folder:
#   bash ~/Hub/hub-update.sh
# The settings, images, clips, model folders and engine stay as they are. Nothing is downloaded. No log is written.
# A build session sends this file unchanged with the release zip (the two sit side by side in ~/Hub).
set -euo pipefail
SHARE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ZIP=$(find "$SHARE" -maxdepth 1 -name 'hub-release-*.zip' | sort | tail -n 1)
[ -n "$ZIP" ] || { echo "STOPPED: put the hub-release-<date-time>.zip beside this script."; exit 1; }
echo "Installing $(basename "$ZIP")"
T=$(mktemp -d)
python3 -m zipfile -e "$ZIP" "$T"
bash "$(ls -d "$T"/hub-release-*)/install/install-hub.sh"
rm -rf "$T"
if systemd-run --user --scope --quiet --collect -- true 2>/dev/null; then
  echo "Engine isolation: on (a memory kill takes the engine, not the Hub)"
else
  echo "Engine isolation: not available here (the Hub starts the engine as before)"
fi
echo "Done. Close and reopen the Hub and Media windows once."
