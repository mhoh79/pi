# CMake toolchain file for cross-compiling to Raspberry Pi AArch64 (64-bit)
# Target: Raspberry Pi 3 / 4 / 5 / Zero 2 W running 64-bit Raspberry Pi OS
#
# Usage (configure):
#   cmake -DCMAKE_TOOLCHAIN_FILE=/opt/toolchain/rpi-aarch64.cmake \
#         -DCMAKE_BUILD_TYPE=Release \
#         -S . -B build
#
# Shorthand alias inside the devcontainer:
#   rpi-cmake64 -DCMAKE_BUILD_TYPE=Release -S . -B build

# ── Target system identity ────────────────────────────────────────────────────
set(CMAKE_SYSTEM_NAME    Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# ── Cross-compiler executables ────────────────────────────────────────────────
# Full paths prevent CMake from accidentally resolving to the host compiler
# during the ABI/feature detection phase.
set(CMAKE_C_COMPILER   /usr/bin/aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER /usr/bin/aarch64-linux-gnu-g++)
set(CMAKE_AR           /usr/bin/aarch64-linux-gnu-ar     CACHE FILEPATH "Archiver")
set(CMAKE_RANLIB       /usr/bin/aarch64-linux-gnu-ranlib CACHE FILEPATH "Ranlib")
set(CMAKE_STRIP        /usr/bin/aarch64-linux-gnu-strip  CACHE FILEPATH "Strip")

# ── Sysroot / search prefixes ─────────────────────────────────────────────────
# /usr/aarch64-linux-gnu  — headers and libs shipped by the Debian cross-
#                           compiler package (always present in this image).
# /opt/rpi-sysroot        — optional user-supplied Pi rootfs, populated by
#                           rsync'ing /usr, /lib, /etc from a real device.
set(CMAKE_FIND_ROOT_PATH
    /usr/aarch64-linux-gnu
    /opt/rpi-sysroot
)

# ── Search mode ───────────────────────────────────────────────────────────────
# Programs (cmake, python, …) come from the host — never search the sysroot.
# Libraries, headers, and CMake packages must come from the AArch64 sysroot only.
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
