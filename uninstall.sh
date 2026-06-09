#!/usr/bin/env bash
# Remove the mini-pad keyd config and restore any prior config.
# Leaves the keyd package installed; just undoes what install.sh wrote.
set -euo pipefail

KEYD="$(command -v keyd.rvaiya || command -v keyd || true)"
DEST=/etc/keyd

if [ "$(id -u)" -ne 0 ]; then
  echo "Re-running with sudo (you may be prompted for your password)..."
  exec sudo -- "$0" "$@"
fi

rm -f "$DEST/modeswitch"

if [ -f "$DEST/default.conf.pre-minikbd.bak" ]; then
  mv -f "$DEST/default.conf.pre-minikbd.bak" "$DEST/default.conf"
  echo "Restored previous $DEST/default.conf from backup."
else
  rm -f "$DEST/default.conf"
  echo "Removed $DEST/default.conf (no prior backup to restore)."
fi

[ -n "$KEYD" ] && "$KEYD" reload || true
echo "Done.  Pad reverts to its factory keycodes (1-9,0,a,b)."
