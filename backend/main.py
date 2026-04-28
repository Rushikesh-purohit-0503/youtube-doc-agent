import asyncio
import logging
import os
import uuid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from dependencies import get_current_user
from models.schemas import GenerateRequest, GenerateResponse, StatusResponse
from routes.auth import router as auth_router
from routes.webhook import router as webhook_router
from routes.dev import router as dev_router
from services.db import init_db
from services.history_service import delete_from_history, get_history
from services.plan_service import check_can_generate, check_duration_allowed
from services.youtube_service import get_video_duration_sec

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
PDF_DIR = os.getenv("PDF_DIR", "/app/pdfs")
APP_ENV = os.getenv("APP_ENV", "production")
os.makedirs(PDF_DIR, exist_ok=True)

# ── Rate limiter (Redis-backed so it survives restarts) ───────────────────────
limiter = Limiter(key_func=get_remote_address, storage_uri=REDIS_URL)

app = FastAPI(title="YouTube Doc Agent", version="3.0.0")
app.state.limiter = limiter

app.include_router(auth_router)
app.include_router(webhook_router)
if APP_ENV in ("dev", "development"):
    app.include_router(dev_router)
    logger.info("Dev routes enabled — /dev/set-plan, /dev/reset-usage")


def _rate_limit(limit_string: str):
    """Apply slowapi rate limit in all environments except dev."""
    def decorator(func):
        if APP_ENV in ("dev", "development"):
            return func
        return limiter.limit(limit_string)(func)
    return decorator


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests. You can generate {exc.detail}."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    init_db()
    app.state.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.state.arq = await create_pool(RedisSettings.from_dsn(REDIS_URL))


@app.on_event("shutdown")
async def shutdown() -> None:
    await app.state.redis.aclose()
    await app.state.arq.aclose()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/generate", response_model=GenerateResponse)
@_rate_limit("50/hour")
async def generate(
    request: Request,
    body: GenerateRequest,
    user: dict = Depends(get_current_user),
) -> GenerateResponse:
    # Check subscription plan limits (on top of IP rate limit)
    allowed, reason = check_can_generate(user["id"], user["plan"])
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    # Check video duration limit — skip if client pre-fetched transcript
    # (duration was already validated client-side or transcript word count used)
    if not body.transcript:
        duration_sec = await asyncio.get_event_loop().run_in_executor(
            None, get_video_duration_sec, str(body.youtube_url)
        )
        if duration_sec > 0:
            dur_allowed, dur_reason = check_duration_allowed(user["plan"], duration_sec)
            if not dur_allowed:
                raise HTTPException(status_code=403, detail=dur_reason)

    job_id = str(uuid.uuid4())
    job_data: dict = {
        "status": "queued",
        "progress": "0",
        "message": "Queued for processing",
        "user_id": user["id"],
    }
    # Store prefetched transcript/metadata so the worker can skip yt-dlp
    if body.transcript:
        job_data["prefetched_transcript"] = body.transcript
    if body.title:
        job_data["prefetched_title"] = body.title
    if body.thumbnail_url:
        job_data["prefetched_thumbnail"] = body.thumbnail_url

    await app.state.redis.hset(f"job:{job_id}", mapping=job_data)
    await app.state.redis.expire(f"job:{job_id}", 86400)
    await app.state.arq.enqueue_job("process_video", job_id, str(body.youtube_url), body.template)

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
        title=data.get("title"),
        thumbnail_url=data.get("thumbnail_url"),
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


@app.delete("/pdf/{job_id}")
async def delete_pdf(job_id: str) -> dict:
    """Called by the Flutter app after PDF is saved to device. Frees server storage."""
    data = await app.state.redis.hgetall(f"job:{job_id}")
    if data:
        pdf_path: str = data.get("pdf_path", "")
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
    return {"success": True}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/config")
async def config() -> dict:
    return {"is_dev": APP_ENV in ("dev", "development")}
