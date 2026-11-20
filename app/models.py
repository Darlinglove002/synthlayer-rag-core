"""Lazy singletons for the local ONNX models (loaded on first use, not at import)."""

import logging
from functools import lru_cache
from typing import Any

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def _embedder() -> Any:
    from fastembed import TextEmbedding

    name = get_settings().embed_model
    log.info("loading embedding model %s", name)
    return TextEmbedding(name)


@lru_cache
def _reranker() -> Any:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    name = get_settings().rerank_model
    log.info("loading rerank model %s", name)
    return TextCrossEncoder(name)


def embed_documents(texts: list[str]) -> list[np.ndarray]:
    return [np.asarray(v, dtype=np.float32) for v in _embedder().passage_embed(texts)]


def embed_query(text: str) -> np.ndarray:
    return np.asarray(next(iter(_embedder().query_embed([text]))), dtype=np.float32)


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    if not passages:
        return []
    return [float(s) for s in _reranker().rerank(query, passages)]
