# CLAUDE.md — Raspberry Pi Devcontainer Project

This file provides context for Claude Code. Read it before generating code, commands, or configuration for this project.

---

## Project Description

This project enables hardware-free Raspberry Pi development on an x86_64 host. All Pi-targeted binaries are built via cross-compilation and tested under QEMU user-mode emulation — no physical Pi is required during development. Code is deployed to a real Pi only at the end of the workflow.

Key capabilities provided by the devcontainer:
- Cross-compilation for ARMv7 (32-bit) and AArch64 (64-bit)
- QEMU user-mode emulation of ARM binaries
- CMake cross-build with a provided toolchain file
- GDB multiarch remote debugging via QEMU's GDB stub
- Docker-in-Docker for running full ARM container images
- Python development with mock GPIO (no hardware needed)

---

## Environment

| Property | Value |
|---|---|
| Host architecture | x86_64 |
| Host OS | Debian Bookworm (inside devcontainer) |
| Docker socket | Available via Docker-in-Docker |
| binfmt_misc | Registered for ARM ELFs (requires `--privileged`) |
| Default shell | bash |

---

## Toolchain Reference

### 32-bit ARMv7 (Raspberry Pi 2 / 3 / 4 in 32-bit mode)

| Item | Path / Value |
|---|---|
| C/C++ compiler | `arm-linux-gnueabihf-gcc` / `arm-linux-gnueabihf-g++` |
| Binutils prefix | `arm-linux-gnueabihf-` |
| QEMU runner | `qemu-arm -L /usr/arm-linux-gnueabihf` |
| CMake toolchain | `.devcontainer/toolchain/rpi-armv7.cmake` |
| CMake build dir | `build-arm/` |
| Debugger | `gdb-multiarch` (attach to `localhost:1234`) |
| Sysroot | `/usr/arm-linux-gnueabihf` |

### 64-bit AArch64 (Raspberry Pi 4 / 5 in 64-bit mode)

| Item | Path / Value |
|---|---|
| C/C++ compiler | `aarch64-linux-gnu-gcc` / `aarch64-linux-gnu-g++` |
| Binutils prefix | `aarch64-linux-gnu-` |
| QEMU runner | `qemu-aarch64 -L /usr/aarch64-linux-gnu` |
| CMake toolchain | (create `.devcontainer/toolchain/rpi-aarch64.cmake` following the ARMv7 pattern) |
| CMake build dir | `build-arm64/` |
| Debugger | `gdb-multiarch` (attach to `localhost:1234`) |
| Sysroot | `/usr/aarch64-linux-gnu` |

---

## Shell Alias Reference

These aliases are defined in the devcontainer shell profile for convenience.

| Alias | Expands to |
|---|---|
| `rpi-shell` | `docker run --rm -it --platform linux/arm/v7 -v $(pwd):/workspace -w /workspace debian:bookworm-slim /bin/bash` |
| `rpi-shell64` | `docker run --rm -it --platform linux/arm64 -v $(pwd):/workspace -w /workspace debian:bookworm-slim /bin/bash` |
| `xcc` | `arm-linux-gnueabihf-gcc` |
| `xcc64` | `aarch64-linux-gnu-gcc` |
| `qarm` | `qemu-arm -L /usr/arm-linux-gnueabihf` |
| `qarm64` | `qemu-aarch64 -L /usr/aarch64-linux-gnu` |

---

## Language Conventions

### Python

- Use **gpiozero** for GPIO; never import `RPi.GPIO` directly.
- Guard all hardware access at module level:
  ```python
  import os
  _IS_PI = os.path.exists("/sys/class/gpio")
  ```
  When `_IS_PI` is `False`, fall back to mock/stub behaviour — never raise unconditionally.
- Use **smbus2** for I2C (`from smbus2 import SMBus`).
- Prefer **asyncio** for I/O-bound tasks (sensors, serial, network).
- All public functions and classes must carry **type hints** (PEP 484 / 526).
- Minimum version: **Python 3.11**.
- Run with mock GPIO: `GPIOZERO_PIN_FACTORY=mock python my_script.py`

### C / C++

- Standards: **C11** (`-std=c11`) and **C++17** (`-std=c++17`).
- Always compile with `-g` during development; strip only for production.
- Guard hardware-specific code with architecture macros:
  ```c
  #if defined(__arm__)
  // ARMv7 path
  #elif defined(__aarch64__)
  // AArch64 path
  #else
  // Host stub / desktop fallback
  #endif
  ```
- Include `<stdint.h>` / `<cstdint>` for fixed-width types; never assume `int` width.
- Abstract hardware behind a HAL so the same source compiles on host with a stub.
- Memory-mapped I/O registers must be `volatile` and documented with comments.
- **No hard-coded pin numbers** in source — define all pins in a single config header/struct.

### Node.js

- Use **onoff** for GPIO, **i2c-bus** for I2C.
- Provide mock/stub when `/sys/class/gpio` or `/dev/i2c-*` are absent:
  ```js
  const isRealPi = fs.existsSync('/sys/class/gpio');
  const gpio = isRealPi ? new Gpio(pin, 'out') : stubGpio(pin);
  ```
- Use **ES modules** (`"type": "module"` in `package.json`); prefer named exports.
- Target **Node.js 20 LTS**.
- Log architecture at startup: `console.log('arch:', process.arch);`

---

## Build Commands

### Quick single-file C compile and run (32-bit)

```bash
# Compile
arm-linux-gnueabihf-gcc -g -o build/hello hello.c

# Run under QEMU
qemu-arm -L /usr/arm-linux-gnueabihf build/hello
```

### CMake cross-build (ARMv7)

```bash
# Configure (only needed once, or after CMakeLists.txt changes)
cmake -B build-arm \
  -DCMAKE_TOOLCHAIN_FILE=.devcontainer/toolchain/rpi-armv7.cmake \
  -G Ninja

# Build
cmake --build build-arm

# Run the output
qemu-arm -L /usr/arm-linux-gnueabihf build-arm/my_binary
```

The VS Code task **"Pi: CMake build (ARMv7)"** (default build task, `Ctrl+Shift+B`) runs both steps.

### Python — run with mock GPIO

```bash
GPIOZERO_PIN_FACTORY=mock python scripts/my_script.py
```

### Node.js — run (GPIO will use stub on non-Pi)

```bash
node src/index.js
```

### ARM container test (interactive shell)

```bash
docker run --rm -it --platform linux/arm/v7 \
  -v "$(pwd)":/workspace -w /workspace \
  debian:bookworm-slim /bin/bash
```

---

## Deployment Commands

The target Pi is identified by the environment variable `RPI_HOST` (e.g., `pi@raspberrypi.local`). Never hard-code this value.

```bash
# Copy a compiled binary
rsync -avz --progress build-arm/my_app "${RPI_HOST}:/home/pi/bin/"

# Copy Python scripts
rsync -avz --progress scripts/ "${RPI_HOST}:/home/pi/scripts/"

# Deploy systemd unit files (create a local systemd/ directory as needed)
# rsync -avz path/to/systemd-units/ "${RPI_HOST}:/etc/systemd/system/"
# ssh "${RPI_HOST}" "sudo systemctl daemon-reload"

# Restart a service
ssh "${RPI_HOST}" "sudo systemctl restart my-app.service"

# One-liner: build, copy, restart
cmake --build build-arm && \
  rsync -avz build-arm/my_app "${RPI_HOST}:/home/pi/bin/" && \
  ssh "${RPI_HOST}" "sudo systemctl restart my-app.service"
```

---

## Key Constraints

1. **No GPIO hardware is available in the devcontainer.** All GPIO access must be guarded or mocked. Tests must pass without physical hardware.
2. **QEMU emulation is 5–10x slower than native.** Avoid benchmarking inside QEMU. Use it for correctness testing only.
3. **binfmt_misc registration requires `--privileged`** (or `--cap-add SYS_ADMIN`). The devcontainer is already configured for this; do not remove that flag.
4. **Always pass `--platform` to Docker** when building or running ARM images. Never rely on automatic platform detection — it fails silently on some hosts.
   - 32-bit: `--platform linux/arm/v7`
   - 64-bit: `--platform linux/arm64`
5. **Target OS is Raspberry Pi OS Bookworm** (Debian 12). Match library versions and `apt` packages accordingly.
6. **Pin numbers must never be hard-coded** in source files. Use a dedicated config module / header / object.
7. **Log the architecture at startup** in every language so runtime issues are immediately diagnosable.
8. **Devcontainer paths** (sysroots, toolchain prefixes, QEMU paths) live under `.devcontainer/` only. Keep application source clean of container-specific assumptions.
