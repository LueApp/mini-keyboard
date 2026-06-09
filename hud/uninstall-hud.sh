#!/usr/bin/env bash
# Remove the MiniPad HUD service and its KWin rule.
set -euo pipefail
RULE_TITLE="MiniPad HUD"

# --- stop + remove the user service --------------------------------------
systemctl --user disable --now minipad-hud.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/minipad-hud.service"
systemctl --user daemon-reload 2>/dev/null || true

# --- remove our KWin rule, leaving any others intact ---------------------
rules="$(kreadconfig6 --file kwinrulesrc --group General --key rules 2>/dev/null || true)"
if [ -n "$rules" ]; then
  keep=""
  IFS=',' read -ra ids <<< "$rules"
  for id in "${ids[@]}"; do
    [ -z "$id" ] && continue
    title="$(kreadconfig6 --file kwinrulesrc --group "$id" --key title 2>/dev/null || true)"
    if [ "$title" = "$RULE_TITLE" ]; then
      for k in Description title titlematch above aboverule skiptaskbar \
               skiptaskbarrule skippager skippagerrule noborder noborderrule; do
        kwriteconfig6 --file kwinrulesrc --group "$id" --key "$k" --delete 2>/dev/null || true
      done
    else
      keep="${keep:+$keep,}$id"
    fi
  done
  count=$(printf '%s' "$keep" | tr ',' '\n' | grep -c . || true)
  kwriteconfig6 --file kwinrulesrc --group General --key rules "$keep"
  kwriteconfig6 --file kwinrulesrc --group General --key count "${count:-0}"
  qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null || qdbus org.kde.KWin /KWin reconfigure 2>/dev/null || true
fi
echo "MiniPad HUD removed (service + KWin rule)."
