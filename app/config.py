from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://rag:rag@localhost:5444/rag"

    # Local ONNX models (fastembed): no API key and no GPU required.
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    # Chunking: sentence-aware windows, never crossing a page boundary.
    chunk_words: int = 120
    overlap_words: int = 30

    # Retrieval.
    candidates: int = 30  # per channel, before fusion
    rrf_k: int = 60
    rerank_pool: int = 20  # fused candidates passed to the cross-encoder
    # Cross-encoder logit below which we refuse to answer (calibrated in eval/RESULTS.md).
    min_rerank_score: float = -3.0

    # Generation (optional). Without a key the answer is extractive.
    anthropic_api_key: str | None = None
    answer_model: str = "claude-haiku-5-5"

    # Optional shared secret. When set, every endpoint except /health requires X-API-Key.
    api_key: str | None = None
    max_upload_mb: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
