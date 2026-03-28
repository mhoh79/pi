FROM --platform=${TARGETPLATFORM:-linux/arm/v7} python:3.11-slim-bookworm

RUN pip install --no-cache-dir aiohttp aiohttp-cors pydantic cyclonedds

COPY . /app
WORKDIR /app

EXPOSE 3000

CMD ["python3", "main.py"]
