ARG BASE_IMAGE=rpi-dds-base
FROM ${BASE_IMAGE}

# Copy shared library and application code
COPY shared/ /opt/shared/
COPY gateway/ /app/

WORKDIR /app

# Health-check – the gateway exposes /health on port 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

EXPOSE 8080

CMD ["python", "main.py"]
