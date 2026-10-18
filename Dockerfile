# API image: the Tier-1 service, both MCP servers (started as subprocesses) and the eval suite.
FROM python:3.12-slim

WORKDIR /app
# HF_HOME inside /app so the embedding model downloaded at build time is found by the non-root user at run time
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/.hf

# CPU-only torch keeps the image a fraction of the size of the default CUDA build
COPY requirements.txt .
RUN pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

COPY . .

# Build the corpus and the vector index at image build time so the first request is not slow, and the embedding
# model is baked into the image (no download on the first ticket).
# The index is built from SYNTHETIC data; replace data/variant_a with real content for a real deployment.
RUN python scripts/generate_synthetic_corpus.py && python scripts/ingest_variant_a.py

# Run as an unprivileged user; only the data volume and the app's own runtime folders are writable.
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown -R app:app /app /data
USER app

EXPOSE 8000
# Secrets (GROQ_API_KEY, JWT_SECRET, ADMIN_EMAIL, PII_HASH_SALT) come from the environment, never the image.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
