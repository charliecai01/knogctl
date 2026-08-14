#!/usr/bin/env python3
"""Read-only probe of a connected Knog light.

Uses only RNVM (0x38), the read-non-volatile-memory command. Nothing here
writes, erases, or programs anything.

    .venv/bin/python tools/probe.py
"""

from __future__ import annotations

import sys

import hid

VID, PID = 0x10C4, 0xEAC9

CMD_RNVM = 0x38
NEWCOMMAND = 0x24

# Memory map version 1, from KnogDeviceMemoryMap.js
PRODUCT_ID_ADDR = 0xFB40
FIRMWARE_VERSION_ADDR = 0xFB81
SERIAL_RANGE = (0xFB41, 0xFB44)
DEVICE_INFO_RANGE = (0xFB72, 0xFB76)
LIGHT_MODES_RANGE = (0xF801, 0xF809)
DELAYS_RANGE = (0xF80A, 0xF819)

PRODUCTS = {
    2: "PWR Commuter", 3: "PWR Rider", 4: "Cobber Front (Small)",
    5: "Cobber Front (Med)", 6: "Cobber Front (Large)",
    7: "Cobber Rear (Small)", 8: "Cobber Rear (Medium)",
    9: "Cobber Rear (Large)", 18: "Cobber Front (Small - Sample)",
    19: "Cobber Front (Medium - Sample)", 20: "Cobber Front (Large - Sample)",
    21: "Cobber Rear (Small - Sample)", 22: "Cobber Rear (Medium - Sample)",
    23: "Cobber Rear (Large - Sample)", 24: "PWR Road", 25: "PWR Trail",
    26: "PWR Mountain / PWR Explorer", 27: "PWR Lantern", 28: "PWR Camper",
    29: "PWR Trekker", 43: "Cobber Rear (Small StVZO)",
    44: "Cobber Rear (Medium StVZO)", 49: "Bandicoot", 52: "Bilby",
    53: "Bilby Run", 54: "Bandicoot 250", 55: "Bandicoot Run 250",
    56: "Bilby", 57: "Bilby Run", 58: "Blinder 600", 59: "Blinder 900",
    60: "Blinder 1300", 61: "Blinder STVZO 500", 62: "Blinder STVZO 700",
    64: "PWR Explorer", 65: "PWR Seeker", 254: "Default/Unknown",
}


def read_byte(dev, address: int) -> int | None:
    """Read one byte of device memory. Returns None on timeout."""
    # [report_id, marker, length, command, addr_hi, addr_lo, count]
    dev.write([0x00, NEWCOMMAND, 0x04, CMD_RNVM,
               (address >> 8) & 0xFF, address & 0xFF, 0x01])
    resp = dev.read(64, timeout_ms=500)
    return resp[0] if resp else None


def read_range(dev, start: int, end: int) -> list[int | None]:
    return [read_byte(dev, a) for a in range(start, end + 1)]


def fmt(values) -> str:
    return " ".join("--" if v is None else f"{v:02X}" for v in values)


def main() -> int:
    matches = [d for d in hid.enumerate()
               if d["vendor_id"] == VID and d["product_id"] == PID]
    if not matches:
        print(f"No Knog light found ({VID:#06x}:{PID:#06x}).", file=sys.stderr)
        print("Plug it in with a data-capable USB-C cable.", file=sys.stderr)
        return 1

    print(f"Found {len(matches)} interface(s); opening the first.\n")
    dev = hid.device()
    dev.open_path(matches[0]["path"])
    try:
        pid_val = read_byte(dev, PRODUCT_ID_ADDR)
        if pid_val is None:
            print("No response to the read command.", file=sys.stderr)
            print("The light may need to be awake - press its button.", file=sys.stderr)
            return 2

        name = PRODUCTS.get(pid_val, "UNKNOWN - not in Modemaker 1.x catalog")
        print(f"  product id        {pid_val}  (0x{pid_val:02X})")
        print(f"  model             {name}")

        fw = read_byte(dev, FIRMWARE_VERSION_ADDR)
        print(f"  firmware version  {fw}")

        serial = read_range(dev, *SERIAL_RANGE)
        print(f"  serial bytes      {fmt(serial)}")
        info = read_range(dev, *DEVICE_INFO_RANGE)
        print(f"  device info       {fmt(info)}")
        if info and info[0] is not None:
            print(f"    bootloader ver  {info[0]}")
            if len(info) > 1 and info[1] is not None:
                print(f"    factory id      {info[1]}")

        print(f"\n  light modes  ({LIGHT_MODES_RANGE[0]:#06x}-{LIGHT_MODES_RANGE[1]:#06x})")
        print(f"    {fmt(read_range(dev, *LIGHT_MODES_RANGE))}")
        print(f"  delays       ({DELAYS_RANGE[0]:#06x}-{DELAYS_RANGE[1]:#06x})")
        print(f"    {fmt(read_range(dev, *DELAYS_RANGE))}")
        return 0
    finally:
        dev.close()


if __name__ == "__main__":
    sys.exit(main())
