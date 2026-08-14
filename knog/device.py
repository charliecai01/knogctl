"""HID transport for Knog lights.

Only reads are implemented so far. The write path (Setup/Erase/WNVM) touches
flash and is deliberately absent until a verified backup/restore round-trip
exists.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import hid

from . import protocol as p


class DeviceError(Exception):
    """Something went wrong talking to the light."""


@dataclass
class DeviceInfo:
    prodcode: int
    name: str
    channels: int
    firmware_version: int | None
    bootloader_version: int | None
    factory_id: int | None
    serial: str
    manufacture_date: str | None = None

    def summary(self) -> str:
        lines = [
            f"model             {self.name}",
            f"prodcode          {self.prodcode}",
            f"channels          {self.channels}",
            f"firmware version  {self.firmware_version}",
            f"bootloader        {self.bootloader_version}",
            f"factory id        {self.factory_id}",
            f"serial            {self.serial}",
        ]
        if self.manufacture_date:
            lines.append(f"manufactured      {self.manufacture_date}")
        return "\n".join(lines)


def find_lights() -> list[dict]:
    """Every connected Knog light, as hidapi device-info dicts."""
    return [
        d for d in hid.enumerate()
        if d["vendor_id"] == p.USB_VID and d["product_id"] == p.USB_PID
    ]


class KnogLight:
    """A connected Knog light. Use as a context manager."""

    def __init__(self, path: bytes | None = None, read_timeout_ms: int = 500):
        self._path = path
        self._read_timeout_ms = read_timeout_ms
        self._dev: hid.device | None = None

    def __enter__(self) -> KnogLight:
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        path = self._path
        if path is None:
            found = find_lights()
            if not found:
                raise DeviceError(
                    f"No Knog light found ({p.USB_VID:#06x}:{p.USB_PID:#06x}). "
                    "Check it is plugged in with a data-capable USB-C cable."
                )
            path = found[0]["path"]
        self._dev = hid.device()
        self._dev.open_path(path)

    def close(self) -> None:
        if self._dev is not None:
            self._dev.close()
            self._dev = None

    @property
    def _device(self) -> hid.device:
        if self._dev is None:
            raise DeviceError("device is not open")
        return self._dev

    # --- reads --------------------------------------------------------------

    def read_byte(self, address: int, retries: int = 2) -> int:
        """Read one byte of device memory."""
        frame = p.build_read_frame(address, 1)
        for attempt in range(retries + 1):
            self._device.write(frame)
            resp = self._device.read(p.FRAME_SIZE, timeout_ms=self._read_timeout_ms)
            if resp:
                return resp[0]
            if attempt < retries:
                time.sleep(0.01)
        raise DeviceError(f"no response reading {address:#06x}")

    def read_range(self, start: int, end: int) -> bytes:
        """Read an inclusive address range, one byte per request."""
        if end < start:
            raise ValueError(f"bad range {start:#06x}..{end:#06x}")
        return bytes(self.read_byte(a) for a in range(start, end + 1))

    # --- identity -----------------------------------------------------------

    def identify(self) -> DeviceInfo:
        prodcode = self.read_byte(p.PRODUCT_ID_ADDR)
        serial_bytes = self.read_range(*p.SERIAL_NUMBER)
        info = self.read_range(*p.DEVICE_INFO)

        firmware = self.read_byte(p.FIRMWARE_VERSION_ADDR)
        # The app clamps implausible firmware readings to 1.
        if firmware > 100:
            firmware = 1

        bootloader = info[0] if len(info) > 0 else None
        # A bootloader reporting 255 is really 0 (app applies the same fix).
        if bootloader == 255:
            bootloader = 0

        date = None
        if len(info) >= 4:
            date = f"20{info[2]:02d}-{info[3]:02d}"

        return DeviceInfo(
            prodcode=prodcode,
            name=p.product_name(prodcode),
            channels=p.channels(prodcode),
            firmware_version=firmware,
            bootloader_version=bootloader,
            factory_id=info[1] if len(info) > 1 else None,
            # The app concatenates the decimal values rather than hex-encoding.
            serial="".join(str(b) for b in serial_bytes),
            manufacture_date=date,
        )

    # --- writes -------------------------------------------------------------
    #
    # Every write is acknowledged with BOOT_ACK_REPLY (0x40). Anything else
    # aborts immediately rather than pressing on through a page sequence.

    def _write_frame(self, command: int, data: list[int]) -> None:
        """Send one command frame and require an ack.

        The frame is [0x24, len(data)+1, command, *data], split into 64-byte
        HID packets (each prefixed with report id 0), with a single ack read
        at the end regardless of how many packets it took.
        """
        for b in data:
            if not 0 <= b <= 0xFF:
                raise DeviceError(f"byte out of range in frame: {b}")
        frame = [p.NEWCOMMAND, len(data) + 1, command, *data]

        for off in range(0, len(frame), p.FRAME_SIZE):
            chunk = frame[off:off + p.FRAME_SIZE]
            self._device.write([p.REPORT_ID, *chunk])

        resp = self._device.read(p.FRAME_SIZE, timeout_ms=self._read_timeout_ms)
        if not resp:
            raise DeviceError(
                f"no ack for command 0x{command:02X} "
                f"(device may have rejected the write)"
            )
        if resp[0] != p.BOOT_ACK_REPLY:
            raise DeviceError(
                f"command 0x{command:02X} not acked: got 0x{resp[0]:02X}, "
                f"expected 0x{p.BOOT_ACK_REPLY:02X}"
            )

    def unlock(self) -> None:
        """Send the Setup magic that permits subsequent page writes."""
        self._write_frame(p.CMD_SETUP, list(p.SETUP_MAGIC))

    def write_page(self, address: int, data: list[int]) -> None:
        """Write `data` at `address`.

        Despite the name, CMD_ERASE is an erase-and-write-page operation: it
        takes a big-endian address followed by the bytes to place there.
        """
        if not 0 <= address <= 0xFFFF:
            raise ValueError(f"address out of range: {address:#x}")
        lo, hi = p.ALL_MEM
        if address < lo or address + len(data) - 1 > hi:
            raise DeviceError(
                f"refusing to write {address:#06x}..{address + len(data) - 1:#06x}: "
                f"outside the settings area {lo:#06x}..{hi:#06x}"
            )
        self._write_frame(p.CMD_ERASE, [(address >> 8) & 0xFF, address & 0xFF, *data])

    def apply_settings_block(self, start_modes, delays, status, buttons) -> None:
        """Write the 40-byte settings block at PreviousMode (0xF800).

        Layout, straight from deviceWriteFlashPatterns():
            PreviousMode(1) StartModes(9) Delays(16) Status(8) Buttons(6)
        """
        for name, seq, want in (("StartModes", start_modes, 9),
                                ("Delays", delays, 16),
                                ("StatusBytes", status, 8),
                                ("Buttons", buttons, 6)):
            if len(seq) != want:
                raise DeviceError(f"{name} must be {want} bytes, got {len(seq)}")
        block = [0, *start_modes, *delays, *status, *buttons]
        self.write_page(p.PREVIOUS_MODE_ADDR, block)

    def apply_step_data(self, step_data: list[int], progress=None) -> None:
        """Write StepData in 64-byte pages, as the app does."""
        expected = p.STEP_DATA[1] - p.STEP_DATA[0] + 1
        if len(step_data) != expected:
            raise DeviceError(
                f"StepData must be {expected} bytes, got {len(step_data)}")
        address = p.STEP_DATA[0]
        for off in range(0, len(step_data), p.FRAME_SIZE):
            page = step_data[off:off + p.FRAME_SIZE]
            if progress:
                progress(address, len(page))
            self.write_page(address, page)
            address += p.FRAME_SIZE

    # --- backup -------------------------------------------------------------

    def backup(self, progress=None) -> dict[str, dict]:
        """Read every known region. Returns a JSON-serialisable dict."""
        out: dict[str, dict] = {}
        for name, start, end in p.BACKUP_REGIONS:
            if progress:
                progress(name, start, end)
            data = self.read_range(start, end)
            out[name] = {
                "start": start,
                "end": end,
                "hex": data.hex(),
                "bytes": list(data),
            }
        return out
