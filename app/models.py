"""Lazy singletons for the local ONNX models (loaded on first use, not at import)."""

from functools import lru_cache

import numpy as np

from app.config import get_settings


@lru_cache
def _embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(get_settings().embed_model)


@lru_cache
def _reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(get_settings().rerank_model)


def embed_documents(texts: list[str]) -> list[np.ndarray]:
    return [np.asarray(v, dtype=np.float32) for v in _embedder().passage_embed(texts)]


def embed_query(text: str) -> np.ndarray:
    return np.asarray(next(iter(_embedder().query_embed([text]))), dtype=np.float32)


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    if not passages:
        return []
    return [float(s) for s in _reranker().rerank(query, passages)]
