"""Event bus. Layers publish/subscribe rather than calling each other directly. Phase 1."""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

Subscriber = Callable[[str, Any], None]


class EventBus:
    """Thread-safe pub/sub. Audio capture, the wake-word/hotkey listeners, and
    the FSM loop each run on their own thread, so publish/subscribe must not
    assume a single-threaded caller. Callbacks run synchronously on the
    publisher's thread under a lock — keep subscribers fast (this is the seam
    the GUI, audit log, and HTTP API attach to in later phases; none of them
    exist yet, so there is nothing slow subscribed as of Phase 1).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        with self._lock:
            self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Subscriber) -> None:
        with self._lock:
            subscribers = self._subscribers.get(topic)
            if subscribers and callback in subscribers:
                subscribers.remove(callback)

    def publish(self, topic: str, payload: Any = None) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(topic, ()))
        for callback in subscribers:
            callback(topic, payload)
