#!/usr/bin/env python3
"""Common keyd right-hand values, grouped, for the editor's preset picker.

Every value here is a verified keyd key/macro. The editor also lets the user
type a raw value for anything not listed (any `man keyd.rvaiya` expression).
"""

PRESETS = [
    ("Edit", [
        ("Copy", "C-c"), ("Paste", "C-v"), ("Cut", "C-x"), ("Undo", "C-z"),
        ("Redo", "C-S-z"), ("Select All", "C-a"), ("Save", "C-s"),
        ("Find", "C-f"), ("Delete", "delete"),
    ]),
    ("Navigation", [
        ("Up", "up"), ("Down", "down"), ("Left", "left"), ("Right", "right"),
        ("Home", "home"), ("End", "end"), ("Page Up", "pageup"),
        ("Page Down", "pagedown"), ("Esc", "esc"), ("Tab", "tab"),
        ("Enter", "enter"), ("Backspace", "backspace"),
    ]),
    ("Numbers", [
        ("0", "0"), ("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"),
        ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8"), ("9", "9"),
        ("Dot  .", "."), ("Enter", "enter"),
    ]),
    ("Media", [
        ("Play/Pause", "playpause"), ("Next", "nextsong"),
        ("Previous", "previoussong"), ("Volume +", "volumeup"),
        ("Volume -", "volumedown"), ("Mute", "mute"),
        ("Brightness +", "brightnessup"), ("Brightness -", "brightnessdown"),
    ]),
    ("Window / Tab", [
        ("New Tab", "C-t"), ("Close", "C-w"), ("Reopen Tab", "C-S-t"),
        ("Switch Window", "A-tab"), ("Fullscreen", "f11"), ("Refresh", "f5"),
    ]),
    ("Key / Modifier", [
        ("Ctrl", "leftctrl"), ("Shift", "leftshift"), ("Alt", "leftalt"),
        ("Super", "leftmeta"), ("Space", "space"), ("Insert", "insert"),
    ]),
]

# value -> friendly label (first match wins), for displaying current bindings.
LABEL = {}
for _group, _items in PRESETS:
    for _lab, _val in _items:
        LABEL.setdefault(_val, _lab)


def label_for(value: str) -> str:
    """Friendly label for a keyd value, or the value itself if unknown."""
    if not value:
        return "·"
    return LABEL.get(value, value)
