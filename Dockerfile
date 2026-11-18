FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FASTEMBED_CACHE_PATH=/models

COPY pyproject.toml ./
COPY app ./app
RUN pip install ".[llm]"

# Bake the ONNX models into the image so the container starts offline and fast.
RUN python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; \
TextEmbedding('BAAI/bge-small-en-v1.5'); TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2')"

RUN useradd -r -u 10001 app && chown -R app /models
USER app
EXPOSE 8020
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8020"]
