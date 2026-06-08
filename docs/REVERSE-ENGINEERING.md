# Reverse-engineering the PeriPage A40 page-mode protocol

How we went from "the open-source library can't align to the perforations" to a
byte-faithful re-implementation of the official app's private page-mode protocol
— and validated it on real hardware.

The printer is a **PeriPage A40** (210 mm fan-fold thermal printer, firmware
V3.6.8), driven over **Bluetooth Classic SPP/RFCOMM** (channel 1, no pairing).

---

## 1. The problem: two different print protocols

The popular open-source [`peripage`](https://pypi.org/project/peripage/) library
prints using an **ESC/POS raster row command** (`1d 76 30`, "GS v 0"). It works —
pixels come out — but it streams rows *immediately, wherever the paper happens to
sit*. There is no concept of a page, no top-of-form, and no use of the printer's
optical **black-mark sensor**. On fan-fold A4 with perforations and registration
marks, that means every print lands mid-sheet and ignores the perforations.

The official phone app, by contrast, starts each job at the top of a sheet and
finishes by advancing the paper so the **perforation lines up at the tear bar**
(the A40 has no auto-cutter — it's manual tear, but the firmware registers the
perforation for you). That behaviour is driven by a *different* command family,
prefixed `1f`, that is not documented anywhere — all prior open work targeted the
A6 receipt models, which use a different protocol.

So we set out to capture and decode the app's `1f` page-mode protocol.

## 2. Capture: Bluetooth HCI snoop

With the official app talking to the printer from an Android phone, we enabled
**Bluetooth HCI snoop logging** (Developer Options) and printed a known test
document — a 2-page PDF where page 1 is a big "1" and page 2 a big "2", each with
a border and TOP/BOTTOM edge markers. Known input + captured output = a
known-plaintext attack, which is what ultimately made the format easy to confirm.

Gotcha: the first couple of `btsnoop_hci.log` pulls contained only BT init and
BLE-scan churn — no ACL data to the printer. Android had rotated the active
snoop session. Toggling Bluetooth and ensuring the print happened *during*
capture produced a log containing the real RFCOMM session, including the
printer's device-info string:

```
PeriPage_A40|04:7F:0E:B0:45:18|C4:7F:0E:B0:45:18|V3.6.8|A40xxxxxxxxxxxx|92@
```

## 3. Parsing the capture (no tshark)

We parsed the capture in pure Python: **btsnoop records → HCI ACL → L2CAP
(with reassembly of continuation fragments) → RFCOMM**, then concatenated the
RFCOMM information payloads on the data channel to recover the application-layer
byte stream the printer actually received.

The one non-obvious detail: **RFCOMM UIH frames with control `0xFF` carry a
one-octet credit-flow field immediately after the length field**, which must be
skipped before the payload begins. Frames with control `0xEF` have no such octet.
Missing this de-synchronises every payload by one byte and turns the stream to
noise.

## 4. The command bracket

With a clean TX stream, the structure of a job emerged. A one-time **prelude**
(configuration + density + a priming reset/feed cycle) is followed by one
**bracket per page**:

```
reset        10 ff fe 01  + 00 ×12
feed-to-mark 1f b2 10                 <- advance to next black mark (top-of-form)
begin-page   10 ff 80 01
pad          00 ×12
<image block>                         <- see §6
end-page     10 ff fe 45              <- finalize -> advance so perforation meets tear bar
```

`reset` and density (`10 ff 10 00 02`, concentration = 2) were already known from
the library; `1f b2 10`, `10 ff 80 01`, and `10 ff fe 45` were the novel
page-mode commands.

## 5. Isolation tests: the commands are inert alone

We replayed `1f b2 10` and `10 ff fe 45` individually to the printer (after a
reset) — and nothing happened. No paper moved. Conclusion: the page commands only
function as part of a complete `1f` page job (begin-page → raster → end-page as a
unit). They are not standalone feed/cut commands, and they do not bracket the
library's `1d 76 30` row mode. This is *why* simply bolting the commands onto the
existing library failed.

## 6. The image block

Each page's image started with `1f 00 00 ce 09 17 00 00 …` followed by a large,
high-entropy blob. High entropy on a mostly-white page was the tell: it isn't raw
bitmap, it's **compressed**. Each captured page was only ~12–16 KB, versus
~480 KB for a full raw bitmap (≈40×).

Trying standard decompressors at successive offsets, **raw DEFLATE (zlib
`wbits=-15`) starting at byte 10** decompressed cleanly to a fixed
**479,362 bytes** for every page. The decompressed data was sparse: ~94 % `0x00`
(white) with the rest `0xFF` (ink).

Examining the 6 trailing bytes after the DEFLATE stream: the first 4 exactly
matched **`adler32` of the decompressed bitmap** (big-endian), followed by a fixed
2-byte marker `1d 0c`. So the stream is effectively a zlib stream with the 2-byte
header stripped, plus an end marker.

That fixes the full header:

| Bytes | Meaning |
|---|---|
| `1f 00 00` | print-page command + reserved |
| `ce` | `0xCE` = 206 bytes per row |
| `09 17` | `0x0917` = 2327 rows (big-endian) |
| `00 00 LL LL` | big-endian = `len(deflate) + 4` |
| `<raw DEFLATE>` | the 1-bit bitmap |
| `AA AA AA AA` | big-endian `adler32` of the decompressed bitmap |
| `1d 0c` | fixed image-end marker |

## 7. Geometry: width by autocorrelation

`479362` is not divisible by 216 (the library's 1728-px row width), so page mode
uses a different geometry. Because a page border repeats identically on every
row, the true row stride shows up as a strong **autocorrelation** peak. Scanning
candidate strides, **206 bytes** scored ~4.5× higher than any neighbour and
divided the data *exactly*:

```
206 bytes/row × 2327 rows = 479,362 bytes   (0 left over)
```

So page-mode geometry is **1648 px wide × 2327 rows**, ink bit = 1, white = 0,
MSB-first. Rendering the decompressed page-1 bitmap at 1648×2327 produced a
pixel-perfect image of our test page — straight borders (width correct), readable
text (bit order correct), black-on-white (polarity correct). Every parameter
confirmed at once.

## 8. Generating our own pages

Generating the format is then straightforward — and our DEFLATE bytes need not
match the app's (DEFLATE encoders vary; the printer just inflates):

1. Render the page to a **1648 × 2327** 1-bit bitmap (Floyd–Steinberg dither for
   any greys), pack MSB-first with **ink = 1**.
2. `deflate = raw-deflate(bitmap)` (`zlib`, `wbits=-15`).
3. `block = 1f 00 00 | 206 | rows(2B BE) | len(deflate)+4 (4B BE) | deflate |
   adler32(bitmap) (4B BE) | 1d 0c`.
4. Wrap with the per-page bracket; prepend the one-time prelude; send over RFCOMM
   in ~180-byte chunks.

## 9. Hardware validation

We generated a synthetic page entirely from our own bitmap (not a replay of the
capture), encoded it per the spec above, and sent it to the printer. The A40:

1. printed our page correctly (text/graphics, correct bit order and polarity);
2. **seeked to the top of a fresh sheet** (top-of-form), not mid-sheet; and
3. advanced afterward so the **perforation lined up at the tear bar**.

All three behaviours matched the official app. The protocol was fully
reverse-engineered and re-implemented.

## 10. Tooling notes

- Everything was decoded with the Python standard library (`struct`, `zlib`) plus
  `numpy` for the autocorrelation and `Pillow` for rendering — no `tshark`.
- The known-plaintext approach (printing a document we designed) is what made the
  geometry and polarity unambiguous; pick a test page with a full border and
  large, distinct shapes.

---

*Reverse-engineering and implementation: Paul Faure with Claude (Anthropic).*
