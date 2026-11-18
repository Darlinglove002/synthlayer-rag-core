"""Sentence-aware sliding-window chunking.

Chunks are packed from whole sentences up to `max_words`; the next chunk starts with the
trailing sentences of the previous one (about `overlap_words` words) so a fact straddling a
boundary still appears intact in at least one chunk. A chunk never crosses a page boundary,
which is what makes page-level citations exact.
"""

import re

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])|\n{2,}")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE.split(text.replace("\r", ""))]
    return [re.sub(r"\s+", " ", p) for p in parts if p]


def _hard_split(sentence: str, max_words: int) -> list[str]:
    words = sentence.split()
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def chunk_text(text: str, max_words: int = 120, overlap_words: int = 30) -> list[str]:
    if max_words <= 0:
        raise ValueError("max_words must be positive")
    if not 0 <= overlap_words < max_words:
        raise ValueError("overlap_words must be in [0, max_words)")

    sentences: list[str] = []
    for s in split_sentences(text):
        sentences.extend(_hard_split(s, max_words) if len(s.split()) > max_words else [s])

    chunks: list[str] = []
    window: list[str] = []
    size = 0
    fresh = 0  # sentences in the window that no emitted chunk contains yet
    for sentence in sentences:
        n = len(sentence.split())
        if window and size + n > max_words:
            chunks.append(" ".join(window))
            carried: list[str] = []
            carried_words = 0
            for prev in reversed(window):
                w = len(prev.split())
                if carried_words + w > overlap_words:
                    break
                carried.insert(0, prev)
                carried_words += w
            window, size, fresh = carried, carried_words, 0
        window.append(sentence)
        size += n
        fresh += 1
    if window and fresh:
        chunks.append(" ".join(window))
    return chunks
