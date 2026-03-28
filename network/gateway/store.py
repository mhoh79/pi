"""
store.py – In-memory time-series ring buffer for the gateway.

Each topic gets its own :class:`collections.deque` capped at *maxlen*
entries (default 1000).  The store also tracks the last-seen timestamp
for every source node.

Example
-------
    store = TimeSeriesStore()
    store.add("sensor-1/temperature", msg_dict)
    latest = store.latest("sensor-1/temperature")
    history = store.history("sensor-1/temperature", n=50)
    nodes   = store.nodes()   # {"sensor-1": 1711234567.89, ...}
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict, List, Optional


class TimeSeriesStore:
    """
    Per-topic ring buffers with source-node tracking.

    Parameters
    ----------
    maxlen:
        Maximum number of messages retained per topic.  Oldest entries
        are discarded automatically once the buffer is full.
    """

    def __init__(self, maxlen: int = 1000) -> None:
        self._maxlen = maxlen
        # topic -> deque[dict]
        self._buffers: Dict[str, deque] = {}
        # node_id -> last-seen Unix timestamp
        self._nodes: Dict[str, float] = {}

    # -- write ---------------------------------------------------------------

    def add(self, topic: str, message: Dict[str, Any]) -> None:
        """
        Append *message* to the ring buffer for *topic*.

        Also updates the last-seen timestamp for the message source.

        Parameters
        ----------
        topic:
            Routing key, e.g. ``"sensor-1/temperature"``.
        message:
            Plain dict (e.g. from ``Message.to_dict()``).
        """
        if topic not in self._buffers:
            self._buffers[topic] = deque(maxlen=self._maxlen)
        self._buffers[topic].append(message)

        # Update node tracking
        source = message.get("source")
        if source:
            self._nodes[source] = message.get("timestamp", time.time())

    # -- read ----------------------------------------------------------------

    def latest(self, topic: str) -> Optional[Dict[str, Any]]:
        """
        Return the most recent message for *topic*, or ``None`` if the topic
        has no data yet.
        """
        buf = self._buffers.get(topic)
        if not buf:
            return None
        return buf[-1]

    def history(self, topic: str, n: int = 100) -> List[Dict[str, Any]]:
        """
        Return the last *n* messages for *topic* in chronological order
        (oldest first).  Returns an empty list if the topic is unknown.
        """
        buf = self._buffers.get(topic)
        if not buf:
            return []
        # deque is iterable; slice the last n entries
        items = list(buf)
        return items[-n:] if n < len(items) else items

    def since(self, topic: str, timestamp: float) -> List[Dict[str, Any]]:
        """
        Return all messages for *topic* whose ``timestamp`` field is
        strictly greater than *timestamp*.  Returns an empty list if the
        topic is unknown.
        """
        buf = self._buffers.get(topic)
        if not buf:
            return []
        return [m for m in buf if m.get("timestamp", 0) > timestamp]

    def all_latest(self) -> Dict[str, Dict[str, Any]]:
        """
        Return a dict mapping every known topic to its most recent message.
        """
        return {topic: buf[-1] for topic, buf in self._buffers.items() if buf}

    # -- node tracking -------------------------------------------------------

    def nodes(self) -> Dict[str, float]:
        """
        Return a mapping of ``node_id -> last_seen_timestamp`` for every
        source node that has published at least one message.
        """
        return dict(self._nodes)

    # -- introspection -------------------------------------------------------

    def topics(self) -> List[str]:
        """Return a sorted list of all known topic names."""
        return sorted(self._buffers.keys())

    def topic_count(self) -> Dict[str, int]:
        """Return a dict of ``topic -> number_of_stored_messages``."""
        return {topic: len(buf) for topic, buf in self._buffers.items()}

    def __len__(self) -> int:
        """Total number of messages across all topics."""
        return sum(len(buf) for buf in self._buffers.values())
