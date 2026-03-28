# CMake toolchain file for cross-compiling to Raspberry Pi ARMv7 (32-bit)
# Target: Raspberry Pi 2 / 3 / 4 / Zero 2 W running 32-bit Raspberry Pi OS
#
# Usage (configure):
#   cmake -DCMAKE_TOOLCHAIN_FILE=/opt/toolchain/rpi-armv7.cmake \
#         -DCMAKE_BUILD_TYPE=Release \
#         -S . -B build
#
# Shorthand alias inside the devcontainer:
#   rpi-cmake -DCMAKE_BUILD_TYPE=Release -S . -B build

# ── Target system identity ────────────────────────────────────────────────────
set(CMAKE_SYSTEM_NAME    Linux)
set(CMAKE_SYSTEM_PROCESSOR armv7l)

# ── Cross-compiler executables ────────────────────────────────────────────────
# Full paths prevent CMake from accidentally resolving to the host compiler
# during the ABI/feature detection phase.
set(CMAKE_C_COMPILER   /usr/bin/arm-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER /usr/bin/arm-linux-gnueabihf-g++)
set(CMAKE_AR           /usr/bin/arm-linux-gnueabihf-ar     CACHE FILEPATH "Archiver")
set(CMAKE_RANLIB       /usr/bin/arm-linux-gnueabihf-ranlib CACHE FILEPATH "Ranlib")
set(CMAKE_STRIP        /usr/bin/arm-linux-gnueabihf-strip  CACHE FILEPATH "Strip")

# ── Sysroot / search prefixes ─────────────────────────────────────────────────
# /usr/arm-linux-gnueabihf  — headers and libs shipped by the Debian cross-
#                             compiler package (always present in this image).
# /opt/rpi-sysroot          — optional user-supplied Pi rootfs, populated by
#                             rsync'ing /usr, /lib, /etc from a real device.
set(CMAKE_FIND_ROOT_PATH
    /usr/arm-linux-gnueabihf
    /opt/rpi-sysroot
)

# ── Search mode ───────────────────────────────────────────────────────────────
# Programs (cmake, python, …) come from the host — never search the sysroot.
# Libraries, headers, and CMake packages must come from the ARM sysroot only.
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
