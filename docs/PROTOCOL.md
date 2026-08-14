# Knog Cobber Mini — protocol notes

Reverse-engineered from Knog's own Modemaker desktop app (Electron, v1.9.96),
whose unminified source is preserved in `modemaker-src/`. **Confirmed against
real hardware** — see "Verified device readout" below.

## Which app, which transport — read this first

There are two Modemaker apps and they speak to *different hardware over
different transports*. Getting this wrong costs hours.

| | Modemaker 1.x (desktop) | Modemaker 2.0 (web) |
|---|---|---|
| Transport | **USB HID** (`node-hid`) | WebUSB (`navigator.usb`) |
| USB IDs | `0x10C4:0xEAC9` | `0x10C4:0x1AE0/0x1A16/0x1A9A` |
| Lights | PWR, Cobber, Bilby, Bandicoot, Blinder 600/900/1300 | Cobber Reflex, Blinder E, Blinder X |

**The Cobber Mini is a Modemaker 1.x / HID device.** It is *not* a 2.0 device,
despite 2.0's bundle containing `CobberMF`/`CobberMR` strings — those device
type IDs (82/83) belong to different, newer hardware.

### Two traps that cost real time here

1. **The light has no USB string descriptors.** `iProduct`, `iManufacturer` and
   `iSerialNumber` are all 0, so it shows up in `ioreg` as an anonymous
   `0x10c4:0xeac9` with no product name. It is easily mistaken for dock or
   hub silicon. It identifies itself only over HID, not in its descriptors.
2. **Knog's "hold the power button until the LED flashes green & red"
   instruction is for Modemaker 2.0 lights only.** The Cobber Mini enumerates
   on plug-in with no button press. Its HID interface uses vendor-defined
   usage page `0xFF00`, usage `0x01`.

## Verified device readout

A Cobber Mini Rear, read over HID:

```
product id        7  (0x07)      -> "Cobber Rear (Small)"
firmware version  3
serial bytes      E9 F1 75 84
bootloader ver    4
factory id        243
light modes (0xF801-0xF809)  00 02 08 08 08 08 08 08 08
delays      (0xF80A-0xF819)  0A 96 0A AF FF FF FF FF FF FF FF FF FF FF FF FF
```

Note the marketing name and the internal name differ: **"Cobber Mini" is
`Cobber Rear (Small)` / `Cobber Front (Small)` internally**. There is no
"Mini" anywhere in the firmware catalog.

## Wire format

HID, 64-byte reports. From `mmdevice.js`:

```js
this.writeFrame = function (command, data) {
  var frame = [0x24, data.length + 1, parseInt(command)];
  // ...concat data, split into 64-byte packets, prepend report id
}
```

A frame is:

```
[ 0x00, 0x24, len, command, *data ]
   ^     ^     ^
   |     |     len = len(data) + 1
   |     NEWCOMMAND marker
   HID report id (hidapi requires this prefix)
```

Responses come back from a plain HID read; for a single-byte memory read the
value is simply `response[0]`.

Note this differs from the WebUSB variant used by Modemaker 2.0, which adds a
sequence-number byte and XOR-`0x15` scrambles payloads. **The HID path has
neither.**

## Commands

From `KnogDeviceMemoryMap.js`:

| Name       | Value | Meaning                     |
|------------|-------|-----------------------------|
| `Identify` | 0x30  | identify                    |
| `Setup`    | 0x31  | begin programming           |
| `Erase`    | 0x32  | erase                       |
| `Write`    | 0x33  | write                       |
| `Verify`   | 0x34  | verify                      |
| `Lock`     | 0x35  | lock                        |
| `RunApp`   | 0x36  | leave bootloader, run app   |
| `WNVM`     | 0x37  | **write** non-volatile mem  |
| `RNVM`     | 0x38  | **read** non-volatile mem   |

`Setup` is invoked as `writeFrame(Setup, [0xA5, 0xF1, 0x01])` — a magic
unlock sequence — before `Erase`.

### Reading memory (safe, non-destructive)

One byte at a time:

```
write: [0x00, 0x24, 0x04, 0x38, addr_hi, addr_lo, 0x01]
read:  response[0] is the byte value
```

## Memory map (version 1)

From `memRanges(1)`. Frame size 64.

| Region             | Address range     |
|--------------------|-------------------|
| `ProductId`        | `0xFB40`          |
| `firmwareVersion`  | `0xFB81`          |
| `PreviousMode`     | `0xF800`          |
| FactoryData        | `0xFB40`-`0xFB7F` |
| — serial number    | `0xFB41`-`0xFB44` |
| — device info      | `0xFB72`-`0xFB76` |
| **LightModes**     | `0xF801`-`0xF809` |
| **Delays**         | `0xF80A`-`0xF819` |
| StatusBytes        | `0xF81A`-`0xF821` |

Device info bytes are `[bootloaderVersion, factoryId, yearLast2, month, ...]`.

Products whose `prodcode` is absent from the catalog fall back to `254`
("Default"), so an unknown reading is a soft failure, not a crash.

## Product catalog (prodcode -> model)

| Code | Ch | Model |
|------|----|-------|
| 2 | 2 | PWR Commuter |
| 3 | 2 | PWR Rider |
| 4 | 2 | Cobber Front (Small) — **Cobber Mini Front** |
| 5 | 3 | Cobber Front (Med) |
| 6 | 3 | Cobber Front (Large) |
| 7 | 3 | Cobber Rear (Small) — **Cobber Mini Rear** |
| 8 | 3 | Cobber Rear (Medium) |
| 9 | 3 | Cobber Rear (Large) |
| 24 | 1 | PWR Road |
| 25 | 2 | PWR Trail |
| 43 | 3 | Cobber Rear (Small StVZO) |
| 49 | 4 | Bandicoot |
| 52 | 8 | Bilby |
| 58 | 1 | Blinder 600 |
| 254 | 4 | Default / unknown |

`channels` is how many independently addressable LED banks the model has —
3 for the Cobber Mini Rear.

## Still to determine

- Encoding of the 9 `LightModes` bytes and 16 `Delays` bytes
- Flash-pattern storage layout (see `DeviceMode.js`, `ModeControl.js`)
- Exact `WNVM` / `Erase` argument layout for the write path
