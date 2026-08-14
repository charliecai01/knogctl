#!/usr/bin/env python3
"""Watch macOS USB for a Knog light appearing.

Stdlib only - no install needed. Parses `ioreg -a` XML plist output, which is
far more robust than scraping the human-readable ioreg tree.

    python3 tools/usbwatch.py snap            # one-shot listing
    python3 tools/usbwatch.py watch           # poll until a device appears
    python3 tools/usbwatch.py watch --secs 90
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
import time

SILABS_VID = 0x10C4
# PIDs the Modemaker 2.0 bundle filters on.
KNOWN_PIDS = {0x1AE0: "Modemaker PID 6880", 0x1A16: "Modemaker PID 6678", 0x1A9A: "Modemaker PID 6810"}

DEVICE_TYPES = {
    82: "Cobber Mini Rear",
    83: "Cobber Mini Front",
    90: "Cobber Mini Rear (StVZO)",
    95: "Cobber Reflex Rear",
    96: "Cobber Reflex Front",
}

FIELDS = (
    "idVendor", "idProduct", "USB Product Name", "USB Vendor Name",
    "USB Serial Number", "bcdDevice", "bDeviceClass", "bDeviceSubClass",
    "bDeviceProtocol", "locationID",
)


def _walk(node, out):
    """Depth-first walk of the ioreg plist tree, collecting USB device nodes."""
    if isinstance(node, dict):
        if "idVendor" in node and "idProduct" in node:
            out.append({k: node.get(k) for k in FIELDS})
        for child in node.get("IORegistryEntryChildren", []) or []:
            _walk(child, out)
    elif isinstance(node, list):
        for item in node:
            _walk(item, out)


def devices():
    """Return every USB device currently enumerated, as a list of dicts."""
    raw = subprocess.run(
        ["ioreg", "-p", "IOUSB", "-a", "-l", "-w0"],
        capture_output=True, check=True,
    ).stdout
    if not raw.strip():
        return []
    found: list[dict] = []
    _walk(plistlib.loads(raw), found)
    return found


def key(d):
    return (d.get("idVendor"), d.get("idProduct"), d.get("locationID"))


def describe(d):
    vid, pid = d.get("idVendor"), d.get("idProduct")
    name = d.get("USB Product Name") or "(no product string)"
    vendor = d.get("USB Vendor Name") or "(no vendor string)"
    line = f"{vid:#06x}:{pid:#06x}  {name}  [{vendor}]"

    notes = []
    if vid == SILABS_VID:
        notes.append("Silicon Labs")
    if pid in KNOWN_PIDS:
        notes.append(f"*** KNOG LIGHT - {KNOWN_PIDS[pid]} ***")
    cls = d.get("bDeviceClass")
    if cls == 0:
        notes.append("class 0 (per-interface; likely vendor-specific - claimable)")
    elif cls == 3:
        notes.append("class 3 HID (macOS claims it; needs WebHID/hidapi, not libusb)")
    if notes:
        line += "\n      " + "\n      ".join(notes)
    return line


def is_candidate(d):
    return d.get("idProduct") in KNOWN_PIDS or d.get("idVendor") == SILABS_VID


def cmd_snap(_args):
    devs = devices()
    print(f"{len(devs)} USB device(s):\n")
    for d in devs:
        print("  " + describe(d) + "\n")
    hits = [d for d in devs if d.get("idProduct") in KNOWN_PIDS]
    print(f"Knog lights detected: {len(hits)}")
    return 0 if hits else 1


def cmd_watch(args):
    baseline = {key(d): d for d in devices()}
    print(f"Baseline: {len(baseline)} devices. Plug in the light now (Ctrl-C to stop).\n")
    deadline = time.time() + args.secs
    try:
        while time.time() < deadline:
            time.sleep(1.0)
            current = {key(d): d for d in devices()}

            for k in current.keys() - baseline.keys():
                print("+ APPEARED  " + describe(current[k]) + "\n")
                if is_candidate(current[k]):
                    print("  ^ This looks like the light. Stopping.\n")
                    return 0
            for k in baseline.keys() - current.keys():
                print("- removed   " + describe(baseline[k]) + "\n")

            baseline = current
    except KeyboardInterrupt:
        print("\nStopped.")
        return 1
    print("Timed out - nothing appeared.")
    return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snap").set_defaults(fn=cmd_snap)
    w = sub.add_parser("watch")
    w.add_argument("--secs", type=int, default=120)
    w.set_defaults(fn=cmd_watch)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
