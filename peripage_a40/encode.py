"""PeriPage A40 native page-mode ('1f' family) encoder.

Reverse-engineered and hardware-validated 2026-06-08 from an HCI capture of the
official app. This byte stream drives the printer's optical black-mark sensor,
giving top-of-form alignment and perforation registration -- which the open
`peripage` library (1d7630 ESC/POS row mode) does NOT do. See README.md.

Header layout per page image block:
    1f 00 00            print-page command + reserved
    CE                  bytes-per-row (206)  -> width 1648 px
    HH HH               rows, big-endian (2327 = one A4 sheet, mark-to-mark)
    LL LL LL LL         big-endian = len(deflate) + 4
    <raw DEFLATE>       1-bit bitmap, MSB-first, ink=1, white=0
    AA AA AA AA         big-endian adler32 of the *decompressed* bitmap
    1d 0c               fixed image-end marker
"""
from __future__ import annotations
import zlib

# --- geometry (validated on hardware) ---
WIDTH_PX = 1648
BYTES_PER_ROW = WIDTH_PX // 8        # 206 (0xCE)
PAGE_ROWS = 2327                     # one A4 sheet, mark-to-mark (0x0917)
PAGE_BYTES = BYTES_PER_ROW * PAGE_ROWS   # 479362

# --- fixed command tokens ---
_RESET      = bytes.fromhex("10fffe01") + b"\x00" * 12
_FEED_MARK  = bytes.fromhex("1fb210")    # advance to next black mark (top-of-form)
_BEGIN_PAGE = bytes.fromhex("10ff8001")
_END_PAGE   = bytes.fromhex("10fffe45")  # finalize -> perforation meets tear bar
_PAD12      = b"\x00" * 12
_IMG_END    = bytes.fromhex("1d0c")

# Sent once before the first page (verbatim from capture): config + a priming
# reset/feed/density/end cycle. Density (concentration) = 2.
JOB_PRELUDE = (
    bytes.fromhex("10ff70")
    + bytes.fromhex("10ff120014")
    + bytes.fromhex("10ff100301")
    + bytes.fromhex("10ff100300")
    + _PAD12
    + bytes.fromhex("10fffe01")
    + _FEED_MARK
    + bytes.fromhex("10ff100002")
    + _END_PAGE
)


def encode_page(bitmap: bytes, rows: int = PAGE_ROWS) -> bytes:
    """Encode one packed 1-bit page bitmap into a '1f' image block.

    bitmap: BYTES_PER_ROW * rows bytes, MSB-first, ink bit = 1, white = 0.
    """
    if len(bitmap) != BYTES_PER_ROW * rows:
        raise ValueError(
            f"bitmap is {len(bitmap)} bytes, expected {BYTES_PER_ROW * rows}")
    co = zlib.compressobj(9, zlib.DEFLATED, -15)     # raw DEFLATE, no zlib header
    deflate = co.compress(bitmap) + co.flush()
    header = (
        b"\x1f\x00\x00"
        + bytes([BYTES_PER_ROW])
        + rows.to_bytes(2, "big")
        + (len(deflate) + 4).to_bytes(4, "big")
    )
    adler = (zlib.adler32(bitmap) & 0xFFFFFFFF).to_bytes(4, "big")
    return header + deflate + adler + _IMG_END


def page_bracket(page_block: bytes) -> bytes:
    """Wrap one image block in the per-page command bracket."""
    return _RESET + _FEED_MARK + _BEGIN_PAGE + _PAD12 + page_block + _END_PAGE


def build_job(page_blocks) -> bytes:
    """Full byte stream for a job: prelude + each page's bracket."""
    page_blocks = list(page_blocks)
    if not page_blocks:
        raise ValueError("no pages")
    return JOB_PRELUDE + b"".join(page_bracket(b) for b in page_blocks)


def decode_page(block: bytes):
    """Inverse of encode_page (verification/tests). Returns (bitmap, rows)."""
    if block[:3] != b"\x1f\x00\x00":
        raise ValueError("bad magic")
    bpr = block[3]
    rows = int.from_bytes(block[4:6], "big")
    length = int.from_bytes(block[6:10], "big")
    deflate = block[10:10 + length - 4]
    bitmap = zlib.decompress(deflate, -15)
    if len(bitmap) != bpr * rows:
        raise ValueError("size mismatch after inflate")
    return bitmap, rows
