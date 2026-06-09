#!/usr/bin/env python3
"""Print the key NAMES keyd actually emits, by reading its virtual output device.

Pure stdlib (no evdev). You must be in the `input` group (you are). This shows
exactly what reaches applications AFTER keyd's remapping — the ground truth for
debugging modes. Press pad keys; each emitted key prints on its own line.

    python3 tools/keyout.py            # auto-find "keyd virtual keyboard"
    python3 tools/keyout.py /dev/input/event26
"""
import struct
import sys

EV_KEY = 0x01
FMT = "@llHHi"           # input_event: tv_sec, tv_usec, type, code, value (24 bytes)
SZ = struct.calcsize(FMT)

# Linux input-event-codes.h -> readable names (only the codes our config can emit).
NAME = {
    1: "ESC", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8",
    10: "9", 11: "0", 14: "BACKSPACE", 15: "TAB", 17: "W", 20: "T", 28: "ENTER",
    29: "LEFTCTRL", 30: "A", 31: "S", 33: "F", 42: "LEFTSHIFT", 44: "Z", 45: "X",
    46: "C", 47: "V", 48: "B", 56: "LEFTALT", 57: "SPACE",
    71: "KP7", 72: "KP8", 73: "KP9", 75: "KP4", 76: "KP5", 77: "KP6",
    79: "KP1", 80: "KP2", 81: "KP3", 82: "KP0", 83: "KPDOT", 96: "KPENTER",
    97: "RIGHTCTRL", 100: "RIGHTALT", 102: "HOME", 103: "UP", 104: "PAGEUP",
    105: "LEFT", 106: "RIGHT", 107: "END", 108: "DOWN", 109: "PAGEDOWN",
    110: "INSERT", 111: "DELETE", 125: "LEFTMETA",
}
VAL = {0: "up", 1: "DOWN", 2: "repeat"}


def find_dev() -> str:
    with open("/proc/bus/input/devices") as fh:
        block = ""
        for line in fh:
            if line.strip() == "":
                if 'Name="keyd virtual keyboard"' in block:
                    for tok in block.split():
                        if tok.startswith("event"):
                            return "/dev/input/" + tok
                block = ""
            else:
                block += line
    raise SystemExit("keyd virtual keyboard not found")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_dev()
    print(f"reading {path} — press pad keys (Ctrl-C to stop)\n", flush=True)
    with open(path, "rb") as fh:
        while True:
            data = fh.read(SZ)
            if len(data) < SZ:
                break
            _, _, etype, code, value = struct.unpack(FMT, data)
            if etype == EV_KEY and value in (0, 1):
                tag = NAME.get(code, f"code{code}")
                print(f"  {VAL[value]:4} {tag}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
