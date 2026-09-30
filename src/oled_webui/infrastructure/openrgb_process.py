"""
File:   openrgb_process.py
Brief:  Spawn, supervise and stop a local OpenRGB SDK server process.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.1
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import subprocess
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Headless start: boot straight into the SDK server (OpenRGB 1.x CLI).
# Passing any action argument also keeps the GUI window hidden.
START_ARGS: tuple[str, ...] = (
    "--server",
    "--server-host",
    "{host}",
    "--server-port",
    "{port}",
)
_PORT_POLL: float = 0.3


class OpenRgbProcessManager:
    """Own the OpenRGB application lifecycle.

    Two backends, tried in order:

    - *Scheduled task* (``task`` set): the app starts a Task Scheduler
      entry via ``schtasks /run``; the task runs OpenRGB elevated, which
      PawnIO needs for SMBus access, without elevating this process.
    - *Direct child* (``exe`` set): spawn the executable directly; fine
      for HID/USB controllers that need no kernel driver.

    If the SDK port is already served, the running instance is adopted
    (external mode) and never killed. Only an instance this manager
    started (child or task run) is terminated on stop.
    """

    def __init__(
        self,
        exe: Path | None,
        host: str,
        port: int,
        start_timeout: float = 45.0,
        monitor_interval: float = 5.0,
        args: tuple[str, ...] = START_ARGS,
        task: str | None = None,
    ) -> None:
        self._exe = exe
        self._host = host
        self._port = port
        self._start_timeout = start_timeout
        self._monitor_interval = monitor_interval
        self._args = tuple(
            arg.format(host=host, port=port) for arg in args
        )
        self._task = task
        self._task_started = False
        self._proc: asyncio.subprocess.Process | None = None
        self._monitor: asyncio.Task[None] | None = None
        self._wanted = False
        self._lifecycle = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        """True when an OpenRGB task or executable is configured."""
        return self._task is not None or self._exe is not None

    @property
    def owned(self) -> bool:
        """True while an instance started by this manager is alive."""
        if self._task_started:
            return True
        return self._proc is not None and self._proc.returncode is None

    def port_open(self) -> bool:
        """True when something is serving the SDK port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((self._host, self._port)) == 0

    def status(self) -> dict[str, Any]:
        """Return a JSON-serializable process supervision snapshot."""
        alive = self._proc is not None and self._proc.returncode is None
        return {
            "managed": self.enabled,
            "running": self.port_open() if self.enabled else False,
            "owned": self.owned,
            "task": self._task,
            "exe": str(self._exe) if self._exe is not None else None,
            "pid": self._proc.pid if alive and self._proc is not None else None,
        }

    async def start(self) -> None:
        """Start the crash-restart monitor (no-op when not configured)."""
        if self.enabled and self._monitor is None:
            self._monitor = asyncio.get_running_loop().create_task(
                self._monitor_loop()
            )

    async def ensure_running(self) -> bool:
        """Make sure the SDK port is served, starting OpenRGB if needed.

        Returns:
            True when the port is (or became) served.

        Raises:
            Nothing; start failures are logged and reported as False.
        """
        if not self.enabled:
            return False
        async with self._lifecycle:
            self._wanted = True
            if await asyncio.to_thread(self.port_open):
                return True
            return await self._bring_up()

    async def stop(self) -> None:
        """Stop monitoring and terminate an instance we started, if any."""
        self._wanted = False
        if self._monitor is not None:
            self._monitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor
            self._monitor = None
        if self._task_started:
            task = self._task or ""
            await self._run_tool("schtasks", "/end", "/tn", task)
            logger.info("openrgb_task_ended", task=task)
        elif self.owned:
            assert self._proc is not None
            logger.info("openrgb_process_stopping", pid=self._proc.pid)
            self._proc.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        self._proc = None
        self._task_started = False

    # ------------------------------------------------------------------

    async def _bring_up(self) -> bool:
        """Start OpenRGB through the task backend or as a direct child."""
        if self._task is not None:
            if not await self._run_tool("schtasks", "/run", "/tn", self._task):
                logger.warning("openrgb_task_run_failed", task=self._task)
                return False
            self._task_started = True
            logger.info("openrgb_task_started", task=self._task)
            return await self._wait_port()
        return await self._spawn_and_wait()

    async def _run_tool(self, *argv: str) -> bool:
        """Run a helper command, returning its success as a boolean."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            logger.warning("openrgb_tool_failed", cmd=argv[0], error=str(exc))
            return False
        return await proc.wait() == 0

    async def _wait_port(self) -> bool:
        """Poll the SDK port until served or the start timeout elapses."""
        deadline = asyncio.get_running_loop().time() + self._start_timeout
        while asyncio.get_running_loop().time() < deadline:
            if await asyncio.to_thread(self.port_open):
                logger.info("openrgb_port_ready", port=self._port)
                return True
            await asyncio.sleep(_PORT_POLL)
        logger.warning("openrgb_port_timeout", port=self._port)
        return False

    async def _spawn_and_wait(self) -> bool:
        """Spawn the configured executable and wait for the SDK port."""
        assert self._exe is not None
        if self.owned:
            self._kill_child()
        try:
            self._proc = await asyncio.create_subprocess_exec(
                str(self._exe),
                *self._args,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            logger.warning("openrgb_spawn_failed", exe=str(self._exe), error=str(exc))
            self._proc = None
            return False
        logger.info("openrgb_spawned", pid=self._proc.pid, exe=str(self._exe))
        deadline = asyncio.get_running_loop().time() + self._start_timeout
        while asyncio.get_running_loop().time() < deadline:
            if not self.owned:
                logger.warning("openrgb_died_before_port", exe=str(self._exe))
                return False
            if await asyncio.to_thread(self.port_open):
                logger.info("openrgb_port_ready", port=self._port)
                return True
            await asyncio.sleep(_PORT_POLL)
        logger.warning("openrgb_port_timeout", port=self._port)
        return False

    async def _monitor_loop(self) -> None:
        """Restart OpenRGB whenever it is wanted but not serving."""
        while True:
            await asyncio.sleep(self._monitor_interval)
            if not self._wanted:
                continue
            if self._task is None and self.owned:
                continue
            if await asyncio.to_thread(self.port_open):
                continue
            logger.warning("openrgb_process_lost", task=self._task)
            async with self._lifecycle:
                if not await asyncio.to_thread(self.port_open):
                    await self._bring_up()

    def _kill_child(self) -> None:
        """Terminate a stale child process handle, ignoring errors."""
        if self._proc is None:
            return
        with contextlib.suppress(Exception):
            self._proc.terminate()
        self._proc = None
