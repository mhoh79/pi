ARG TARGETPLATFORM=linux/amd64
FROM --platform=${TARGETPLATFORM} python:3.11-slim-bookworm

# Build tools for compiling CycloneDDS C library and Python bindings
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gcc g++ cmake make libssl-dev python3-dev git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build CycloneDDS C library from source
ARG CYCLONEDDS_VERSION=11.0.1
RUN git clone --depth 1 --branch ${CYCLONEDDS_VERSION} \
    https://github.com/eclipse-cyclonedds/cyclonedds.git /tmp/cyclonedds \
    && mkdir /tmp/cyclonedds/build \
    && cd /tmp/cyclonedds/build \
    && cmake .. \
    -DCMAKE_INSTALL_PREFIX=/opt/cyclonedds \
    -DCMAKE_BUILD_TYPE=Release \
    -DENABLE_SSL=OFF \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_TESTING=OFF \
    && cmake --build . --parallel "$(nproc)" --target install \
    # Copy internal DDSI headers needed by the Python bindings
    && cp -rn /tmp/cyclonedds/src/core/ddsi/include/dds/ddsi /opt/cyclonedds/include/dds/ 2>/dev/null || true \
    && rm -rf /tmp/cyclonedds

ENV CYCLONEDDS_HOME=/opt/cyclonedds
ENV CMAKE_PREFIX_PATH=/opt/cyclonedds
ENV LD_LIBRARY_PATH=/opt/cyclonedds/lib

# Install common Python dependencies + CycloneDDS Python bindings
RUN pip install --no-cache-dir aiohttp pydantic cyclonedds
