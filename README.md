# knogctl — an open replacement for Knog Modemaker

**Customise the flash patterns on your Knog bike light from the command line or
your browser, without the official Modemaker app.**

If you landed here because *Knog Modemaker won't detect your light*, because
Modemaker 2.0 says your Cobber Mini isn't supported, or because the official app
is simply painful to use — this is for you. `knogctl` talks to the light
directly over USB HID, reads its settings, backs them up, and writes new flash
patterns.

Works on **macOS and Linux** (and the browser UI works anywhere Chrome does).
No account, no cloud sync, no login.

> Not affiliated with, authorised, or endorsed by Knog. "Knog", "Cobber" and
> "Modemaker" are trademarks of their respective owner. This is an independent
> interoperability project for hardware you already own.

---

## Does this work with my light?

`knogctl` supports the **Modemaker 1.x generation**, which present as USB HID
device `0x10C4:0xEAC9`:

| Supported | Notes |
|---|---|
| **Cobber Mini Front / Rear** | sold as "Mini", internally `Cobber Front/Rear (Small)` |
| Lil' / Mid / Big Cobber | prodcodes 4–9, 43–44 |
| PWR Commuter, Rider, Road, Trail, Mountain | |
| PWR Explorer, Seeker, Camper, Trekker, Lantern | |
| Bilby, Bandicoot headlamps | |
| Blinder 600 / 900 / 1300 | |

**Not supported:** Cobber Reflex, Blinder E, Blinder X. Those are the
*Modemaker 2.0* generation and use a completely different WebUSB protocol with
different USB product IDs. See [docs/PROTOCOL.md](docs/PROTOCOL.md).

Verified end-to-end on **two models** — Cobber Mini **Rear** (prodcode 7) and
Cobber Mini **Front** (prodcode 4), both firmware 3. Reads, backup, write and
read-back verification all confirmed on each. Other models in the table share
the protocol and memory map but are untested — see
[Drawbacks](#drawbacks-and-known-limitations).

### Per-model differences worth knowing

Two lights of the same generation are not identical, and assuming they are will
bite you:

| | Cobber Mini Rear (7) | Cobber Mini Front (4) |
|---|---|---|
| LED channels | 3 (uses ch1-4 at peak) | 2 (only ch1, ch2) |
| `StatusBytes` base | `0x03` | `0x01` |
| Factory modes | 2 | 3 |

**Always read a light before writing to it.** Copy `StatusBytes` conventions
from that light's own backup, not from another model.

---

## Why this exists

Three things about these lights cost people hours, and none are documented by
Knog:

1. **Knog's marketing pages list the wrong app.** The Cobber Mini appears on
   *neither* Modemaker support list, but it is a Modemaker 1.x device. Modemaker
   2.0 filters for USB IDs your Mini doesn't have, so it will never see it.
2. **The light publishes no USB string descriptors.** `iProduct`,
   `iManufacturer` and `iSerialNumber` are all zero, so it appears in `ioreg` or
   `lsusb` as an anonymous Silicon Labs device with no name — easy to mistake
   for a dock or hub chip. It is easy to conclude your cable is broken when it
   isn't.
3. **The "hold the power button until the LED flashes green and red"
   instruction is for Modemaker 2.0 lights only.** Modemaker 1.x lights,
   including the Cobber Mini, enumerate on plug-in with no button press.

If your light charges but nothing appears on USB, see
[Troubleshooting](#troubleshooting).

---

## Features

- **Identify** your light — model, prodcode, firmware, bootloader, serial
- **Back up** every readable settings region to timestamped JSON
- **Decode** flash patterns into readable steps: brightness, timing, LED channels
- **Write** new patterns, with an automatic pre-write backup, a model guard, an
  ack required on every page, and full read-back verification
- **Browser UI** (WebHID) that reads the light and **animates** each mode so you
  can see a pattern before committing to it
- **Hexdump** any address range for your own protocol poking
- Patterns are **plain JSON** you can edit, diff, and version-control
- **No cloud.** The official app syncs patterns from a remote CouchDB and wants
  an account. This does not.

---

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/charliecai01/knogctl.git
cd knogctl
python3 -m venv .venv
./.venv/bin/pip install hidapi
```

On Linux you may need libusb/hidraw headers and a udev rule granting access to
`10c4:eac9` (macOS needs neither):

```bash
sudo tee /etc/udev/rules.d/99-knog.rules <<'EOF'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="eac9", MODE="0666"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## Usage

Plug the light in with a **data-capable** USB-C cable and run:

```bash
./.venv/bin/python -m knog identify
```

```
model             Cobber Mini Rear (Cobber Rear (Small))
prodcode          7
channels          3
firmware version  3
bootloader        4
serial            000000000000
```

| Command | What it does |
|---|---|
| `list` | list connected Knog lights |
| `identify` | model, firmware, bootloader, serial |
| `backup` | save all readable regions to `backups/*.json` |
| `modes` | decode and print the light's current flash patterns |
| `modes --file <json>` | decode a saved backup or a pattern file |
| `apply <json>` | write a pattern file to the light |
| `apply <json> --dry-run` | back up and show the write plan, write nothing |
| `dump <start> <end>` | hexdump an address range, e.g. `dump 0xF840 0xF8BF` |
| `regions` | list known memory regions |

### Back up before you change anything

```bash
./.venv/bin/python -m knog backup
```

### See what's on the light now

```bash
./.venv/bin/python -m knog modes
```

```
Mode 1: 4 steps   delays short=20 long=150   status=0x0B
    0xEF  brightness 7/7  ch 1,2,3,4  20 units
    0x2E  brightness 1/7  ch 1,2,3    20 units
    0xEF  brightness 7/7  ch 1,2,3,4  20 units
    0x5E  brightness 2/7  ch 1,2,3    150 units
```

### Write a pattern

```bash
./.venv/bin/python -m knog apply patterns/dawn-patrol.json --dry-run
./.venv/bin/python -m knog apply patterns/dawn-patrol.json
```

`apply` refuses to run if the pattern's prodcode doesn't match the connected
light, takes a `PRE-APPLY-*` backup first, requires an ack on every page, and
reads everything back to confirm it matches.

### Restore

A backup is a valid pattern file, so restoring is just:

```bash
./.venv/bin/python -m knog apply backups/PRE-APPLY-....json
```

---

## Browser UI

Open `web/index.html` in **Chrome or Edge** (Safari and Firefox have no WebHID).
Click *Connect light* to read it directly in the browser, or *Load backup JSON*
to inspect a file. Every mode gets an animated preview across the light's LED
channels.

The browser UI is **read-only** — it never writes. Use the CLI to apply.

---

## Writing your own patterns

A pattern is JSON. Each step of a flash pattern is one byte:

```
bits 7-5  brightness (0-7, where 0 is off)
bit  4    delay selector (picks one of the mode's two delay values)
bits 3-0  channels 1-4, ch1 in the high bit
```

So `0xEF` = brightness 7, short delay, all four channels — a full-output flash.
`0x5E` = brightness 2, long delay, channels 1-3 — a dim steady floor.

Each mode has exactly **two** delay values (short and long), and each step picks
one. Up to **8 modes**, sharing a 256-byte pool of steps. `LightModes` holds
nine cumulative offsets that carve that pool into modes.

Included patterns:

| File | For |
|---|---|
| `patterns/dawn-patrol.json` | Cobber Mini **Rear** — daylight commuting, two modes |
| `patterns/front-light.json` | Cobber Mini **Front** — daylight, plus a steady low-light mode |

[docs/PATTERN-DESIGN.md](docs/PATTERN-DESIGN.md) explains the reasoning, with
citations — daytime running lights cut crashes ~33%, flashing is detected ~3×
further away, but flashing alone degrades the distance judgement drivers need,
so these patterns never go fully dark.

---

## Troubleshooting

**The light charges but doesn't appear on USB.**
Charging only needs the power pins; enumeration needs the data lines. Try a
different USB-C cable — cables bundled with small devices are very often
charge-only. Then try a different port.

**`No Knog light found`, but it's plugged in.**

```bash
python3 tools/usbwatch.py snap    # lists all USB devices, flags Knog ones
python3 tools/usbwatch.py watch   # watches for one appearing
```

Look for `0x10c4:0xeac9`. It has **no product name** — that's normal.

**I see the device but reads time out.** Press the light's button to wake it,
then retry. On Linux, check the udev rule above.

**Modemaker 2.0 doesn't list my light.** It won't. Your light is Modemaker 1.x
generation. That's what this tool is for.

---

## Drawbacks and known limitations

Being honest about what this doesn't do:

- **Only verified on the Cobber Mini Front and Rear (prodcodes 4 and 7).**
  Everything else in the support table shares the documented protocol but is
  untested on real hardware. Reads are safe to try; back up before writing.
- **Some factory modes may live outside the editable region.** The Cobber Mini
  Front is sold as 5 modes but exposes only 3 in the settings area, none at full
  brightness. Where the others live is not yet known.
- **The delay unit is unknown.** Timing values are unitless in the firmware. All
  timings are relative, and stated flash rates are estimates. Time a known
  pattern with a stopwatch to calibrate for your model.
- **Writing carries risk.** It erases and rewrites flash pages. Writes are
  bounded to `0xF800`–`0xF93F` — FactoryData (serial, calibration) at `0xFB40`
  and the bootloader are outside that range, so a failed write should scramble
  modes rather than brick the light. *Should*. There is no recovery path for a
  light that stops enumerating. **Back up first.**
- **No firmware flashing.** Deliberately. Settings only.
- **No Modemaker 2.0 support** (Cobber Reflex, Blinder E/X) — different protocol.
- **Pattern authoring is JSON**, not a visual editor. The browser UI previews and
  animates but cannot yet author or write.
- **Windows untested.** The HID layer should be portable; nobody has tried.
- **`StatusBytes` semantics are partly inferred** from a comment in Knog's
  source. Bit 2 is "skip mode" — set it and a mode disappears from the button
  cycle.
- Reads are **one byte per USB round-trip**, so a full backup takes a few
  seconds.

---

## How it works

Knog's Modemaker desktop app is Electron and drives the light with `node-hid`.
The protocol was recovered from that app's own JavaScript and verified against
hardware.

- **Transport:** USB HID, 64-byte reports, vendor usage page `0xFF00`
- **Frame:** `[0x00, 0x24, len+1, command, ...data]` (`0x00` = HID report id,
  `0x24` = frame marker)
- **Commands:** `Identify 0x30`, `Setup 0x31`, `Erase 0x32`, `Write 0x33`,
  `Verify 0x34`, `Lock 0x35`, `RunApp 0x36`, `WNVM 0x37`, `RNVM 0x38`
- **Reads:** `RNVM` with a big-endian address; the value comes back as byte 0
- **Writes:** `Setup` with magic `[0xA5, 0xF1, 0x01]`, then `Erase` — which is
  really erase-and-write-page — taking `[addrHi, addrLo, ...data]`. Every frame
  is acked with `0x40`.

Full detail, including the memory map: [docs/PROTOCOL.md](docs/PROTOCOL.md).

---

## Project layout

```
knog/            library + CLI
  protocol.py    constants, memory map, step encode/decode (no I/O)
  device.py      HID transport, identify, backup, write
  modes.py       decode memory into readable modes
  cli.py         command line
tools/
  usbwatch.py    watch USB for a light appearing (stdlib only)
  probe.py       standalone read-only probe
web/index.html   WebHID viewer with animated previews
patterns/        pattern definitions
docs/            protocol notes and pattern design rationale
backups/         your saved settings (gitignored)
```

---

## Contributing

The most useful contribution is **a backup from a model not yet verified**.
Run `backup` and open an issue with the JSON (it contains your device serial —
redact it if you'd rather not share). That's how the support table gets real
rather than inferred.

Bug reports should include the output of `identify` and
`python3 tools/usbwatch.py snap`.

## Licence

MIT. Use at your own risk — see [Drawbacks](#drawbacks-and-known-limitations).
