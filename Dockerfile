# ─── Build stage ───
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Runtime stage ───
FROM python:3.12-slim

# Labels chuẩn OCI
LABEL org.opencontainers.image.title="free-llm-provider-discovery"
LABEL org.opencontainers.image.description="CLI tool để khám phá và thu thập danh sách các LLM API provider miễn phí"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/nguyenson/app-free-api-information-retrieval"

WORKDIR /app

# Copy installed packages từ builder
COPY --from=builder /install /usr/local

# Non-root user (bảo mật)
RUN useradd --create-home appuser
USER appuser

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser run.py pyproject.toml README.md ./

# HEALTHCHECK — chạy lệnh health của chính CLI
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=2 \
    CMD ["python", "run.py", "health", "--output", "/tmp/health.json"]

# REST API server (dùng với: docker compose run app serve --host 0.0.0.0)
EXPOSE 8000

ENTRYPOINT ["python", "run.py"]
CMD ["--help"]
