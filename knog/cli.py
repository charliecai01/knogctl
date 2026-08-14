"""Command-line interface for the Knog controller.

    .venv/bin/python -m knog identify
    .venv/bin/python -m knog backup
    .venv/bin/python -m knog dump 0xF800 0xF830
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .device import DeviceError, KnogLight, find_lights
from . import protocol as p

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"


def _hexdump(data: bytes, base: int, width: int = 16) -> str:
    lines = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hexpart = " ".join(f"{b:02X}" for b in chunk).ljust(width * 3 - 1)
        lines.append(f"  {base + off:#06x}  {hexpart}")
    return "\n".join(lines)


def cmd_list(_args) -> int:
    lights = find_lights()
    if not lights:
        print("No Knog lights connected.")
        return 1
    print(f"{len(lights)} light(s) connected:")
    for d in lights:
        print(f"  path={d['path'].decode(errors='replace')} "
              f"usage_page={d['usage_page']:#06x}")
    return 0


def cmd_identify(_args) -> int:
    with KnogLight() as light:
        print(light.identify().summary())
    return 0


def cmd_backup(args) -> int:
    with KnogLight() as light:
        info = light.identify()
        print(info.summary())
        print("\nreading regions...")

        def progress(name, start, end):
            print(f"  {name:<14} {start:#06x}-{end:#06x} ({end - start + 1} bytes)")

        regions = light.backup(progress=progress)

    payload = {
        "captured": datetime.now().astimezone().isoformat(timespec="seconds"),
        "device": {
            "prodcode": info.prodcode,
            "name": info.name,
            "channels": info.channels,
            "firmware_version": info.firmware_version,
            "bootloader_version": info.bootloader_version,
            "factory_id": info.factory_id,
            "serial": info.serial,
            "manufacture_date": info.manufacture_date,
        },
        "regions": regions,
    }

    out_dir = Path(args.out) if args.out else BACKUP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() else "-" for c in info.name).strip("-").lower()
    path = out_dir / f"{safe}-{info.serial}-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"\nsaved {path}")
    return 0


def cmd_dump(args) -> int:
    start, end = int(args.start, 0), int(args.end, 0)
    if end < start:
        print("end address is below start address", file=sys.stderr)
        return 2
    total = end - start + 1
    if total > 4096:
        print(f"refusing to dump {total} bytes one at a time; narrow the range",
              file=sys.stderr)
        return 2
    with KnogLight() as light:
        data = light.read_range(start, end)
    print(_hexdump(data, start))
    return 0


def cmd_modes(args) -> int:
    """Decode and print the light's programmed modes."""
    from . import modes as modes_mod

    if args.file:
        backup = json.loads(Path(args.file).read_text())
    else:
        with KnogLight() as light:
            info = light.identify()
            print("reading device...\n")
            regions = light.backup()
        backup = {
            "device": {
                "name": info.name, "serial": info.serial,
                "channels": info.channels, "prodcode": info.prodcode,
            },
            "regions": regions,
        }
    print(modes_mod.summarise(backup))
    return 0


def cmd_apply(args) -> int:
    """Write a pattern file to the light, after backing it up."""
    from . import modes as modes_mod

    pattern = json.loads(Path(args.file).read_text())
    regions = pattern["regions"]
    want_prodcode = pattern.get("device", {}).get("prodcode")

    with KnogLight() as light:
        info = light.identify()
        print(info.summary())

        if want_prodcode is not None and info.prodcode != want_prodcode:
            print(f"\nrefusing to write: pattern targets prodcode "
                  f"{want_prodcode}, connected light is {info.prodcode}",
                  file=sys.stderr)
            return 2

        # Safety net before touching flash.
        print("\nbacking up current settings first...")
        before = light.backup()
        out_dir = BACKUP_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if c.isalnum() else "-" for c in info.name).strip("-").lower()
        backup_path = out_dir / f"PRE-APPLY-{safe}-{info.serial}-{stamp}.json"
        backup_path.write_text(json.dumps({
            "captured": datetime.now().astimezone().isoformat(timespec="seconds"),
            "device": {"prodcode": info.prodcode, "name": info.name,
                       "channels": info.channels, "serial": info.serial},
            "regions": before,
        }, indent=2) + "\n")
        print(f"  saved {backup_path}")

        if args.dry_run:
            print("\n-- dry run, nothing written --")
            print(f"  settings block -> {p.PREVIOUS_MODE_ADDR:#06x} (40 bytes)")
            for i in range(0, 256, p.FRAME_SIZE):
                print(f"  step data      -> {p.STEP_DATA[0] + i:#06x} "
                      f"({p.FRAME_SIZE} bytes)")
            return 0

        print("\nwriting...")
        light.unlock()
        print("  unlocked")
        light.apply_settings_block(
            regions["LightModes"]["bytes"], regions["Delays"]["bytes"],
            regions["StatusBytes"]["bytes"], regions["Buttons"]["bytes"])
        print(f"  settings block -> {p.PREVIOUS_MODE_ADDR:#06x}")
        light.apply_step_data(
            regions["StepData"]["bytes"],
            progress=lambda a, n: print(f"  step data      -> {a:#06x} ({n} bytes)"))

        print("\nverifying by reading back...")
        after = light.backup()

    mismatches = []
    for name in ("LightModes", "Delays", "StatusBytes", "Buttons", "StepData"):
        want = list(regions[name]["bytes"])
        got = list(after[name]["bytes"])
        if want != got:
            diffs = [(i, w, g) for i, (w, g) in enumerate(zip(want, got)) if w != g]
            mismatches.append((name, diffs))

    if mismatches:
        print("\nVERIFY FAILED:", file=sys.stderr)
        for name, diffs in mismatches:
            print(f"  {name}: {len(diffs)} byte(s) differ", file=sys.stderr)
            for i, w, g in diffs[:8]:
                print(f"    [{i}] wrote 0x{w:02X}, read 0x{g:02X}", file=sys.stderr)
        print(f"\nRestore with the backup at {backup_path}", file=sys.stderr)
        return 1

    print("  all regions match\n")
    print(modes_mod.summarise({"device": {"name": info.name, "serial": info.serial,
                                          "channels": info.channels},
                               "regions": after}))
    return 0


def cmd_regions(_args) -> int:
    print("known regions:")
    for name, start, end in p.BACKUP_REGIONS:
        print(f"  {name:<14} {start:#06x}-{end:#06x}  ({end - start + 1} bytes)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="knog", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list connected lights").set_defaults(fn=cmd_list)
    sub.add_parser("identify", help="show device details").set_defaults(fn=cmd_identify)
    sub.add_parser("regions", help="list known memory regions").set_defaults(fn=cmd_regions)

    b = sub.add_parser("backup", help="save all readable settings to JSON")
    b.add_argument("--out", help="output directory")
    b.set_defaults(fn=cmd_backup)

    m = sub.add_parser("modes", help="decode programmed light modes")
    m.add_argument("--file", help="decode a saved backup instead of reading the light")
    m.set_defaults(fn=cmd_modes)

    a = sub.add_parser("apply", help="write a pattern file to the light")
    a.add_argument("file")
    a.add_argument("--dry-run", action="store_true",
                   help="back up and show the write plan without writing")
    a.set_defaults(fn=cmd_apply)

    d = sub.add_parser("dump", help="hexdump an address range")
    d.add_argument("start")
    d.add_argument("end")
    d.set_defaults(fn=cmd_dump)

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except DeviceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
