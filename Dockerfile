FROM python:3.12-slim

# Node.js is required for npx-based MCP servers (e.g. @modelcontextprotocol/server-filesystem).
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python package and serve extras.
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir -e ".[serve]"

# Session database lives here; mount a volume to persist across restarts.
RUN mkdir -p /app/data

# aria.config.json is expected to be bind-mounted at runtime (see docker-compose.yml).
ENV ARIA_CONFIG=/app/aria.config.json
ENV ARIA_DB_PATH=/app/data/aria.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c \
        "import urllib.request, sys; \
         r = urllib.request.urlopen('http://localhost:8000/health', timeout=4); \
         sys.exit(0 if r.status == 200 else 1)"

CMD ["uvicorn", "aria.serve:app", "--host", "0.0.0.0", "--port", "8000"]
