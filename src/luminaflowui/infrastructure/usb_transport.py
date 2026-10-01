"""
File:   usb_transport.py
Brief:  PyUSB bulk transport adapter for 87AD:70DB.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
import usb.backend.libusb1
import usb.core
import usb.util

from luminaflowui.core.constants import (
    DEFAULT_TIMEOUT_MS,
    ENDPOINT_IN,
    ENDPOINT_OUT,
    PID,
    VID,
)
from luminaflowui.exceptions import DeviceNotFoundError, TransportError

if TYPE_CHECKING:
    from usb.core import Device

logger = structlog.get_logger(__name__)


def _get_libusb_backend() -> Any | None:
    """Locate a libusb1 backend, falling back to libusb-package if needed."""
    backend = usb.backend.libusb1.get_backend()
    if backend is not None:
        return backend
    try:
        import libusb_package
    except ImportError:
        return None
    # get_library_path() may return a Path object; pyusb needs a plain str.
    path = str(libusb_package.get_library_path())
    return usb.backend.libusb1.get_backend(find_library=lambda _name: path)


# Resolved once at import; safe for concurrent reads afterwards.
_LIBUSB_BACKEND = _get_libusb_backend()


class PyUsbBulkTransport:
    """Low-level PyUSB bulk IN/OUT transport for a single device.

    The transport performs no locking of its own; callers must serialize
    access (the display service owns a single asyncio.Lock for that).
    """

    def __init__(self, vid: int = VID, pid: int = PID) -> None:
        self._vid = vid
        self._pid = pid
        self._device: Device | None = None
        self._interface_number: int | None = None

    @property
    def is_connected(self) -> bool:
        """True when the device is claimed and ready."""
        return self._device is not None

    @property
    def vid(self) -> int:
        """USB vendor ID this transport targets."""
        return self._vid

    @property
    def pid(self) -> int:
        """USB product ID this transport targets."""
        return self._pid

    def find_device(self) -> Device:
        """Locate the USB device on the bus.

        Returns:
            The matching usb.core.Device instance.

        Raises:
            DeviceNotFoundError: If no matching device is present.
            TransportError: If no libusb backend is available.
        """
        try:
            device = usb.core.find(
                idVendor=self._vid,
                idProduct=self._pid,
                backend=_LIBUSB_BACKEND,
            )
        except usb.core.NoBackendError as exc:
            msg = (
                "No libusb backend available; install libusb or a WinUSB "
                "driver for the device (see README)"
            )
            raise TransportError(msg) from exc
        if device is None:
            msg = f"Device {self._vid:04X}:{self._pid:04X} not found"
            raise DeviceNotFoundError(msg)
        return device

    def connect(self) -> None:
        """Open the device, detach kernel driver and claim the interface.

        Raises:
            DeviceNotFoundError: If the device is absent.
            TransportError: If configuration or interface claim fails.
        """
        if self._device is not None:
            return

        device = self.find_device()
        try:
            device.set_configuration()
        except usb.core.USBError as exc:
            msg = f"Failed to set device configuration: {exc}"
            raise TransportError(msg) from exc

        config = device.get_active_configuration()
        interface = config[(0, 0)]
        self._interface_number = interface.bInterfaceNumber

        try:
            kernel_active = device.is_kernel_driver_active(self._interface_number)
        except NotImplementedError:
            # Windows backends do not implement kernel driver queries.
            kernel_active = False

        if kernel_active:
            try:
                device.detach_kernel_driver(self._interface_number)
                logger.debug("kernel_driver_detached", interface=self._interface_number)
            except usb.core.USBError as exc:
                logger.warning("kernel_driver_detach_failed", error=str(exc))

        usb.util.claim_interface(device, self._interface_number)
        self._device = device
        logger.debug(
            "interface_claimed",
            interface=self._interface_number,
            vid=f"{self._vid:04X}",
            pid=f"{self._pid:04X}",
        )

    def disconnect(self) -> None:
        """Release the interface and close the device reference."""
        if self._device is None or self._interface_number is None:
            return

        try:
            usb.util.release_interface(self._device, self._interface_number)
        except usb.core.USBError as exc:
            logger.warning("interface_release_failed", error=str(exc))
        finally:
            self._device = None
            self._interface_number = None

    def bulk_write(self, data: bytes, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> int:
        """Write a buffer to the bulk OUT endpoint.

        Args:
            data: Payload bytes to send.
            timeout_ms: Transfer timeout in milliseconds.

        Returns:
            Number of bytes written.

        Raises:
            TransportError: If the transfer fails.
        """
        if self._device is None:
            raise TransportError("Transport is not connected")

        try:
            return int(self._device.write(ENDPOINT_OUT, data, timeout=timeout_ms))
        except usb.core.USBError as exc:
            msg = f"Bulk write failed: {exc}"
            raise TransportError(msg) from exc

    def bulk_read(
        self,
        length: int,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> bytes:
        """Read up to ``length`` bytes from the bulk IN endpoint.

        Args:
            length: Maximum number of bytes to read.
            timeout_ms: Transfer timeout in milliseconds.

        Returns:
            Bytes read from the device.

        Raises:
            TransportError: If the transfer fails.
        """
        if self._device is None:
            raise TransportError("Transport is not connected")

        try:
            response = self._device.read(ENDPOINT_IN, length, timeout=timeout_ms)
            return (
                response.tobytes() if hasattr(response, "tobytes") else bytes(response)
            )
        except usb.core.USBError as exc:
            msg = f"Bulk read failed: {exc}"
            raise TransportError(msg) from exc

    def __enter__(self) -> PyUsbBulkTransport:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.disconnect()
