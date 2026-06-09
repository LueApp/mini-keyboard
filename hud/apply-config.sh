#!/usr/bin/env bash
# Root helper, invoked as:  pkexec /usr/local/sbin/minipad-apply <staged.conf>
# Validates a staged keyd config, installs it as /etc/keyd/default.conf, restarts
# keyd, and ROLLS BACK automatically if the restart reports config errors.
#
# Installed root-owned 0755 by install.sh. Runs with full privilege via pkexec,
# so it is deliberately strict about what it will install: it copies the staged
# file to a private root-owned work copy FIRST (closing any swap/TOCTOU between
# checking and installing), refuses symlinks, and rejects command() bindings
# (keyd's command() runs a shell AS ROOT on every keypress).
set -euo pipefail

DEST=/etc/keyd/default.conf
BAK=/etc/keyd/default.conf.bak.minipad
STAGED="${1:-}"

KEYD="$(command -v keyd.rvaiya || command -v keyd || echo /usr/bin/keyd.rvaiya)"

die() { echo "minipad-apply: $*" >&2; exit 1; }

[ -n "$STAGED" ]   || die "no staged file given"
[ ! -L "$STAGED" ] || die "staged path is a symlink (refused)"
[ -f "$STAGED" ]   || die "staged file not found"

# Must be owned by the user who invoked pkexec (not some other user's file).
if [ -n "${PKEXEC_UID:-}" ]; then
  owner="$(stat -c %u "$STAGED")"
  [ "$owner" = "$PKEXEC_UID" ] || die "staged file is not owned by the caller"
fi

# Immutable root-owned work copy — everything below validates/install THIS.
WORK="$(mktemp /etc/keyd/.minipad-stage.XXXXXX)"
trap 'rm -f "$WORK"' EXIT
cat -- "$STAGED" > "$WORK"
chmod 0644 "$WORK"

# --- validate the work copy ----------------------------------------------
grep -q '^\[ids\]' "$WORK" || die "not a keyd config (no [ids] section)"
if grep -nE '^[^#].*=[^=]*[[:space:]]#' "$WORK" >/dev/null; then
  die "inline comment on a binding line (keyd would drop the binding)"
fi
if grep -niE '=[[:space:]]*command[[:space:]]*\(' "$WORK" >/dev/null; then
  die "command() bindings are not allowed (they run a shell as root)"
fi

# --- install with automatic rollback on error ----------------------------
[ -f "$DEST" ] && cp -a "$DEST" "$BAK"
install -m 0644 "$WORK" "$DEST"

# Restart (not reload): reload leaves the active-layer pointer stale and can
# desync modes after a rename/remove (see install.sh).
systemctl restart keyd 2>/dev/null || "$KEYD" reload 2>/dev/null || true
sleep 1

errs="$(journalctl -u keyd --no-pager --since '4 seconds ago' 2>/dev/null \
        | grep -iE 'error|invalid' || true)"
if [ -n "$errs" ]; then
  echo "minipad-apply: keyd reported errors, rolling back:" >&2
  echo "$errs" >&2
  if [ -f "$BAK" ]; then
    install -m 0644 "$BAK" "$DEST"
    systemctl restart keyd 2>/dev/null || "$KEYD" reload 2>/dev/null || true
  fi
  exit 3
fi

echo "minipad-apply: applied OK"
