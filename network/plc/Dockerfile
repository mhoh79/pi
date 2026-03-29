ARG BASE_IMAGE=rpi-dds-base
FROM ${BASE_IMAGE}

# Copy shared library and application code
COPY shared/ /opt/shared/
COPY plc/ /app/

WORKDIR /app

EXPOSE 8081

CMD ["python3", "main.py"]
