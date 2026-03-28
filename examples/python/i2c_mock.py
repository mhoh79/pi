"""
i2c_mock.py - Drop-in I2C mock for Raspberry Pi sensor development.

``get_i2c_bus(bus_number)`` is the single entry point.  It returns a real
``smbus2.SMBus`` when the corresponding ``/dev/i2c-<n>`` device node exists,
and a ``MockI2CBus`` otherwise.

MockI2CBus conforms to the I2CBus Protocol used by smbus2 so it can be used
for type-checking and as a direct substitute in any code that accepts an
smbus2-compatible bus object.

Simulated sensor profiles
--------------------------
Address  Device   Values
0x48     TMP102   temperature  ~22 °C  (slow sine drift ± 3 °C, Gaussian noise)
0x76     BME280   temperature, humidity, pressure
0x23     BH1750   illuminance (lux)
0x68     MPU6050  3-axis accelerometer (accel_x, accel_y, accel_z)
"""

from __future__ import annotations

import math
import os
import random
import time
from typing import List, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# I2CBus Protocol (mirrors the interface exposed by smbus2.SMBus)
# ---------------------------------------------------------------------------

@runtime_checkable
class I2CBus(Protocol):
    """Structural protocol for an I2C bus handle."""

    def read_byte_data(self, i2c_address: int, register: int) -> int:
        ...

    def write_byte_data(self, i2c_address: int, register: int, value: int) -> None:
        ...

    def read_i2c_block_data(
        self, i2c_address: int, register: int, length: int
    ) -> List[int]:
        ...

    def close(self) -> None:
        ...


# ---------------------------------------------------------------------------
# Sensor simulation helpers
# ---------------------------------------------------------------------------

def _sine_drift(period_s: float = 120.0, amplitude: float = 1.0) -> float:
    """Return a slow sinusoidal drift value centred on zero."""
    t = time.monotonic()
    return amplitude * math.sin(2.0 * math.pi * t / period_s)


def _noisy(base: float, noise_sigma: float = 0.05) -> float:
    """Add Gaussian noise to *base*."""
    return base + random.gauss(0.0, noise_sigma)


# Per-address simulation functions.
# Each returns a dict of human-readable values; raw encoding happens in the
# read helpers below.

def _sim_tmp102() -> dict:
    temp = _noisy(22.0 + _sine_drift(period_s=120.0, amplitude=3.0), noise_sigma=0.1)
    return {"temperature_c": round(temp, 3)}


def _sim_bme280() -> dict:
    temp     = _noisy(22.0   + _sine_drift(period_s=90.0,  amplitude=2.0), noise_sigma=0.08)
    humidity = _noisy(45.0   + _sine_drift(period_s=180.0, amplitude=5.0), noise_sigma=0.5)
    pressure = _noisy(1013.25 + _sine_drift(period_s=300.0, amplitude=2.0), noise_sigma=0.1)
    return {
        "temperature_c": round(temp, 3),
        "humidity_pct":  round(max(0.0, min(100.0, humidity)), 3),
        "pressure_hpa":  round(pressure, 3),
    }


def _sim_bh1750() -> dict:
    lux = _noisy(300.0 + _sine_drift(period_s=60.0, amplitude=50.0), noise_sigma=5.0)
    return {"illuminance_lux": round(max(0.0, lux), 2)}


def _sim_mpu6050() -> dict:
    ax = _noisy(0.0 + _sine_drift(period_s=45.0, amplitude=0.02), noise_sigma=0.005)
    ay = _noisy(0.0 + _sine_drift(period_s=55.0, amplitude=0.02), noise_sigma=0.005)
    az = _noisy(1.0 + _sine_drift(period_s=65.0, amplitude=0.01), noise_sigma=0.005)
    return {
        "accel_x_g": round(ax, 5),
        "accel_y_g": round(ay, 5),
        "accel_z_g": round(az, 5),
    }


# Map I2C address -> (simulator_fn, description)
_SENSOR_PROFILES: dict[int, tuple] = {
    0x48: (_sim_tmp102,  "TMP102 temperature sensor"),
    0x76: (_sim_bme280,  "BME280 temp/humidity/pressure sensor"),
    0x23: (_sim_bh1750,  "BH1750 light sensor"),
    0x68: (_sim_mpu6050, "MPU6050 6-axis IMU"),
}


def _pack_float_to_bytes(value: float, n_bytes: int = 2) -> List[int]:
    """Encode *value* as a big-endian signed fixed-point integer list.

    The value is scaled by 100 before truncation so callers can recover
    two decimal places by dividing the raw integer by 100.
    """
    raw = int(round(value * 100.0))
    # Clamp to the representable range for n_bytes signed integer.
    max_val = (1 << (8 * n_bytes - 1)) - 1
    min_val = -(1 << (8 * n_bytes - 1))
    raw = max(min_val, min(max_val, raw))
    # Two's-complement encoding, big-endian.
    result: List[int] = []
    for _ in range(n_bytes):
        result.insert(0, raw & 0xFF)
        raw >>= 8
    return result


def _get_raw_byte(address: int, register: int) -> int:
    """Return a single simulated byte for *address* / *register*."""
    if address not in _SENSOR_PROFILES:
        return 0xFF

    sim_fn, _ = _SENSOR_PROFILES[address]
    values = sim_fn()
    first_value = next(iter(values.values()), 0.0)
    packed = _pack_float_to_bytes(first_value, n_bytes=2)
    # Register 0 -> high byte, register 1 -> low byte, others -> 0.
    if register == 0:
        return packed[0]
    if register == 1:
        return packed[1]
    return 0x00


def _get_raw_block(address: int, register: int, length: int) -> List[int]:
    """Return a block of simulated bytes for *address* starting at *register*."""
    if address not in _SENSOR_PROFILES:
        return [0xFF] * length

    sim_fn, _ = _SENSOR_PROFILES[address]
    values = sim_fn()

    # Pack every value into 2-byte big-endian words and concatenate.
    payload: List[int] = []
    for v in values.values():
        payload.extend(_pack_float_to_bytes(v, n_bytes=2))

    # Pad or truncate to the requested length.
    while len(payload) < length:
        payload.append(0x00)
    return payload[:length]


# ---------------------------------------------------------------------------
# MockI2CBus
# ---------------------------------------------------------------------------

class MockI2CBus:
    """Simulated I2C bus that conforms to the I2CBus Protocol.

    All reads return deterministic-but-noisy sensor values so upstream
    code that parses raw register data can be exercised without hardware.
    """

    def __init__(self, bus_number: int) -> None:
        self._bus_number = bus_number
        self._closed = False
        self._write_log: list[tuple[int, int, int]] = []

    # ------------------------------------------------------------------
    # I2CBus Protocol implementation
    # ------------------------------------------------------------------

    def read_byte_data(self, i2c_address: int, register: int) -> int:
        self._check_open()
        return _get_raw_byte(i2c_address, register)

    def write_byte_data(
        self, i2c_address: int, register: int, value: int
    ) -> None:
        self._check_open()
        self._write_log.append((i2c_address, register, value))

    def read_i2c_block_data(
        self, i2c_address: int, register: int, length: int
    ) -> List[int]:
        self._check_open()
        return _get_raw_block(i2c_address, register, length)

    def close(self) -> None:
        self._closed = True

    # ------------------------------------------------------------------
    # Extras
    # ------------------------------------------------------------------

    @property
    def bus_number(self) -> int:
        return self._bus_number

    @property
    def write_log(self) -> list[tuple[int, int, int]]:
        """List of (address, register, value) tuples from write_byte_data calls."""
        return list(self._write_log)

    def sensor_info(self, address: int) -> str:
        """Return a human-readable description for a known sensor address."""
        entry = _SENSOR_PROFILES.get(address)
        if entry is None:
            return f"Unknown device at 0x{address:02X}"
        _, desc = entry
        return f"0x{address:02X}: {desc}"

    def _check_open(self) -> None:
        if self._closed:
            raise IOError("I2C bus is already closed.")

    def __repr__(self) -> str:
        state = "closed" if self._closed else "open"
        return f"MockI2CBus(bus={self._bus_number}, {state})"


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def get_i2c_bus(bus_number: int = 1) -> I2CBus:
    """Return a real or mock I2C bus for *bus_number*.

    If ``/dev/i2c-<bus_number>`` exists the function tries to import and
    return an ``smbus2.SMBus``.  If the device node is absent (devcontainer,
    CI, macOS, etc.) a ``MockI2CBus`` is returned instead.

    The return type is annotated as ``I2CBus`` (the protocol) so callers
    can accept either implementation transparently.
    """
    device_path = f"/dev/i2c-{bus_number}"
    if os.path.exists(device_path):
        try:
            import smbus2  # type: ignore[import]
            return smbus2.SMBus(bus_number)
        except ImportError:
            pass  # fall through to mock

    return MockI2CBus(bus_number)


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bus = get_i2c_bus(1)
    print(f"Bus type           : {type(bus).__name__}")
    print(f"Is I2CBus protocol : {isinstance(bus, I2CBus)}")
    print()

    for addr in sorted(_SENSOR_PROFILES):
        block = bus.read_i2c_block_data(addr, 0, 8)
        sim_fn, desc = _SENSOR_PROFILES[addr]
        values = sim_fn()
        print(f"  {desc}")
        print(f"    raw block : {[f'0x{b:02X}' for b in block]}")
        print(f"    decoded   : {values}")
        print()

    bus.close()
