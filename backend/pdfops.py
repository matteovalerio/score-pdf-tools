"""
pdfops.py — the two auxiliary tools from the design.

  images_to_pdf(images, page_size)  one image per page, three sizing modes
  merge_pdfs(pdfs)                   concatenate in the given order
"""
from __future__ import annotations
import fitz

A4 = (595.28, 841.89)
LETTER = (612.0, 792.0)
_IMG_MARGIN = 28.0


def images_to_pdf(images, page_size: str = "fit-a4") -> bytes:
    """
    images: list of {"name": str, "bytes": bytes}
    page_size: 'fit-a4' | 'fit-letter' | 'original'
    """
    out = fitz.open()
    for it in images:
        data = it["bytes"]
        # open the image to learn its pixel size
        pix = fitz.Pixmap(data)
        iw, ih = pix.width, pix.height
        if page_size == "original":
            page = out.new_page(width=iw, height=ih)
            page.insert_image(fitz.Rect(0, 0, iw, ih), stream=data)
        else:
            pw, ph = LETTER if page_size == "fit-letter" else A4
            page = out.new_page(width=pw, height=ph)
            max_w, max_h = pw - 2 * _IMG_MARGIN, ph - 2 * _IMG_MARGIN
            r = min(max_w / iw, max_h / ih)
            w, h = iw * r, ih * r
            x, y = (pw - w) / 2, (ph - h) / 2
            page.insert_image(fitz.Rect(x, y, x + w, y + h), stream=data)
    data = out.tobytes(deflate=True)
    out.close()
    return data


def merge_pdfs(pdfs) -> bytes:
    """pdfs: list of {"name": str, "bytes": bytes} — concatenated in order."""
    out = fitz.open()
    for it in pdfs:
        src = fitz.open(stream=it["bytes"], filetype="pdf")
        out.insert_pdf(src)
        src.close()
    data = out.tobytes(deflate=True)
    out.close()
    return data


def pdf_page_count(data: bytes) -> int:
    try:
        d = fitz.open(stream=data, filetype="pdf")
        n = d.page_count
        d.close()
        return n
    except Exception:
        return 0
