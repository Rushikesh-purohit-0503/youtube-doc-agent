import logging
import os
import traceback
import uuid
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.schemas import GenerateRequest, GenerateResponse, StatusResponse
from services.assembler import assemble_and_add_intro
from services.chunker import chunk_transcript
from services.history_service import delete_from_history, get_history, save_to_history
from services.llm_service import process_chunks_parallel
from services.pdf_service import generate_pdf
from services.whisper_service import transcribe_audio
from services.youtube_service import (
    NoTranscriptError,
    PrivateVideoError,
    get_transcript,
    get_video_info,
)

app = FastAPI(title="YouTube Doc Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_default_pdf_dir = os.path.join(os.path.dirname(__file__), "..", "pdfs")
PDF_DIR = os.getenv("PDF_DIR", os.path.abspath(_default_pdf_dir))
os.makedirs(PDF_DIR, exist_ok=True)

# In-memory job store  {job_id: {status, progress, message, pdf_path?, doc_id?}}
_jobs: Dict[str, Dict[str, Any]] = {}


def _update(job_id: str, status: str, progress: int, message: str) -> None:
    _jobs[job_id] = {**_jobs.get(job_id, {}), "status": status, "progress": progress, "message": message}


# ── Background pipeline ───────────────────────────────────────────────────────
async def _process_video(job_id: str, youtube_url: str) -> None:
    try:
        _update(job_id, "transcribing", 5, "Fetching video info...")
        video_info = await get_video_info(youtube_url)
        title = video_info["title"]
        thumbnail_url = video_info["thumbnail"]

        _update(job_id, "transcribing", 10, "Extracting transcript...")
        transcript_text: str

        try:
            transcript_text = await get_transcript(youtube_url)
        except PrivateVideoError:
            _update(job_id, "error", 0, "This video is private")
            return
        except NoTranscriptError:
            _update(
                job_id, "transcribing", 15,
                "No captions found — transcribing audio (this may take a few minutes)..."
            )
            transcript_text = await transcribe_audio(youtube_url)

        _update(job_id, "chunking", 30, "Splitting transcript into sections...")
        # Cap at 12,000 words so each chunk stays manageable on local hardware
        words = transcript_text.split()
        if len(words) > 12000:
            transcript_text = ' '.join(words[:12000])
        chunks = chunk_transcript(transcript_text, num_chunks=10)

        _update(job_id, "processing", 35, f"Processing section 1 of {len(chunks)}...")

        def _chunk_progress(idx: int, msg: str) -> None:
            # progress goes from 35 → 78 across the chunks
            pct = 35 + int((idx / len(chunks)) * 43)
            _update(job_id, "processing", pct, msg)

        chunk_outputs = await process_chunks_parallel(chunks, progress_callback=_chunk_progress)

        _update(job_id, "assembling", 80, "Writing introduction and key takeaways...")
        assembled = await assemble_and_add_intro(chunk_outputs, title)

        _update(job_id, "generating_pdf", 90, "Generating your creative notebook PDF...")
        pdf_path = os.path.join(PDF_DIR, f"{job_id}.pdf")
        await generate_pdf(
            output_path=pdf_path,
            title=title,
            thumbnail_url=thumbnail_url,
            assembled=assembled,
        )

        doc_id = str(uuid.uuid4())
        save_to_history(doc_id, job_id, title, thumbnail_url, pdf_path)

        _jobs[job_id].update({"status": "done", "progress": 100, "message": "Your notebook is ready!", "pdf_path": pdf_path, "doc_id": doc_id})

    except ConnectionError as exc:
        logger.error("Connection error: %s", exc)
        _update(job_id, "error", 0, str(exc))
    except Exception as exc:
        logger.error("Pipeline error: %s\n%s", exc, traceback.format_exc())
        _update(job_id, "error", 0, f"Error: {type(exc).__name__}: {exc}")


# ── Routes ────────────────────────────────────────────────────────────────────
@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "queued", "progress": 0, "message": "Queued for processing"}
    background_tasks.add_task(_process_video, job_id, str(request.youtube_url))
    return GenerateResponse(job_id=job_id, status="queued")


@app.get("/status/{job_id}", response_model=StatusResponse)
async def status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = _jobs[job_id]
    return StatusResponse(
        job_id=job_id,
        status=j["status"],
        progress=j["progress"],
        message=j["message"],
    )


@app.get("/download/{job_id}")
async def download(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = _jobs[job_id]
    if j["status"] != "done":
        raise HTTPException(status_code=400, detail="PDF not ready yet")
    pdf_path: str = j.get("pdf_path", "")
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found")
    filename = f"notebook_{job_id[:8]}.pdf"
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


@app.get("/history")
async def history():
    return get_history()


@app.delete("/history/{doc_id}")
async def delete_doc(doc_id: str):
    delete_from_history(doc_id)
    return {"success": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
