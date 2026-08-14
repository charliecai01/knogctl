"""Knog Modemaker 1.x HID protocol constants and memory map.

Pure data and pure functions - no I/O, so this is testable without hardware.
Verified against a Cobber Mini Rear. See docs/PROTOCOL.md.

Note: this is the *HID* protocol used by the Cobber Mini / PWR / Bilby /
Bandicoot family. The newer Cobber Reflex and Blinder E/X use a different
WebUSB protocol that is not implemented here.
"""

from __future__ import annotations

USB_VID = 0x10C4  # Silicon Labs
USB_PID = 0xEAC9

HID_USAGE_PAGE = 0xFF00  # vendor-defined
HID_USAGE = 0x01

REPORT_ID = 0x00
NEWCOMMAND = 0x24
FRAME_SIZE = 64

# --- Commands ---------------------------------------------------------------

CMD_IDENTIFY = 0x30
CMD_SETUP = 0x31
CMD_ERASE = 0x32
CMD_WRITE = 0x33
CMD_VERIFY = 0x34
CMD_LOCK = 0x35
CMD_RUN_APP = 0x36
CMD_WNVM = 0x37  # write non-volatile memory
CMD_RNVM = 0x38  # read non-volatile memory

# Magic payload the app sends with CMD_SETUP before erasing.
SETUP_MAGIC = (0xA5, 0xF1, 0x01)

# Response codes. Every successful write is acked with '@' (0x40).
BOOT_ACK_REPLY = 0x40
BOOT_ERR_RANGE = 0x41
BOOT_INVALID_DEVICE = 0x45
BOOT_SEND_DATA_PACKAGE = 0xFF

# --- Memory map (version 1) -------------------------------------------------

PRODUCT_ID_ADDR = 0xFB40
FIRMWARE_VERSION_ADDR = 0xFB81
PREVIOUS_MODE_ADDR = 0xF800

FACTORY_DATA = (0xFB40, 0xFB7F)
SERIAL_NUMBER = (0xFB41, 0xFB44)
DEVICE_INFO = (0xFB72, 0xFB76)
LIGHT_MODES = (0xF801, 0xF809)
DELAYS = (0xF80A, 0xF819)
STATUS_BYTES = (0xF81A, 0xF821)
BUTTONS = (0xF822, 0xF827)
STEP_DATA = (0xF840, 0xF93F)  # 256 bytes - the flash patterns themselves
ALL_MEM = (0xF800, 0xFB83)

MAX_MODES = 8

# Everything worth capturing in a backup, in address order.
BACKUP_REGIONS = (
    ("PreviousMode", 0xF800, 0xF800),
    ("LightModes", *LIGHT_MODES),
    ("Delays", *DELAYS),
    ("StatusBytes", *STATUS_BYTES),
    ("Buttons", *BUTTONS),
    ("StepData", *STEP_DATA),
    ("FactoryData", *FACTORY_DATA),
)


def decode_step(byte: int) -> dict:
    """Decode one pattern step byte (memory map version 1).

    Layout, most significant bit first:
        bits 7-5  brightness (0-7)
        bit  4    delay selector
        bits 3-0  channels 1-4, ch1 in the high bit
    """
    return {
        "brightness": (byte >> 5) & 0x07,
        "delay": (byte >> 4) & 0x01,
        "ch1": (byte >> 3) & 0x01,
        "ch2": (byte >> 2) & 0x01,
        "ch3": (byte >> 1) & 0x01,
        "ch4": byte & 0x01,
    }


def encode_step(brightness: int, delay: int, ch1=0, ch2=0, ch3=0, ch4=0) -> int:
    """Inverse of decode_step."""
    if not 0 <= brightness <= 7:
        raise ValueError(f"brightness must be 0-7, got {brightness}")
    if delay not in (0, 1):
        raise ValueError(f"delay must be 0 or 1, got {delay}")
    return (
        (brightness & 0x07) << 5
        | (delay & 0x01) << 4
        | (bool(ch1)) << 3
        | (bool(ch2)) << 2
        | (bool(ch3)) << 1
        | (bool(ch4))
    )

# --- Product catalog --------------------------------------------------------

# prodcode -> (display name, channel count)
PRODUCTS: dict[int, tuple[str, int]] = {
    2: ("PWR Commuter", 2),
    3: ("PWR Rider", 2),
    4: ("Cobber Front (Small)", 2),
    5: ("Cobber Front (Med)", 3),
    6: ("Cobber Front (Large)", 3),
    7: ("Cobber Rear (Small)", 3),
    8: ("Cobber Rear (Medium)", 3),
    9: ("Cobber Rear (Large)", 3),
    18: ("Cobber Front (Small - Sample)", 2),
    19: ("Cobber Front (Medium - Sample)", 3),
    20: ("Cobber Front (Large - Sample)", 3),
    21: ("Cobber Rear (Small - Sample)", 3),
    22: ("Cobber Rear (Medium - Sample)", 3),
    23: ("Cobber Rear (Large - Sample)", 3),
    24: ("PWR Road", 1),
    25: ("PWR Trail", 2),
    26: ("PWR Mountain / PWR Explorer", 2),
    27: ("PWR Lantern", 1),
    28: ("PWR Camper", 1),
    29: ("PWR Trekker", 1),
    43: ("Cobber Rear (Small StVZO)", 3),
    44: ("Cobber Rear (Medium StVZO)", 3),
    49: ("Bandicoot", 4),
    52: ("Bilby", 8),
    53: ("Bilby Run", 8),
    54: ("Bandicoot 250", 7),
    55: ("Bandicoot Run 250", 8),
    56: ("Bilby", 8),
    57: ("Bilby Run", 8),
    58: ("Blinder 600", 1),
    59: ("Blinder 900", 1),
    60: ("Blinder 1300", 1),
    61: ("Blinder STVZO 500", 1),
    62: ("Blinder STVZO 700", 1),
    64: ("PWR Explorer", 2),
    65: ("PWR Seeker", 1),
    254: ("Default/Unknown", 4),
}

# What Knog sells these as, versus what the firmware calls them.
MARKETING_NAMES = {
    4: "Cobber Mini Front",
    7: "Cobber Mini Rear",
}


def product_name(prodcode: int) -> str:
    """Human-readable model name, preferring the name on the box."""
    if prodcode in MARKETING_NAMES:
        internal = PRODUCTS[prodcode][0]
        return f"{MARKETING_NAMES[prodcode]} ({internal})"
    entry = PRODUCTS.get(prodcode)
    return entry[0] if entry else f"Unknown (prodcode {prodcode})"


def channels(prodcode: int) -> int:
    """Number of independently addressable LED banks."""
    entry = PRODUCTS.get(prodcode)
    return entry[1] if entry else 0


def build_frame(command: int, data: bytes = b"") -> list[int]:
    """Build an outbound HID frame.

    Layout: [report_id, NEWCOMMAND, len(data) + 1, command, *data]

    The length byte counts the command byte plus the data, but not itself,
    the marker, or the report id.
    """
    if not 0 <= command <= 0xFF:
        raise ValueError(f"command out of range: {command}")
    if len(data) + 1 > 0xFF:
        raise ValueError(f"data too long: {len(data)} bytes")
    return [REPORT_ID, NEWCOMMAND, len(data) + 1, command, *data]


def build_read_frame(address: int, count: int = 1) -> list[int]:
    """Frame that reads `count` bytes starting at `address`."""
    if not 0 <= address <= 0xFFFF:
        raise ValueError(f"address out of range: {address:#x}")
    if not 1 <= count <= 0xFF:
        raise ValueError(f"count out of range: {count}")
    return build_frame(CMD_RNVM, bytes([(address >> 8) & 0xFF, address & 0xFF, count]))
