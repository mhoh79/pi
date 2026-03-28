FROM mcr.microsoft.com/devcontainers/base:bookworm

# Install cross-compilation toolchains, QEMU emulation, and deployment tools.
# All packages are grouped logically and installed in a single RUN layer to
# minimise image layers while keeping the apt cache clean.
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
        # ── ARMv7 (32-bit) cross-compiler ─────────────────────────────────────
        gcc-arm-linux-gnueabihf \
        g++-arm-linux-gnueabihf \
        binutils-arm-linux-gnueabihf \
        # ── AArch64 (64-bit) cross-compiler ───────────────────────────────────
        gcc-aarch64-linux-gnu \
        g++-aarch64-linux-gnu \
        binutils-aarch64-linux-gnu \
        # ── QEMU user-mode emulation ───────────────────────────────────────────
        qemu-user \
        qemu-user-static \
        binfmt-support \
        # ── Build system tools ─────────────────────────────────────────────────
        cmake \
        ninja-build \
        make \
        pkg-config \
        # ── Multi-architecture debugger ────────────────────────────────────────
        gdb-multiarch \
        # ── Deployment and file-transfer utilities ─────────────────────────────
        curl \
        wget \
        file \
        rsync \
        sshpass \
        openssh-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Register QEMU binfmt handlers so that ARM binaries can be executed
# transparently by the kernel.  The "|| true" guards let the layer succeed
# inside BuildKit environments where binfmt_misc may not be writable; the
# post-create script re-registers them at runtime using the privileged
# tonistiigi/binfmt image.
RUN update-binfmts --enable qemu-arm    2>/dev/null || true \
    && update-binfmts --enable qemu-aarch64 2>/dev/null || true

# Copy CMake toolchain files into a stable, well-known path inside the image.
# They are available regardless of how or where the workspace is mounted.
COPY .devcontainer/toolchain/ /opt/toolchain/

# Create the sysroot staging directory.  It starts empty; developers can
# populate it by running rpi-deploy or by mounting a pre-built Pi rootfs.
RUN mkdir -p /opt/rpi-sysroot
