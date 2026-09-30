"""
File:   test_display_power_watcher.py
Brief:  Unit tests for the Win32 display power notification parser.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import ctypes
import struct
import sys

import pytest

from oled_webui.services.display_power_watcher import (
    _POWERBROADCAST_SETTING,
    DISPLAY_POWER_GUIDS,
    GUID_CONSOLE_DISPLAY_STATE,
    PBT_POWERSETTINGCHANGE,
    WM_POWERBROADCAST,
    DisplayPowerWatcher,
    _guid_structure,
    _guid_uuid,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

WM_CLOSE: int = 0x0010
UNRELATED_GUID: str = "00000000-0000-0000-0000-00000000002a"
# Not registered on purpose: it tracks the RDP session, not the console.
SESSION_GUID: str = "{2B84C20E-AD23-4DDF-93DB-05FFBD7EFCA5}"


def _make_setting(
    guid_text: str, value: int, data_length: int = 4
) -> _POWERBROADCAST_SETTING:
    """Build a POWERBROADCAST_SETTING payload as delivered by Windows.

    Args:
        guid_text: Power setting GUID the notification claims to carry.
        value: DWORD value placed in the Data member.
        data_length: Value stored in DataLength (payload size check).

    Returns:
        The notification structure (must stay referenced while dispatched).
    """
    setting = _POWERBROADCAST_SETTING()
    setting.PowerSetting = _guid_structure(guid_text)
    setting.DataLength = data_length
    for index, byte in enumerate(struct.pack("<I", value)):
        setting.Data[index] = byte
    return setting


def _dispatch(watcher: DisplayPowerWatcher, setting: _POWERBROADCAST_SETTING) -> int:
    """Feed a notification payload to the window procedure directly.

    Args:
        watcher: Watcher whose window procedure is exercised.
        setting: Crafted notification payload.

    Returns:
        The window procedure result.
    """
    return watcher._wnd_proc(
        0, WM_POWERBROADCAST, PBT_POWERSETTINGCHANGE, ctypes.addressof(setting)
    )


def test_guid_roundtrip_for_all_registered_guids() -> None:
    """Structure encoding must preserve every registered GUID."""
    for guid_text, _name in DISPLAY_POWER_GUIDS:
        assert str(_guid_uuid(_guid_structure(guid_text))) == guid_text[1:-1].lower()


def test_display_off_notification_invokes_callback() -> None:
    """A zero DWORD from the console display GUID means display off."""
    events: list[bool] = []
    watcher = DisplayPowerWatcher(events.append)
    assert _dispatch(watcher, _make_setting(GUID_CONSOLE_DISPLAY_STATE, 0)) == 0
    assert events == [False]
    assert watcher.last_state is False


def test_last_state_is_none_before_first_notification() -> None:
    """The property reports None until anything has been received."""
    watcher = DisplayPowerWatcher(lambda _state: None)
    assert watcher.last_state is None


def test_dim_and_on_both_count_as_display_on() -> None:
    """Dimmed (2) and on (1) restore the panel; repeats are deduplicated."""
    events: list[bool] = []
    watcher = DisplayPowerWatcher(events.append)
    _dispatch(watcher, _make_setting(GUID_CONSOLE_DISPLAY_STATE, 0))
    _dispatch(watcher, _make_setting(GUID_CONSOLE_DISPLAY_STATE, 2))
    _dispatch(watcher, _make_setting(GUID_CONSOLE_DISPLAY_STATE, 1))
    assert events == [False, True]


def test_session_display_status_is_not_registered() -> None:
    """The RDP session GUID must not drive the panel state."""
    events: list[bool] = []
    watcher = DisplayPowerWatcher(events.append)
    _dispatch(watcher, _make_setting(SESSION_GUID, 0))
    assert events == []
    assert watcher.last_state is None


def test_unrelated_guid_is_ignored() -> None:
    """Notifications for GUIDs the watcher never registered are dropped."""
    events: list[bool] = []
    watcher = DisplayPowerWatcher(events.append)
    assert _dispatch(watcher, _make_setting(UNRELATED_GUID, 0)) == 0
    assert events == []


def test_short_payload_is_ignored() -> None:
    """Payloads without a full DWORD carry no display state."""
    events: list[bool] = []
    watcher = DisplayPowerWatcher(events.append)
    _dispatch(watcher, _make_setting(GUID_CONSOLE_DISPLAY_STATE, 0, data_length=0))
    assert events == []


def test_callback_exception_does_not_propagate() -> None:
    """A raising callback is contained inside the window procedure."""

    def boom(state: bool) -> None:
        raise RuntimeError("boom")

    watcher = DisplayPowerWatcher(boom)
    assert _dispatch(watcher, _make_setting(GUID_CONSOLE_DISPLAY_STATE, 0)) == 0


def test_non_power_message_delegates_to_default_procedure() -> None:
    """Messages other than WM_POWERBROADCAST reach DefWindowProcW."""
    watcher = DisplayPowerWatcher(lambda _state: None)
    assert watcher._wnd_proc(0, WM_CLOSE, 0, 0) == 0
