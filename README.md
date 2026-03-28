# Raspberry Pi Devcontainer

A fully self-contained development environment for Raspberry Pi targets that runs entirely inside GitHub Codespaces — no physical hardware required. The container bundles ARMv7 and AArch64 cross-compilers, QEMU user-mode emulation, Docker buildx for multi-platform image builds, rsync-based deployment tooling, and pre-configured VS Code extensions for C/C++, Python, and Node.js. You can write, build, run, and debug ARM binaries from any browser without owning a single board.

### Supported Targets

| Architecture | Alias      | Raspberry Pi Models          |
|--------------|------------|------------------------------|
| ARMv7 32-bit | `armv7l`   | Pi 2, Pi 3, Pi Zero 2 W      |
| AArch64 64-bit | `aarch64` | Pi 3, Pi 4, Pi 5             |

---

## Quick Start

1. **Open in Codespaces** — click the button below to launch a new Codespace from this repository:

   [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/mhoh79/pi)

2. **Wait for setup** — the post-create script runs automatically. It registers QEMU binfmt handlers, configures the `rpi-builder` Docker buildx instance, pulls the ARM base image, installs Python stubs, and loads all `rpi-*` shell aliases. This takes roughly 2-3 minutes on the first launch.

3. **Start developing** — open a terminal and use any of the `rpi-*` aliases described below. The cross-compilers, QEMU runners, and CMake toolchain files are ready immediately.

---

## Workflows

### Cross-Compile C/C++

The container provides both the ARMv7 (`arm-linux-gnueabihf`) and AArch64 (`aarch64-linux-gnu`) toolchains. Use the short aliases for one-off compilation:

```bash
# Compile a single file for ARMv7 (Pi 2/3/Zero 2 W)
rpi-gcc -O2 -o hello hello.c

# Compile for AArch64 (Pi 3/4/5)
rpi-gcc64 -O2 -o hello hello.c

# Run the resulting binary under QEMU without leaving the Codespace
rpi-run ./hello
rpi-run64 ./hello
```

For larger projects, use the pre-configured CMake toolchain files:

```bash
# ARMv7 build
mkdir build-arm && cd build-arm
rpi-cmake -GNinja ..
ninja

# AArch64 build
mkdir build-arm64 && cd build-arm64
rpi-cmake64 -GNinja ..
ninja
```

CMake toolchain files are located at `/opt/toolchain/rpi-armv7.cmake` and `/opt/toolchain/rpi-aarch64.cmake`. They set the correct sysroot paths under `/usr/arm-linux-gnueabihf` and `/opt/rpi-sysroot` so `find_package` and `find_library` resolve against ARM headers and libraries, not the host x86-64 ones.

---

### Python with Mock GPIO

The container installs `RPi.GPIO-stubs`, `gpiozero`, and `smbus2` via pip during setup. GPIO calls auto-detect the mock environment — no code changes are needed between running on a real Pi and running in the Codespace:

```bash
python3 my_sensor_script.py
```

If your script uses `RPi.GPIO` directly, the stubs raise `RuntimeError` on real hardware checks but allow pin logic to execute in simulation. `gpiozero` ships its own mock pin factory and activates it automatically when running outside a Pi kernel. For `smbus2`, use environment-level patching or the built-in `SMBus` mock provided by the stubs package.

---

### Node.js Sensor Streaming

Node.js 20 is available in the container. Ports 3000, 5000, 8000, and 8080 are pre-configured in `devcontainer.json`, so Express or WebSocket servers are accessible from your browser tab automatically:

```bash
npm install
node server.js
# VS Code prompts to open the forwarded port in a browser
```

---

### Build ARM Docker Images

The post-create script creates a `rpi-builder` buildx instance with multi-platform support. Use the aliases to target ARM platforms:

```bash
# Build a 32-bit ARMv7 image
rpi-docker-build -t my-app:armv7 .

# Build a 64-bit AArch64 image
rpi-docker-build64 -t my-app:arm64 .

# Push to a registry at the same time
rpi-docker-build --push -t ghcr.io/youruser/my-app:armv7 .
```

Both aliases automatically pass the correct `--platform` flag to `docker buildx build` and use the `rpi-builder` instance created during setup.

---

### Deploy to Pi

Set the `RPI_HOST` environment variable to your Pi's SSH target, then call `rpi-deploy`:

```bash
# RPI_HOST accepts "user@host" or just "host" (defaults to user "pi")
export RPI_HOST=pi@192.168.1.100

# Deploy current directory to /home/pi/app on the Pi
rpi-deploy

# Deploy a specific source directory to a custom destination
rpi-deploy ./build /home/pi/my-project
```

`rpi-deploy` is a shell function that calls `rsync -avz` and automatically excludes `.git`, `build*`, `node_modules`, and `__pycache__` directories. SSH authentication uses your Codespace's forwarded SSH agent. For key-based auth, add your private key to the Codespace secrets as `SSH_PRIVATE_KEY` and load it with `ssh-add`.

For scripted CI deploys, the repository also includes `scripts/deploy-to-pi.sh` which wraps this logic with pre/post-deploy hooks and argument parsing.

---

### Debug ARM Binaries

The container includes `gdb-multiarch` and QEMU user-mode emulation, which together allow source-level debugging of ARM binaries without a physical device.

**From the terminal:**

```bash
# Start the binary under QEMU in GDB server mode on port 1234
qemu-arm -L /usr/arm-linux-gnueabihf -g 1234 ./hello &

# Connect gdb-multiarch
gdb-multiarch -ex "set architecture arm" \
              -ex "set sysroot /usr/arm-linux-gnueabihf" \
              -ex "target remote :1234" \
              ./hello
```

**From VS Code:**

The `Cortex-Debug` and `ms-vscode.cpptools` extensions are pre-installed. Add a `launch.json` entry with `"MIMode": "gdb"`, `"miDebuggerPath": "/usr/bin/gdb-multiarch"`, and `"miDebuggerServerAddress": "localhost:1234"` to attach the VS Code debugger UI to the QEMU GDB stub.

---

### Multi-Node Network

Simulate a Pi cluster with Docker Compose. Place your `docker-compose.yml` under a `network/` directory and use the network aliases:

```bash
# Start all nodes
rpi-net-up

# Tail logs from all services
rpi-net-logs

# Show running containers and their status
rpi-net-ps

# Tear down and remove volumes
rpi-net-down
```

**Example architecture:**

```
                  +--------------+
                  |   gateway    |  (linux/arm/v7, port 8080)
                  +------+-------+
                         |
          +--------------+--------------+
          |                             |
   +------+------+              +-------+-----+
   |   sensor-1  |              |  sensor-2   |
   | (arm/v7)    |              | (arm64)     |
   +-------------+              +-------------+
```

Each service can target a different ARM platform. Docker buildx handles the per-service platform selection via the `platform:` key in `docker-compose.yml`.

---

## Using AI Assistants

### GitHub Copilot

This repository includes `.github/copilot-instructions.md`, which provides Copilot with context about the ARM cross-compilation toolchain, available aliases, and environment variables. Copilot will automatically read this file in supported editors and apply the context to suggestions.

**Example prompts:**

- "Write a CMakeLists.txt that cross-compiles for ARMv7 using the rpi-armv7.cmake toolchain."
- "Generate a Python GPIO blink script that works with mock GPIO in this devcontainer."
- "Create a Dockerfile for a Node.js app targeting linux/arm/v7."

### Claude Code

The `CLAUDE.md` file at the repository root gives Claude Code the same toolchain and environment context. Open Claude Code in the Codespace and reference the environment directly:

**Example prompts:**

- "Cross-compile the src/ directory for AArch64 and show me how to run the binary under QEMU."
- "Write a deploy script that uses rpi-deploy to push the build/ output to my Pi."
- "Explain what rpi-cmake64 expands to and which CMake variables it sets."

---

## Project Structure

```
.
├── .devcontainer/
│   ├── devcontainer.json          # Codespaces/devcontainer configuration, extensions, env vars
│   ├── Dockerfile                 # Container image: cross-compilers, QEMU, build tools
│   ├── scripts/
│   │   └── post-create.sh         # One-time setup: binfmt, buildx, pip packages, aliases
│   └── toolchain/
│       ├── rpi-armv7.cmake        # CMake toolchain file for ARMv7 32-bit
│       └── rpi-aarch64.cmake      # CMake toolchain file for AArch64 64-bit
├── .github/
│   └── copilot-instructions.md    # Copilot context for this ARM dev environment
├── CLAUDE.md                      # Claude Code context and project conventions
├── network/
│   └── docker-compose.yml         # Multi-node ARM container network definition
├── scripts/
│   └── deploy-to-pi.sh            # Scripted rsync deploy helper with hooks
└── README.md                      # This file
```

---

## Shell Aliases

All aliases are defined in `~/.zsh_aliases` and sourced automatically from `~/.zshrc`.

| Alias               | Expands To / Description                                                      |
|---------------------|-------------------------------------------------------------------------------|
| `rpi-gcc`           | `arm-linux-gnueabihf-gcc` — ARMv7 C compiler                                 |
| `rpi-g++`           | `arm-linux-gnueabihf-g++` — ARMv7 C++ compiler                               |
| `rpi-gcc64`         | `aarch64-linux-gnu-gcc` — AArch64 C compiler                                 |
| `rpi-g++64`         | `aarch64-linux-gnu-g++` — AArch64 C++ compiler                               |
| `rpi-run`           | `qemu-arm -L /usr/arm-linux-gnueabihf` — run an ARMv7 binary via QEMU        |
| `rpi-run64`         | `qemu-aarch64 -L /usr/aarch64-linux-gnu` — run an AArch64 binary via QEMU    |
| `rpi-cmake`         | `cmake -DCMAKE_TOOLCHAIN_FILE=/opt/toolchain/rpi-armv7.cmake`                 |
| `rpi-cmake64`       | `cmake -DCMAKE_TOOLCHAIN_FILE=/opt/toolchain/rpi-aarch64.cmake`               |
| `rpi-shell`         | Interactive ARMv7 Debian shell via Docker                                     |
| `rpi-shell64`       | Interactive AArch64 Debian shell via Docker                                   |
| `rpi-docker-build`  | `docker buildx build --platform linux/arm/v7`                                 |
| `rpi-docker-build64`| `docker buildx build --platform linux/arm64`                                  |
| `rpi-deploy`        | `rsync -avz` to `$RPI_HOST` (shell function, accepts `[src] [dest]` args)     |
| `rpi-net-up`        | `docker compose -f network/docker-compose.yml up --build -d`                  |
| `rpi-net-down`      | `docker compose -f network/docker-compose.yml down -v`                        |
| `rpi-net-logs`      | `docker compose -f network/docker-compose.yml logs -f`                        |
| `rpi-net-ps`        | `docker compose -f network/docker-compose.yml ps`                             |

---

## Environment Variables

These variables are set in `devcontainer.json` under `containerEnv` and are available in every terminal session.

| Variable         | Default Value                  | Purpose                                                              |
|------------------|--------------------------------|----------------------------------------------------------------------|
| `RPI_TOOLCHAIN`  | `/usr/bin/arm-linux-gnueabihf-`| Prefix path for the ARMv7 cross-toolchain binaries                  |
| `RPI_SYSROOT`    | `/opt/rpi-sysroot`             | Path to the ARM sysroot used by CMake and the linker                 |
| `QEMU_LD_PREFIX` | `/usr/arm-linux-gnueabihf`     | Library search root used by `qemu-arm` when executing ARM binaries   |
| `RPI_HOST`       | _(not set)_                    | SSH target for `rpi-deploy`, e.g. `pi@192.168.1.100` — set manually |

---

## Troubleshooting

### QEMU "exec format error"

**Symptom:** Running an ARM binary prints `exec format error` or the shell reports the binary is in an unknown format.

**Cause:** The binfmt handler for ARM was not registered, so the kernel does not know to invoke QEMU for ARM ELF files.

**Fix:** Run the binfmt registration manually:
```bash
docker run --privileged --rm tonistiigi/binfmt --install arm,aarch64
```
Then retry. If Docker is not yet available, wait for the Codespace to fully initialize and run the post-create script output to confirm the step completed.

---

### Slow Emulation

**Symptom:** QEMU-emulated processes run noticeably slower than expected, or `rpi-shell` feels sluggish.

**Cause:** QEMU user-mode emulation translates every ARM instruction to x86-64 at runtime. This is inherent to software emulation and is most noticeable with CPU-bound workloads.

**Workaround:** Use the 8-core Codespace size (see Recommended Codespace Size). Offload heavy computation to native x86-64 compilation for development cycles and only emulate for final integration testing. Docker-based ARM shells (`rpi-shell`) have higher overhead than running binaries directly via `rpi-run`.

---

### GPIO "Permission Denied"

**Symptom:** Python raises `RuntimeError: No access to /dev/mem` or `PermissionError` when importing `RPi.GPIO`.

**Cause:** The real `RPi.GPIO` library tries to open `/dev/mem` to memory-map GPIO registers. This device does not exist in the container.

**Fix:** Ensure you are using the mock stubs installed during setup. Check that `RPi.GPIO-stubs` is importable:
```bash
python3 -c "import RPi.GPIO; print(RPi.GPIO.__file__)"
```
If the real library was installed (e.g., via a `requirements.txt`), uninstall it and reinstall the stubs:
```bash
pip uninstall RPi.GPIO -y
pip install RPi.GPIO-stubs
```

---

### Docker Buildx Failures

**Symptom:** `rpi-docker-build` fails with `error: multiple platforms feature is currently not supported for docker driver`.

**Cause:** The active buildx builder is the default `docker` driver, which does not support multi-platform builds. The `rpi-builder` instance may not have been created.

**Fix:**
```bash
docker buildx create --name rpi-builder --use
docker buildx inspect --bootstrap rpi-builder
```
Then re-run `rpi-docker-build`.

---

### Multi-Node Network Issues

**Symptom:** `rpi-net-up` fails or containers in the network cannot reach each other.

**Cause:** Common causes are a missing or malformed `network/docker-compose.yml`, the `rpi-builder` buildx instance not being set as the active builder, or port conflicts on 8080.

**Fix:**
- Verify the compose file exists at `network/docker-compose.yml`.
- Confirm buildx is active: `docker buildx ls` should show `rpi-builder` with an asterisk.
- Check for port conflicts: `ss -tlnp | grep 8080`.
- Inspect individual service logs: `rpi-net-logs` or `docker compose -f network/docker-compose.yml logs <service-name>`.

---

## Recommended Codespace Size

| Use Case                                      | Cores | RAM   |
|-----------------------------------------------|-------|-------|
| Minimum (single binary, light Python work)    | 4     | 8 GB  |
| Recommended (CMake builds, Docker images)     | 8     | 16 GB |
| Heavy (multi-node network + concurrent builds)| 8+    | 16 GB+|

The 2-core Codespace size is not recommended. CMake configuration, Docker buildx, and QEMU emulation each impose meaningful overhead, and running them concurrently on 2 cores produces noticeably degraded responsiveness.

---

## Limitations

| Limitation                                | Details                                                  | Workaround                                                                          |
|-------------------------------------------|----------------------------------------------------------|-------------------------------------------------------------------------------------|
| No real hardware access                   | `/dev/mem`, `/dev/gpiomem`, I2C, SPI, UART not available | Use mock GPIO stubs; test hardware-dependent paths on a physical Pi                |
| QEMU is not cycle-accurate                | Timing-sensitive code may behave differently             | Profile on real hardware; avoid `time.sleep`-based timing in emulation             |
| QEMU performance                          | Emulated code runs 5-20x slower than native ARM         | Use emulation for correctness testing only; rely on cross-compilation for speed    |
| No GPU / VideoCore                        | OpenGL ES, camera, hardware video encode not available   | These require a real Pi; no practical workaround in the container                  |
| Docker-in-Docker overhead                 | Nested Docker has extra layer overhead for buildx        | Use a Codespace with at least 8 cores and 16 GB RAM                                |
| SSH deploy requires network access to Pi  | `rpi-deploy` requires the Pi to be reachable from Codespace | Use VS Code port forwarding or a VPN/tunnel if the Pi is on a private network   |
| AArch64 sysroot is minimal                | `/opt/rpi-sysroot` is empty by default                  | Populate it by copying libraries from a real Pi or a Pi OS Docker image            |
