"""
app.py
------
FastAPI web server for the tennis swing analyser.

    uvicorn app:app --reload        # dev
    uvicorn app:app --host 0.0.0.0  # production

Endpoints:
    GET  /              → upload page (static/index.html)
    POST /analyse       → accepts video upload, returns JSON scores
    GET  /report/<id>   → serves the self-contained HTML report
"""

import asyncio
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from pipeline import RESULTS_DIR, run_analysis

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Tennis Swing Analyser", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")

os.makedirs(RESULTS_DIR, exist_ok=True)

# MediaPipe inference is CPU-bound; run in a thread pool to avoid blocking the
# event loop.  max_workers=2 limits concurrent analyses on a single server.
_executor = ThreadPoolExecutor(max_workers=2)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/analyse")
async def analyse(video: UploadFile = File(...)) -> dict:
    """
    Accept a video upload, run the full analysis pipeline, return scores JSON.

    The client receives the result when analysis is complete (typically 10–60s
    depending on video length).  A spinner on the frontend covers the wait.
    """
    if not (video.content_type or "").startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video (MP4, MOV, AVI …)")

    analysis_id = str(uuid.uuid4())
    work_dir    = os.path.join(RESULTS_DIR, analysis_id)
    os.makedirs(work_dir, exist_ok=True)

    video_path = os.path.join(work_dir, "input.mp4")
    try:
        with open(video_path, "wb") as f:
            shutil.copyfileobj(video.file, f)
    finally:
        await video.close()

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, run_analysis, video_path, analysis_id
        )
    except RuntimeError as exc:
        # e.g. "No pose landmarks detected" from extract_pose.py
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    return result


@app.get("/report/{analysis_id}", response_class=HTMLResponse)
async def get_report(analysis_id: str) -> HTMLResponse:
    """Serve the self-contained HTML report for a completed analysis."""
    report_path = os.path.join(RESULTS_DIR, analysis_id, "report.html")
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found")
    with open(report_path, encoding="utf-8") as f:
        return HTMLResponse(f.read())
