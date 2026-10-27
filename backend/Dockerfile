# Trekly API (FastAPI) for Render. Build context is backend/.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

# catalog_data and config are read at runtime; alembic and scripts are kept so one-off
# jobs (migrations, catalogue syncs) can run from a Render shell.
COPY app ./app
COPY catalog_data ./catalog_data
COPY config ./config
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 trekly
USER trekly

# Render sets PORT; it terminates TLS and forwards the client address.
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
