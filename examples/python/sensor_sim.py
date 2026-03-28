"""
sensor_sim.py - Async multi-sensor I2C poller using the mock I2C bus.

Reads TMP102, BME280, and BH1750 concurrently at independent rates and
writes all collected readings to ``sensor_log.json`` on exit.

Polling rates
-------------
    TMP102   1.00 Hz  (every 1.0 s)
    BME280   0.50 Hz  (every 2.0 s)
    BH1750   0.67 Hz  (every 1.5 s)

Usage
-----
    python sensor_sim.py           # run until Ctrl-C / SIGTERM
    python sensor_sim.py --secs 10 # run for 10 seconds then exit cleanly
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------------------
# Local import - works whether this file is run directly or as a module.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from i2c_mock import get_i2c_bus, I2CBus, _SENSOR_PROFILES  # noqa: E402


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SensorReading:
    """A single timestamped snapshot from one sensor."""
    sensor_name: str
    address: int
    timestamp: float                  # UNIX epoch seconds
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["address_hex"] = f"0x{self.address:02X}"
        return d


# ---------------------------------------------------------------------------
# Decode helpers  (raw block -> physical units)
# The mock encodes each float as a 2-byte big-endian signed integer scaled
# by 100.  Reverse that here so the poller works against the mock output.
# ---------------------------------------------------------------------------

def _decode_s16(high: int, low: int) -> float:
    """Reconstruct a signed 16-bit value encoded by _pack_float_to_bytes."""
    raw = (high << 8) | low
    if raw >= 0x8000:
        raw -= 0x10000
    return raw / 100.0


def _decode_block_pairs(block: list[int], n_fields: int) -> list[float]:
    """Decode *n_fields* consecutive 2-byte big-endian fixed-point values."""
    values = []
    for i in range(n_fields):
        high = block[2 * i]     if 2 * i     < len(block) else 0
        low  = block[2 * i + 1] if 2 * i + 1 < len(block) else 0
        values.append(_decode_s16(high, low))
    return values


# ---------------------------------------------------------------------------
# Reader classes
# ---------------------------------------------------------------------------

class TMP102Reader:
    ADDRESS    = 0x48
    NAME       = "TMP102"
    INTERVAL_S = 1.0   # 1 Hz

    def __init__(self, bus: I2CBus) -> None:
        self._bus = bus

    def read(self) -> SensorReading:
        block = self._bus.read_i2c_block_data(self.ADDRESS, 0, 2)
        (temp,) = _decode_block_pairs(block, 1)
        return SensorReading(
            sensor_name=self.NAME,
            address=self.ADDRESS,
            timestamp=time.time(),
            values={"temperature_c": temp},
        )


class BME280Reader:
    ADDRESS    = 0x76
    NAME       = "BME280"
    INTERVAL_S = 2.0   # 0.5 Hz

    def __init__(self, bus: I2CBus) -> None:
        self._bus = bus

    def read(self) -> SensorReading:
        block = self._bus.read_i2c_block_data(self.ADDRESS, 0, 6)
        temp, humidity, pressure = _decode_block_pairs(block, 3)
        return SensorReading(
            sensor_name=self.NAME,
            address=self.ADDRESS,
            timestamp=time.time(),
            values={
                "temperature_c": temp,
                "humidity_pct":  humidity,
                "pressure_hpa":  pressure,
            },
        )


class BH1750Reader:
    ADDRESS    = 0x23
    NAME       = "BH1750"
    INTERVAL_S = 1.5   # ~0.67 Hz

    def __init__(self, bus: I2CBus) -> None:
        self._bus = bus

    def read(self) -> SensorReading:
        block = self._bus.read_i2c_block_data(self.ADDRESS, 0, 2)
        (lux,) = _decode_block_pairs(block, 1)
        return SensorReading(
            sensor_name=self.NAME,
            address=self.ADDRESS,
            timestamp=time.time(),
            values={"illuminance_lux": max(0.0, lux)},
        )


# ---------------------------------------------------------------------------
# Async poller
# ---------------------------------------------------------------------------

_all_readings: list[SensorReading] = []


async def _poll_sensor(reader, stop: asyncio.Event) -> None:
    """Continuously read *reader* at its configured interval until *stop*."""
    while not stop.is_set():
        try:
            reading = reader.read()
            _all_readings.append(reading)
            vals = "  ".join(f"{k}={v}" for k, v in reading.values.items())
            print(f"[{time.strftime('%H:%M:%S')}] {reading.sensor_name:<8} {vals}")
        except Exception as exc:
            print(
                f"[{time.strftime('%H:%M:%S')}] {reader.NAME} read error: {exc}",
                file=sys.stderr,
            )
        try:
            await asyncio.wait_for(
                asyncio.shield(stop.wait()),
                timeout=reader.INTERVAL_S,
            )
        except asyncio.TimeoutError:
            pass   # normal path: interval elapsed, loop again


def _write_log(path: str) -> None:
    data = [r.to_dict() for r in _all_readings]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    print(f"\nWrote {len(data)} readings to {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(run_secs: float | None) -> None:
    shutdown_event = asyncio.Event()

    bus = get_i2c_bus(1)
    readers = [TMP102Reader(bus), BME280Reader(bus), BH1750Reader(bus)]

    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        print("\nShutdown signal received.")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows does not support add_signal_handler
            pass

    print(f"Starting sensor poller  (bus={type(bus).__name__})")
    print(f"Sensors : {', '.join(r.NAME for r in readers)}")
    if run_secs:
        print(f"Will run for {run_secs} seconds.")
    else:
        print("Press Ctrl-C to stop.")
    print()

    tasks = [
        asyncio.create_task(_poll_sensor(r, shutdown_event)) for r in readers
    ]

    if run_secs is not None:
        loop.call_later(run_secs, shutdown_event.set)

    await asyncio.gather(*tasks)
    bus.close()
    _write_log("sensor_log.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Async multi-sensor I2C poller")
    parser.add_argument(
        "--secs",
        type=float,
        default=None,
        metavar="N",
        help="Run for N seconds then exit (default: run until Ctrl-C)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.secs))
