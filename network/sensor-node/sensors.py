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
        temp = self._base + \
            self._sine(period_s=120, amplitude=3.0) + self._noise(0.05)
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
        temp = 35.0 + self._sine(period_s=60,
                                 amplitude=0.5) + self._noise(0.02)

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
# DS18B20 – 1-Wire waterproof temperature sensor
# ---------------------------------------------------------------------------


class DS18B20Simulator(SensorSimulator):
    """
    Simulates a Maxim DS18B20 1-Wire temperature sensor.

    Nominal range: -55 °C to +125 °C; resolution 0.0625 °C (12-bit).
    Default idle temperature: 20 °C with a ±4 °C slow drift.
    """

    def __init__(self, base_temp: float = 20.0) -> None:
        self._base = base_temp

    def read(self) -> Dict[str, Any]:
        temp = self._base + \
            self._sine(period_s=180, amplitude=4.0) + self._noise(0.08)
        temp = round(temp / 0.0625) * 0.0625
        return {
            "temperature_c": round(temp, 4),
            "sensor": "DS18B20",
        }


# ---------------------------------------------------------------------------
# SHT31 – precision temperature + humidity sensor
# ---------------------------------------------------------------------------


class SHT31Simulator(SensorSimulator):
    """
    Simulates a Sensirion SHT31-D precision temperature/humidity sensor.

    Outputs temperature (°C) and relative humidity (%RH).
    """

    def __init__(
        self,
        base_temp: float = 21.0,
        base_humidity: float = 60.0,
    ) -> None:
        self._base_temp = base_temp
        self._base_hum = base_humidity

    def read(self) -> Dict[str, Any]:
        temp = (
            self._base_temp
            + self._sine(period_s=100, amplitude=2.0)
            + self._noise(0.05)
        )
        humidity = (
            self._base_hum
            + self._sine(period_s=160, amplitude=6.0)
            + self._noise(0.25)
        )
        humidity = max(0.0, min(100.0, humidity))
        return {
            "temperature_c": round(temp, 4),
            "humidity_pct": round(humidity, 4),
            "sensor": "SHT31",
        }


# ---------------------------------------------------------------------------
# HC-SR04 – ultrasonic distance sensor
# ---------------------------------------------------------------------------


class HC_SR04Simulator(SensorSimulator):
    """
    Simulates an HC-SR04 ultrasonic ranging module.

    Effective range: 2–400 cm; output in centimetres.
    Default simulates an object oscillating between 50 and 200 cm.
    """

    def __init__(self, base_distance: float = 120.0) -> None:
        self._base = base_distance

    def read(self) -> Dict[str, Any]:
        dist = (
            self._base
            + self._sine(period_s=30, amplitude=70.0)
            + self._noise(2.0)
        )
        dist = max(2.0, min(400.0, dist))
        return {
            "distance_cm": round(dist, 2),
            "sensor": "HC-SR04",
        }


# ---------------------------------------------------------------------------
# INA219 – current / power monitor
# ---------------------------------------------------------------------------


class INA219Simulator(SensorSimulator):
    """
    Simulates a Texas Instruments INA219 high-side current/power monitor.

    Outputs current (mA) and power (mW) assuming a fixed 5 V rail.
    """

    RAIL_VOLTAGE: float = 5.0  # volts

    def __init__(self, base_current_ma: float = 250.0) -> None:
        self._base = base_current_ma

    def read(self) -> Dict[str, Any]:
        current = (
            self._base
            + self._sine(period_s=45, amplitude=150.0)
            + self._noise(5.0)
        )
        current = max(0.0, current)
        power = current * self.RAIL_VOLTAGE  # mA × V = mW
        return {
            "current_ma": round(current, 2),
            "power_mw": round(power, 2),
            "sensor": "INA219",
        }


# ---------------------------------------------------------------------------
# MQ-2 – gas / smoke sensor
# ---------------------------------------------------------------------------


class MQ2Simulator(SensorSimulator):
    """
    Simulates an MQ-2 gas/smoke sensor.

    Output: concentration in parts-per-million (ppm).
    Baseline ~50 ppm with random spike events to simulate gas leaks.
    """

    def __init__(self, base_ppm: float = 50.0) -> None:
        self._base = base_ppm

    def read(self) -> Dict[str, Any]:
        ppm = (
            self._base
            + self._sine(period_s=240, amplitude=30.0)
            + self._noise(3.0)
        )
        # Random spike: ~0.5 % chance per read (≈ every 200 s at 1 Hz)
        if random.random() < 0.005:
            ppm += random.uniform(450, 850)
        ppm = max(0.0, ppm)
        return {
            "gas_ppm": round(ppm, 2),
            "sensor": "MQ-2",
        }


# ---------------------------------------------------------------------------
# Composite: TMP102 + BME280 + DS18B20 + SHT31
# ---------------------------------------------------------------------------


class TMP102BME280DS18B20SHT31Simulator(SensorSimulator):
    """All four temperature/environment sensors on one I2C/1-Wire bus."""

    def __init__(self) -> None:
        self._tmp = TMP102Simulator()
        self._bme = BME280Simulator()
        self._ds = DS18B20Simulator()
        self._sht = SHT31Simulator()

    def read(self) -> Dict[str, Any]:
        tmp_data = self._tmp.read()
        bme_data = self._bme.read()
        ds_data = self._ds.read()
        sht_data = self._sht.read()
        return {
            "tmp102_temperature_c": tmp_data["temperature_c"],
            "bme280_temperature_c": bme_data["temperature_c"],
            "humidity_pct": bme_data["humidity_pct"],
            "pressure_hpa": bme_data["pressure_hpa"],
            "ds18b20_temperature_c": ds_data["temperature_c"],
            "sht31_temperature_c": sht_data["temperature_c"],
            "sht31_humidity_pct": sht_data["humidity_pct"],
            "sensor": "TMP102+BME280+DS18B20+SHT31",
        }


# ---------------------------------------------------------------------------
# Composite: BH1750 + MQ-2
# ---------------------------------------------------------------------------


class BH1750MQ2Simulator(SensorSimulator):
    """Ambient light plus gas/smoke sensing on one node."""

    def __init__(self) -> None:
        self._bh = BH1750Simulator()
        self._mq = MQ2Simulator()

    def read(self) -> Dict[str, Any]:
        bh_data = self._bh.read()
        mq_data = self._mq.read()
        return {
            "illuminance_lux": bh_data["illuminance_lux"],
            "mq2_gas_ppm": mq_data["gas_ppm"],
            "sensor": "BH1750+MQ2",
        }


# ---------------------------------------------------------------------------
# Composite: MPU6050 + HC-SR04 + INA219
# ---------------------------------------------------------------------------


class MPU6050HCSR04INA219Simulator(SensorSimulator):
    """IMU plus distance and power monitoring on one node."""

    def __init__(self) -> None:
        self._mpu = MPU6050Simulator()
        self._hc = HC_SR04Simulator()
        self._ina = INA219Simulator()

    def read(self) -> Dict[str, Any]:
        mpu_data = self._mpu.read()
        hc_data = self._hc.read()
        ina_data = self._ina.read()
        data = {
            "accel_x_g": mpu_data["accel_x_g"],
            "accel_y_g": mpu_data["accel_y_g"],
            "accel_z_g": mpu_data["accel_z_g"],
            "gyro_x_dps": mpu_data["gyro_x_dps"],
            "gyro_y_dps": mpu_data["gyro_y_dps"],
            "gyro_z_dps": mpu_data["gyro_z_dps"],
            "temperature_c": mpu_data["temperature_c"],
            "hc_sr04_distance_cm": hc_data["distance_cm"],
            "ina219_current_ma": ina_data["current_ma"],
            "ina219_power_mw": ina_data["power_mw"],
            "sensor": "MPU6050+HC-SR04+INA219",
        }
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
    "ds18b20": DS18B20Simulator,
    "sht31": SHT31Simulator,
    "hc-sr04": HC_SR04Simulator,
    "ina219": INA219Simulator,
    "mq2": MQ2Simulator,
    "tmp102+bme280+ds18b20+sht31": TMP102BME280DS18B20SHT31Simulator,
    "bh1750+mq2": BH1750MQ2Simulator,
    "mpu6050+hc-sr04+ina219": MPU6050HCSR04INA219Simulator,
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
