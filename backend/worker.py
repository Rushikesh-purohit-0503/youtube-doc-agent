import logging
import os
import traceback
import uuid

from arq.connections import RedisSettings

from services.assembler import assemble_and_add_intro
from services.chunker import chunk_transcript
from services.history_service import save_to_history
from services.llm_service import process_chunks_parallel
from services.pdf_service import generate_pdf
from services.whisper_service import transcribe_audio
from services.youtube_service import NoTranscriptError, PrivateVideoError, get_transcript, get_video_info

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
PDF_DIR = os.getenv("PDF_DIR", "/app/pdfs")
JOB_TTL = 86400  # 24 hours


async def _update(redis, job_id: str, status: str, progress: int, message: str) -> None:
    await redis.hset(f"job:{job_id}", mapping={
        "status": status,
        "progress": str(progress),
        "message": message,
    })
    await redis.expire(f"job:{job_id}", JOB_TTL)


async def process_video(ctx: dict, job_id: str, youtube_url: str) -> None:
    redis = ctx["redis"]
    try:
        await _update(redis, job_id, "transcribing", 5, "Fetching video info...")
        video_info = await get_video_info(youtube_url)
        title = video_info["title"]
        thumbnail_url = video_info["thumbnail"]

        await _update(redis, job_id, "transcribing", 10, "Extracting transcript...")

        try:
            transcript_text = await get_transcript(youtube_url)
        except PrivateVideoError:
            await _update(redis, job_id, "error", 0, "This video is private")
            return
        except NoTranscriptError:
            await _update(
                redis, job_id, "transcribing", 15,
                "No captions found — transcribing audio (this may take a few minutes)..."
            )
            transcript_text = await transcribe_audio(youtube_url)

        await _update(redis, job_id, "chunking", 30, "Splitting transcript into sections...")
        words = transcript_text.split()
        if len(words) > 12000:
            transcript_text = ' '.join(words[:12000])
        chunks = chunk_transcript(transcript_text, num_chunks=10)

        await _update(redis, job_id, "processing", 35, f"Processing section 1 of {len(chunks)}...")

        async def _chunk_progress(idx: int, msg: str) -> None:
            pct = 35 + int((idx / len(chunks)) * 43)
            await _update(redis, job_id, "processing", pct, msg)

        chunk_outputs = await process_chunks_parallel(chunks, progress_callback=_chunk_progress)

        await _update(redis, job_id, "assembling", 80, "Writing introduction and key takeaways...")
        assembled = await assemble_and_add_intro(chunk_outputs, title)

        await _update(redis, job_id, "generating_pdf", 90, "Generating your creative notebook PDF...")
        os.makedirs(PDF_DIR, exist_ok=True)
        pdf_path = os.path.join(PDF_DIR, f"{job_id}.pdf")
        await generate_pdf(output_path=pdf_path, title=title, thumbnail_url=thumbnail_url, assembled=assembled)

        doc_id = str(uuid.uuid4())
        save_to_history(doc_id, job_id, title, thumbnail_url, pdf_path)

        await redis.hset(f"job:{job_id}", mapping={
            "status": "done",
            "progress": "100",
            "message": "Your notebook is ready!",
            "pdf_path": pdf_path,
            "doc_id": doc_id,
        })
        await redis.expire(f"job:{job_id}", JOB_TTL)

    except ConnectionError as exc:
        logger.error("Connection error: %s", exc)
        await _update(redis, job_id, "error", 0, str(exc))
    except Exception as exc:
        logger.error("Pipeline error: %s\n%s", exc, traceback.format_exc())
        await _update(redis, job_id, "error", 0, f"Error: {type(exc).__name__}: {exc}")


class WorkerSettings:
    functions = [process_video]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 2        # 2 videos processed concurrently
    job_timeout = 1800  # 30 min max per job
    keep_result = 3600  # keep ARQ result metadata for 1h
