"""
File:   test_openrgb_process.py
Brief:  Tests for the OpenRGB process manager (spawn, adopt, monitor, stop).
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import asyncio
import socket
import sys
import threading
from pathlib import Path

import psutil
import pytest

from luminaflowui.infrastructure.openrgb_process import OpenRgbProcessManager

# Fake OpenRGB: binds the SDK port, accepts connections, stays alive.
FAKE_SERVER_SCRIPT = (
    "import socket, sys, time\n"
    "s = socket.socket()\n"
    "s.bind(('127.0.0.1', int(sys.argv[1])))\n"
    "s.listen(8)\n"
    "s.settimeout(0.2)\n"
    "while True:\n"
    "    try:\n"
    "        conn, _ = s.accept()\n"
    "        conn.close()\n"
    "    except TimeoutError:\n"
    "        pass\n"
)


def free_port() -> int:
    """Grab an unused localhost port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_manager(port: int, **kwargs: object) -> OpenRgbProcessManager:
    """A manager pointed at a python child acting as the SDK server."""
    return OpenRgbProcessManager(
        Path(sys.executable),
        "127.0.0.1",
        port,
        args=("-c", FAKE_SERVER_SCRIPT, str(port)),
        **kwargs,  # type: ignore[arg-type]
    )


async def wait_until(predicate, timeout: float = 5.0) -> bool:
    """Poll a predicate until true or the timeout elapses."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


async def test_disabled_manager_is_noop() -> None:
    manager = OpenRgbProcessManager(None, "127.0.0.1", free_port())
    assert manager.enabled is False
    assert await manager.ensure_running() is False
    await manager.start()
    await manager.stop()
    assert manager.status()["managed"] is False


async def test_adopts_external_server() -> None:
    port = free_port()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", port))
    listener.listen(4)
    listener.settimeout(0.2)

    def accept_forever() -> None:
        while True:
            try:
                conn, _ = listener.accept()
                conn.close()
            except TimeoutError:
                continue
            except OSError:
                return

    thread = threading.Thread(target=accept_forever, daemon=True)
    thread.start()
    try:
        manager = make_manager(port)
        assert await manager.ensure_running() is True
        status = manager.status()
        assert status["running"] is True
        assert status["owned"] is False
        await manager.stop()
        # An adopted (external) server must survive the manager's stop.
        assert manager.port_open() is True
    finally:
        listener.close()
        thread.join(timeout=2.0)


async def test_spawn_wait_and_stop() -> None:
    manager = make_manager(free_port())
    assert await manager.ensure_running() is True
    status = manager.status()
    assert status["owned"] is True
    assert status["pid"] is not None
    assert psutil.pid_exists(status["pid"]) is True
    await manager.stop()
    assert manager.owned is False
    assert manager.port_open() is False


async def test_ensure_running_is_idempotent() -> None:
    manager = make_manager(free_port())
    assert await manager.ensure_running() is True
    first = manager.status()["pid"]
    assert await manager.ensure_running() is True
    assert manager.status()["pid"] == first
    await manager.stop()


async def test_monitor_restarts_crashed_child() -> None:
    manager = make_manager(free_port(), monitor_interval=0.3)
    await manager.start()
    try:
        assert await manager.ensure_running() is True
        first_pid = manager.status()["pid"]
        psutil.Process(first_pid).kill()
        assert await wait_until(lambda: not manager.owned) is True
        assert (
            await wait_until(
                lambda: manager.owned and manager.status()["pid"] != first_pid,
                timeout=10.0,
            )
            is True
        )
    finally:
        await manager.stop()
    # The terminated child's listening port is released asynchronously.
    assert await wait_until(lambda: not manager.port_open(), timeout=5.0) is True


@pytest.mark.parametrize("exe", [Path("C:/definitely/missing/OpenRGB.exe")])
async def test_spawn_failure_reports_false(exe: Path) -> None:
    manager = OpenRgbProcessManager(exe, "127.0.0.1", free_port(), start_timeout=2.0)
    assert await manager.ensure_running() is False
    await manager.stop()
