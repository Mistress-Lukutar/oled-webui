"""
File:   sse_manager.py
Brief:  Server-sent events broadcaster for connected browsers.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.1.0
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Per-client queue bound; a slow client drops events instead of growing
# memory without limit.
CLIENT_QUEUE_SIZE: int = 100

# Keepalive comment interval so proxies do not close idle connections.
PING_INTERVAL_S: float = 25.0


class SseManager:
    """Fan-out broadcaster: one async queue per connected SSE client."""

    def __init__(self) -> None:
        self._clients: list[asyncio.Queue[str]] = []

    async def subscribe(self) -> AsyncIterator[str]:
        """Yield SSE-formatted messages for one client connection.

        Yields:
            Strings in ``data: {...}\\n\\n`` format, plus ``: ping`` comments.
        """
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=CLIENT_QUEUE_SIZE)
        self._clients.append(queue)
        try:
            while True:
                try:
                    message = await asyncio.wait_for(
                        queue.get(), timeout=PING_INTERVAL_S
                    )
                    yield message
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            self._clients.remove(queue)

    def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        """Push an event to all connected clients.

        Args:
            event_type: SSE event name.
            payload: JSON-serializable event data.
        """
        message = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
        for queue in self._clients:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("sse_client_queue_full")


# Deliberately module-global: routers and services both need the one bus.
sse_manager = SseManager()
