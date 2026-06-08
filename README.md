# peripage-a40

App-free, cloud-free printing for the **PeriPage A40** (210 mm thermal printer)
using its **native page-mode protocol** — the same one the official app uses to
drive the printer's optical **black-mark sensor** for top-of-form alignment and
perforation registration on fan-fold A4 paper.

The popular open `peripage` library prints in ESC/POS row mode (`1d 76 30`),
which streams pixels immediately wherever the paper happens to sit — no page
alignment, no perforation registration. This project speaks the app's private
`1f` page-mode family instead, which was reverse-engineered from a Bluetooth
HCI capture and validated on real hardware.

> Status: **core validated on hardware** (single generated page: top-of-form
> seek + print + perforation alignment all correct). PDF pipeline + Home
> Assistant add-on web UI in progress.

## Protocol (page image block)

| Bytes | Meaning |
|---|---|
| `1f 00 00` | print-page command + reserved |
| `CE` | bytes-per-row = 206 → width **1648 px** |
| `HH HH` | rows, big-endian (**2327** = one A4 sheet, mark-to-mark) |
| `LL LL LL LL` | big-endian = `len(deflate) + 4` |
| `<raw DEFLATE>` | 1-bit bitmap, MSB-first, **ink = 1**, white = 0 |
| `AA AA AA AA` | big-endian adler32 of the **decompressed** bitmap |
| `1d 0c` | fixed image-end marker |

Per-page bracket: `reset · 1fb210 (feed-to-mark) · 10ff8001 (begin) · 00×12 ·
<block> · 10fffe45 (end → perforation meets tear bar)`. A one-time job prelude
(config + density) precedes the first page. The A40 has **no auto-cutter** — the
end-page command advances the sheet so the perforation lines up at the tear bar.

## Install

```bash
pip install pillow pypdfium2          # runtime deps
pip install -e .                      # this package (provides `peripage-a40`)
```

## Usage

```bash
# Render a PDF to a job .bin without a printer (offline / CI):
peripage-a40 build mydoc.pdf -o job.bin

# Render and print over Bluetooth RFCOMM:
peripage-a40 print mydoc.pdf --mac 04:7F:0E:B0:45:18
```

```python
from peripage_a40 import print_pdf, PrinterAsleep
try:
    print_pdf("mydoc.pdf", "04:7F:0E:B0:45:18")
except PrinterAsleep:
    ...  # ask the user to wake the printer (press power/feed) and retry
```

## Requirements / deployment

- A Linux host whose Python was built with Bluetooth support
  (`socket.AF_BLUETOOTH`) and a **Bluetooth Classic** adapter in range of the
  printer (e.g. the Home Assistant box's Sena UD100-G03). No PyBluez needed.
- The A40 auto-sleeps when idle; a reconnect then fails fast and raises
  `PrinterAsleep` → surface a "press the power/feed button" prompt to the user.

## Credits

Protocol reverse-engineering and implementation by **Paul Faure** with
**Claude (Anthropic)**. MIT licensed.
