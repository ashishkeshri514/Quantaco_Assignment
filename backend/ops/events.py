"""
SSE fan-out via an in-process bus.

If REDIS_URL is set, uses Redis pub/sub so multiple processes can share events.
Otherwise a local subscriber list is enough for `runserver`.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

CHANNEL = "ops:transactions"


class _LocalFanout:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, payload: str) -> None:
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    pass


class EventBus:
    def __init__(self) -> None:
        self._local = _LocalFanout()
        self._redis = None
        url = getattr(settings, "REDIS_URL", "") or ""
        if url:
            try:
                import redis

                self._redis = redis.Redis.from_url(url, decode_responses=True)
                self._redis.ping()
                logger.info("EventBus using Redis pub/sub at %s", url)
            except Exception:  # noqa: BLE001
                logger.warning("Redis unavailable (%s); falling back to in-process bus", url)
                self._redis = None

    def publish(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event)
        if self._redis is not None:
            try:
                self._redis.publish(CHANNEL, payload)
                return
            except Exception:  # noqa: BLE001
                logger.exception("Redis publish failed; using local fan-out")
        self._local.publish(payload)

    def subscribe(self) -> queue.Queue:
        if self._redis is None:
            return self._local.subscribe()

        q: queue.Queue = queue.Queue(maxsize=64)
        stop = threading.Event()

        def _listen() -> None:
            try:
                import redis

                client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(CHANNEL)
                while not stop.is_set():
                    message = pubsub.get_message(timeout=1.0)
                    if message and message.get("type") == "message":
                        data = message.get("data")
                        if data:
                            try:
                                q.put_nowait(data)
                            except queue.Full:
                                pass
            except Exception:  # noqa: BLE001
                logger.exception("Redis subscribe loop ended")
            finally:
                stop.set()

        thread = threading.Thread(target=_listen, name="sse-redis", daemon=True)
        thread.start()
        q._ops_stop = stop  # type: ignore[attr-defined]
        q._ops_thread = thread  # type: ignore[attr-defined]
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        stop = getattr(q, "_ops_stop", None)
        if stop is not None:
            stop.set()
            return
        self._local.unsubscribe(q)


bus = EventBus()
