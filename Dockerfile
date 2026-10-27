# ─── Build stage ───
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Runtime stage ───
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages từ builder
COPY --from=builder /install /usr/local

# Non-root user (bảo mật)
RUN useradd --create-home appuser
USER appuser

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser run.py pyproject.toml README.md ./

ENTRYPOINT ["python", "run.py"]
CMD ["--help"]
