"""
api.py - API proxy routes for the HMI web server.

Routing rules
-------------
  /api/gateway/*  →  http://gateway:8080/api/*
  /api/plc/*      →  http://plc:8081/api/*

All request methods, headers, query strings, and bodies are forwarded
transparently.  Responses are streamed back to the browser.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from aiohttp import web, ClientSession, ClientTimeout, ClientError

logger = logging.getLogger("hmi.api")

GATEWAY_BASE: str = os.environ.get("GATEWAY_URL", "http://gateway:8080").rstrip("/")
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

        logger.debug("Proxy %s %s → %s", request.method, request.path, upstream_url)

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

    logger.info(
        "API proxy registered: /api/gateway/* → %s/api/*", GATEWAY_BASE
    )
    logger.info(
        "API proxy registered: /api/plc/*     → %s/api/*", PLC_BASE
    )
