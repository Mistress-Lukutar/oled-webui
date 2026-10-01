"""
File:   providers.py
Brief:  System metric providers (psutil) feeding scene widgets.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

import psutil
import structlog

from luminaflowui.exceptions import SceneError

logger = structlog.get_logger(__name__)

_GB = 1024.0**3

# Short source aliases accepted by DataSources.get.
_ALIASES: dict[str, str] = {
    "cpu": "cpu.percent",
    "ram": "ram.percent",
    "disk": "disk.percent",
    "net": "net.kbps",
    "gpu": "gpu.percent",
}

class DataSources:
    """Polls system metrics once per tick and exposes named values.

    Values are addressed with dotted paths (``cpu.percent``, ``ram.used_gb``).
    Polling is decoupled from rendering: :meth:`poll` refreshes an internal
    snapshot that :meth:`get` reads.
    """

    def __init__(self) -> None:
        """Initialize providers and prime cumulative counters."""
        self._snapshot: dict[str, float | str] = {}
        self._last_net: tuple[float, float] | None = None  # (bytes_sent+recv, time)
        # Prime cpu_percent so subsequent non-blocking calls return real data.
        psutil.cpu_percent(interval=None)
        self._gpu = self._init_gpu()

    @staticmethod
    def _init_gpu() -> Any:
        """Optionally initialize NVIDIA NVML for GPU metrics.

        Returns:
            pynvml module if available and initialized, otherwise None.
        """
        try:
            import pynvml
        except ImportError:
            return None
        try:
            pynvml.nvmlInit()
            return pynvml
        except Exception:
            logger.debug("NVML unavailable, gpu.* sources disabled")
            return None

    def poll(self) -> None:
        """Refresh the metric snapshot.

        Raises:
            SceneError: If system metrics cannot be queried.
        """
        try:
            now = time.monotonic()
            timestamp = datetime.now()

            snapshot: dict[str, float | str] = {
                "cpu.percent": psutil.cpu_percent(interval=None),
                "cpu.cores": psutil.cpu_count(logical=True) or 0,
                "ram.percent": psutil.virtual_memory().percent,
                "ram.used_gb": round(psutil.virtual_memory().used / _GB, 2),
                "ram.free_gb": round(psutil.virtual_memory().available / _GB, 2),
                "ram.total_gb": round(psutil.virtual_memory().total / _GB, 2),
                "time.h": timestamp.strftime("%H"),
                "time.m": timestamp.strftime("%M"),
                "time.s": timestamp.strftime("%S"),
                "time.hms": timestamp.strftime("%H:%M:%S"),
                "time.hhmm": timestamp.strftime("%H:%M"),
                "time.date": timestamp.strftime("%Y-%m-%d"),
            }

            freq = psutil.cpu_freq()
            if freq is not None:
                snapshot["cpu.freq_ghz"] = round(freq.current / 1000.0, 2)

            root = self._disk_root()
            usage = psutil.disk_usage(root)
            snapshot["disk.percent"] = usage.percent
            snapshot["disk.used_gb"] = round(usage.used / _GB, 2)
            snapshot["disk.free_gb"] = round((usage.total - usage.used) / _GB, 2)

            net = psutil.net_io_counters()
            if net is not None:
                total_bytes = float(net.bytes_sent + net.bytes_recv)
                if self._last_net is not None:
                    prev_bytes, prev_time = self._last_net
                    elapsed = max(now - prev_time, 1e-6)
                    rate_kbps = (total_bytes - prev_bytes) / elapsed / 1024.0
                    snapshot["net.kbps"] = round(rate_kbps, 1)
                self._last_net = (total_bytes, now)

            temps = self._cpu_temp()
            if temps is not None:
                snapshot["temp.cpu"] = temps

            if self._gpu is not None:
                handle = self._gpu.nvmlDeviceGetHandleByIndex(0)
                utilization = self._gpu.nvmlDeviceGetUtilizationRates(handle)
                snapshot["gpu.percent"] = float(utilization.gpu)
                snapshot["gpu.temp"] = float(
                    self._gpu.nvmlDeviceGetTemperature(
                        handle, self._gpu.NVML_TEMPERATURE_GPU
                    )
                )

            self._snapshot = snapshot
        except SceneError:
            raise
        except Exception as exc:
            raise SceneError(f"Failed to poll system metrics: {exc}") from exc

    @staticmethod
    def _disk_root() -> str:
        """Return the filesystem root for the current platform.

        Returns:
            Path string usable with :func:`psutil.disk_usage`.
        """
        return os.path.abspath(os.sep)

    @staticmethod
    def _cpu_temp() -> float | None:
        """Return the first available CPU temperature reading.

        Returns:
            Temperature in Celsius or None when the platform lacks sensors.
        """
        getter = getattr(psutil, "sensors_temperatures", None)
        if getter is None:
            return None
        try:
            readings = getter()
        except (OSError, PermissionError, AttributeError):
            return None
        for entries in readings.values():
            for entry in entries:
                if entry.current:
                    return float(entry.current)
        return None

    def get(self, path: str) -> float | str:
        """Read a value from the current snapshot.

        Short aliases (``cpu``, ``ram``, ``disk``, ``net``, ``gpu``) map to
        their primary percent/rate paths for convenience.

        Args:
            path: Dotted source path, e.g. ``cpu.percent``.

        Returns:
            Numeric or string value.

        Raises:
            SceneError: If the path is unknown on this platform.
        """
        resolved = _ALIASES.get(path, path)
        try:
            value = self._snapshot[resolved]
        except KeyError as exc:
            raise SceneError(f"Unknown data source {path!r}") from exc
        return value

    def has(self, path: str) -> bool:
        """Check whether a source exists in the snapshot.

        Args:
            path: Dotted source path.

        Returns:
            True when the source is available.
        """
        return path in self._snapshot

    def snapshot(self) -> dict[str, float | str]:
        """Return a copy of the current metric snapshot."""
        return dict(self._snapshot)
