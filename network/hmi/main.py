"""
main.py - HMI web server.

Serves static files from ./static/ and proxies API calls to the
gateway and PLC services.  When TRANSPORT=dds, also subscribes to
ControlData and AlarmData DDS topics and caches PLC outputs for the
``/api/dds/plc`` endpoint.

Environment variables
---------------------
HMI_HOST    Bind address (default: 0.0.0.0)
HMI_PORT    Listening port  (default: 3000)
TRANSPORT   Transport back-end: ``http`` or ``dds`` (default: from .env)
"""

from __future__ import annotations
from api import register_routes
from aiohttp import web, ClientSession
import aiohttp_cors

import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, "/opt/shared")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hmi")

HMI_HOST: str = os.environ.get("HMI_HOST", "0.0.0.0")
HMI_PORT: int = int(os.environ.get("HMI_PORT", 3000))
STATIC_DIR: Path = Path(__file__).parent / "static"
TRANSPORT_TYPE: str = os.environ.get("TRANSPORT", "http").lower().strip()

# ---------------------------------------------------------------------------
# DDS cache – updated by subscriber callbacks
# ---------------------------------------------------------------------------
_dds_transport = None


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def build_app() -> web.Application:
    app = web.Application()
    app["started_at"] = time.time()

    # Shared HTTP client session (reused by proxy handlers)
    async def on_startup(application: web.Application) -> None:
        application["client_session"] = ClientSession()
        logger.info("HTTP client session created")

    async def on_cleanup(application: web.Application) -> None:
        await application["client_session"].close()
        logger.info("HTTP client session closed")

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # CORS – allow all origins for development; tighten for production
    cors = aiohttp_cors.setup(
        app,
        defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=False,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            )
        },
    )

    # API proxy routes (registered before static so /api/* takes priority)
    register_routes(app)

    # Apply CORS to every route registered so far
    for route in list(app.router.routes()):
        try:
            cors.add(route)
        except ValueError:
            pass  # some routes (e.g. HEAD) may already have CORS applied

    # Static file serving – index.html served at "/"
    if STATIC_DIR.is_dir():
        app.router.add_static("/", path=str(STATIC_DIR),
                              name="static", show_index=False)
        logger.info("Serving static files from %s", STATIC_DIR)
    else:
        logger.warning("Static directory not found: %s", STATIC_DIR)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    global _dds_transport
    app = build_app()

    # In-memory DDS-backed cache exposed by /api/dds/* handlers.
    app["dds_latest"] = {}
    app["dds_nodes"] = {}
    app["dds_outputs"] = {}
    app["dds_alarms"] = {}
    app["sse_clients"] = set()
    app["sse_event_id"] = 0
    app["dds_metrics"] = {
        "clients": 0,
        "dds_messages": 0,
        "events_emitted": 0,
        "events_dropped": 0,
        "last_event_id": 0,
        "last_source_ts": 0.0,
        "last_server_ts": 0.0,
        "avg_lag_ms": 0.0,
    }

    def _metrics_snapshot() -> Dict[str, Any]:
        metrics = app["dds_metrics"]
        return {
            "clients": int(metrics.get("clients", 0)),
            "dds_messages": int(metrics.get("dds_messages", 0)),
            "events_emitted": int(metrics.get("events_emitted", 0)),
            "events_dropped": int(metrics.get("events_dropped", 0)),
            "last_event_id": int(metrics.get("last_event_id", 0)),
            "last_source_ts": float(metrics.get("last_source_ts", 0.0)),
            "last_server_ts": float(metrics.get("last_server_ts", 0.0)),
            "avg_lag_ms": round(float(metrics.get("avg_lag_ms", 0.0)), 2),
        }

    def _emit_event(event_type: str, payload: Dict[str, Any]) -> None:
        """Push an event envelope to all connected SSE clients."""
        app["sse_event_id"] += 1
        event_id = int(app["sse_event_id"])

        metrics = app["dds_metrics"]
        metrics["last_event_id"] = event_id
        metrics["last_server_ts"] = time.time()

        envelope = {
            "id": event_id,
            "type": event_type,
            "server_ts": metrics["last_server_ts"],
            "payload": payload,
            "metrics": _metrics_snapshot(),
        }

        dead = []
        for q in list(app["sse_clients"]):
            try:
                q.put_nowait(envelope)
                metrics["events_emitted"] += 1
            except asyncio.QueueFull:
                metrics["events_dropped"] += 1
                dead.append(q)

        for q in dead:
            app["sse_clients"].discard(q)

        metrics["clients"] = len(app["sse_clients"])

    app["emit_event"] = _emit_event
    app["metrics_snapshot"] = _metrics_snapshot

    def _on_dds_data(app_topic: str, data: Dict[str, Any]) -> None:
        """DDS callback – update all HMI caches from incoming DDS samples."""
        now_ts = time.time()
        msg_ts = float(data.get("timestamp", now_ts) or now_ts)
        source = str(data.get("source", "") or "")

        metrics = app["dds_metrics"]
        metrics["dds_messages"] = int(metrics.get("dds_messages", 0)) + 1
        metrics["last_source_ts"] = msg_ts
        lag_ms = max(0.0, (now_ts - msg_ts) * 1000.0)
        prev = float(metrics.get("avg_lag_ms", lag_ms))
        metrics["avg_lag_ms"] = (prev * 0.9) + (lag_ms * 0.1)

        latest: Dict[str, Dict[str, Any]] = app["dds_latest"]
        latest[app_topic] = data

        value = None
        payload = data.get("payload", {})
        if isinstance(payload, dict):
            value = payload.get("value")
        _emit_event(
            "sensor",
            {
                "topic": app_topic,
                "entry": {
                    "value": value,
                    "timestamp": msg_ts,
                    "source": source,
                },
            },
        )

        if source:
            nodes: Dict[str, float] = app["dds_nodes"]
            nodes[source] = msg_ts
            _emit_event("node", {"node_id": source, "last_seen": msg_ts})

        if not isinstance(payload, dict):
            return

        # ControlData payloads include output_id/value.
        output_id = payload.get("output_id")
        if output_id is not None and "value" in payload:
            outputs: Dict[str, Any] = app["dds_outputs"]
            outputs[str(output_id)] = payload.get("value")
            _emit_event(
                "plc_output",
                {
                    "output_id": str(output_id),
                    "value": payload.get("value"),
                    "outputs": dict(outputs),
                },
            )

        # AlarmData payloads include alarm_id/active/message.
        alarm_id = payload.get("alarm_id")
        if alarm_id is not None:
            alarms: Dict[str, Dict[str, Any]] = app["dds_alarms"]
            alarm_key = str(alarm_id)
            is_active = bool(payload.get("active", True))
            if is_active:
                alarms[alarm_key] = {
                    "name": alarm_key,
                    "ts": msg_ts,
                    "message": payload.get("message", ""),
                    "severity": payload.get("severity", "WARNING"),
                }
            else:
                alarms.pop(alarm_key, None)
            _emit_event("alarm", {"alarms": list(alarms.values())})

        # Emit an always-fresh PLC status view whenever PLC data arrives.
        plc_last_seen = float(app["dds_nodes"].get("plc", 0.0) or 0.0)
        running = plc_last_seen > 0 and (now_ts - plc_last_seen) < 10.0
        _emit_event(
            "plc_status",
            {
                "running": running,
                "cycle_count": None,
                "last_cycle_ts": plc_last_seen,
                "uptime_s": round(now_ts - app.get("started_at", now_ts), 1),
                "scan_cycle_ms": int(os.environ.get("PLC_SCAN_CYCLE_MS", "500")),
                "errors": [],
                "alarms": list(app["dds_alarms"].values()),
                "source": "dds",
            },
        )

    # Start DDS subscribers if configured
    if TRANSPORT_TYPE == "dds":
        from transport import create_transport
        from dds_types import TOPIC_SENSOR_DATA, TOPIC_CONTROL_DATA, TOPIC_ALARM_DATA

        _dds_transport = create_transport("dds")
        await _dds_transport.connect()
        await _dds_transport.subscribe(TOPIC_SENSOR_DATA, _on_dds_data)
        await _dds_transport.subscribe(TOPIC_CONTROL_DATA, _on_dds_data)
        await _dds_transport.subscribe(TOPIC_ALARM_DATA, _on_dds_data)
        logger.info(
            "HMI subscribed to DDS topics: SensorData, ControlData, AlarmData"
        )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HMI_HOST, HMI_PORT)
    await site.start()
    logger.info("HMI server listening on http://%s:%d", HMI_HOST, HMI_PORT)

    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await shutdown_event.wait()

    if _dds_transport is not None:
        await _dds_transport.close()

    await runner.cleanup()
    logger.info("HMI server stopped")


if __name__ == "__main__":
    asyncio.run(main())
