"""
main.py - PLC scan-cycle loop with REST status API.

Environment variables
---------------------
PLC_SCAN_CYCLE_MS   Scan-cycle period in milliseconds (default: 500)
GATEWAY_URL         Base URL of the gateway service (default: http://gateway:8080)
PLC_HOST            Address the REST API listens on (default: 0.0.0.0)
PLC_PORT            REST API port (default: 8081)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from typing import Any

from collections import deque

from aiohttp import web, ClientSession, ClientTimeout, ClientError

from io_table import IOTable
from logic import ControlLogic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("plc")

SCAN_CYCLE_MS: int = int(os.environ.get("PLC_SCAN_CYCLE_MS", 500))
GATEWAY_URL: str = os.environ.get("GATEWAY_URL", "http://gateway:8080").rstrip("/")
PLC_HOST: str = os.environ.get("PLC_HOST", "0.0.0.0")
PLC_PORT: int = int(os.environ.get("PLC_PORT", 8081))

HTTP_TIMEOUT = ClientTimeout(total=max(1.0, SCAN_CYCLE_MS / 1000 * 0.8))


# ---------------------------------------------------------------------------
# PLC runtime state (shared between scan loop and REST handlers)
# ---------------------------------------------------------------------------
class PlcState:
    def __init__(self) -> None:
        self.inputs: dict[str, Any] = {}
        self.outputs: dict[str, Any] = {}
        self.cycle_count: int = 0
        self.last_cycle_ts: float = 0.0
        self.errors: deque[str] = deque(maxlen=100)
        self.running: bool = False
        self.start_ts: float = time.time()

    def status_dict(self) -> dict:
        # Derive alarms from outputs
        alarms = []
        if self.outputs.get("alarm_high_temp"):
            alarms.append({"name": "high_temp", "ts": self.last_cycle_ts})
        return {
            "running": self.running,
            "cycle_count": self.cycle_count,
            "last_cycle_ts": self.last_cycle_ts,
            "uptime_s": round(time.time() - self.start_ts, 1),
            "scan_cycle_ms": SCAN_CYCLE_MS,
            "errors": list(self.errors)[-20:],  # last 20 for API response
            "alarms": alarms,
        }


# ---------------------------------------------------------------------------
# Gateway I/O helpers
# ---------------------------------------------------------------------------
async def read_inputs(
    session: ClientSession,
    io_table: IOTable,
    state: PlcState,
) -> dict[str, Any]:
    """Fetch latest sensor values from the gateway and map to logical names."""
    inputs: dict[str, Any] = {}
    try:
        url = f"{GATEWAY_URL}/api/latest"
        async with session.get(url, timeout=HTTP_TIMEOUT) as resp:
            if resp.status == 200:
                data: dict = await resp.json()
                # Gateway returns {topic: {message_dict}, ...}
                for name in io_table.list_inputs():
                    topic = io_table.get_input_topic(name)
                    if topic in data:
                        msg_data = data[topic]
                        # Extract the scalar value from the payload
                        payload = msg_data.get("payload", msg_data) if isinstance(msg_data, dict) else msg_data
                        value = payload.get("value", payload) if isinstance(payload, dict) else payload
                        inputs[name] = value
            else:
                msg = f"Gateway /api/latest returned HTTP {resp.status}"
                logger.warning(msg)
                state.errors.append(msg)
    except ClientError as exc:
        msg = f"Gateway read error: {exc}"
        logger.warning(msg)
        state.errors.append(msg)
    return inputs


async def write_outputs(
    session: ClientSession,
    io_table: IOTable,
    outputs: dict[str, Any],
    state: PlcState,
) -> None:
    """Push computed output values to the gateway."""
    payload: dict[str, Any] = {}
    for name, value in outputs.items():
        try:
            topic = io_table.get_output_topic(name)
            payload[topic] = value
        except KeyError:
            logger.warning("No output topic mapped for '%s'", name)

    if not payload:
        return

    # Publish each output as a separate message via /api/ingest
    url = f"{GATEWAY_URL}/api/ingest"
    for topic, value in payload.items():
        body = {
            "topic": topic,
            "source": os.environ.get("NODE_ID", "plc"),
            "timestamp": time.time(),
            "payload": {"value": value},
            "quality": "good",
        }
        try:
            async with session.post(
                url, json=body, timeout=HTTP_TIMEOUT
            ) as resp:
                if resp.status not in (200, 201, 204):
                    msg = f"Gateway /api/ingest returned HTTP {resp.status} for {topic}"
                    logger.warning(msg)
                    state.errors.append(msg)
        except ClientError as exc:
            msg = f"Gateway write error for {topic}: {exc}"
            logger.warning(msg)
            state.errors.append(msg)


# ---------------------------------------------------------------------------
# Scan-cycle loop
# ---------------------------------------------------------------------------
async def scan_loop(state: PlcState) -> None:
    io_table = IOTable()
    logic = ControlLogic()
    period = SCAN_CYCLE_MS / 1000.0

    async with ClientSession() as session:
        state.running = True
        logger.info(
            "PLC scan loop started (cycle=%d ms, gateway=%s)",
            SCAN_CYCLE_MS,
            GATEWAY_URL,
        )
        while state.running:
            cycle_start = time.monotonic()

            # 1. Read inputs
            inputs = await read_inputs(session, io_table, state)
            state.inputs = inputs

            # 2. Execute control logic
            try:
                outputs = logic.execute(inputs)
            except Exception as exc:
                msg = f"Logic error: {exc}"
                logger.error(msg, exc_info=True)
                state.errors.append(msg)
                outputs = logic.last_outputs  # retain previous safe state

            state.outputs = outputs

            # 3. Write outputs
            await write_outputs(session, io_table, outputs, state)

            state.cycle_count += 1
            state.last_cycle_ts = time.time()

            # 4. Sleep for the remainder of the scan period
            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0.0, period - elapsed)
            if elapsed > period:
                logger.warning(
                    "Scan overrun: cycle took %.1f ms (limit %d ms)",
                    elapsed * 1000,
                    SCAN_CYCLE_MS,
                )
            await asyncio.sleep(sleep_time)

    logger.info("PLC scan loop stopped after %d cycles", state.cycle_count)


# ---------------------------------------------------------------------------
# REST API handlers
# ---------------------------------------------------------------------------
async def handle_status(request: web.Request) -> web.Response:
    state: PlcState = request.app["state"]
    return web.json_response(state.status_dict())


async def handle_outputs(request: web.Request) -> web.Response:
    state: PlcState = request.app["state"]
    return web.json_response(
        {
            "outputs": state.outputs,
            "inputs": state.inputs,
            "cycle_count": state.cycle_count,
        }
    )


# ---------------------------------------------------------------------------
# Application factory & startup/shutdown
# ---------------------------------------------------------------------------
def build_app(state: PlcState) -> web.Application:
    app = web.Application()
    app["state"] = state

    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/outputs", handle_outputs)

    return app


async def main() -> None:
    state = PlcState()

    # Start scan loop as a background task
    loop_task = asyncio.create_task(scan_loop(state))

    # Build and start the REST API
    app = build_app(state)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, PLC_HOST, PLC_PORT)
    await site.start()
    logger.info("REST API listening on http://%s:%d", PLC_HOST, PLC_PORT)

    # Graceful shutdown on SIGINT / SIGTERM
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await shutdown_event.wait()

    # Stop scan loop
    state.running = False
    try:
        await asyncio.wait_for(loop_task, timeout=SCAN_CYCLE_MS / 1000 * 2 + 1)
    except asyncio.TimeoutError:
        loop_task.cancel()

    await runner.cleanup()
    logger.info("PLC shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
