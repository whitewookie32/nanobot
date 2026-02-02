# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Minimal runtime deps for bash entrypoint + TLS.
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV"

WORKDIR /app

# Install package (keeps image smaller than copying full repo).
COPY pyproject.toml README.md LICENSE /app/
COPY nanobot /app/nanobot
COPY bridge /app/bridge
RUN pip install --upgrade pip \
  && pip install .

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Create a non-root user for runtime.
RUN useradd -m -u 10001 appuser \
  && mkdir -p /home/appuser/.nanobot \
  && chown -R appuser:appuser /home/appuser

USER appuser
ENV HOME=/home/appuser

EXPOSE 18790

ENTRYPOINT ["/app/start.sh"]
