import asyncio
import logging
import os
from typing import Dict, List, Tuple

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(MODEL)

_GENERATION_CONFIG = genai.types.GenerationConfig(
    temperature=0.8,
    max_output_tokens=600,
)

# ── Per-template intro + takeaway prompt fragments ────────────────────────────

_INTRO_INSTRUCTIONS: Dict[str, str] = {
    'storybook': (
        "Write it like the opening of a storybook — grab the reader, tell them what amazing "
        "things they'll learn, make them excited! Keep it to 2–3 short paragraphs. "
        "Simple, fun English. No headings, just flowing text."
    ),
    'professional': (
        "Write a concise executive overview: what this video covers, why it matters to a business "
        "professional, and what actionable insights the reader will gain. "
        "2–3 tight paragraphs. Formal business English. No headings."
    ),
    'academic': (
        "Write a scholarly introduction: state the topic, its academic significance, the key "
        "concepts covered, and the scope of the notes. "
        "2–3 structured paragraphs. Formal academic English. No headings."
    ),
    'minimal': (
        "Write exactly 2 sentences: what this video is about and the single most important "
        "thing the reader will take away. Plain, direct English. Nothing else."
    ),
}

_TAKEAWAY_INSTRUCTIONS: Dict[str, str] = {
    'storybook': (
        "List the 5–7 most important things to remember. Make each point short, punchy, "
        "and memorable — like sticky notes on your wall. Simple English."
    ),
    'professional': (
        "List the 5–7 key business takeaways. Each must be strategic, actionable, and "
        "immediately applicable. No filler. Formal business English."
    ),
    'academic': (
        "List the 5–7 principal academic insights or theoretical conclusions. "
        "Each should be substantive and precise. Formal academic English."
    ),
    'minimal': (
        "List exactly 5 takeaways in one sentence each. Ruthlessly concise. Plain English."
    ),
}


def _build_prompts(video_title: str, preview: str, ending: str, template: str) -> Tuple[str, str]:
    intro_instr = _INTRO_INSTRUCTIONS.get(template, _INTRO_INSTRUCTIONS['storybook'])
    takeway_instr = _TAKEAWAY_INSTRUCTIONS.get(template, _TAKEAWAY_INSTRUCTIONS['storybook'])

    intro_prompt = (
        f'Based on these notes about "{video_title}", write an INTRODUCTION.\n\n'
        f"{intro_instr}\n"
        "Output ONLY the introduction — no preamble, no meta-commentary.\n\n"
        f"Content to draw from:\n{preview}"
    )

    summary_prompt = (
        f'Based on these notes about "{video_title}", write a KEY TAKEAWAYS section.\n\n'
        f"{takeway_instr}\n"
        "Output ONLY the takeaways — no preamble, no meta-commentary.\n\n"
        f"Content to draw from:\n{ending}\n\n"
        "Format each as: ▸ [Takeaway]"
    )

    return intro_prompt, summary_prompt


async def _call_with_retry(prompt: str, max_retries: int = 4) -> genai.types.GenerateContentResponse:
    for attempt in range(max_retries):
        try:
            return await _model.generate_content_async(prompt, generation_config=_GENERATION_CONFIG)
        except ResourceExhausted:
            if attempt == max_retries - 1:
                raise
            delay = 20 * (attempt + 1)
            logger.warning("Rate limited in assembler — retrying in %ds", delay)
            await asyncio.sleep(delay)
    raise RuntimeError("Unreachable")  # pragma: no cover


async def assemble_and_add_intro(
    chunk_outputs: List[str],
    video_title: str,
    template: str = 'storybook',
) -> dict:
    """Generate intro and key takeaways in the voice of the chosen template."""
    preview = '\n\n'.join(chunk_outputs[:3])[:3000]
    ending = '\n\n'.join(chunk_outputs[-2:])[-2000:]

    intro_prompt, summary_prompt = _build_prompts(video_title, preview, ending, template)

    intro_response = await _call_with_retry(intro_prompt)
    summary_response = await _call_with_retry(summary_prompt)

    return {
        "intro": intro_response.text.strip(),  # type: ignore[union-attr]
        "chapters": chunk_outputs,
        "summary": summary_response.text.strip(),  # type: ignore[union-attr]
    }
