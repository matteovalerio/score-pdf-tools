"""
app.py — FastAPI server for wedding·lifeboat score & PDF tools.

Run:  uvicorn app:app --reload --port 8000   (from the backend/ directory)
Then open http://localhost:8000

Endpoints
  GET  /                     serves the frontend
  POST /api/detect           PDF -> page previews + suggested crop geometry
  POST /api/extract          PDF + geometry -> one PDF per instrument
  POST /api/images-to-pdf    images -> single PDF (one per page)
  POST /api/merge-pdfs       PDFs -> single merged PDF
"""
from __future__ import annotations
import base64
import json
import os
from typing import List

import fitz
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import splitter
import pdfops

app = FastAPI(title="wedding·lifeboat")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.normpath(os.path.join(HERE, "..", "frontend", "index.html"))

ENSEMBLES = {
    "quartet": ["Violin I", "Violin II", "Viola", "Cello"],
    "trio":    ["Violin", "Viola", "Cello"],
    "duo":     ["Part 1", "Part 2"],
    "quintet": ["Violin I", "Violin II", "Viola", "Cello 1", "Cello 2"],
}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/pdf-info")
async def api_pdf_info(files: List[UploadFile] = File(...)):
    info = []
    for f in files:
        data = await f.read()
        info.append({"name": f.filename, "pageCount": pdfops.pdf_page_count(data)})
    return {"files": info}


@app.get("/")
def index():
    if not os.path.exists(FRONTEND):
        return JSONResponse({"error": "frontend/index.html not found"}, status_code=404)
    return FileResponse(FRONTEND, media_type="text/html")


@app.post("/api/detect")
async def api_detect(file: UploadFile = File(...), ensemble: str = Form("quartet")):
    part_names = ENSEMBLES.get(ensemble, ENSEMBLES["quartet"])
    n_parts = len(part_names)
    data = await file.read()
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        raise HTTPException(400, f"Could not read PDF: {e}")

    pages = []
    warnings = []
    for i in range(doc.page_count):
        page = doc[i]
        systems = splitter.detect_systems(page, n_parts)
        preview = page.get_pixmap(matrix=fitz.Matrix(splitter.PREVIEW_DPI / 72,
                                                     splitter.PREVIEW_DPI / 72))
        jpg = preview.tobytes("jpeg", jpg_quality=80)
        pages.append({
            "num": i + 1,
            "w": preview.width,
            "h": preview.height,
            "preview": "data:image/jpeg;base64," + _b64(jpg),
            "systems": systems,
        })
        if not systems:
            warnings.append(f"Page {i + 1}: nothing detected — add a system by hand.")
    doc.close()
    return {"parts": part_names, "pages": pages, "warnings": warnings}


@app.post("/api/extract")
async def api_extract(
    file: UploadFile = File(...),
    geometry: str = Form(...),
    parts: str = Form(...),
    title: str = Form("score"),
):
    data = await file.read()
    try:
        pages_geometry = json.loads(geometry)
        part_names = json.loads(parts)
    except Exception as e:
        raise HTTPException(400, f"Bad geometry/parts payload: {e}")
    if not part_names:
        raise HTTPException(400, "No parts specified.")
    try:
        results = splitter.extract_parts(data, pages_geometry, part_names, title)
    except Exception as e:
        raise HTTPException(500, f"Extraction failed: {e}")
    return {"parts": [
        {"name": r["name"], "filename": r["filename"],
         "dataUrl": "data:application/pdf;base64," + _b64(r["bytes"])}
        for r in results
    ]}


@app.post("/api/images-to-pdf")
async def api_images_to_pdf(files: List[UploadFile] = File(...),
                            pageSize: str = Form("fit-a4")):
    images = []
    for f in files:
        images.append({"name": f.filename, "bytes": await f.read()})
    if not images:
        raise HTTPException(400, "No images uploaded.")
    try:
        out = pdfops.images_to_pdf(images, pageSize)
    except Exception as e:
        raise HTTPException(500, f"Image→PDF failed: {e}")
    return {"filename": "images.pdf",
            "dataUrl": "data:application/pdf;base64," + _b64(out)}


@app.post("/api/merge-pdfs")
async def api_merge_pdfs(files: List[UploadFile] = File(...)):
    pdfs = []
    for f in files:
        pdfs.append({"name": f.filename, "bytes": await f.read()})
    if not pdfs:
        raise HTTPException(400, "No PDFs uploaded.")
    try:
        out = pdfops.merge_pdfs(pdfs)
    except Exception as e:
        raise HTTPException(500, f"Merge failed: {e}")
    return {"filename": "merged.pdf",
            "dataUrl": "data:application/pdf;base64," + _b64(out)}
