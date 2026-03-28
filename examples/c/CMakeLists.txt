cmake_minimum_required(VERSION 3.16)
project(rpi-examples C)

# Require at least C11 for modern fixed-width integer types and _Static_assert.
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_executable(blink blink.c)

# Enable a sensible set of warnings so the example is easy to audit.
target_compile_options(blink PRIVATE
    -Wall
    -Wextra
    -Wpedantic
)
