# GitHub Copilot Instructions — Raspberry Pi Devcontainer Project

This project targets Raspberry Pi hardware but develops entirely inside a devcontainer on an x86_64 host. All binaries are cross-compiled or run under QEMU emulation. There is no physical GPIO hardware available during development.

---

## Architecture and Toolchain

| Target       | Architecture | Cross-compiler                  | QEMU runner                    | Sysroot / libs                   |
|-------------|-------------|--------------------------------|-------------------------------|----------------------------------|
| RPi 3/4 (32-bit) | ARMv7        | `arm-linux-gnueabihf-gcc`       | `qemu-arm -L /usr/arm-linux-gnueabihf` | `/usr/arm-linux-gnueabihf`        |
| RPi 4/5 (64-bit) | AArch64      | `aarch64-linux-gnu-gcc`         | `qemu-aarch64 -L /usr/aarch64-linux-gnu` | `/usr/aarch64-linux-gnu`          |

- CMake toolchain file for ARMv7: `.devcontainer/toolchain/rpi-armv7.cmake`
- CMake build directory: `build-arm/`
- GDB multiarch debugger: `gdb-multiarch`; QEMU GDB stub listens on `localhost:1234`
- binfmt_misc is registered in the container so ARM ELF files can be executed directly

---

## Python Conventions

- Use **gpiozero** for all GPIO operations; never use `RPi.GPIO` directly.
- Guard all hardware access with a runtime check before touching real pins:
  ```python
  import os
  _IS_PI = os.path.exists("/sys/class/gpio")
  ```
- When `_IS_PI` is `False` (i.e., inside the devcontainer), fall back to mock/stub behaviour; never raise unconditionally.
- Use **smbus2** for I2C communication (`from smbus2 import SMBus`).
- Prefer **asyncio** for I/O-bound Pi tasks (polling sensors, network, serial).
- All public functions and classes must have **type hints** (PEP 484 / 526).
- Set `GPIOZERO_PIN_FACTORY=mock` to enable mock GPIO; the VS Code launch config already does this.
- Minimum Python version: 3.11.

---

## C / C++ Conventions

- Language standards: **C11** (`-std=c11`) and **C++17** (`-std=c++17`).
- Always compile with `-g` during development; strip only for production releases.
- Use architecture detection macros to guard hardware-specific code:
  ```c
  #if defined(__arm__)
  // ARMv7 path
  #elif defined(__aarch64__)
  // AArch64 path
  #else
  // Host / desktop stub
  #endif
  ```
- Include `<stdint.h>` (or `<cstdint>` in C++) for fixed-width integer types; never assume `int` size.
- Abstract hardware access behind a HAL (Hardware Abstraction Layer) interface so the same code compiles on host with a stub implementation.
- For memory-mapped I/O, use `volatile` and document the register map with comments.
- Link order for cross-compiled binaries: object files first, then `-l` libraries.

---

## Node.js Conventions

- Use **onoff** (`npm i onoff`) for GPIO control.
- Use **i2c-bus** (`npm i i2c-bus`) for I2C communication.
- Provide mock/stub implementations when `/dev/i2c-*` or `/sys/class/gpio` are not present so the module loads cleanly in the devcontainer.
  ```js
  const isRealPi = fs.existsSync('/sys/class/gpio');
  const gpio = isRealPi ? new Gpio(pin, 'out') : stubGpio(pin);
  ```
- Use **ES modules** (`"type": "module"` in `package.json`); prefer named exports over default exports.
- Target Node.js 20 LTS.
- Test GPIO and I2C paths with `jest` mocks; never skip tests because hardware is unavailable.

---

## General Rules

- **No hard-coded pin numbers** anywhere in source files. Define pins in a single configuration object/struct/dict and import it wherever needed.
- **Log the detected architecture at startup**:
  - Python: `import platform; logging.info("arch: %s", platform.machine())`
  - C: `printf("[startup] arch: " __ARCH_STRING__ "\n");` (define `__ARCH_STRING__` in the toolchain cmake)
  - Node.js: `console.log('arch:', process.arch);`
- Always use the devcontainer cross-compiler paths (`arm-linux-gnueabihf-gcc`, etc.) for builds; do not rely on the host `gcc` for ARM targets.
- When writing `Dockerfile` or `docker run` commands that need to execute ARM binaries, always pass `--platform linux/arm/v7` (32-bit) or `--platform linux/arm64` (64-bit) explicitly — never rely on default platform detection.
- Store devcontainer-specific paths (sysroots, toolchain prefixes) in `.devcontainer/` only; keep source code free of container assumptions.

---

## Deployment

- The target Pi is identified by the environment variable `$RPI_HOST` (e.g., `pi@raspberrypi.local`).
- **Copy binaries / scripts** using rsync:
  ```bash
  rsync -avz --progress build-arm/my_app ${RPI_HOST}:/home/pi/bin/
  ```
- **Run remotely** via SSH:
  ```bash
  ssh ${RPI_HOST} "sudo systemctl restart my-app.service"
  ```
- systemd unit files live in `deploy/systemd/`; deploy them with:
  ```bash
  rsync -avz deploy/systemd/ ${RPI_HOST}:/etc/systemd/system/
  ssh ${RPI_HOST} "sudo systemctl daemon-reload"
  ```
- Never bake `$RPI_HOST` into source files; always read it from the environment at deploy time.

---

## Testing

| Scenario | How to test |
|---|---|
| C / C++ binary correctness | Run under QEMU: `qemu-arm -L /usr/arm-linux-gnueabihf ./build-arm/my_binary` |
| C / C++ with GDB | Start `qemu-arm -g 1234 …` in one terminal, attach `gdb-multiarch` in another (or use the VS Code launch config) |
| Python GPIO logic | `GPIOZERO_PIN_FACTORY=mock python my_script.py` |
| Python unit tests | `pytest` — gpiozero mock factory is activated in `conftest.py` via the env var |
| Integration / smoke tests | Use the `rpi-shell` alias to drop into an ARM container: `docker run --rm -it --platform linux/arm/v7 -v $(pwd):/workspace -w /workspace debian:bookworm-slim /bin/bash` |
| Docker --platform validation | Always build and run test images with `--platform linux/arm/v7` or `--platform linux/arm64` to catch endianness and ABI issues early |
