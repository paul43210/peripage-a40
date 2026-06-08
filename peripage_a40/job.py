"""High-level print jobs: PDF -> job stream -> printer."""
from __future__ import annotations
from .encode import encode_page, build_job
from .render import pdf_to_bitmaps
from .transport import RfcommTransport


def render_pdf_job(pdf_path: str, dither: bool = True):
    """Render a PDF to the full A40 job byte stream. Returns (stream, n_pages)."""
    blocks = [encode_page(bm) for bm in pdf_to_bitmaps(pdf_path, dither=dither)]
    return build_job(blocks), len(blocks)


def print_pdf(pdf_path: str, mac: str, dither: bool = True, **transport_kw) -> int:
    """Render and print a PDF. Returns page count. Raises PrinterAsleep."""
    stream, n = render_pdf_job(pdf_path, dither=dither)
    with RfcommTransport(mac, **transport_kw) as t:
        t.send(stream)
    return n
