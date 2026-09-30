"""
File:   test_header.py
Brief:  Unit tests for the 64-byte frame header layout.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import struct

from oled_webui.services.bulk_device import BulkLcd


def test_header_layout() -> None:
    """Header must match the reverse-engineered wire layout exactly."""
    header = BulkLcd.build_header(cmd=2, width=1600, height=720, length=123456)

    assert len(header) == 64
    assert header[0:4] == b"\x12\x34\x56\x78"
    assert struct.unpack_from("<I", header, 4)[0] == 2  # cmd
    assert struct.unpack_from("<I", header, 8)[0] == 1600  # width
    assert struct.unpack_from("<I", header, 12)[0] == 720  # height
    assert struct.unpack_from("<I", header, 56)[0] == 2  # flag
    assert struct.unpack_from("<I", header, 60)[0] == 123456  # payload length
    # Everything between height and flag must stay zero.
    assert header[16:56] == b"\x00" * 40


def test_resolve_resolution_known_profiles() -> None:
    """Known PM/SUB pairs must resolve to their documented resolutions."""
    from oled_webui.core.constants import resolve_resolution

    assert (resolve_resolution(63, 0).width, resolve_resolution(63, 0).height) == (
        1600,
        720,
    )
    assert (resolve_resolution(65, 0).width, resolve_resolution(65, 0).height) == (
        1920,
        462,
    )
    assert (resolve_resolution(1, 49).width, resolve_resolution(1, 49).height) == (
        1920,
        462,
    )


def test_resolve_resolution_fallback() -> None:
    """Unknown PM/SUB pairs fall back to the default 480x480."""
    from oled_webui.core.constants import resolve_resolution

    resolved = resolve_resolution(199, 199)
    assert (resolved.width, resolved.height) == (480, 480)
