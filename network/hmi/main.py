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
import logging
import os
import signal
import sys
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
_dds_plc_cache: Dict[str, Dict[str, Any]] = {}
_dds_transport = None


def _on_plc_data(app_topic: str, data: Dict[str, Any]) -> None:
    """DDS callback – cache latest PLC output / alarm data by app topic."""
    _dds_plc_cache[app_topic] = data


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def build_app() -> web.Application:
    app = web.Application()

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

    # Start DDS subscribers if configured
    if TRANSPORT_TYPE == "dds":
        from transport import create_transport
        from dds_types import TOPIC_CONTROL_DATA, TOPIC_ALARM_DATA

        _dds_transport = create_transport("dds")
        await _dds_transport.connect()
        await _dds_transport.subscribe(TOPIC_CONTROL_DATA, _on_plc_data)
        await _dds_transport.subscribe(TOPIC_ALARM_DATA, _on_plc_data)
        logger.info("HMI subscribed to DDS topics: ControlData, AlarmData")

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
