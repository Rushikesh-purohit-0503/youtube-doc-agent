import os
from typing import List

import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL = "qwen3.5:4b"


async def assemble_and_add_intro(chunk_outputs: List[str], video_title: str) -> dict:
    """Generate intro and key takeaways, then bundle everything together."""
    preview = '\n\n'.join(chunk_outputs[:3])[:3000]
    ending = '\n\n'.join(chunk_outputs[-2:])[-2000:]

    async with httpx.AsyncClient() as client:
        intro_r = await client.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL,
                "prompt": (
                    f'Based on this notebook about "{video_title}", write a fun and engaging INTRODUCTION.\n\n'
                    "Write it like the opening of a storybook — grab the reader, tell them what amazing "
                    "things they'll learn, make them excited! Keep it to 2–3 short paragraphs. "
                    "Simple English, fun tone. No headings, just flowing text.\n\n"
                    f"Content to draw from:\n{preview}"
                ),
                "stream": False,
                "think": False,
                "options": {"temperature": 0.8, "num_ctx": 8192, "num_predict": 512},
            },
            timeout=300.0,
        )
        intro_r.raise_for_status()
        intro_text = intro_r.json()["response"]

        summary_r = await client.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL,
                "prompt": (
                    f'Based on this notebook about "{video_title}", write a KEY TAKEAWAYS section.\n\n'
                    "List the 5–7 most important things to remember. Make each point short, punchy, "
                    "memorable — like sticky notes on your wall. Simple English.\n\n"
                    f"Content to draw from:\n{ending}\n\n"
                    "Format each as: ▸ [The takeaway]"
                ),
                "stream": False,
                "think": False,
                "options": {"temperature": 0.7, "num_ctx": 8192, "num_predict": 512},
            },
            timeout=300.0,
        )
        summary_r.raise_for_status()
        summary_text = summary_r.json()["response"]

    return {"intro": intro_text, "chapters": chunk_outputs, "summary": summary_text}
