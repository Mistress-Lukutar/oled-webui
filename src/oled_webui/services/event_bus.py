"""
File:   event_bus.py
Brief:  In-process topic-based publish/subscribe event bus.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """Minimal async pub/sub bus for decoupling services from SSE."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Register a handler for a topic.

        Args:
            topic: Event topic name.
            handler: Async callable receiving the event payload.
        """
        self._subscribers[topic].append(handler)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event to all subscribers of a topic.

        Handlers run fire-and-forget: failures are logged, never raised, so a
        broken subscriber cannot interrupt the publishing code path.

        Args:
            topic: Event topic name.
            payload: JSON-serializable event data.
        """
        for handler in self._subscribers.get(topic, []):
            try:
                await handler(payload)
            except Exception as exc:
                logger.warning("event_handler_failed", topic=topic, error=str(exc))

    def publish_soon(self, topic: str, payload: dict[str, Any]) -> None:
        """Schedule a publish from sync-ish code without awaiting it.

        Args:
            topic: Event topic name.
            payload: JSON-serializable event data.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.publish(topic, payload))
        task.add_done_callback(self._log_task_failure)

    @staticmethod
    def _log_task_failure(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("event_publish_failed", error=str(exc))
