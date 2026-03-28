"""
sensors.py – Pluggable sensor simulation for the RPi sensor node.

Each simulator mimics the output of a real I2C sensor, adding a slow
sinusoidal drift plus Gaussian noise so that the gateway receives a
realistic, time-varying signal.

Usage
-----
    from sensors import create_sensor

    sensor = create_sensor("BME280")   # or "TMP102+BME280", "BH1750", "MPU6050"
    readings = sensor.read()           # returns a plain dict
"""

from __future__ import annotations

import math
import random
import time
from typing import Dict, Any


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class SensorSimulator:
    """
    Abstract base for all sensor simulators.

    Sub-classes must implement :meth:`read`.  The helpers
    :meth:`_sine` and :meth:`_noise` are provided for convenience.
    """

    def read(self) -> Dict[str, Any]:
        """Return a dict of sensor readings.  Must be overridden."""
        raise NotImplementedError

    # -- private helpers -----------------------------------------------------

    @staticmethod
    def _sine(
        period_s: float = 60.0,
        amplitude: float = 1.0,
        offset: float = 0.0,
    ) -> float:
        """Return a sine value that completes one cycle every *period_s* seconds."""
        t = time.time()
        return offset + amplitude * math.sin(2 * math.pi * t / period_s)

    @staticmethod
    def _noise(sigma: float = 0.1) -> float:
        """Return zero-mean Gaussian noise with standard deviation *sigma*."""
        return random.gauss(0.0, sigma)


# ---------------------------------------------------------------------------
# TMP102 – high-accuracy temperature sensor
# ---------------------------------------------------------------------------


class TMP102Simulator(SensorSimulator):
    """
    Simulates a Texas Instruments TMP102 temperature sensor.

    Nominal range: -40 °C to +125 °C; resolution 0.0625 °C.
    Default idle temperature: 22 °C with a ±3 °C slow drift.
    """

    def __init__(self, base_temp: float = 22.0) -> None:
        self._base = base_temp

    def read(self) -> Dict[str, Any]:
        temp = self._base + self._sine(period_s=120, amplitude=3.0) + self._noise(0.05)
        # Quantise to 0.0625 °C steps (12-bit ADC)
        temp = round(temp / 0.0625) * 0.0625
        return {
            "temperature_c": round(temp, 4),
            "sensor": "TMP102",
        }


# ---------------------------------------------------------------------------
# BME280 – temperature, humidity, and pressure
# ---------------------------------------------------------------------------


class BME280Simulator(SensorSimulator):
    """
    Simulates a Bosch BME280 environmental sensor.

    Outputs temperature (°C), relative humidity (%RH), and barometric
    pressure (hPa).
    """

    def __init__(
        self,
        base_temp: float = 23.0,
        base_humidity: float = 55.0,
        base_pressure: float = 1013.25,
    ) -> None:
        self._base_temp = base_temp
        self._base_hum = base_humidity
        self._base_pres = base_pressure

    def read(self) -> Dict[str, Any]:
        temp = (
            self._base_temp
            + self._sine(period_s=90, amplitude=2.5)
            + self._noise(0.08)
        )
        humidity = (
            self._base_hum
            + self._sine(period_s=150, amplitude=5.0, offset=0)
            + self._noise(0.3)
        )
        humidity = max(0.0, min(100.0, humidity))
        pressure = (
            self._base_pres
            + self._sine(period_s=300, amplitude=2.0)
            + self._noise(0.1)
        )
        return {
            "temperature_c": round(temp, 4),
            "humidity_pct": round(humidity, 4),
            "pressure_hpa": round(pressure, 4),
            "sensor": "BME280",
        }


# ---------------------------------------------------------------------------
# BH1750 – ambient light sensor
# ---------------------------------------------------------------------------


class BH1750Simulator(SensorSimulator):
    """
    Simulates a ROHM BH1750FVI ambient-light sensor.

    Output: illuminance in lux (1–65535 lx range).
    Simulates a slow day/night sine cycle plus random cloud flicker.
    """

    def __init__(self, base_lux: float = 400.0) -> None:
        self._base = base_lux

    def read(self) -> Dict[str, Any]:
        lux = (
            self._base
            + self._sine(period_s=200, amplitude=300.0)
            + self._noise(10.0)
        )
        lux = max(1.0, lux)
        return {
            "illuminance_lux": round(lux, 2),
            "sensor": "BH1750",
        }


# ---------------------------------------------------------------------------
# MPU6050 – 6-axis IMU (accelerometer + gyroscope)
# ---------------------------------------------------------------------------


class MPU6050Simulator(SensorSimulator):
    """
    Simulates an InvenSense MPU-6050 6-DoF IMU.

    Outputs:
    - accel_x/y/z in units of *g* (gravity)
    - gyro_x/y/z in degrees per second (°/s)
    - temperature_c (on-die temperature)
    """

    def read(self) -> Dict[str, Any]:
        # At rest, Z-axis acceleration should be ~1 g (gravity).
        ax = self._sine(period_s=7, amplitude=0.02) + self._noise(0.005)
        ay = self._sine(period_s=11, amplitude=0.02) + self._noise(0.005)
        az = 1.0 + self._sine(period_s=13, amplitude=0.01) + self._noise(0.003)

        gx = self._sine(period_s=5, amplitude=0.5) + self._noise(0.02)
        gy = self._sine(period_s=8, amplitude=0.5) + self._noise(0.02)
        gz = self._sine(period_s=12, amplitude=0.3) + self._noise(0.01)

        # On-die temperature runs warm (offset ~35 °C)
        temp = 35.0 + self._sine(period_s=60, amplitude=0.5) + self._noise(0.02)

        return {
            "accel_x_g": round(ax, 6),
            "accel_y_g": round(ay, 6),
            "accel_z_g": round(az, 6),
            "gyro_x_dps": round(gx, 4),
            "gyro_y_dps": round(gy, 4),
            "gyro_z_dps": round(gz, 4),
            "temperature_c": round(temp, 4),
            "sensor": "MPU6050",
        }


# ---------------------------------------------------------------------------
# Composite: TMP102 + BME280 on the same node
# ---------------------------------------------------------------------------


class TMP102BME280Simulator(SensorSimulator):
    """
    Both sensors mounted on the same I2C bus.

    Merges the readings of :class:`TMP102Simulator` and
    :class:`BME280Simulator` into a single dict.
    """

    def __init__(self) -> None:
        self._tmp = TMP102Simulator()
        self._bme = BME280Simulator()

    def read(self) -> Dict[str, Any]:
        data = {}
        tmp_data = self._tmp.read()
        bme_data = self._bme.read()
        # Prefix keys to avoid collision on temperature
        data["tmp102_temperature_c"] = tmp_data["temperature_c"]
        data["bme280_temperature_c"] = bme_data["temperature_c"]
        data["humidity_pct"] = bme_data["humidity_pct"]
        data["pressure_hpa"] = bme_data["pressure_hpa"]
        data["sensor"] = "TMP102+BME280"
        return data


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, type] = {
    "tmp102": TMP102Simulator,
    "bme280": BME280Simulator,
    "bh1750": BH1750Simulator,
    "mpu6050": MPU6050Simulator,
    "tmp102+bme280": TMP102BME280Simulator,
}


def create_sensor(profile: str) -> SensorSimulator:
    """
    Instantiate the simulator for the given *profile* string.

    Profile names are case-insensitive, e.g. ``"BME280"``, ``"bh1750"``,
    ``"TMP102+BME280"``.

    Raises
    ------
    ValueError
        If *profile* is not recognised.
    """
    key = profile.strip().lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        valid = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown sensor profile {profile!r}.  "
            f"Valid choices: {valid}"
        )
    return cls()
