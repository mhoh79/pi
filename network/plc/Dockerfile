FROM --platform=${TARGETPLATFORM:-linux/arm/v7} python:3.11-slim-bookworm

RUN pip install --no-cache-dir aiohttp pydantic cyclonedds

COPY . /app
WORKDIR /app

EXPOSE 8081

CMD ["python3", "main.py"]
