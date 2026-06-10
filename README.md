# mini-keyboard — modal remapping for a 4×3 macro pad

A [keyd](https://github.com/rvaiya/keyd) service that turns a generic USB mini
keyboard (**`4132:2107`**, 12 keys, 4×3) into a **3-mode macro pad**, plus a small
always-on-top **HUD** showing the live key map. apps is the base keyd layer;
**nav** and **num** toggle over it and `swap`/`clear` move between them, so exactly
one mode is effective at a time. Switch by pressing a row's outer-corner pair.
Only the pad is remapped; every other keyboard (e.g. the Keychron K2) is
untouched, and it works under Wayland because keyd operates at the kernel input
layer (KDE Plasma 6).

## Layout

```
[ 1 ][ 2 ][ 3 ]
[ 4 ][ 5 ][ 6 ]
[ 7 ][ 8 ][ 9 ]
[ 0 ][ a ][ b ]      <- labels = the factory keycode each key sends
```

## Switch modes

Press both keys of a row's **outer pair together** (within 50 ms):

| Chord   | Mode   |
|---------|--------|
| `1` + `3` | **apps** |
| `4` + `6` | **nav**  |
| `7` + `9` | **num**  |

Boots in **apps**. Single taps of these keys keep their normal per-mode action;
only a simultaneous press switches mode.

## Mode maps

**apps** — application shortcuts
```
copy C-c   paste C-v   cut C-x
undo C-z   redo C-S-z  save C-s
all  C-a   find  C-f   close C-w
A-tab      newtab C-t  reopen C-S-t
```

**nav** — arrows / navigation
```
home   up    pageup
left   enter right
end    down  pagedown
esc    tab   backspace
```

**num** — numbers, calculator layout
```
7  8  9
4  5  6
1  2  3
0  .  enter
```
Uses digit-row keycodes, not keypad (`kp*`) codes: with NumLock off (laptops
with no numpad) the `kp*` keys act as Home/Up/PageUp and would not type numbers.

## Viewer (HUD panel)

A frameless PyQt6 panel shows the current mode and its key map, updating live as
you switch. Install it (no sudo; KDE Plasma 6 / Wayland):

```bash
hud/install-hud.sh
```

This pins it always-on-top via a KWin window rule and autostarts it each login
via a `systemd --user` service. It reads the active mode from `keyd listen`
(launched through `sg keyd` so the keyd-group socket works without re-login) and
the key labels straight from `/etc/keyd/default.conf`, so edits show up after a
reload. Drag to move; right-click → Quit. Remove with `hud/uninstall-hud.sh`.

### When the panel appears

The HUD has three states, so it only takes up space when the pad is actually in
play:

- **Pad unplugged → gone.** The window is shown only while the macro pad
  (USB `4132:2107`, taken from the config's `[ids]`) is connected. Unplug the pad
  and it disappears; plug it back in and it returns.
- **Connected but idle → a mini ball.** After ~10 s with no pad activity the full
  panel collapses to a small draggable circle showing the current mode's initial
  (e.g. **A**/**N**/**#**) — a quiet "pad is connected" dot that stays out of the
  way.
- **Connected and in use → the full panel.** It expands back to the full key map
  the instant you use the pad (any key or a mode switch) **or click the ball**.
  So it reminds you of the layout right when you reach for the pad, then shrinks
  away again.
- While you're **editing** the map (✎) it stays the full panel regardless, even if
  the pad is unplugged — it won't collapse mid-edit.

Collapsing/expanding is just a resize (the window stays put where you dragged it);
it only fully unmaps when the pad is unplugged. Tune the behavior with environment
variables (set them on the service — see below):

| Variable | Default | Effect |
|---|---|---|
| `MINIPAD_IDLE_SECS`  | `10`   | Seconds of no pad activity before it collapses to the ball. |
| `MINIPAD_AUTOHIDE`   | `1`    | `0` disables collapsing — stays the full panel whenever connected. |
| `MINIPAD_OPACITY`    | `0.70` | Panel/ball background opacity. |

Collapse-on-idle needs to read the pad's emitted keys from the `keyd virtual
keyboard` device, which requires membership in the **`input`** group (you already
are, for the editor). If that device can't be read it logs a notice and falls
back to staying the full panel whenever the pad is plugged in.

To change a variable on the installed service:

```bash
systemctl --user edit minipad-hud      # add: [Service]\nEnvironment=MINIPAD_IDLE_SECS=20
systemctl --user restart minipad-hud
```

### Edit remaps in the panel

Click **✎** in the panel header to enter edit mode (green border):

- **Remap a key:** click any cell → pick a preset or type a raw keyd value.
- **Pick which mode to edit:** click its pill.
- **Modes & chords:** **＋ Mode** adds one (name + 2-key activation chord);
  **⚙ Mode** renames / re-chords / deletes the selected mode.
- **Save:** writes the config via `pkexec` (one graphical password prompt),
  validates + restarts keyd, and **auto-rolls-back** if keyd reports errors.
  **Cancel** discards.

Requires the root apply helper from `install.sh` (`/usr/local/sbin/minipad-apply`).
The helper refuses anything unsafe: symlinked input, inline comments, and
`command()` bindings (keyd's `command()` would run a shell **as root** on a
keypress). Mode names are restricted to `A-Za-z0-9_-` and may not be keyd
reserved layer names; activation chords must be unique across modes.

## Install

```bash
./install.sh        # self-elevates with sudo
```

Copies `config/default.conf` to `/etc/keyd/`, enables the `keyd` systemd service,
**restarts** it (so the active layer resets cleanly), and reports whether the
config loaded with no errors. An existing `/etc/keyd/default.conf` is backed up to
`default.conf.pre-minikbd.bak` once.

Prereq: `sudo apt-get install -y keyd` (Ubuntu ships the binary as `keyd.rvaiya`).

> **keyd gotcha:** no inline comments on binding lines. `1 = C-c   # copy` makes
> keyd silently drop the binding (the key falls through to its factory code). Put
> comments on their own line.

## Edit a mapping

Change the right-hand side in `config/default.conf`, then either re-run
`./install.sh` or copy the file and reload:

```bash
sudo cp config/default.conf /etc/keyd/default.conf && sudo keyd.rvaiya reload
```

Changing a key's right-hand side → `reload` is enough. Adding/removing modes or
otherwise changing layer *structure* → `sudo systemctl restart keyd` instead, so
the toggled-layer state resets cleanly (a bare reload can leave a mode stuck).

Right-hand values: a key name (`up`, `7`), a modifier macro (`C-S-z`), literal
text (`macro(git space status enter)`), or a keyd action (`toggle`, `swap`,
`clear`). Valid key names: `keyd.rvaiya list-keys`. Full reference: `man keyd.rvaiya`.

## Uninstall

```bash
./uninstall.sh      # restores prior config (or clears ours) and reloads
```

## Troubleshooting

- **Keys wedged by a bad edit:** hold **`backspace` + `esc` + `enter`** — keyd's
  panic sequence kills the daemon and returns raw input.
- **Config errors / which mode loaded:** `journalctl -eu keyd`
- **Discover keycodes / device ids:** `sudo keyd.rvaiya monitor`
- **Watch live mode changes:** `sg keyd -c 'keyd.rvaiya listen'`
- **See what keyd actually emits (post-remap):** `python3 tools/keyout.py`
- **Chord won't trigger:** press the two keys simultaneously; if still hard,
  raise `chord_timeout` in `[global]` (default 50 ms).

## Files

```
config/default.conf    keyd config: [ids] + [global] + apps/[nav]/[num] layers
install.sh             copy config to /etc/keyd, install apply helper, restart keyd
uninstall.sh           restore prior config, reload
hud/minipad_hud.py     PyQt6 live keymap panel + in-panel remap editor
hud/configmodel.py     parse/generate the keyd config as editable data (+validate)
hud/presets.py         common keyd values for the editor's preset picker
hud/apply-config.sh    root helper (pkexec): validate + install + restart + rollback
hud/install-hud.sh     KWin pin rule + systemd --user autostart for the panel
hud/uninstall-hud.sh   remove the panel rule + service
tools/keyout.py        print the keys keyd emits (reads its virtual device)
```
