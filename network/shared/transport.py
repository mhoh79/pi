"""
transport.py – Pluggable transport abstraction for the RPi simulation network.

Supported back-ends
-------------------
  http   – aiohttp-based HTTP polling / POST (default, zero extra deps)
  dds    – CycloneDDS pub/sub  (install cyclonedds + pydantic to enable)
  mqtt   – asyncio-mqtt stub  (install asyncio-mqtt to enable)
  opcua  – asyncua stub       (install asyncua to enable)

Usage
-----
    from transport import create_transport

    transport = create_transport()          # reads TRANSPORT env-var
    await transport.connect()
    await transport.publish("sensors/temp", {"value": 23.5})
    await transport.close()
"""

from __future__ import annotations

import abc
import asyncio
import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Abstract base protocol
# ---------------------------------------------------------------------------


class Transport(abc.ABC):
    """Contract that every transport back-end must satisfy."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish the underlying connection / session."""

    @abc.abstractmethod
    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Send *payload* to *topic* (fire-and-forget semantics)."""

    @abc.abstractmethod
    async def subscribe(
        self,
        topic: str,
        callback: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        """Register *callback* to be invoked whenever a message arrives on *topic*."""

    @abc.abstractmethod
    async def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Perform a request/response call.

        Parameters
        ----------
        method:
            HTTP verb (``"GET"``, ``"POST"``, …) or transport-specific name.
        path:
            Resource path, e.g. ``"/api/latest/sensor-1/temperature"``.
        payload:
            Optional body / query parameters.

        Returns
        -------
        Parsed response as a plain dict.
        """

    @abc.abstractmethod
    async def close(self) -> None:
        """Release all resources."""


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------


class HttpTransport(Transport):
    """
    aiohttp-based transport that talks to the gateway REST API.

    Publish   → POST /api/ingest  (wraps payload with the topic key)
    Subscribe → background polling loop against GET /api/latest/{topic}
    Request   → arbitrary GET or POST to any path on the gateway
    """

    def __init__(
        self,
        base_url: str,
        poll_interval: float = 1.0,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._poll_interval = poll_interval
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        # topic → list[callback]
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._poll_tasks: List[asyncio.Task] = []

    # -- lifecycle -----------------------------------------------------------

    async def connect(self, retries: int = 5, backoff: float = 2.0) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        # Verify gateway is reachable before declaring connected
        for attempt in range(1, retries + 1):
            try:
                async with self._session.get(f"{self._base_url}/health") as resp:
                    if resp.status == 200:
                        logger.info(
                            "HttpTransport connected to %s", self._base_url)
                        return
            except aiohttp.ClientError:
                pass
            if attempt < retries:
                wait = backoff * attempt
                logger.warning(
                    "Gateway not ready (attempt %d/%d), retrying in %.0fs...",
                    attempt, retries, wait,
                )
                await asyncio.sleep(wait)
        # Proceed anyway — gateway may come up later
        logger.warning(
            "Gateway not reachable after %d attempts; proceeding anyway", retries
        )

    async def close(self) -> None:
        for task in self._poll_tasks:
            task.cancel()
        if self._poll_tasks:
            await asyncio.gather(*self._poll_tasks, return_exceptions=True)
        self._poll_tasks.clear()
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("HttpTransport closed")

    # -- publish -------------------------------------------------------------

    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """POST *payload* to ``/api/ingest`` tagged with *topic*."""
        if self._session is None:
            raise RuntimeError(
                "Transport not connected – call connect() first")

        body = {**payload, "topic": topic}  # topic always wins over payload
        url = f"{self._base_url}/api/ingest"
        try:
            async with self._session.post(url, json=body) as resp:
                if resp.status not in (200, 201, 204):
                    text = await resp.text()
                    logger.warning(
                        "publish to %s returned HTTP %d: %s", url, resp.status, text
                    )
        except aiohttp.ClientError as exc:
            logger.error("publish error: %s", exc)

    # -- subscribe -----------------------------------------------------------

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        """
        Poll ``/api/latest/{topic}`` and invoke *callback* on new data.

        One polling task is created per unique topic the first time it is
        subscribed; subsequent calls for the same topic append to the
        callback list.
        """
        self._subscriptions.setdefault(topic, []).append(callback)
        # Only one polling task per topic
        existing = [t for t in self._poll_tasks if not t.done()
                    and t.get_name() == topic]
        if not existing:
            task = asyncio.create_task(self._poll_loop(topic), name=topic)
            self._poll_tasks.append(task)
            logger.debug("Started polling task for topic '%s'", topic)

    async def _poll_loop(self, topic: str) -> None:
        """Background coroutine: poll /api/latest/{topic} and fire callbacks."""
        url = f"{self._base_url}/api/latest/{topic}"
        last_seq: int = -1

        while True:
            await asyncio.sleep(self._poll_interval)
            if self._session is None or self._session.closed:
                break
            try:
                async with self._session.get(url) as resp:
                    if resp.status == 200:
                        data: Dict[str, Any] = await resp.json()
                        seq = data.get("sequence", 0)
                        if seq != last_seq:
                            last_seq = seq
                            for cb in self._subscriptions.get(topic, []):
                                try:
                                    cb(topic, data)
                                except Exception as exc:  # noqa: BLE001
                                    logger.error(
                                        "Subscriber callback error: %s", exc)
                    elif resp.status == 404:
                        pass  # topic not yet populated – normal at startup
                    else:
                        logger.warning(
                            "Poll %s returned HTTP %d", url, resp.status)
            except asyncio.CancelledError:
                break
            except aiohttp.ClientError as exc:
                logger.warning("Poll error for topic '%s': %s", topic, exc)

    # -- request -------------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Perform an HTTP GET or POST against *path* on the gateway.

        Returns the parsed JSON body, or ``{}`` on error.
        """
        if self._session is None:
            raise RuntimeError(
                "Transport not connected – call connect() first")

        url = f"{self._base_url}{path}"
        method = method.upper()
        try:
            if method == "GET":
                async with self._session.get(url, params=payload) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            elif method == "POST":
                async with self._session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            else:
                raise ValueError(f"Unsupported HTTP method: {method!r}")
        except aiohttp.ClientError as exc:
            logger.error("request %s %s failed: %s", method, url, exc)
            return {}


# ---------------------------------------------------------------------------
# DDS transport (CycloneDDS)
# ---------------------------------------------------------------------------


class DdsTransport(Transport):
    """
    CycloneDDS-based transport.

    Publish   → write an IdlStruct sample to the appropriate DDS topic
    Subscribe → background thread calling ``take_iter()`` on a DataReader,
                dispatching callbacks to the asyncio event loop
    Request   → not supported (DDS is pub/sub only)

    Requires: ``pip install cyclonedds pydantic``
    """

    def __init__(self, domain_id: int = 0) -> None:
        self._domain_id = domain_id
        self._participant: Any = None
        self._topics: Dict[str, Any] = {}       # DDS topic name → Topic
        self._writers: Dict[str, Any] = {}       # DDS topic name → DataWriter
        self._readers: List[Any] = []
        self._reader_threads: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        from cyclonedds.domain import DomainParticipant
        from cyclonedds.topic import Topic as DdsTopic

        from dds_types import (
            DdsAlarmEvent,
            DdsControlOutput,
            DdsSensorReading,
            TOPIC_ALARM_DATA,
            TOPIC_CONTROL_DATA,
            TOPIC_SENSOR_DATA,
        )

        self._stop_event.clear()
        self._loop = asyncio.get_running_loop()
        self._participant = DomainParticipant(domain_id=self._domain_id)

        self._topics[TOPIC_SENSOR_DATA] = DdsTopic(
            self._participant, TOPIC_SENSOR_DATA, DdsSensorReading,
        )
        self._topics[TOPIC_CONTROL_DATA] = DdsTopic(
            self._participant, TOPIC_CONTROL_DATA, DdsControlOutput,
        )
        self._topics[TOPIC_ALARM_DATA] = DdsTopic(
            self._participant, TOPIC_ALARM_DATA, DdsAlarmEvent,
        )
        logger.info(
            "DdsTransport connected (domain=%d, topics=%s)",
            self._domain_id,
            list(self._topics.keys()),
        )

    async def close(self) -> None:
        self._stop_event.set()
        for t in self._reader_threads:
            t.join(timeout=3.0)
        self._reader_threads.clear()
        self._readers.clear()
        self._writers.clear()
        self._topics.clear()
        self._participant = None
        logger.info("DdsTransport closed")

    # -- publish -------------------------------------------------------------

    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Detect payload type, convert to DDS sample, and write.

        The *topic* parameter is the application-level topic string (e.g.
        ``"rpi-net/sensor/sensor-1/temperature"``).  The DDS topic is
        selected by inspecting the payload keys.
        """
        if self._participant is None:
            raise RuntimeError(
                "DdsTransport not connected – call connect() first")

        from cyclonedds.pub import DataWriter
        from cyclonedds.qos import Qos, Policy

        from dds_types import TOPIC_ALARM_DATA, TOPIC_CONTROL_DATA, TOPIC_SENSOR_DATA
        from models import AlarmEvent, ControlOutput, SensorReading

        # Determine DDS topic from payload content
        inner = payload.get("payload", payload) if isinstance(
            payload, dict) else payload
        if isinstance(inner, dict) and "alarm_id" in inner:
            dds_topic_name = TOPIC_ALARM_DATA
            model = AlarmEvent.from_legacy_dict(payload)
        elif isinstance(inner, dict) and "output_id" in inner:
            dds_topic_name = TOPIC_CONTROL_DATA
            model = ControlOutput.from_legacy_dict(payload)
        else:
            dds_topic_name = TOPIC_SENSOR_DATA
            model = SensorReading.from_legacy_dict(payload)

        # Make the topic parameter authoritative (mirrors HttpTransport behaviour)
        model.topic = topic

        dds_topic = self._topics.get(dds_topic_name)
        if dds_topic is None:
            raise RuntimeError(
                f"DDS topic {dds_topic_name!r} is not registered; "
                "call connect() first"
            )

        if dds_topic_name not in self._writers:
            writer_qos = Qos(
                # Keep enough queued samples for bursty multi-sensor publishes.
                Policy.History.KeepLast(512),
                # Reliable delivery between sensor nodes and gateway/plc/hmi.
                Policy.Reliability.Reliable(1_000_000_000),
            )
            self._writers[dds_topic_name] = DataWriter(
                self._participant, dds_topic, qos=writer_qos)

        writer = self._writers[dds_topic_name]
        sample = model.to_dds()
        writer.write(sample)
        logger.debug("DDS write → %s (app-topic=%s)", dds_topic_name, topic)

    # -- subscribe -----------------------------------------------------------

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        """
        Subscribe to a DDS topic.

        *topic* must be one of the DDS topic name constants
        (``"SensorData"``, ``"ControlData"``, ``"AlarmData"``).  A daemon
        thread is spawned that reads samples and dispatches them to the
        asyncio event loop via ``call_soon_threadsafe``.
        """
        from cyclonedds.sub import DataReader
        from cyclonedds.qos import Qos, Policy

        from dds_types import TOPIC_ALARM_DATA, TOPIC_CONTROL_DATA, TOPIC_SENSOR_DATA
        from models import AlarmEvent, ControlOutput, SensorReading

        dds_topic = self._topics.get(topic)
        if dds_topic is None:
            logger.error(
                "Cannot subscribe: DDS topic %r not registered", topic)
            return

        reader_qos = Qos(
            # Avoid losing most samples when publishers emit multiple values quickly.
            Policy.History.KeepLast(512),
            Policy.Reliability.Reliable(1_000_000_000),
        )
        reader = DataReader(self._participant, dds_topic, qos=reader_qos)
        self._readers.append(reader)

        # Map DDS topic name → Pydantic model class for conversion
        model_map = {
            TOPIC_SENSOR_DATA: SensorReading,
            TOPIC_CONTROL_DATA: ControlOutput,
            TOPIC_ALARM_DATA: AlarmEvent,
        }
        model_cls = model_map[topic]

        def _reader_loop() -> None:
            """Blocking loop in a daemon thread."""
            while not self._stop_event.is_set():
                try:
                    samples = reader.take(N=100)
                    for sample in samples:
                        try:
                            # CycloneDDS may return InvalidSample entries;
                            # skip them instead of aborting the whole batch.
                            if not hasattr(sample, "topic"):
                                continue

                            model = model_cls.from_dds(sample)
                            data = model.to_dict()
                            app_topic = data.get("topic", topic)

                            if self._loop is not None and self._loop.is_running():
                                self._loop.call_soon_threadsafe(
                                    callback, app_topic, data)
                        except Exception as exc:  # noqa: BLE001
                            if not self._stop_event.is_set():
                                logger.debug(
                                    "Skipping malformed DDS sample on %s: %s",
                                    topic,
                                    exc,
                                )
                except Exception as exc:  # noqa: BLE001
                    if not self._stop_event.is_set():
                        logger.warning(
                            "DDS reader error on %s: %s", topic, exc)
                # Poll interval when no samples are available
                self._stop_event.wait(timeout=0.5)

        thread = threading.Thread(
            target=_reader_loop, daemon=True, name=f"dds-reader-{topic}",
        )
        thread.start()
        self._reader_threads.append(thread)
        logger.info("DDS subscriber started for topic '%s'", topic)

    # -- request (not supported) ---------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            "DdsTransport does not support request/response.  "
            "Use an HttpTransport for REST-style calls."
        )


# ---------------------------------------------------------------------------
# MQTT stub
# ---------------------------------------------------------------------------


class MqttTransport(Transport):
    """
    MQTT transport stub.

    To activate, install asyncio-mqtt and replace this stub::

        pip install asyncio-mqtt

    Then set ``TRANSPORT=mqtt`` in .env, configure ``MQTT_HOST`` /
    ``MQTT_PORT`` (defaults: ``mosquitto`` / ``1883``), and uncomment the
    mosquitto service in docker-compose.yml.
    """

    _MSG = (
        "MqttTransport is not yet implemented.  "
        "Install asyncio-mqtt (`pip install asyncio-mqtt`), uncomment the "
        "mosquitto service in docker-compose.yml, set TRANSPORT=mqtt in .env, "
        "and replace this stub with a real implementation."
    )

    async def connect(self) -> None:
        raise NotImplementedError(self._MSG)

    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        raise NotImplementedError(self._MSG)

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        raise NotImplementedError(self._MSG)

    async def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError(self._MSG)

    async def close(self) -> None:
        raise NotImplementedError(self._MSG)


# ---------------------------------------------------------------------------
# OPC-UA stub
# ---------------------------------------------------------------------------


class OpcUaTransport(Transport):
    """
    OPC-UA transport stub.

    To activate, install asyncua and replace this stub::

        pip install asyncua

    Then set ``TRANSPORT=opcua`` in .env and configure ``OPCUA_URL``
    (default: ``opc.tcp://localhost:4840``).
    """

    _MSG = (
        "OpcUaTransport is not yet implemented.  "
        "Install asyncua (`pip install asyncua`), set TRANSPORT=opcua in .env, "
        "configure OPCUA_URL, and replace this stub with a real implementation."
    )

    async def connect(self) -> None:
        raise NotImplementedError(self._MSG)

    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        raise NotImplementedError(self._MSG)

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        raise NotImplementedError(self._MSG)

    async def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError(self._MSG)

    async def close(self) -> None:
        raise NotImplementedError(self._MSG)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_transport(transport_type: Optional[str] = None) -> Transport:
    """
    Build and return a :class:`Transport` instance.

    Parameters
    ----------
    transport_type:
        ``"http"``, ``"dds"``, ``"mqtt"``, or ``"opcua"``.  When *None* the
        value of the ``TRANSPORT`` environment variable is used
        (default ``"http"``).

    Raises
    ------
    ValueError
        If *transport_type* is not recognised.
    """
    if transport_type is None:
        transport_type = os.environ.get("TRANSPORT", "http")

    transport_type = transport_type.lower().strip()

    if transport_type == "http":
        host = os.environ.get("GATEWAY_HOST", "gateway")
        port = os.environ.get("GATEWAY_PORT", "8080")
        base_url = f"http://{host}:{port}"
        poll_interval = float(os.environ.get(
            "SENSOR_INTERVAL_MS", "1000")) / 1000.0
        logger.info("Creating HttpTransport → %s (poll %.1fs)",
                    base_url, poll_interval)
        return HttpTransport(base_url=base_url, poll_interval=poll_interval)

    if transport_type == "dds":
        domain_id = int(os.environ.get("DDS_DOMAIN_ID", "0"))
        logger.info("Creating DdsTransport (domain=%d)", domain_id)
        try:
            return DdsTransport(domain_id=domain_id)
        except ImportError as exc:
            raise ImportError(
                "DDS transport requires additional dependencies. "
                "Install them with: pip install cyclonedds pydantic"
            ) from exc

    if transport_type == "mqtt":
        return MqttTransport()

    if transport_type in ("opcua", "opc-ua", "opc_ua"):
        return OpcUaTransport()

    raise ValueError(
        f"Unknown transport type {transport_type!r}.  "
        "Valid choices: 'http', 'dds', 'mqtt', 'opcua'."
    )
