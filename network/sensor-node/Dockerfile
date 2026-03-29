ARG BASE_IMAGE=rpi-dds-base
FROM ${BASE_IMAGE}

# Copy shared library and application code
COPY shared/ /opt/shared/
COPY sensor-node/ /app/

WORKDIR /app

# Health-check endpoint (served by the sensor node on port 9000)
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health')"

EXPOSE 9000

CMD ["python", "main.py"]
