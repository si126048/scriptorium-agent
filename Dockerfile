FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY scriptorium ./scriptorium
RUN pip install --no-cache-dir .

RUN mkdir -p /data /app/web/dist

ENV LACAN_DB_PATH=/data/lacan.db LACAN_STORAGE_PATH=/data/storage

RUN useradd -m -r scriptorium && chown scriptorium /data

USER scriptorium

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

CMD ["uvicorn", "scriptorium.api:app", "--host", "0.0.0.0", "--port", "8000"]
