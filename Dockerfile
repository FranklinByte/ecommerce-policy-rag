FROM ghcr.io/astral-sh/uv:0.8.17 AS uv
FROM python:3.12.10-slim-bookworm

COPY --from=uv /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/app/model-cache \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY data ./data
COPY scripts/container_start.py ./scripts/container_start.py
RUN uv sync --frozen --no-dev && \
    groupadd --gid 10001 policy && \
    useradd --uid 10001 --gid policy --create-home policy && \
    mkdir -p /app/data/index /app/model-cache /app/eval-results && \
    chown -R policy:policy /app/data/index /app/model-cache /app/eval-results
USER policy
EXPOSE 8010
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/ready', timeout=3)"
CMD ["python", "scripts/container_start.py"]
