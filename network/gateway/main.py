"""
main.py – Gateway aggregator entry point.

Creates an aiohttp web application, registers REST API routes, and
starts the server on port 8080 (configurable via env vars).

Environment variables
---------------------
GATEWAY_HOST      Bind address        (default: ``0.0.0.0``)
GATEWAY_PORT      Listening port      (default: ``8080``)
STORE_MAXLEN      Ring-buffer depth   (default: ``1000``)
LOG_LEVEL         Logging verbosity   (default: ``INFO``)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

# ---------------------------------------------------------------------------
# Add /opt/shared to sys.path so shared modules can be imported whether
# the directory was bind-mounted at runtime or copied at image build time.
# ---------------------------------------------------------------------------
sys.path.insert(0, "/opt/shared")

from aiohttp import web

from store import TimeSeriesStore
from api import register_routes

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway")

GATEWAY_HOST: str = os.environ.get("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT: int = int(os.environ.get("GATEWAY_PORT", "8080"))
STORE_MAXLEN: int = int(os.environ.get("STORE_MAXLEN", "1000"))


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def build_app() -> web.Application:
    """Create and configure the aiohttp application."""
    store = TimeSeriesStore(maxlen=STORE_MAXLEN)
    app = web.Application()
    register_routes(app, store)

    async def on_startup(application: web.Application) -> None:
        logger.info(
            "Gateway started – store maxlen=%d, port=%d",
            STORE_MAXLEN,
            GATEWAY_PORT,
        )

    async def on_cleanup(application: web.Application) -> None:
        logger.info("Gateway shutting down")

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    app = build_app()

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, GATEWAY_HOST, GATEWAY_PORT)
    await site.start()
    logger.info("Gateway listening on http://%s:%d", GATEWAY_HOST, GATEWAY_PORT)

    shutdown_event = asyncio.Event()

    def _on_signal() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    await shutdown_event.wait()
    await runner.cleanup()
    logger.info("Gateway stopped")


if __name__ == "__main__":
    asyncio.run(main())
