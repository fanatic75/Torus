#!/usr/bin/env bash
# Deploy Torus to a CoreELEC/Kodi box over SSH.
#
# Usage:
#   ./deploy.sh                       # uses defaults below
#   TORUS_BOX=root@192.168.1.50 ./deploy.sh
#
# The on-device folder MUST be named plugin.video.torus (matches addon.xml id),
# even though this repo folder is named "Torus".
set -euo pipefail

BOX="${TORUS_BOX:-root@192.168.29.55}"
DEST="/storage/.kodi/addons/plugin.video.torus"

echo "Deploying to ${BOX}:${DEST}"

# NOTE: dev.config.json IS synced (over your LAN) so the box reads your local
# TMDB key. It stays gitignored and is never committed or posted online.
rsync -av --delete \
  --exclude '.git' \
  --exclude '.devprofile' \
  --exclude '__pycache__' \
  --exclude '.DS_Store' \
  --exclude 'deploy.sh' \
  --exclude 'README.md' \
  --exclude 'LICENSE' \
  ./ "${BOX}:${DEST}/"

echo "Files synced. Reload the addon:"
echo "  - Easiest: Settings > Add-ons > toggle Torus off/on, or restart Kodi."
echo "  - Logs:    ssh ${BOX} 'tail -f /storage/.kodi/temp/kodi.log | grep -i torus'"
