import re
from typing import List

# Maximum words per chunk to stay within the 8192-token context window
# (12,000 words / 10 chunks = 1,200 words; headroom for prompt template)
_MAX_WORDS_PER_CHUNK = 1000


def chunk_transcript(text: str, num_chunks: int = 10) -> List[str]:
    """Split transcript into ~num_chunks equal parts, bounded by word count.

    Strategy:
    1. Try to split on sentence boundaries first.
    2. If chunks would exceed _MAX_WORDS_PER_CHUNK (e.g. captions with no
       punctuation), fall back to plain word-count splitting.
    """
    text = ' '.join(text.split())
    if not text:
        return []

    # ── Sentence-based split ─────────────────────────────────────────────────
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    # If transcript has no punctuation, sentences == [whole text] — fall through
    # to word-count split instead.
    if len(sentences) > 1:
        total_words = sum(len(s.split()) for s in sentences)
        target_per_chunk = max(1, total_words // num_chunks)

        # Only use sentence split if each chunk stays within token budget
        if target_per_chunk <= _MAX_WORDS_PER_CHUNK:
            chunks: List[str] = []
            current: List[str] = []
            current_words = 0

            for sentence in sentences:
                word_count = len(sentence.split())
                current.append(sentence)
                current_words += word_count

                if current_words >= target_per_chunk and len(chunks) < num_chunks - 1:
                    chunks.append(' '.join(current))
                    current = []
                    current_words = 0

            if current:
                chunks.append(' '.join(current))

            return chunks

    # ── Word-count fallback (no/little punctuation) ──────────────────────────
    words = text.split()
    chunk_size = max(1, min(_MAX_WORDS_PER_CHUNK, len(words) // num_chunks))
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
        if len(chunks) == num_chunks:
            # Append remaining words to the last chunk
            remainder = ' '.join(words[i + chunk_size:])
            if remainder:
                chunks[-1] += ' ' + remainder
            break
    return chunks
