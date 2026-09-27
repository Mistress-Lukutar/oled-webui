"""
File:   bulk_device.py
Brief:  High-level bulk LCD device: handshake plus framed send.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

import struct

import structlog

from oled_webui.core.constants import (
    BULK_PACKET_SIZE,
    FRAME_CMD_JPEG,
    FRAME_FLAG_VALUE,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    HANDSHAKE_CMD_DEV_INFO,
    HANDSHAKE_CMD_OFFSET,
    HANDSHAKE_MAGIC,
    HANDSHAKE_SIZE,
    HEADER_CMD_OFFSET,
    HEADER_FLAG_OFFSET,
    HEADER_HEIGHT_OFFSET,
    HEADER_LENGTH_OFFSET,
    HEADER_MAGIC_OFFSET,
    HEADER_WIDTH_OFFSET,
    RESPONSE_PM_INDEX,
    RESPONSE_SIZE,
    RESPONSE_SUB_INDEX,
    RESPONSE_VALID_INDEX,
)
from oled_webui.core.models import DeviceProfile, HandshakeResult, Resolution
from oled_webui.exceptions import HandshakeError, TransportError
from oled_webui.infrastructure.usb_transport import PyUsbBulkTransport

logger = structlog.get_logger(__name__)


class BulkLcd:
    """Bulk USB LCD controller for 87AD:70DB.

    Not thread-safe by itself; concurrent access must be serialized by the
    owning service.
    """

    def __init__(self, transport: PyUsbBulkTransport | None = None) -> None:
        self._transport = transport or PyUsbBulkTransport()
        self._profile: DeviceProfile | None = None

    @property
    def is_connected(self) -> bool:
        """True when the transport is open."""
        return self._transport.is_connected

    @property
    def profile(self) -> DeviceProfile | None:
        """Resolved device profile after handshake."""
        return self._profile

    @property
    def resolution(self) -> Resolution:
        """Current panel resolution.

        Raises:
            HandshakeError: If handshake has not been performed.
        """
        if self._profile is None:
            raise HandshakeError("Handshake not performed yet")
        return self._profile.resolution

    def connect(self) -> HandshakeResult:
        """Open transport and perform the device handshake.

        Returns:
            Handshake result containing resolution and IDs.

        Raises:
            HandshakeError: If the device response is invalid.
            TransportError: If USB communication fails.
        """
        self._transport.connect()
        self._profile = self._handshake()
        return HandshakeResult.from_profile(
            self._transport.vid,
            self._transport.pid,
            self._profile,
        )

    def disconnect(self) -> None:
        """Close the transport and clear cached profile."""
        self._transport.disconnect()
        self._profile = None

    def _handshake(self) -> DeviceProfile:
        """Send the 64-byte handshake and parse the 1024-byte response.

        Returns:
            Resolved device profile.

        Raises:
            HandshakeError: If the response indicates no device info.
        """
        packet = bytearray(HANDSHAKE_SIZE)
        end = HEADER_MAGIC_OFFSET + len(HANDSHAKE_MAGIC)
        packet[HEADER_MAGIC_OFFSET:end] = HANDSHAKE_MAGIC
        packet[HANDSHAKE_CMD_OFFSET] = HANDSHAKE_CMD_DEV_INFO

        try:
            self._transport.bulk_write(bytes(packet))
            response = self._transport.bulk_read(RESPONSE_SIZE)
        except TransportError as exc:
            raise HandshakeError(f"Handshake transfer failed: {exc}") from exc

        if len(response) <= RESPONSE_VALID_INDEX or response[RESPONSE_VALID_INDEX] == 0:
            raise HandshakeError("Device did not return valid info")

        pm = response[RESPONSE_PM_INDEX]
        sub = response[RESPONSE_SUB_INDEX]
        logger.debug("handshake_ok", pm=pm, sub=sub)
        return DeviceProfile.from_raw(pm, sub)

    def send(
        self,
        payload: bytes,
        width: int,
        height: int,
        cmd: int = FRAME_CMD_JPEG,
    ) -> int:
        """Send a framed payload to the display.

        Args:
            payload: Encoded image bytes (JPEG or RGB565).
            width: Frame width in pixels.
            height: Frame height in pixels.
            cmd: Frame command type (JPEG or RGB565).

        Returns:
            Total bytes written including header and optional ZLP.

        Raises:
            TransportError: If USB communication fails.
        """
        header = self._build_header(cmd, width, height, len(payload))
        full_packet = header + payload
        written = self._transport.bulk_write(full_packet)

        # If the full packet is an exact multiple of the bulk packet size,
        # a zero-length packet is required to terminate the transfer.
        if len(full_packet) % BULK_PACKET_SIZE == 0:
            self._transport.bulk_write(b"")

        return written

    @staticmethod
    def build_header(cmd: int, width: int, height: int, length: int) -> bytes:
        """Construct the 64-byte frame header.

        Args:
            cmd: Frame command type.
            width: Frame width in pixels.
            height: Frame height in pixels.
            length: Payload length in bytes.

        Returns:
            64-byte header.
        """
        header = bytearray(FRAME_HEADER_SIZE)
        header[HEADER_MAGIC_OFFSET : HEADER_MAGIC_OFFSET + len(FRAME_MAGIC)] = (
            FRAME_MAGIC
        )
        struct.pack_into("<I", header, HEADER_CMD_OFFSET, cmd)
        struct.pack_into("<I", header, HEADER_WIDTH_OFFSET, width)
        struct.pack_into("<I", header, HEADER_HEIGHT_OFFSET, height)
        struct.pack_into("<I", header, HEADER_FLAG_OFFSET, FRAME_FLAG_VALUE)
        struct.pack_into("<I", header, HEADER_LENGTH_OFFSET, length)
        return bytes(header)

    def _build_header(self, cmd: int, width: int, height: int, length: int) -> bytes:
        """Instance wrapper kept for backwards compatibility."""
        return self.build_header(cmd, width, height, length)

    def __enter__(self) -> BulkLcd:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.disconnect()
