"""Render a PDF (or PIL images) to packed 1-bit A40 page bitmaps."""
from __future__ import annotations
from PIL import Image
from .encode import WIDTH_PX, PAGE_ROWS, PAGE_BYTES


def image_to_bitmap(img, dither: bool = True, threshold: int = 128) -> bytes:
    """Fit a PIL image into a WIDTH_PX x PAGE_ROWS page; pack to 1-bit, ink=1."""
    img = img.convert("L")
    scale = min(WIDTH_PX / img.width, PAGE_ROWS / img.height)
    if scale < 1.0 or img.width != WIDTH_PX:
        new = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new, Image.LANCZOS)
    if dither:
        bw = img.convert("1")                         # Floyd-Steinberg
    else:
        bw = img.point(lambda p: 255 if p >= threshold else 0).convert("1")
    canvas = Image.new("1", (WIDTH_PX, PAGE_ROWS), 1)     # 1 = white
    x = max(0, (WIDTH_PX - bw.width) // 2)                # center horizontally
    canvas.paste(bw, (x, 0))                              # top-align (top-of-form)
    raw = canvas.tobytes()                                # MSB-first, white=1
    bitmap = bytes(b ^ 0xFF for b in raw)                 # ink=1
    assert len(bitmap) == PAGE_BYTES
    return bitmap


def pdf_to_bitmaps(pdf_path: str, dither: bool = True, threshold: int = 128):
    """Render every page of a PDF to a packed 1-bit page bitmap (list)."""
    import pypdfium2 as pdfium
    out = []
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        for page in pdf:
            w_pt, _ = page.get_size()
            pil = page.render(scale=WIDTH_PX / w_pt).to_pil()
            out.append(image_to_bitmap(pil, dither=dither, threshold=threshold))
            page.close()
    finally:
        pdf.close()
    return out
