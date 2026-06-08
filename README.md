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

> Status: **validated on hardware.** Single- and multi-page PDFs print with
> correct top-of-form seek and perforation registration; battery level can be
> queried over Bluetooth. Used in production by the Home Assistant add-on
> [`paul43210/ha-peripage-a40`](https://github.com/paul43210/ha-peripage-a40).

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

## How it works

See [docs/REVERSE-ENGINEERING.md](docs/REVERSE-ENGINEERING.md) for the full reverse-engineering writeup — capture, RFCOMM parsing, the compression and geometry decode, and hardware validation.

## Credits

Protocol reverse-engineering and implementation by **Paul Faure** with
**Claude (Anthropic)**. MIT licensed.

## Status queries

After connecting, the printer needs its reset/init sequence before it will
reply, then answers simple `10 ff …` queries:

```python
from peripage_a40 import get_battery
pct = get_battery("04:7F:0E:B0:45:18")   # -> int 0..100, or None if unreadable
```

`get_battery()` connects, sends the reset sequence, queries `10ff50f1`, and
returns the battery percentage (the printer replies with two bytes
`{0x00, percent}`). It raises `PrinterAsleep` if the printer is off/asleep.

## Print quality

The printer's native width (1648 px / 206 bytes per row) is the hardware
resolution ceiling. Print **concentration/density** ranges `0–2`; this library
uses **2 (maximum)** in the job prelude, which is the darkest/highest-quality
setting the A40 offers. Grayscale is Floyd–Steinberg dithered; solid black text
stays crisp.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

The `1f` page-mode format was reverse-engineered independently for this project.
The simple `10ff…` status-query opcodes (battery, name, firmware) are the same
ones documented by the GPLv3 [`bitrate16/peripage-python`](https://github.com/bitrate16/peripage-python)
project; this library is a clean-room reimplementation and shares no code with it.
