import logging
import os
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.schemas import GenerateRequest, GenerateResponse, StatusResponse
from services.history_service import delete_from_history, get_history

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
PDF_DIR = os.getenv("PDF_DIR", "/app/pdfs")
os.makedirs(PDF_DIR, exist_ok=True)

app = FastAPI(title="YouTube Doc Agent", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    app.state.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.state.arq = await create_pool(RedisSettings.from_dsn(REDIS_URL))


@app.on_event("shutdown")
async def shutdown() -> None:
    await app.state.redis.aclose()
    await app.state.arq.aclose()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    job_id = str(uuid.uuid4())
    await app.state.redis.hset(f"job:{job_id}", mapping={
        "status": "queued",
        "progress": "0",
        "message": "Queued for processing",
    })
    await app.state.redis.expire(f"job:{job_id}", 86400)  # 24h TTL
    await app.state.arq.enqueue_job("process_video", job_id, str(request.youtube_url))
    return GenerateResponse(job_id=job_id, status="queued")


@app.get("/status/{job_id}", response_model=StatusResponse)
async def status(job_id: str) -> StatusResponse:
    data = await app.state.redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(
        job_id=job_id,
        status=data["status"],
        progress=int(data["progress"]),
        message=data["message"],
    )


@app.get("/download/{job_id}")
async def download(job_id: str) -> FileResponse:
    data = await app.state.redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")
    if data["status"] != "done":
        raise HTTPException(status_code=400, detail="PDF not ready yet")
    pdf_path: str = data.get("pdf_path", "")
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"notebook_{job_id[:8]}.pdf")


@app.get("/history")
async def history() -> list:
    return get_history()


@app.delete("/history/{doc_id}")
async def delete_doc(doc_id: str) -> dict:
    delete_from_history(doc_id)
    return {"success": True}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
