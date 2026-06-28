"""
splitter.py — score detection and part extraction.

Two responsibilities, deliberately separated so the UI can sit in between:

  detect_systems(page, n_parts)   -> suggested crop geometry (normalised 0..1)
  extract_parts(src, geometry, …) -> one vector-preserving PDF per instrument

Detection uses a lenient, paper-relative ink threshold and raw row-coverage
(no morphology), which survives the thin / anti-aliased staff lines that defeat
a fixed Otsu threshold. Extraction is driven entirely by the geometry handed
back from the client, so any manual edits the user made to the crop regions are
honoured exactly.
"""
from __future__ import annotations
from dataclasses import dataclass

import fitz          # PyMuPDF
import numpy as np
import cv2


DETECT_DPI = 150
PREVIEW_DPI = 130


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _render_gray(page: fitz.Page, dpi: int) -> np.ndarray:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n >= 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return img[:, :, 0].copy()


def render_preview_png(page: fitz.Page, dpi: int = PREVIEW_DPI) -> bytes:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


# --------------------------------------------------------------------------- #
# detection
# --------------------------------------------------------------------------- #
def _binarize_ink(gray: np.ndarray) -> np.ndarray:
    """Ink = anything clearly darker than paper-white (lenient, paper-relative)."""
    paper = float(np.percentile(gray, 95))
    thr = max(60.0, paper * 0.82)
    _, b = cv2.threshold(gray, thr, 255, cv2.THRESH_BINARY_INV)
    return b


def _staff_line_rows(gray: np.ndarray, cov_frac: float = 0.5) -> np.ndarray:
    """Row centres of full-width horizontal lines (the staff lines)."""
    h, w = gray.shape
    binary = _binarize_ink(gray)
    prof = binary.sum(axis=1) / 255.0 / w
    rows = prof > cov_frac
    lines, y = [], 0
    while y < h:
        if rows[y]:
            y0 = y
            while y < h and rows[y]:
                y += 1
            lines.append((y0 + y - 1) // 2)
        else:
            y += 1
    return np.array(lines, dtype=int)


def _median(a):
    return float(np.median(a)) if len(a) else 0.0


def _group_staves(lines: np.ndarray):
    """Cluster staff lines into staves (~5 tightly-spaced lines)."""
    if len(lines) < 2:
        return [], 0.0
    gaps = np.diff(lines)
    small = gaps[gaps <= np.median(gaps) * 1.5]
    line_space = _median(small) if len(small) else _median(gaps)
    split = max(2.0, line_space * 2.5)
    staves, cur = [], [int(lines[0])]
    for i in range(1, len(lines)):
        if lines[i] - lines[i - 1] <= split:
            cur.append(int(lines[i]))
        else:
            staves.append(cur); cur = [int(lines[i])]
    staves.append(cur)
    # keep real staves: >=3 lines and a real vertical span
    staves = [s for s in staves if len(s) >= 3 and (s[-1] - s[0]) >= 2.0 * line_space]
    out = [{"top": s[0], "bottom": s[-1]} for s in staves]
    return out, line_space


def _group_systems(staves, n_parts):
    """Chunk staves into systems: by N when it divides cleanly, else by gaps."""
    if not staves:
        return []
    n = len(staves)
    if n_parts > 0 and n % n_parts == 0:
        return [staves[i:i + n_parts] for i in range(0, n, n_parts)]
    # fallback: break on unusually large inter-staff gaps
    inter = [staves[i]["top"] - staves[i - 1]["bottom"] for i in range(1, n)]
    med = _median(inter) or 1.0
    systems, cur = [], [staves[0]]
    for i in range(1, n):
        if staves[i]["top"] - staves[i - 1]["bottom"] > med * 1.6:
            systems.append(cur); cur = [staves[i]]
        else:
            cur.append(staves[i])
    systems.append(cur)
    return systems


def detect_systems(page: fitz.Page, n_parts: int, margin_frac: float = 0.04):
    """Return suggested crop geometry for one page.

    [{ y0, y1, x0, x1, dividers:[…] }]  — all normalised to page size (0..1),
    with (n_parts - 1) dividers splitting each system band between parts.
    """
    gray = _render_gray(page, DETECT_DPI)
    h, w = gray.shape
    lines = _staff_line_rows(gray)
    staves, line_space = _group_staves(lines)
    systems = _group_systems(staves, n_parts)
    staff_h = _median([s["bottom"] - s["top"] for s in staves]) or line_space * 4
    pad = staff_h * 0.9

    out = []
    for grp in systems:
        top = max(0.0, grp[0]["top"] - pad)
        bot = min(float(h), grp[-1]["bottom"] + pad)
        if len(grp) == n_parts:
            dividers = [((grp[i - 1]["bottom"] + grp[i]["top"]) / 2.0) / h
                        for i in range(1, n_parts)]
        else:
            dividers = [(top + (bot - top) * (i / n_parts)) / h
                        for i in range(1, n_parts)]
        out.append({
            "y0": round(top / h, 5),
            "y1": round(bot / h, 5),
            "x0": round(margin_frac, 5),
            "x1": round(1 - margin_frac, 5),
            "dividers": [round(d, 5) for d in dividers],
        })
    return out


def detect_document(src_bytes: bytes, n_parts: int):
    """Detect every page. Returns (pages_geometry, page_meta, warnings)."""
    doc = fitz.open(stream=src_bytes, filetype="pdf")
    pages, warnings = [], []
    for i in range(doc.page_count):
        page = doc[i]
        systems = detect_systems(page, n_parts)
        pages.append({"systems": systems})
        if not systems:
            warnings.append(f"Page {i + 1}: no systems detected — add one manually.")
        elif any(len(s["dividers"]) != n_parts - 1 for s in systems):
            warnings.append(f"Page {i + 1}: a system didn't split into {n_parts} parts cleanly.")
    doc.close()
    return pages, warnings


# --------------------------------------------------------------------------- #
# extraction (vector-preserving)
# --------------------------------------------------------------------------- #
@dataclass
class PageSize:
    w: float = 595.28   # A4 portrait, points
    h: float = 841.89
    margin: float = 40.0
    gap: float = 16.0
    header: float = 52.0


def _part_bounds(sys, part_idx, n_parts):
    """(yTop, yBot) for one part within a system, from its dividers."""
    y_top = sys["y0"] if part_idx == 0 else sys["dividers"][part_idx - 1]
    y_bot = sys["y1"] if part_idx == n_parts - 1 else sys["dividers"][part_idx]
    return y_top, y_bot


def extract_parts(src_bytes: bytes, pages_geometry, part_names, title: str,
                  ps: PageSize = PageSize()):
    """
    Build one PDF per part by clipping the ORIGINAL page content (vectors, text,
    images) — never re-rasterised — and stacking each system's band vertically.

    pages_geometry: [{ systems:[{y0,y1,x0,x1,dividers}] }]  (one entry per src page)
    Returns: [{ "name", "filename", "bytes" }]
    """
    src = fitz.open(stream=src_bytes, filetype="pdf")
    n_parts = len(part_names)
    safe_title = (title or "score").strip()
    results = []
    content_w = ps.w - 2 * ps.margin

    for p_idx, pname in enumerate(part_names):
        out = fitz.open()
        page = out.new_page(width=ps.w, height=ps.h)
        # header
        page.insert_text((ps.margin, ps.margin + 12), safe_title,
                         fontsize=13, fontname="times-italic", color=(0.17, 0.13, 0.09))
        page.insert_text((ps.margin, ps.margin + 32), pname,
                         fontsize=17, fontname="times-italic", color=(0.71, 0.33, 0.16))
        y = ps.margin + ps.header

        for src_idx, pg in enumerate(pages_geometry):
            if src_idx >= src.page_count:
                break
            src_page = src[src_idx]
            W, H = src_page.rect.width, src_page.rect.height
            for sys in pg.get("systems", []):
                if len(sys.get("dividers", [])) != n_parts - 1:
                    continue
                y_top, y_bot = _part_bounds(sys, p_idx, n_parts)
                x0, x1 = sys["x0"], sys["x1"]
                if y_bot <= y_top or x1 <= x0:
                    continue
                clip = fitz.Rect(x0 * W, y_top * H, x1 * W, y_bot * H)
                draw_w = content_w
                draw_h = draw_w * (clip.height / clip.width)
                if y + draw_h > ps.h - ps.margin and y > ps.margin + ps.header:
                    page = out.new_page(width=ps.w, height=ps.h)
                    y = ps.margin
                dest = fitz.Rect(ps.margin, y, ps.margin + draw_w, y + draw_h)
                page.show_pdf_page(dest, src, src_idx, clip=clip)
                y += draw_h + ps.gap

        # page numbers
        for i in range(out.page_count):
            out[i].insert_text((ps.w - ps.margin - 14, ps.margin - 6),
                               str(i + 1), fontsize=9, fontname="helv",
                               color=(0.48, 0.42, 0.34))
        results.append({
            "name": pname,
            "filename": f"{safe_title} - {pname}.pdf",
            "bytes": out.tobytes(deflate=True),
        })
        out.close()
    src.close()
    return results
