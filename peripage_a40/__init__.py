"""App-free, cloud-free PeriPage A40 printing via the native page-mode protocol."""
from .encode import (encode_page, decode_page, page_bracket, build_job,
                     WIDTH_PX, BYTES_PER_ROW, PAGE_ROWS, PAGE_BYTES, JOB_PRELUDE)
from .render import pdf_to_bitmaps, image_to_bitmap
from .transport import (RfcommTransport, PrinterAsleep, TransportError,
                        get_battery, BATTERY_QUERY, RESET)
from .job import render_pdf_job, print_pdf

__version__ = "0.1.3"
__all__ = [
    "encode_page", "decode_page", "page_bracket", "build_job",
    "WIDTH_PX", "BYTES_PER_ROW", "PAGE_ROWS", "PAGE_BYTES", "JOB_PRELUDE",
    "pdf_to_bitmaps", "image_to_bitmap",
    "RfcommTransport", "PrinterAsleep", "TransportError",
    "get_battery", "BATTERY_QUERY", "RESET",
    "render_pdf_job", "print_pdf", "__version__",
]
