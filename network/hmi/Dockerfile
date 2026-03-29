ARG BASE_IMAGE=rpi-dds-base
FROM ${BASE_IMAGE}

RUN pip install --no-cache-dir aiohttp-cors

# Copy shared library and application code
COPY shared/ /opt/shared/
COPY hmi/ /app/

WORKDIR /app

EXPOSE 3000

CMD ["python3", "main.py"]
