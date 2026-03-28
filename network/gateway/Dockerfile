FROM --platform=${TARGETPLATFORM:-linux/arm/v7} python:3.11-slim-bookworm

# Install runtime dependencies
RUN pip install --no-cache-dir aiohttp

# Copy application code
COPY . /app

# Note: /opt/shared is bind-mounted at runtime by docker-compose.
# For standalone builds, mount or copy the shared/ directory manually.
RUN mkdir -p /opt/shared

WORKDIR /app

# Health-check – the gateway exposes /health on port 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

EXPOSE 8080

CMD ["python", "main.py"]
