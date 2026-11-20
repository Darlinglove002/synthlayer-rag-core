"""Retrieval + answer-quality evaluation on a hermetic database.

    python -m eval.run_eval              # prints a table and writes eval/RESULTS.md

It creates a throwaway database `rag_eval` on the server from DATABASE_URL, ingests the PDFs in
eval/corpus, runs every question in eval/questions.json through each retrieval mode and reports:

  hit@k   fraction of questions whose gold (document, page) is among the top k hits
  MRR     mean reciprocal rank of the first hit on the gold page
  p50/p95 search latency in ms (warm models)

Out-of-scope ("oos") questions have no gold page; for those we report how often the system
correctly refuses, and the same numbers are used to calibrate MIN_RERANK_SCORE.
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:  # app modules are imported lazily in main(), after DATABASE_URL is redirected
    from app.search import Mode

HERE = Path(__file__).parent
MODES: tuple["Mode", ...] = ("dense", "lexical", "hybrid", "hybrid_rerank")
CATEGORIES = ("semantic", "exact", "mixed")
KS = (1, 3, 5)


def _prepare_database() -> None:
    import psycopg

    base = os.environ.get("DATABASE_URL", "postgresql://rag:rag@localhost:5444/rag")
    parts = urlsplit(base)
    admin = urlunsplit(parts._replace(path="/postgres"))
    eval_url = urlunsplit(parts._replace(path="/rag_eval"))
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS rag_eval WITH (FORCE)")
        conn.execute("CREATE DATABASE rag_eval")
    os.environ["DATABASE_URL"] = eval_url


def _pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def _hit_at(rows: list[tuple[int | None, float]], k: int) -> float:
    return sum(1 for r, _ in rows if r is not None and r <= k) / len(rows)


def main() -> None:
    _prepare_database()
    from app.answer import answer, is_relevant
    from app.config import get_settings
    from app.db import close_pool
    from app.ingest import ingest_bytes
    from app.search import search

    cfg = get_settings()
    questions = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    pdfs = sorted((HERE / "corpus").glob("*.pdf"))
    if not pdfs:
        sys.exit("eval/corpus is empty - run: python -m eval.build_corpus")

    n_chunks = 0
    for pdf in pdfs:
        r = ingest_bytes(pdf.name, pdf.read_bytes(), title=pdf.stem)
        n_chunks += r.chunks
    print(f"ingested {len(pdfs)} documents, {n_chunks} chunks")

    search("warm up", 1)  # load models before timing anything

    scored = [q for q in questions if q["category"] in CATEGORIES]
    oos = [q for q in questions if q["category"] == "oos"]

    # results[mode][category] -> list of (rank|None, latency_ms)
    results: dict[str, dict[str, list[tuple[int | None, float]]]] = {
        m: {c: [] for c in CATEGORIES} for m in MODES
    }
    top_scores: dict[int, float] = {}
    for q in scored + oos:
        for mode in MODES:
            t0 = time.perf_counter()
            hits = search(q["question"], 5, mode)
            ms = (time.perf_counter() - t0) * 1000
            if mode == "hybrid_rerank":
                top = hits[0].rerank_score if hits else None
                top_scores[q["id"]] = float("-inf") if top is None else top
            if q["category"] == "oos":
                continue
            rank = next(
                (i for i, h in enumerate(hits, 1) if h.title == q["doc"] and h.page == q["page"]),
                None,
            )
            results[mode][q["category"]].append((rank, ms))

    lines: list[str] = []
    out = lines.append
    out(
        f"Corpus: {len(pdfs)} documents, {n_chunks} chunks, {len(scored)} scored questions "
        f"(+{len(oos)} out-of-scope). Embeddings `{cfg.embed_model}`, reranker `{cfg.rerank_model}`.\n"
    )

    out("### Retrieval quality (gold = exact document + page)\n")
    out("| mode | slice | n | hit@1 | hit@3 | hit@5 | MRR |")
    out("|---|---|---|---|---|---|---|")
    for mode in MODES:
        for cat in (*CATEGORIES, "all"):
            rows = (
                [r for c in CATEGORIES for r in results[mode][c]]
                if cat == "all"
                else results[mode][cat]
            )
            n = len(rows)
            hits_at = [_pct(_hit_at(rows, k)) for k in KS]
            mrr = sum(1 / r for r, _ in rows if r) / n
            out(f"| {mode} | {cat} | {n} | {' | '.join(hits_at)} | {mrr:.3f} |")

    out("\n### Search latency (warm, single query, includes query embedding)\n")
    out("| mode | p50 ms | p95 ms |")
    out("|---|---|---|")
    for mode in MODES:
        latencies = sorted(m for c in CATEGORIES for _, m in results[mode][c])
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        out(f"| {mode} | {statistics.median(latencies):.1f} | {p95:.1f} |")

    in_scores = sorted(top_scores[q["id"]] for q in scored)
    oos_scores = sorted(top_scores[q["id"]] for q in oos)
    out("\n### Refusal calibration (top reranker logit)\n")
    out(
        f"- in-scope questions: min {in_scores[0]:.2f}, p10 {in_scores[len(in_scores) // 10]:.2f}, "
        f"median {statistics.median(in_scores):.2f}"
    )
    out(
        f"- out-of-scope questions: median {statistics.median(oos_scores):.2f}, max {oos_scores[-1]:.2f}"
    )
    out("\n| threshold | in-scope answered | out-of-scope refused |")
    out("|---|---|---|")
    for t in (-8, -6, -4, -3, -2, 0):
        answered = sum(s >= t for s in in_scores) / len(in_scores)
        refused = sum(s < t for s in oos_scores) / len(oos_scores)
        mark = "  <- configured" if t == cfg.min_rerank_score else ""
        out(f"| {t} | {_pct(answered)} | {_pct(refused)}{mark} |")

    # End-to-end answer check using the default (extractive) generator.
    good = cited_gold = 0
    refused_oos = 0
    for q in scored:
        hits = search(q["question"], 5, "hybrid_rerank")
        a = answer(q["question"], hits)
        if a.grounded:
            good += 1
            cited_gold += any(c.title == q["doc"] and c.page == q["page"] for c in a.citations)
    for q in oos:
        refused_oos += not answer(q["question"], search(q["question"], 5, "hybrid_rerank")).grounded
    out("\n### End-to-end answers (extractive generator, no LLM)\n")
    out(
        f"- in-scope: answered {good}/{len(scored)}, cited the gold page in {cited_gold}/{len(scored)}"
    )
    out(f"- out-of-scope: refused {refused_oos}/{len(oos)}")
    _ = is_relevant  # imported for readers who want to reuse the refusal rule

    report = "\n".join(lines)
    print(report)
    (HERE / "RESULTS.md").write_text(
        "# Eval results\n\nGenerated by `python -m eval.run_eval`. The corpus is small and synthetic "
        "(see eval/corpus_text.py), so read these as a regression baseline and a demonstration of the "
        "two channels, not as a benchmark of the method.\n\n" + report + "\n",
        encoding="utf-8",
    )
    close_pool()

    # Regression guard for CI: the full pipeline must keep finding the gold page.
    floor = float(os.environ.get("MIN_HIT3", "0.9"))
    final = [r for c in CATEGORIES for r in results["hybrid_rerank"][c]]
    got = _hit_at(final, 3)
    if got < floor:
        sys.exit(f"FAIL: hybrid_rerank hit@3 {got:.3f} is below the floor {floor:.2f}")


if __name__ == "__main__":
    main()
