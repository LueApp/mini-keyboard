#!/usr/bin/env bash
# Install the MiniPad HUD: KWin pin rule + systemd --user autostart service.
# Runs entirely as your normal user (no sudo). KDE Plasma 6 / Wayland.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HUD_PY="$HERE/minipad_hud.py"
RULE_TITLE="MiniPad HUD"

# --- sanity ---------------------------------------------------------------
python3 -c 'import PyQt6' 2>/dev/null || {
  echo "PyQt6 missing. Install:  sudo apt-get install -y python3-pyqt6" >&2; exit 1; }
command -v kwriteconfig6 >/dev/null || { echo "kwriteconfig6 not found (KDE Plasma 6 required)." >&2; exit 1; }

# --- KWin window rule: keep-above + no border + skip taskbar/pager --------
# Append-safe: preserves any existing rules in kwinrulesrc.
UUID="$(uuidgen)"
add() { kwriteconfig6 --file kwinrulesrc --group "$UUID" --key "$1" "$2"; }
add Description "$RULE_TITLE"
add title       "$RULE_TITLE"
add titlematch  1            # 1 = exact title match
add above       true
add aboverule   2            # 2 = Force
add skiptaskbar true
add skiptaskbarrule 2
add skippager   true
add skippagerrule 2
add skipswitcher true       # panel/ball is a HUD; keep it out of Alt+Tab/Overview
add skipswitcherrule 2
add noborder    true
add noborderrule 2

existing="$(kreadconfig6 --file kwinrulesrc --group General --key rules 2>/dev/null || true)"
if [ -n "$existing" ]; then
  newrules="$existing,$UUID"
  newcount=$(( $(printf '%s' "$newrules" | tr ',' '\n' | grep -c .) ))
else
  newrules="$UUID"; newcount=1
fi
kwriteconfig6 --file kwinrulesrc --group General --key count "$newcount"
kwriteconfig6 --file kwinrulesrc --group General --key rules "$newrules"
qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null || qdbus org.kde.KWin /KWin reconfigure 2>/dev/null || true
echo "KWin rule installed (keep-above, frameless, off taskbar)."

# --- systemd --user service ----------------------------------------------
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
sed "s|@HUD_PY@|$HUD_PY|g" "$HERE/minipad-hud.service.in" > "$UNIT_DIR/minipad-hud.service"
systemctl --user daemon-reload
# Make the graphical env (WAYLAND_DISPLAY etc.) visible to the user manager now.
systemctl --user import-environment WAYLAND_DISPLAY DISPLAY XDG_RUNTIME_DIR XAUTHORITY 2>/dev/null || true
systemctl --user enable --now minipad-hud.service
echo "systemd --user service enabled and started."

echo
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx keyd; then
  echo "NOTE: '$USER' is in the keyd group but this LOGIN session predates it."
  echo "      Live mode-switching needs a re-login (or reboot) once."
  echo "      To test live updates right now without re-login, run:"
  echo "        sg keyd -c 'python3 $HUD_PY'"
fi
echo "Done. Panel shows the current mode; switch on the pad: 1+3 / 4+6 / 7+9."
