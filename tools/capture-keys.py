#!/usr/bin/python3
"""Capture HID scancodes and current keycode mappings for a device.

Reads every evdev node belonging to the Kinesis Freestyle2 for Mac (or any
device given on the command line) and prints, for each key press, the raw HID
scancode alongside the keycode the kernel currently maps it to. The scancode
is what goes into a hwdb KEYBOARD_KEY_ entry.

Usage:
    sudo ./tools/capture-keys.py            # auto-detect by vid:pid
    sudo ./tools/capture-keys.py /dev/input/event5 /dev/input/event10
"""

import glob
import os
import re
import select
import struct
import sys

VID = "058f"
PID = "9410"

EV_SYN = 0x00
EV_KEY = 0x01
EV_MSC = 0x04
MSC_SCAN = 0x04

# struct input_event { struct timeval time; __u16 type, code; __s32 value; }
EVENT_FMT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

VALUE_NAMES = {0: "release", 1: "press", 2: "repeat"}


def load_keycode_names():
    """Map keycode number -> KEY_* name from the kernel uapi header."""
    names = {}
    path = "/usr/include/linux/input-event-codes.h"
    pattern = re.compile(r"^#define\s+((?:KEY|BTN)_\w+)\s+(\w+)")
    try:
        with open(path) as fh:
            raw = {}
            for line in fh:
                m = pattern.match(line)
                if m:
                    raw[m.group(1)] = m.group(2)
        for name, value in raw.items():
            try:
                code = int(value, 0)
            except ValueError:
                # Aliases such as KEY_MIN_INTERESTING defined by another name
                ref = raw.get(value)
                if ref is None:
                    continue
                try:
                    code = int(ref, 0)
                except ValueError:
                    continue
            # Prefer the canonical KEY_ name over later aliases
            names.setdefault(code, name)
    except OSError:
        pass
    return names


def find_devices():
    found = []
    for path in sorted(glob.glob("/sys/class/input/event*")):
        uevent = os.path.join(path, "device", "uevent")
        try:
            with open(uevent) as fh:
                text = fh.read().lower()
        except OSError:
            continue
        if f"v{VID.zfill(4)}p{PID.zfill(4)}" in text.replace("0000", "") or (
            VID in text and PID in text
        ):
            found.append("/dev/input/" + os.path.basename(path))
    return found


def device_name(dev):
    node = os.path.basename(dev)
    try:
        with open(f"/sys/class/input/{node}/device/name") as fh:
            return fh.read().strip()
    except OSError:
        return dev


def main():
    keynames = load_keycode_names()

    devices = sys.argv[1:] or find_devices()
    if not devices:
        sys.exit(f"No input devices found for {VID}:{PID}")

    handles = {}
    for dev in devices:
        try:
            handles[os.open(dev, os.O_RDONLY)] = dev
        except PermissionError:
            sys.exit(f"Permission denied opening {dev}; run with sudo")

    print("Watching:")
    for fd, dev in handles.items():
        print(f"  {dev}  {device_name(dev)}")
    print("\nPress each key you want to map. Ctrl-C when done.\n")
    print(f"{'scancode':>10}  {'keycode':>5}  {'name':<24} {'action':<8} device")
    print("-" * 78)

    pending_scan = {}
    try:
        while True:
            ready, _, _ = select.select(list(handles), [], [])
            for fd in ready:
                data = os.read(fd, EVENT_SIZE * 64)
                for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
                    _, _, etype, code, value = struct.unpack_from(
                        EVENT_FMT, data, off
                    )
                    if etype == EV_MSC and code == MSC_SCAN:
                        pending_scan[fd] = value
                    elif etype == EV_KEY:
                        scan = pending_scan.pop(fd, None)
                        # Only report press and release, skip autorepeat noise
                        if value == 2:
                            continue
                        scan_text = f"{scan:x}" if scan is not None else "-"
                        name = keynames.get(code, "?")
                        node = os.path.basename(handles[fd])
                        print(
                            f"{scan_text:>10}  {code:>5}  {name:<24} "
                            f"{VALUE_NAMES.get(value, value):<8} {node}"
                        )
                        sys.stdout.flush()
                    elif etype == EV_SYN:
                        pending_scan.pop(fd, None)
    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        for fd in handles:
            os.close(fd)


if __name__ == "__main__":
    main()
