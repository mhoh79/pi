"""
api.py - API proxy routes for the HMI web server.

Routing rules
-------------
  /api/gateway/*  →  http://gateway:8080/api/*
  /api/plc/*      →  http://plc:8081/api/*
  /api/dds/plc    →  local DDS cache of PLC outputs / alarms

All request methods, headers, query strings, and bodies are forwarded
transparently.  Responses are streamed back to the browser.
"""

from __future__ import annotations
from aiohttp import web, ClientSession, ClientTimeout, ClientError

import logging
import os
import sys
from typing import Callable

sys.path.insert(0, "/opt/shared")


logger = logging.getLogger("hmi.api")

GATEWAY_BASE: str = os.environ.get(
    "GATEWAY_URL", "http://gateway:8080").rstrip("/")
PLC_BASE: str = os.environ.get("PLC_URL", "http://plc:8081").rstrip("/")

PROXY_TIMEOUT = ClientTimeout(total=10)

# Headers that must NOT be forwarded (hop-by-hop)
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
    }
)


def _forward_headers(request: web.Request) -> dict[str, str]:
    return {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }


def _make_proxy_handler(upstream_base: str, strip_prefix: str) -> Callable:
    """Return an aiohttp request handler that proxies to *upstream_base*."""

    async def handler(request: web.Request) -> web.StreamResponse:
        # Build upstream URL: strip the local prefix, keep the rest
        tail = request.path[len(strip_prefix):]  # e.g. "/status"
        upstream_url = f"{upstream_base}/api{tail}"
        if request.query_string:
            upstream_url = f"{upstream_url}?{request.query_string}"

        session: ClientSession = request.app["client_session"]
        headers = _forward_headers(request)
        body = await request.read()

        logger.debug("Proxy %s %s → %s", request.method,
                     request.path, upstream_url)

        try:
            async with session.request(
                method=request.method,
                url=upstream_url,
                headers=headers,
                data=body or None,
                timeout=PROXY_TIMEOUT,
                allow_redirects=False,
            ) as upstream_resp:
                # Stream the response back
                response = web.StreamResponse(
                    status=upstream_resp.status,
                    reason=upstream_resp.reason,
                )
                for k, v in upstream_resp.headers.items():
                    if k.lower() not in _HOP_BY_HOP:
                        response.headers[k] = v

                await response.prepare(request)
                async for chunk in upstream_resp.content.iter_any():
                    await response.write(chunk)
                await response.write_eof()
                return response

        except ClientError as exc:
            logger.warning("Proxy error for %s: %s", upstream_url, exc)
            raise web.HTTPBadGateway(reason=str(exc)) from exc

    return handler


def register_routes(app: web.Application) -> None:
    """Attach all proxy routes to *app*."""

    gateway_handler = _make_proxy_handler(GATEWAY_BASE, "/api/gateway")
    plc_handler = _make_proxy_handler(PLC_BASE, "/api/plc")

    # Catch-all patterns so every sub-path is forwarded
    app.router.add_route("*", "/api/gateway/{tail:.*}", gateway_handler)
    app.router.add_route("*", "/api/plc/{tail:.*}", plc_handler)

    # DDS-sourced PLC data endpoint (populated by main.py DDS subscriber)
    app.router.add_get("/api/dds/plc", _handle_dds_plc)

    logger.info(
        "API proxy registered: /api/gateway/* → %s/api/*", GATEWAY_BASE
    )
    logger.info(
        "API proxy registered: /api/plc/*     → %s/api/*", PLC_BASE
    )
    logger.info("API endpoint registered: /api/dds/plc (DDS cache)")


async def _handle_dds_plc(request: web.Request) -> web.Response:
    """GET /api/dds/plc – return cached PLC data received via DDS."""
    # The DDS PLC cache is stored on the application object by the DDS subscriber.
    # Access it via request.app to avoid importing from the main module.
    dds_plc_cache = request.app.get("dds_plc_cache") or {}
    return web.json_response(dds_plc_cache)
