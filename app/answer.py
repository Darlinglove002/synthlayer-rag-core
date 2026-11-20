"""Answer generation with citations.

With ANTHROPIC_API_KEY the answer is written by an LLM from the numbered sources only.
Without a key it falls back to an extractive answer (the best-matching sentences verbatim).
Either way, every claim carries a [n] marker that maps to a (document, page) citation, and the
system refuses when the best reranked passage is below the calibrated relevance threshold.
"""

import logging
import re
from dataclasses import dataclass, field

from app.chunking import split_sentences
from app.config import get_settings
from app.search import Hit

log = logging.getLogger(__name__)

NO_ANSWER = "I couldn't find this in the indexed documents."
_STOP = set(
    "a an the of to in on for and or is are was were be been it its this that with as at by from "
    "do does did how what why when where which who can i my me you your we our there their".split()
)
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")


@dataclass
class Citation:
    n: int
    document_id: int
    title: str
    page: int
    snippet: str


@dataclass
class Answer:
    text: str
    grounded: bool
    citations: list[Citation] = field(default_factory=list)
    generator: str = "extractive"


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if w.lower() not in _STOP}


def _citation(n: int, hit: Hit) -> Citation:
    snippet = hit.content if len(hit.content) <= 280 else hit.content[:277] + "..."
    return Citation(n, hit.document_id, hit.title, hit.page, snippet)


def is_relevant(hits: list[Hit]) -> bool:
    if not hits:
        return False
    top = hits[0].rerank_score
    return top is None or top >= get_settings().min_rerank_score


def extractive_answer(question: str, hits: list[Hit]) -> Answer:
    q = _terms(question)
    best: tuple[float, int, str] | None = None
    for n, hit in enumerate(hits[:3], start=1):
        for sent in split_sentences(hit.content):
            overlap = len(q & _terms(sent))
            score = overlap + (0.01 if n == 1 else 0.0)  # tie-break toward the better-ranked hit
            if best is None or score > best[0]:
                best = (score, n, sent)
    assert best is not None
    _, n, sent = best
    return Answer(f"{sent} [{n}]", True, [_citation(n, hits[n - 1])], "extractive")


_SYSTEM = (
    "Answer the question using ONLY the numbered sources. Cite every claim with its source "
    "number in square brackets, like [1]. If the sources do not contain the answer, reply "
    f"exactly: {NO_ANSWER} Be concise."
)


def llm_answer(question: str, hits: list[Hit]) -> Answer:
    import anthropic

    cfg = get_settings()
    sources = "\n\n".join(
        f"[{i}] ({h.title}, page {h.page})\n{h.content}" for i, h in enumerate(hits, start=1)
    )
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    msg = client.messages.create(
        model=cfg.answer_model,
        max_tokens=400,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"Sources:\n{sources}\n\nQuestion: {question}"}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text) if 1 <= int(n) <= len(hits)})
    if text.startswith(NO_ANSWER) or not used:
        return Answer(NO_ANSWER, False, [], cfg.answer_model)
    return Answer(text, True, [_citation(n, hits[n - 1]) for n in used], cfg.answer_model)


def answer(question: str, hits: list[Hit]) -> Answer:
    if not is_relevant(hits):
        log.info("refusing to answer: nothing relevant in the indexed documents")
        return Answer(NO_ANSWER, False, [], "none")
    if get_settings().anthropic_api_key:
        try:
            return llm_answer(question, hits)
        except Exception as exc:  # provider outage must not take the endpoint down
            log.warning(
                "LLM answer failed (%s), falling back to the extractive answer", type(exc).__name__
            )
    return extractive_answer(question, hits)
