"""
main.py – Sensor node entry point.

Reads from a simulated sensor at a configurable interval, wraps each
reading in a :class:`Message`, and publishes it to the gateway via the
configured transport.

A lightweight health endpoint is served on port 9000 so that Docker
can determine when the node is ready.

Environment variables
---------------------
NODE_ID              Node identifier, e.g. ``sensor-1``  (default: ``sensor-unknown``)
SENSOR_PROFILE       Sensor type: ``TMP102``, ``BME280``, ``BH1750``, ``MPU6050``,
                     ``TMP102+BME280``  (default: ``BME280``)
SENSOR_INTERVAL_MS   Publish cadence in milliseconds      (default: 1000)
TRANSPORT            Transport back-end: ``http``          (default: ``http``)
GATEWAY_HOST         Gateway hostname                      (default: ``gateway``)
GATEWAY_PORT         Gateway port                          (default: ``8080``)
LOG_LEVEL            Logging level                         (default: ``INFO``)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Add /opt/shared to sys.path so the shared library can be imported whether
# it was bind-mounted at runtime or copied during the image build.
# ---------------------------------------------------------------------------
sys.path.insert(0, "/opt/shared")

from aiohttp import web

from sensors import create_sensor, SensorSimulator
from messages import Message

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sensor-node")

NODE_ID: str = os.environ.get("NODE_ID", "sensor-unknown")
SENSOR_PROFILE: str = os.environ.get("SENSOR_PROFILE", "BME280")
INTERVAL_MS: int = int(os.environ.get("SENSOR_INTERVAL_MS", "1000"))
HEALTH_PORT: int = int(os.environ.get("HEALTH_PORT", "9000"))

# ---------------------------------------------------------------------------
# Shared state (read by health endpoint)
# ---------------------------------------------------------------------------
_state: Dict[str, Any] = {
    "node_id": NODE_ID,
    "sensor_profile": SENSOR_PROFILE,
    "readings_published": 0,
    "last_reading": None,
    "started_at": time.time(),
    "healthy": False,
}

_seq: int = 0


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


# ---------------------------------------------------------------------------
# Sensor-read helper
# ---------------------------------------------------------------------------


def _build_messages(sensor: SensorSimulator, readings: Dict[str, Any]) -> list[Message]:
    """
    Convert raw sensor readings to a list of :class:`Message` objects.

    Each numeric measurement becomes its own message on a typed topic so
    that the gateway can index by topic.
    """
    ts = time.time()
    msgs: list[Message] = []

    for key, value in readings.items():
        if key == "sensor":
            continue  # metadata, not a measurement

        topic = f"rpi-net/sensor/{NODE_ID}/{key}"
        msg = Message(
            topic=topic,
            source=NODE_ID,
            timestamp=ts,
            payload={"value": value, "raw_key": key},
            quality="good",
            sequence=_next_seq(),
        )
        msgs.append(msg)

    return msgs


# ---------------------------------------------------------------------------
# Publish loop
# ---------------------------------------------------------------------------


async def publish_loop(sensor: SensorSimulator, transport: Any) -> None:
    """Read sensor at every tick and publish each measurement."""
    interval = INTERVAL_MS / 1000.0
    logger.info(
        "Publish loop started – profile=%s, interval=%.3fs, node=%s",
        SENSOR_PROFILE,
        interval,
        NODE_ID,
    )

    while True:
        start = time.monotonic()
        try:
            readings = sensor.read()
            _state["last_reading"] = readings
            messages = _build_messages(sensor, readings)

            for msg in messages:
                await transport.publish(msg.topic, msg.to_dict())

            _state["readings_published"] += len(messages)
            _state["healthy"] = True
            logger.debug(
                "Published %d message(s) from %s: %s",
                len(messages),
                SENSOR_PROFILE,
                readings,
            )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Error in publish loop: %s", exc, exc_info=True)
            _state["healthy"] = False

        elapsed = time.monotonic() - start
        sleep_for = max(0.0, interval - elapsed)
        await asyncio.sleep(sleep_for)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


async def handle_health(request: web.Request) -> web.Response:
    if _state["healthy"]:
        return web.json_response(
            {
                "status": "ok",
                **_state,
                "uptime_s": round(time.time() - _state["started_at"], 1),
            }
        )
    return web.json_response(
        {"status": "starting", **_state},
        status=503,
    )


async def start_health_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    logger.info("Health endpoint: http://0.0.0.0:%d/health", HEALTH_PORT)
    return runner


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    # Delayed import so /opt/shared is on sys.path before we import transport
    from transport import create_transport

    logger.info("Sensor node starting – NODE_ID=%s PROFILE=%s", NODE_ID, SENSOR_PROFILE)

    # Create sensor simulator
    try:
        sensor = create_sensor(SENSOR_PROFILE)
    except ValueError as exc:
        logger.critical("Cannot create sensor: %s", exc)
        raise SystemExit(1) from exc

    # Create and connect transport
    transport = create_transport()
    await transport.connect()

    # Start health server
    health_runner = await start_health_server()

    # Graceful shutdown on SIGINT / SIGTERM
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    # Run the publish loop until shutdown is requested
    publish_task = asyncio.create_task(publish_loop(sensor, transport))
    await shutdown_event.wait()

    publish_task.cancel()
    try:
        await publish_task
    except asyncio.CancelledError:
        pass

    await transport.close()
    await health_runner.cleanup()
    logger.info("Sensor node stopped (published %d readings)", _state["readings_published"])


if __name__ == "__main__":
    asyncio.run(main())
