"""Decode a Knog light's memory into readable modes.

The layout below is inferred from the app source plus verified device reads.
Where it is inference rather than fact, the docstrings say so.

Confidence notes
----------------
- Step byte encoding: **confirmed** - taken directly from DeviceMode.js.
- LightModes as cumulative step offsets: **strongly supported but inferred.**
  Nine values bound eight modes, they are non-decreasing, and they account
  for exactly the non-erased bytes in StepData on a real device. The same
  cumulative-offset scheme appears in the Modemaker 2.0 bundle. It has not
  been proven by writing to hardware.
- Delays as (short, long) pairs per mode: **inferred** from the 16-byte
  region splitting evenly across 8 modes, matching the count of programmed
  modes on a real device.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import protocol as p

ERASED = 0xFF  # unprogrammed flash


@dataclass
class Step:
    """One step of a flash pattern."""

    raw: int
    brightness: int  # 0-7
    delay: int  # 0 or 1 - selects which of the mode's two delays applies
    channels: tuple[int, ...]  # which of ch1..ch4 are lit

    @classmethod
    def from_byte(cls, byte: int) -> Step:
        d = p.decode_step(byte)
        channels = tuple(n for n in (1, 2, 3, 4) if d[f"ch{n}"])
        return cls(raw=byte, brightness=d["brightness"], delay=d["delay"],
                   channels=channels)

    def describe(self, delays: tuple[int, int] | None = None) -> str:
        ch = ",".join(str(c) for c in self.channels) if self.channels else "none"
        ms = ""
        if delays:
            ms = f"  {delays[self.delay]} units"
        return (f"0x{self.raw:02X}  brightness {self.brightness}/7  "
                f"ch {ch:<7}{ms}")


@dataclass
class Mode:
    index: int  # 1-based, as the user counts button presses
    steps: list[Step]
    delays: tuple[int, int] | None
    status: int | None

    @property
    def programmed(self) -> bool:
        return bool(self.steps)

    def describe(self) -> str:
        if not self.programmed:
            return f"Mode {self.index}: (empty)"
        head = f"Mode {self.index}: {len(self.steps)} steps"
        if self.delays:
            head += f"   delays short={self.delays[0]} long={self.delays[1]}"
        if self.status is not None and self.status != ERASED:
            head += f"   status=0x{self.status:02X}"
        body = "\n".join("    " + s.describe(self.delays) for s in self.steps)
        return head + "\n" + body


def _region(backup: dict, name: str) -> bytes:
    region = backup.get("regions", {}).get(name)
    if not region:
        return b""
    return bytes(region["bytes"])


def decode(backup: dict) -> list[Mode]:
    """Decode a backup dict (as written by `knog backup`) into modes."""
    offsets = _region(backup, "LightModes")
    steps_raw = _region(backup, "StepData")
    delays_raw = _region(backup, "Delays")
    status_raw = _region(backup, "StatusBytes")

    modes: list[Mode] = []
    for i in range(p.MAX_MODES):
        start = offsets[i] if i < len(offsets) else None
        end = offsets[i + 1] if i + 1 < len(offsets) else None

        steps: list[Step] = []
        # An erased or non-increasing boundary means the slot is unused.
        if (start is not None and end is not None
                and start != ERASED and end != ERASED and end > start):
            for byte in steps_raw[start:end]:
                if byte == ERASED:
                    break
                steps.append(Step.from_byte(byte))

        delays = None
        lo, hi = 2 * i, 2 * i + 1
        if hi < len(delays_raw) and delays_raw[lo] != ERASED:
            delays = (delays_raw[lo], delays_raw[hi])

        status = status_raw[i] if i < len(status_raw) else None
        modes.append(Mode(index=i + 1, steps=steps, delays=delays, status=status))

    return modes


def summarise(backup: dict) -> str:
    modes = decode(backup)
    dev = backup.get("device", {})
    out = [f"{dev.get('name', 'unknown device')}  (serial {dev.get('serial', '?')})",
           f"channels: {dev.get('channels', '?')}", ""]
    active = [m for m in modes if m.programmed]
    out.append(f"{len(active)} of {p.MAX_MODES} mode slots programmed")
    out.append("")
    for mode in modes:
        if mode.programmed:
            out.append(mode.describe())
    empty = [str(m.index) for m in modes if not m.programmed]
    if empty:
        out.append(f"\nempty slots: {', '.join(empty)}")
    return "\n".join(out)
