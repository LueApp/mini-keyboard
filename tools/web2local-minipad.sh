#!/usr/bin/env bash
# Narrow helper for running mini-keyboard maintenance actions through web2local.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-status}"
KEYD="$(command -v keyd.rvaiya || command -v keyd || true)"

print_header() {
  printf '\n== %s ==\n' "$1"
}

case "$ACTION" in
  status)
    print_header "mini-keyboard"
    printf 'repo: %s\n' "$ROOT"
    if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      git -C "$ROOT" status --short --branch
    fi

    print_header "keyd"
    printf 'binary: %s\n' "${KEYD:-not found}"
    if command -v systemctl >/dev/null 2>&1; then
      systemctl is-active keyd 2>/dev/null || true
    fi

    print_header "HUD service"
    if command -v systemctl >/dev/null 2>&1; then
      systemctl --user is-active minipad-hud 2>/dev/null || true
    fi
    ;;

  validate)
    print_header "shell syntax"
    bash -n "$ROOT/install.sh"
    bash -n "$ROOT/uninstall.sh"
    bash -n "$ROOT/hud/install-hud.sh"
    bash -n "$ROOT/hud/uninstall-hud.sh"
    bash -n "$ROOT/hud/apply-config.sh"
    printf 'ok\n'

    print_header "python syntax"
    python3 -m py_compile \
      "$ROOT/hud/configmodel.py" \
      "$ROOT/hud/presets.py" \
      "$ROOT/hud/minipad_hud.py" \
      "$ROOT/tools/keyout.py"
    printf 'ok\n'
    ;;

  keyd-log)
    print_header "recent keyd log"
    journalctl -u keyd --no-pager --since "10 minutes ago" 2>/dev/null | tail -120 || true
    ;;

  install-hud)
    exec "$ROOT/hud/install-hud.sh"
    ;;

  uninstall-hud)
    exec "$ROOT/hud/uninstall-hud.sh"
    ;;

  *)
    printf 'unknown action: %s\n' "$ACTION" >&2
    printf 'valid actions: status validate keyd-log install-hud uninstall-hud\n' >&2
    exit 64
    ;;
esac
