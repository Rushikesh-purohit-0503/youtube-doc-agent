import logging
import os
import traceback
import uuid

from arq.connections import RedisSettings

from services.assembler import assemble_and_add_intro
from services.plan_service import record_usage
from services.chunker import chunk_transcript
from services.history_service import save_to_history
from services.llm_service import process_chunks_parallel
from services.pdf_service import generate_pdf
from services.whisper_service import transcribe_audio
from services.youtube_service import NoTranscriptError, PrivateVideoError, get_transcript_and_info, get_video_info

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
PDF_DIR = os.getenv("PDF_DIR", "/app/pdfs")
JOB_TTL = 86400       # 24 hours for job state
TRANSCRIPT_TTL = 604800  # 7 days for cached transcripts


async def _update(redis, job_id: str, status: str, progress: int, message: str) -> None:
    await redis.hset(f"job:{job_id}", mapping={
        "status": status,
        "progress": str(progress),
        "message": message,
    })
    await redis.expire(f"job:{job_id}", JOB_TTL)


def _video_id_from_url(url: str) -> str:
    import re
    match = re.search(r'(?:v=|youtu\.be/|shorts/)([^&\n?#\s]+)', url)
    return match.group(1) if match else url


def _friendly_error(exc: Exception) -> str:
    """Map internal exceptions to user-readable messages."""
    msg = str(exc).lower()
    if "private" in msg or "unavailable" in msg:
        return "This video is private or unavailable. Try a public video."
    if "age" in msg and ("restrict" in msg or "verif" in msg):
        return "This video requires age verification and cannot be processed."
    if "copyright" in msg or "removed" in msg:
        return "This video has been removed or is blocked due to copyright."
    if "no captions" in msg or "no transcript" in msg or "subtitle" in msg:
        return "No captions found for this video and audio transcription failed."
    if "network" in msg or "connection" in msg or "timeout" in msg:
        return "Network error — please check your connection and try again."
    if "invalid url" in msg or "could not extract" in msg:
        return "Invalid YouTube URL. Please paste a valid youtube.com or youtu.be link."
    if "quota" in msg or "rate limit" in msg or "429" in msg:
        return "AI service is temporarily busy. Please try again in a minute."
    if "pdf" in msg or "reportlab" in msg:
        return "Failed to generate PDF. Our team has been notified — please try again."
    return "Something went wrong processing this video. Please try again."


async def process_video(ctx: dict, job_id: str, youtube_url: str, template: str = 'storybook') -> None:
    redis = ctx["redis"]
    try:
        await _update(redis, job_id, "transcribing", 5, "Connecting to YouTube...")

        # ── Transcript cache (skip yt-dlp + Whisper on repeat requests) ──────
        cache_key = f"transcript:{_video_id_from_url(youtube_url)}"
        cached_raw = await redis.hgetall(cache_key)
        cached = {(k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v) for k, v in cached_raw.items()}

        if cached:
            logger.info("Cache hit for %s", youtube_url)
            transcript_text = cached["transcript"]
            title = cached["title"]
            thumbnail_url = cached["thumbnail"]
            await _update(redis, job_id, "transcribing", 20, f'Found cached transcript for "{title}"')
        else:
            try:
                await _update(redis, job_id, "transcribing", 10, "Fetching video info and captions...")
                # Single yt-dlp call: fetches captions + metadata together
                transcript_text, video_info = await get_transcript_and_info(youtube_url)
                title = video_info["title"]
                thumbnail_url = video_info["thumbnail"]
                await _update(redis, job_id, "transcribing", 20, f'Got transcript for "{title}"')
            except PrivateVideoError:
                await _update(redis, job_id, "error", 0, "This video is private or unavailable. Try a public video.")
                return
            except NoTranscriptError:
                # No captions — fetch info separately then use Whisper
                await _update(redis, job_id, "transcribing", 12, "No captions found — fetching video info...")
                video_info = await get_video_info(youtube_url)
                title = video_info["title"]
                thumbnail_url = video_info["thumbnail"]
                await _update(
                    redis, job_id, "transcribing", 15,
                    "No captions available — transcribing audio with Whisper AI (2–5 min)..."
                )
                transcript_text = await transcribe_audio(youtube_url)
                await _update(redis, job_id, "transcribing", 28, "Audio transcription complete!")

            await redis.hset(cache_key, mapping={
                "transcript": transcript_text,
                "title": title,
                "thumbnail": thumbnail_url,
            })
            await redis.expire(cache_key, TRANSCRIPT_TTL)

        # Store title/thumbnail in job state so status endpoint can return them
        await redis.hset(f"job:{job_id}", mapping={
            "title": title,
            "thumbnail_url": thumbnail_url,
        })

        await _update(redis, job_id, "chunking", 30, "Analysing transcript structure...")
        words = transcript_text.split()

        # Reject videos that are too long to process cost-effectively.
        # ~6,000 words ≈ 45–60 min video. Beyond that the token cost and
        # Gemini rate-limit wait time become impractical on the free tier.
        MAX_WORDS = int(os.getenv("MAX_TRANSCRIPT_WORDS", "6000"))
        if len(words) > MAX_WORDS:
            approx_minutes = len(words) // 130  # ~130 words/min speech rate
            await _update(
                redis, job_id, "error", 0,
                f"This video is too long (~{approx_minutes} min). "
                f"Please use a video under ~{MAX_WORDS // 130} minutes."
            )
            return

        chunks = chunk_transcript(transcript_text, num_chunks=10)

        await _update(redis, job_id, "processing", 35, f"Summarising content — 0 of {len(chunks)} sections done...")

        # Count usage only when Gemini is about to be called (not on early errors)
        job_data = await redis.hgetall(f"job:{job_id}")
        user_id = job_data.get("user_id") or (job_data.get(b"user_id") or b"").decode()
        if user_id:
            record_usage(user_id, job_id)

        async def _chunk_progress(idx: int, msg: str) -> None:
            pct = 35 + int((idx / len(chunks)) * 43)
            await _update(redis, job_id, "processing", pct,
                          f"Summarising content — {idx} of {len(chunks)} sections done...")

        chunk_outputs = await process_chunks_parallel(chunks, progress_callback=_chunk_progress, template=template)

        await _update(redis, job_id, "assembling", 80, "Writing introduction and key takeaways...")
        assembled = await assemble_and_add_intro(chunk_outputs, title, template=template)

        await _update(redis, job_id, "generating_pdf", 90, "Designing your notebook layout...")
        os.makedirs(PDF_DIR, exist_ok=True)
        pdf_path = os.path.join(PDF_DIR, f"{job_id}.pdf")
        await generate_pdf(output_path=pdf_path, title=title, thumbnail_url=thumbnail_url, assembled=assembled, template=template)

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
        await _update(redis, job_id, "error", 0,
                      "Connection error — please check your internet and try again.")
    except Exception as exc:
        logger.error("Pipeline error: %s\n%s", exc, traceback.format_exc())
        await _update(redis, job_id, "error", 0, _friendly_error(exc))


class WorkerSettings:
    functions = [process_video]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 1       # 2 videos processed concurrently
    job_timeout = 1800  # 30 min max per job
    keep_result = 3600  # keep ARQ result metadata for 1h
