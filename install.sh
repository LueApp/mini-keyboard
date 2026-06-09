#!/usr/bin/env bash
# Install the mini-pad keyd config and (re)start the keyd service.
# Safe to re-run: it backs up any pre-existing /etc/keyd/default.conf once.
set -euo pipefail

# Debian/Ubuntu ship the binary as keyd.rvaiya (name clash); fall back to keyd.
KEYD="$(command -v keyd.rvaiya || command -v keyd || true)"
if [ -z "$KEYD" ]; then
  echo "keyd is not installed.  Install it with:  sudo apt-get install -y keyd" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config"
DEST=/etc/keyd

# Need root to write /etc/keyd and manage the service.
if [ "$(id -u)" -ne 0 ]; then
  echo "Re-running with sudo (you may be prompted for your password)..."
  exec sudo -- "$0" "$@"
fi

mkdir -p "$DEST"

# One-time backup of an existing config so we never silently clobber it.
if [ -f "$DEST/default.conf" ] && [ ! -f "$DEST/default.conf.pre-minikbd.bak" ]; then
  cp -a "$DEST/default.conf" "$DEST/default.conf.pre-minikbd.bak"
  echo "Backed up existing $DEST/default.conf -> default.conf.pre-minikbd.bak"
fi

install -m 0644 "$SRC/default.conf" "$DEST/default.conf"
rm -f "$DEST/modeswitch"   # no longer used (was an include in the old layout design)
echo "Installed config -> $DEST/default.conf"

# Root-owned apply helper used by the panel's editor (run via pkexec on Save).
HELPER_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hud/apply-config.sh"
if [ -f "$HELPER_SRC" ]; then
  install -m 0755 -o root -g root "$HELPER_SRC" /usr/local/sbin/minipad-apply
  echo "Installed editor apply helper -> /usr/local/sbin/minipad-apply"
fi

systemctl enable keyd
# Restart (not reload): reload updates bindings but leaves the active layout
# pointer where it was, which can desync modes. Restart applies default_layout.
systemctl restart keyd

echo
echo "--- keyd service ---"
systemctl --no-pager --lines=0 status keyd 2>/dev/null | head -4 || true

# Surface config errors from the load we just triggered (these are fatal to
# the affected bindings — they must be empty for the modes to work).
errs="$(journalctl -u keyd --no-pager --since '5 seconds ago' 2>/dev/null | grep -iE 'error|invalid' || true)"
if [ -n "$errs" ]; then
  echo "!!! CONFIG ERRORS — these bindings were rejected, fix before use:"
  echo "$errs"
else
  echo "Config loaded with NO errors."
fi
echo
echo "Done.  Pad is in 'apps' mode.  Switch:  1+3=apps   4+6=nav   7+9=num"
