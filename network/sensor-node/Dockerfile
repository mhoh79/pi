FROM --platform=${TARGETPLATFORM:-linux/arm/v7} python:3.11-slim-bookworm

# Install runtime dependencies
RUN pip install --no-cache-dir aiohttp

# Copy application code
COPY . /app

# Note: /opt/shared is bind-mounted at runtime by docker-compose.
# For standalone builds, mount or copy the shared/ directory manually:
#   docker build --build-arg ... -t sensor-node .
#   docker run -v /path/to/shared:/opt/shared:ro sensor-node
RUN mkdir -p /opt/shared

WORKDIR /app

# Health-check endpoint (served by the sensor node on port 9000)
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health')"

EXPOSE 9000

CMD ["python", "main.py"]
