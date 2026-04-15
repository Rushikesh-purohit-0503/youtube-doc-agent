import asyncio
import os
from typing import Callable, List, Optional

import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = "qwen3.5:4b"

_CHUNK_PROMPT = """\
You are writing a creative learning notebook. A student will read this to deeply \
understand what was discussed in a YouTube video.

This is chunk {idx} of {total} from the video transcript.

RULES:
- Write in simple, fun English like you're explaining to a curious 12-year-old
- Go in-depth — explain every concept fully, don't skip anything
- Use real-world examples that make the idea click (e.g. "think of it like Netflix...")
- Format as: ## Chapter Title, then bullet points, then a "Real Example" box
- Do NOT summarize — document everything discussed in this chunk

Transcript chunk:
{chunk_text}"""


async def _check_ollama(client: httpx.AsyncClient) -> None:
    try:
        r = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        r.raise_for_status()
    except Exception:
        raise ConnectionError(
            "Cannot connect to Ollama. Make sure it is running on your machine."
        )


async def _process_single_chunk(
    client: httpx.AsyncClient,
    chunk: str,
    idx: int,
    total: int,
) -> str:
    prompt = _CHUNK_PROMPT.format(idx=idx, total=total, chunk_text=chunk)
    r = await client.post(
        f"{OLLAMA_HOST}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.7,
                "num_ctx": 8192,
                "num_predict": 1500,
            },
        },
        timeout=300.0,
    )
    r.raise_for_status()
    return r.json()["response"]


async def process_chunks_parallel(
    chunks: List[str],
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> List[str]:
    """Process all chunks concurrently. Ollama's OLLAMA_NUM_PARALLEL controls
    how many requests it handles at once; extras queue automatically."""
    async with httpx.AsyncClient() as client:
        await _check_ollama(client)

        total = len(chunks)
        results: List[Optional[str]] = [None] * total
        completed = 0

        async def _run(i: int, chunk: str) -> None:
            nonlocal completed
            try:
                output = await _process_single_chunk(client, chunk, i + 1, total)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed on section {i + 1} of {total}: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            results[i] = output
            completed += 1
            if progress_callback:
                progress_callback(completed, f"Processing section {completed} of {total}...")

        await asyncio.gather(*[_run(i, chunk) for i, chunk in enumerate(chunks)])

    return results  # type: ignore[return-value]
