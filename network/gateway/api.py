"""
api.py – REST API route handlers for the gateway.

Endpoints
---------
GET  /health                  Liveness / readiness probe
GET  /api/nodes               List known nodes and their last-seen timestamps
POST /api/ingest              Ingest a message from a sensor node
GET  /api/latest/{topic}      Most recent message for a topic
GET  /api/history/{topic}     Last N messages for a topic  (?n=100)
GET  /api/subscribe           Server-Sent Events stream of all ingested messages

Usage
-----
    from store import TimeSeriesStore
    from api import register_routes

    store = TimeSeriesStore()
    app = web.Application()
    register_routes(app, store)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Set

from aiohttp import web

from store import TimeSeriesStore

logger = logging.getLogger("gateway.api")

# ---------------------------------------------------------------------------
# SSE subscriber registry (populated at app startup)
# ---------------------------------------------------------------------------
_sse_queues: Set[asyncio.Queue] = set()


def _broadcast(message: dict) -> None:
    """Push a message dict to all active SSE subscribers."""
    payload = json.dumps(message, default=str)
    dead: list[asyncio.Queue] = []
    for q in _sse_queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_queues.discard(q)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def handle_health(request: web.Request) -> web.Response:
    """GET /health – basic liveness probe."""
    store: TimeSeriesStore = request.app["store"]
    return web.json_response(
        {
            "status": "ok",
            "topics": len(store.topics()),
            "total_messages": len(store),
            "nodes": len(store.nodes()),
            "uptime_s": round(time.time() - request.app["started_at"], 1),
        }
    )


async def handle_nodes(request: web.Request) -> web.Response:
    """GET /api/nodes – return all known nodes and last-seen timestamps."""
    store: TimeSeriesStore = request.app["store"]
    return web.json_response(store.nodes())


async def handle_ingest(request: web.Request) -> web.Response:
    """
    POST /api/ingest – accept a message dict from a sensor or PLC node.

    Body must be JSON.  The ``topic`` key is used as the ring-buffer key.
    """
    store: TimeSeriesStore = request.app["store"]
    try:
        data: dict = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(reason=f"Invalid JSON: {exc}") from exc

    topic = data.get("topic")
    if not topic:
        raise web.HTTPBadRequest(reason="Missing required field: topic")

    # Stamp server-side receive time if the message has no timestamp
    if "timestamp" not in data:
        data["timestamp"] = time.time()

    store.add(topic, data)
    logger.debug("Ingested topic=%s source=%s", topic, data.get("source"))

    # Fan-out to SSE subscribers
    _broadcast(data)

    return web.json_response({"status": "ok", "topic": topic}, status=201)


async def handle_all_latest(request: web.Request) -> web.Response:
    """GET /api/latest – return latest message for every known topic."""
    store: TimeSeriesStore = request.app["store"]
    return web.json_response(store.all_latest())


async def handle_latest(request: web.Request) -> web.Response:
    """GET /api/latest/{topic} – return the most recent message."""
    store: TimeSeriesStore = request.app["store"]
    # The route parameter captures everything after /api/latest/
    topic: str = request.match_info["topic"]
    msg = store.latest(topic)
    if msg is None:
        raise web.HTTPNotFound(reason=f"No data for topic: {topic!r}")
    return web.json_response(msg)


async def handle_history(request: web.Request) -> web.Response:
    """
    GET /api/history/{topic}?n=100 – return the last N messages.

    Query parameters
    ----------------
    n : int, default 100
        Number of messages to return (capped at the store's maxlen).
    since : float, optional
        If provided, return only messages with timestamp > since.
    """
    store: TimeSeriesStore = request.app["store"]
    topic: str = request.match_info["topic"]

    since_str = request.rel_url.query.get("since")
    if since_str is not None:
        try:
            since_ts = float(since_str)
        except ValueError as exc:
            raise web.HTTPBadRequest(reason=f"Invalid 'since' value: {since_str!r}") from exc
        messages = store.since(topic, since_ts)
    else:
        try:
            n = int(request.rel_url.query.get("n", "100"))
        except ValueError as exc:
            raise web.HTTPBadRequest(reason="'n' must be an integer") from exc
        messages = store.history(topic, n=n)

    return web.json_response({"topic": topic, "count": len(messages), "messages": messages})


async def handle_subscribe(request: web.Request) -> web.StreamResponse:
    """
    GET /api/subscribe – Server-Sent Events stream.

    Each ingested message is pushed as an SSE ``data:`` event.
    Clients can filter by topic in their own handler.

    Example (JavaScript)
    --------------------
        const es = new EventSource('/api/subscribe');
        es.onmessage = e => console.log(JSON.parse(e.data));
    """
    response = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
        }
    )
    await response.prepare(request)

    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    _sse_queues.add(queue)
    logger.debug("SSE client connected (total=%d)", len(_sse_queues))

    try:
        # Send a comment to establish the connection and keep proxies alive
        await response.write(b": connected\n\n")

        while True:
            try:
                payload: str = await asyncio.wait_for(queue.get(), timeout=30.0)
                await response.write(f"data: {payload}\n\n".encode())
            except asyncio.TimeoutError:
                # Send a keep-alive comment every 30 s
                await response.write(b": keepalive\n\n")
            except asyncio.CancelledError:
                break
    except ConnectionResetError:
        pass
    finally:
        _sse_queues.discard(queue)
        logger.debug("SSE client disconnected (total=%d)", len(_sse_queues))

    return response


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def register_routes(app: web.Application, store: TimeSeriesStore) -> None:
    """
    Attach all API routes to *app* and store the :class:`TimeSeriesStore`
    reference on ``app["store"]``.
    """
    app["store"] = store
    app["started_at"] = time.time()

    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/status", handle_health)  # alias for HMI proxy
    app.router.add_get("/api/nodes", handle_nodes)
    app.router.add_post("/api/ingest", handle_ingest)
    app.router.add_get("/api/latest", handle_all_latest)
    # Capture multi-segment topics like "sensor-1/temperature"
    app.router.add_get("/api/latest/{topic:.+}", handle_latest)
    app.router.add_get("/api/history/{topic:.+}", handle_history)
    app.router.add_get("/api/subscribe", handle_subscribe)

    logger.info("Gateway API routes registered")
