#!/usr/bin/env python3
"""Parse/generate the mini-pad keyd config as editable data.

The editable model is simple:

    Config(ids, globals, base, modes=[Mode(name, chord, keys), ...])

  * base   = display name of the base mode (generated as keyd's [main] layer)
  * each non-base mode generates as its own [name] layer
  * chord  = the 2-key activation chord for a mode, e.g. ["1","3"]
  * keys   = {phys_key: keyd_value}, phys_key in PHYS

generate() emits the toggle/swap/clear wiring (generalized to N modes) so the
caller never has to think about it:

  - in the base [main] layer:  M.chord -> toggle(M)   for each non-base M
                               base.chord -> clear()
  - in a non-base layer L:      base.chord -> clear()
                               M.chord -> swap(M)      for each non-base M

No inline comments are ever emitted on binding lines (keyd silently drops a
binding that has a trailing `# ...`). A machine-readable `#minipad {json}` line
records mode order + base name so parse() can recover display names exactly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

PHYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "a", "b"]

# A mode name becomes a keyd [section] header and a toggle()/swap() target, so
# it must be a safe identifier and not a reserved keyd layer name.
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
RESERVED = {"main", "control", "shift", "alt", "meta", "altgr"}
# keyd's command(...) runs a shell command AS ROOT (the daemon is root) — never
# allow it through the editor/generator.
_BADVALUE = re.compile(r"command\s*\(", re.IGNORECASE)

_SECTION = re.compile(r"^\[([^\]:]+)(?::[^\]]+)?\]\s*$")
_META = re.compile(r"^#\s*minipad\s+(\{.*\})\s*$")
_TOGGLE = re.compile(r"^(?:toggle|swap)\(([^)]+)\)$")


@dataclass
class Mode:
    name: str
    chord: list[str] = field(default_factory=list)   # e.g. ["1","3"]
    keys: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    ids: list[str] = field(default_factory=lambda: ["k:4132:2107"])
    globals: dict[str, str] = field(default_factory=lambda: {"chord_timeout": "50"})
    base: str = "apps"
    modes: list[Mode] = field(default_factory=list)

    def mode(self, name: str) -> Mode | None:
        return next((m for m in self.modes if m.name == name), None)


def _strip_comment(rhs: str) -> str:
    # keyd has no inline comments; defensively cut a ` # ...` tail if present.
    i = rhs.find(" #")
    return (rhs[:i] if i >= 0 else rhs).strip()


def parse(text: str) -> Config:
    cfg = Config(ids=[], globals={}, base="apps", modes=[])
    meta = None
    section = None                  # current section header name (or special)
    raw: dict[str, dict] = {}       # section -> {"keys":{}, "chords":[(keys,action)]}
    order: list[str] = []           # section order as they appear

    for line in text.splitlines():
        m = _META.match(line)
        if m:
            try:
                meta = json.loads(m.group(1))
            except ValueError:
                meta = None
            continue
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        sec = _SECTION.match(s)
        if sec:
            section = sec.group(1).strip()
            if section not in ("ids", "global"):
                raw.setdefault(section, {"keys": {}, "chords": []})
                if section not in order:
                    order.append(section)
            continue
        if section == "ids":
            cfg.ids.append(s)
            continue
        if section == "global":
            if "=" in s:
                k, v = s.split("=", 1)
                cfg.globals[k.strip()] = _strip_comment(v)
            continue
        if section is None or "=" not in s:
            continue
        lhs, rhs = s.split("=", 1)
        lhs, rhs = lhs.strip(), _strip_comment(rhs)
        if "+" in lhs:                                   # a chord binding
            raw[section]["chords"].append((lhs.split("+"), rhs))
        elif lhs in PHYS:                                # a single-key binding
            raw[section]["keys"][lhs] = rhs

    # Resolve base display name. Our generated configs carry meta; a hand-written
    # one does not -> the [main] section is the base, displayed as "apps".
    base_disp = (meta or {}).get("base", "apps")
    order_disp = (meta or {}).get("order")

    # Map section name -> display name ("main" is the base).
    def disp(sec_name: str) -> str:
        return base_disp if sec_name == "main" else sec_name

    cfg.base = base_disp

    # Recover each mode's activation chord from the BASE section's chord lines:
    #   chord -> clear()    => base mode's chord
    #   chord -> toggle(X)  => mode X's chord
    chord_for: dict[str, list[str]] = {}
    base_sec = "main" if "main" in raw else next(iter(order), None)
    if base_sec and base_sec in raw:
        for keys, action in raw[base_sec]["chords"]:
            action = action.strip()
            if action == "clear()":
                chord_for[base_disp] = keys
            else:
                t = _TOGGLE.match(action)
                if t:
                    chord_for[disp(t.group(1).strip())] = keys

    # Build modes in display order (base first if known), preserving file order.
    seen = set()
    ordered_secs: list[str] = []
    if order_disp:
        # translate display order back to section names
        for d in order_disp:
            sn = "main" if d == base_disp else d
            if sn in raw and sn not in seen:
                ordered_secs.append(sn); seen.add(sn)
    for sn in (["main"] if "main" in raw else []) + order:
        if sn in raw and sn not in seen:
            ordered_secs.append(sn); seen.add(sn)

    for sn in ordered_secs:
        name = disp(sn)
        cfg.modes.append(Mode(name=name,
                              chord=chord_for.get(name, []),
                              keys=dict(raw[sn]["keys"])))
    if not cfg.ids:
        cfg.ids = ["k:4132:2107"]
    if not cfg.globals:
        cfg.globals = {"chord_timeout": "50"}
    return cfg


def name_ok(name: str) -> bool:
    return bool(NAME_RE.match(name)) and name.lower() not in RESERVED


def value_ok(value: str) -> bool:
    """A key's right-hand value is safe to write into the root keyd config."""
    return not _BADVALUE.search(value) and not any(ord(c) < 32 for c in value)


def validate(cfg: Config) -> list[str]:
    """Return a list of human-readable problems; empty == safe to generate."""
    errs: list[str] = []
    names: set[str] = set()
    chords: dict[frozenset, str] = {}
    for m in cfg.modes:
        if not NAME_RE.match(m.name):
            errs.append(f"mode name '{m.name}' must be letters/digits/_/- (max 32)")
        elif m.name.lower() in RESERVED:
            errs.append(f"mode name '{m.name}' is reserved by keyd")
        if m.name in names:
            errs.append(f"duplicate mode name '{m.name}'")
        names.add(m.name)
        if len(m.chord) == 2 and m.chord[0] != m.chord[1]:
            pair = frozenset(m.chord)
            if pair in chords:
                errs.append(f"chord {_chord_str(m.chord)} is used by both "
                            f"'{chords[pair]}' and '{m.name}'")
            else:
                chords[pair] = m.name
        for k, v in m.keys.items():
            if not value_ok(v):
                errs.append(f"{m.name} key {k}: value '{v}' is not allowed "
                            "(control char or command())")
    return errs


def _chord_str(chord: list[str]) -> str:
    return "+".join(chord)


def generate(cfg: Config) -> str:
    errs = validate(cfg)
    if errs:
        raise ValueError("; ".join(errs))
    base = cfg.base
    non_base = [m for m in cfg.modes if m.name != base]
    out: list[str] = []
    a = out.append

    a("# mini-pad keyd config — generated by the editor. Edit in the panel, or")
    a("# by hand (NO inline comments on binding lines — keyd drops them).")
    a("# Switch a mode = press its 2-key chord together. Base mode is always on;")
    a("# others toggle over it.")
    a("#minipad " + json.dumps(
        {"base": base, "order": [m.name for m in cfg.modes]}, sort_keys=True))
    a("")
    a("[ids]")
    for i in cfg.ids:
        a(i)
    a("")
    a("[global]")
    for k, v in cfg.globals.items():
        a(f"{k} = {v}")
    a("")

    base_mode = cfg.mode(base)
    base_chord = base_mode.chord if base_mode else []

    for mode in cfg.modes:
        is_base = mode.name == base
        a(f"# mode: {mode.name}" + ("  (base)" if is_base else ""))
        a("[main]" if is_base else f"[{mode.name}]")
        a("")
        for k in PHYS:
            if k in mode.keys and mode.keys[k]:
                a(f"{k} = {mode.keys[k]}")
        a("")
        # mode-switch chords
        if base_chord:
            a(f"{_chord_str(base_chord)} = clear()")
        if is_base:
            for other in non_base:
                if other.chord:
                    a(f"{_chord_str(other.chord)} = toggle({other.name})")
        else:
            for other in non_base:
                if other.chord:
                    a(f"{_chord_str(other.chord)} = swap({other.name})")
        a("")
    return "\n".join(out).rstrip() + "\n"


# ── self-test: round-trip stability ──────────────────────────────────────────
if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "/etc/keyd/default.conf"
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    c1 = parse(text)
    g1 = generate(c1)
    c2 = parse(g1)
    g2 = generate(c2)
    print(g1)
    print("=" * 60)
    print("base:", c1.base, "| modes:", [(m.name, m.chord) for m in c1.modes])
    ok = (g1 == g2 and c1.base == c2.base
          and [(m.name, m.chord, m.keys) for m in c1.modes]
          == [(m.name, m.chord, m.keys) for m in c2.modes])
    print("ROUND-TRIP STABLE:", ok)
    sys.exit(0 if ok else 1)
