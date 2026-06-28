# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
./run.sh          # creates venv, installs deps, starts on http://localhost:8000
```

Manual equivalent:
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

There is no build step for the frontend — `frontend/index.html` is served directly by FastAPI.

## Architecture

```
frontend/index.html   vanilla JS SPA (no framework, no bundler) — all UI state in one file
backend/app.py        FastAPI: routes, ensemble config, serves the frontend
backend/splitter.py   staff detection + vector-preserving part extraction
backend/pdfops.py     images→PDF and PDF merge
```

**Request flow for score extraction:**
1. `POST /api/detect` — renders each page at 150 DPI, detects staff lines, returns normalised crop geometry (0–1) + JPEG previews
2. User reviews/adjusts crop regions in the browser (draggable dividers)
3. `POST /api/extract` — clips original vector content with the client-supplied geometry, stacks bands onto A4 pages, returns one base64-encoded PDF per instrument

All outputs are returned inline as base64 data URLs; nothing is persisted server-side.

## Key design decisions in `splitter.py`

- **Paper-relative ink threshold** (`_binarize_ink`): uses the 95th-percentile pixel as "paper white" and thresholds at `paper * 0.82`. A fixed Otsu threshold misses thin/anti-aliased staff lines from many engravers.
- **System grouping** (`_group_systems`): divides staves by `n_parts` when the total count divides evenly, otherwise falls back to gap-based clustering (gap > 1.6× median inter-staff gap).
- **Vector-preserving extraction** (`extract_parts`): uses `page.show_pdf_page(dest, src, page_idx, clip=clip)` — never rasterises. This keeps files small and output crisp at any zoom.

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serves `frontend/index.html` |
| GET | `/api/health` | Health check |
| POST | `/api/detect` | PDF → page previews + crop geometry |
| POST | `/api/extract` | PDF + geometry → one PDF per part |
| POST | `/api/images-to-pdf` | Images → single PDF (`fit-a4` / `fit-letter` / `original`) |
| POST | `/api/merge-pdfs` | Multiple PDFs → one merged PDF |
| POST | `/api/pdf-info` | PDFs → page count per file |

## Ensembles

Hardcoded in both `app.py` (`ENSEMBLES` dict) and `frontend/index.html` (`ENSEMBLES` array). If you add a new ensemble type, update both places.

## Dependencies

`PyMuPDF` (imported as `fitz`) is the core PDF library for rendering, clipping, and building output documents. `opencv-python-headless` + `numpy` are used only in `splitter.py` for the staff-line detection raster pipeline.
