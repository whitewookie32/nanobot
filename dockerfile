FROM python:3.11-slim

# install system deps (if any needed)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Create a non-root user (optional but good practice)
RUN useradd -m appuser
USER appuser

# Install project in editable mode so CLI is available
RUN pip install --upgrade pip
RUN pip install -e .

# copy start script and make executable
COPY --chown=appuser:appuser start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Default command
CMD ["/app/start.sh"]
