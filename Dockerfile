# Dockerfile for nanobot - AI Agent
# Optimized for Fly.io deployment

FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application code first (needed for editable install)
COPY . /app/

# Install the package
RUN pip install --no-cache-dir -e .

# Create data directory for persistent storage
RUN mkdir -p /data/nanobot

# Create startup script
RUN echo '#!/bin/bash\n\
cd /app\n\
exec python -u nanobot_gateway.py' > /app/start.sh && chmod +x /app/start.sh

# Set up non-root user for security
RUN useradd -m -u 1000 nanobot && \
    chown -R nanobot:nanobot /data /app

# Switch to non-root user
USER nanobot

# Set home directory for config
ENV HOME=/data
ENV NANOBOT_DATA_DIR=/data/nanobot

# Expose the gateway port
EXPOSE 18790

# Default command
CMD ["/app/start.sh"]
