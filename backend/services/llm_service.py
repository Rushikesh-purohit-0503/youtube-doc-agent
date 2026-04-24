import asyncio
import logging
import os
from typing import Callable, Dict, List, Optional

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_CONCURRENCY = int(os.getenv("GEMINI_CONCURRENCY", "3"))
_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 20

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(MODEL)

# ── Per-template chunk prompts ────────────────────────────────────────────────

_CHUNK_PROMPTS: Dict[str, str] = {
    'storybook': """\
You are writing a creative learning notebook. A student will read this to deeply \
understand what was discussed in a YouTube video.

This is chunk {idx} of {total} from the video transcript.

RULES:
- Write in simple, fun English like you're explaining to a curious 12-year-old
- Go in-depth — explain every concept fully, don't skip anything
- Use real-world analogies that make ideas click (e.g. "think of it like Netflix...")
- Format as: ## Chapter Title, then bullet points, then a "Real Example" box
- Do NOT summarize — document everything discussed in this chunk
- Output ONLY the notebook content — no preamble, no meta-commentary

Transcript chunk:
{chunk_text}""",

    'professional': """\
You are writing executive briefing notes from a video for a senior business professional.

This is section {idx} of {total} from the transcript.

RULES:
- Write in clear, formal business English — concise, direct, and actionable
- Focus on strategic implications, key decisions, and practical applications
- Every point must be immediately useful to a decision-maker — no filler
- Format as: ## Section Title, then bullet points, then a "Key Insight" box with \
the single most important strategic takeaway from this section
- Do NOT pad with background or obvious statements
- Output ONLY the briefing content — no preamble, no meta-commentary

Transcript section:
{chunk_text}""",

    'academic': """\
You are creating scholarly study notes from a video for a university student or researcher.

This is section {idx} of {total} from the transcript.

RULES:
- Write in formal academic English — precise, analytical, and thorough
- Define technical terms clearly on first use
- Explain concepts with their theoretical foundations and context
- Format as: ## Topic Heading, then detailed prose paragraphs, then an \
"Example" box that illustrates the concept with a concrete case
- Do NOT oversimplify — academic notes should preserve depth and nuance
- Output ONLY the study notes — no preamble, no meta-commentary

Transcript section:
{chunk_text}""",

    'minimal': """\
You are creating ultra-concise reference notes from a video.

This is section {idx} of {total} from the transcript.

RULES:
- Write in plain, direct English — no fluff, no filler, no pleasantries
- Each bullet must be one clear, standalone fact or insight (max 2 sentences)
- Skip anything that isn't a hard fact, key concept, or actionable point
- Format as: ## Topic, bullet points only, then an "Example" line (one sentence max)
- Do NOT elaborate — brevity is the goal
- Output ONLY the notes — no preamble, no meta-commentary

Transcript section:
{chunk_text}""",
}

_GENERATION_CONFIG = genai.types.GenerationConfig(
    temperature=0.7,
    max_output_tokens=1500,
)


async def _process_single_chunk(
    chunk: str,
    idx: int,
    total: int,
    template: str,
) -> str:
    prompt_template = _CHUNK_PROMPTS.get(template, _CHUNK_PROMPTS['storybook'])
    prompt = prompt_template.format(idx=idx, total=total, chunk_text=chunk)
    for attempt in range(_MAX_RETRIES):
        try:
            response = await _model.generate_content_async(
                prompt,
                generation_config=_GENERATION_CONFIG,
            )
            return response.text.strip()
        except ResourceExhausted:
            if attempt == _MAX_RETRIES - 1:
                raise
            delay = _RETRY_BASE_DELAY * (attempt + 1)
            logger.warning("Rate limited on chunk %d/%d — retrying in %ds", idx, total, delay)
            await asyncio.sleep(delay)
    raise RuntimeError("Unreachable")  # pragma: no cover


async def process_chunks_parallel(
    chunks: List[str],
    progress_callback: Optional[Callable[[int, str], None]] = None,
    template: str = 'storybook',
) -> List[str]:
    """Process chunks with bounded concurrency to stay within Gemini rate limits."""
    total = len(chunks)
    results: List[Optional[str]] = [None] * total
    completed = 0
    semaphore = asyncio.Semaphore(GEMINI_CONCURRENCY)

    async def _run(i: int, chunk: str) -> None:
        nonlocal completed
        async with semaphore:
            try:
                output = await _process_single_chunk(chunk, i + 1, total, template)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed on section {i + 1} of {total}: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
        results[i] = output
        completed += 1
        if progress_callback:
            result = progress_callback(completed, f"Processing section {completed} of {total}...")
            if asyncio.iscoroutine(result):
                await result

    await asyncio.gather(*[_run(i, chunk) for i, chunk in enumerate(chunks)])
    return results  # type: ignore[return-value]
