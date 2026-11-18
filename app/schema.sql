CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          serial PRIMARY KEY,
    title       text        NOT NULL,
    source      text        NOT NULL UNIQUE,   -- original filename
    sha256      text        NOT NULL,
    pages       int         NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- One row = one chunk. Vector and full-text index live side by side,
-- so both channels are queried (and kept consistent) in the same database.
CREATE TABLE IF NOT EXISTS chunks (
    id           bigserial PRIMARY KEY,
    document_id  int    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page         int    NOT NULL,
    chunk_index  int    NOT NULL,
    content      text   NOT NULL,
    embedding    vector(384) NOT NULL,
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks (document_id);
