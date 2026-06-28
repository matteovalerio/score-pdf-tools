# wedding·lifeboat — score & PDF tools

A small local web app with three tools for working with sheet-music PDFs:

1. **Score Extraction** — split a stacked full score (e.g. a string quartet,
   where every system shows all four instruments top-to-bottom) into one clean
   PDF per instrument. Detection is automatic; you confirm or fine-tune the crop
   regions, then export.
2. **Images → PDF** — combine PNG/JPEG images into a single PDF, one image per
   page, in the order you arrange them (A4-fit, US-Letter-fit, or original size).
3. **Merge PDFs** — concatenate several PDFs into one, in your chosen order.

The UI is the design exported from Claude Design; the PDF/image work runs in a
small Python backend.

## Quick start

```bash
./run.sh
```

Then open <http://localhost:8000>. The script creates a virtualenv, installs
dependencies, and starts the server.

### Manual start

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --port 8000
```

## How it works

```
frontend/index.html      the UI (vanilla JS, no build step) — talks to the API
backend/app.py           FastAPI server: routes + serves the frontend
backend/splitter.py      staff/system detection + vector-preserving extraction
backend/pdfops.py        images→PDF and PDF merge (PyMuPDF)
```

### Score extraction

- **Detection** renders each page and finds the staff lines using a lenient,
  paper-relative ink threshold and a full-width row-coverage test. This is the
  key robustness point: a fixed (Otsu) threshold silently drops the thin,
  anti-aliased staff lines that many engravers produce, so half the staves go
  undetected. The paper-relative threshold handles both solid-black and faint
  engravings. Staves are grouped into systems (by ensemble size when the count
  divides cleanly, else by vertical gaps), and each system band is split between
  parts at the midpoints between adjacent staves.
- The detector returns **normalised crop geometry** (0–1) per page: each system
  has outer edges `x0,x1,y0,y1` and the dividers between parts. The UI overlays
  these as draggable regions so you can correct anything before exporting.
- **Extraction is vector-preserving.** Rather than rasterising crops, the
  backend clips the original page content (`show_pdf_page` with a clip rect) and
  stacks each instrument's system-bands onto fresh A4 pages. The parts stay
  crisp at any zoom and the files stay small.

### What the crop method does and doesn't do

It crops the engraving — it does not read the notes (no OMR). So:

- Multi-measure rests are **not** consolidated; a resting instrument still shows
  its empty systems.
- Line and page breaks follow wherever the original score placed them.
- Occasionally a sliver of a neighbouring staff's slur or hairpin can appear at
  a band edge where content overlaps the gap — nudge the divider to fix it.

For performance-grade parts (consolidated rests, independent re-layout) you'd
need full optical music recognition, which is a much larger undertaking.

## Notes

- Output PDFs are returned inline (base64) and downloaded straight from the
  browser; nothing is persisted server-side.
- If you open `frontend/index.html` directly via `file://` instead of through
  the server, set `const API = "http://localhost:8000"` near the top of the
  `<script>` so it can find the backend (CORS is already open).
