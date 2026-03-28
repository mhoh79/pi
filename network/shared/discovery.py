"""
discovery.py – Lightweight service-discovery helpers for the RPi simulation network.

All look-ups read environment variables so that Docker Compose networking
(container hostnames) works out of the box, but the same code also runs
locally by overriding the variables.

Example
-------
    from discovery import get_gateway_url, get_node_id

    base = get_gateway_url()   # "http://gateway:8080"
    me   = get_node_id()       # "sensor-1"
"""

from __future__ import annotations

import os
from typing import Optional


# ---------------------------------------------------------------------------
# Well-known service helpers
# ---------------------------------------------------------------------------


def get_gateway_url() -> str:
    """
    Return the base URL for the gateway service.

    Reads
    -----
    GATEWAY_HOST : str, default ``"gateway"``
    GATEWAY_PORT : int, default ``8080``

    Returns
    -------
    ``"http://<GATEWAY_HOST>:<GATEWAY_PORT>"``
    """
    host = os.environ.get("GATEWAY_HOST", "gateway")
    port = os.environ.get("GATEWAY_PORT", "8080")
    return f"http://{host}:{port}"


def get_plc_url() -> str:
    """
    Return the base URL for the PLC service.

    Reads
    -----
    PLC_HOST : str, default ``"plc"``
    PLC_PORT : int, default ``8081``

    Returns
    -------
    ``"http://<PLC_HOST>:<PLC_PORT>"``
    """
    host = os.environ.get("PLC_HOST", "plc")
    port = os.environ.get("PLC_PORT", "8081")
    return f"http://{host}:{port}"


def get_node_id() -> str:
    """
    Return the identifier for the current node.

    Reads
    -----
    NODE_ID : str, default ``"unknown"``
    """
    return os.environ.get("NODE_ID", "unknown")


def get_service_url(service_name: str) -> str:
    """
    Generic service URL look-up.

    Checks, in order:

    1. ``<SERVICE_NAME_UPPER>_URL`` – fully-qualified override, e.g.
       ``GATEWAY_URL=http://192.168.1.10:8080``
    2. ``<SERVICE_NAME_UPPER>_HOST`` + ``<SERVICE_NAME_UPPER>_PORT`` –
       e.g. ``GATEWAY_HOST=gateway`` and ``GATEWAY_PORT=8080``
    3. Falls back to ``http://<service_name>:80``.

    Parameters
    ----------
    service_name:
        Lower-case service name as used in Docker Compose, e.g.
        ``"gateway"``, ``"plc"``, ``"hmi"``.

    Returns
    -------
    A base URL string.

    Examples
    --------
    >>> import os
    >>> os.environ["MYSERVICE_HOST"] = "10.0.0.5"
    >>> os.environ["MYSERVICE_PORT"] = "9999"
    >>> get_service_url("myservice")
    'http://10.0.0.5:9999'
    """
    prefix = service_name.upper().replace("-", "_")

    # 1. Fully-qualified override
    full_url = os.environ.get(f"{prefix}_URL")
    if full_url:
        return full_url.rstrip("/")

    # 2. Host + port pair
    host = os.environ.get(f"{prefix}_HOST", service_name)
    port = os.environ.get(f"{prefix}_PORT", "80")
    return f"http://{host}:{port}"


# ---------------------------------------------------------------------------
# Convenience aliases
# ---------------------------------------------------------------------------


def gateway_url() -> str:
    """Alias for :func:`get_gateway_url`."""
    return get_gateway_url()


def plc_url() -> str:
    """Alias for :func:`get_plc_url`."""
    return get_plc_url()


def node_id() -> str:
    """Alias for :func:`get_node_id`."""
    return get_node_id()
