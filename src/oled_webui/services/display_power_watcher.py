"""
File:   display_power_watcher.py
Brief:  Win32 display power-on/off notifications via a hidden window.
Author: Mistress-Lukutar
Date:   2026-09-28
Version: v0.4.1
"""

from __future__ import annotations

import ctypes
import threading
import uuid
from ctypes import wintypes
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger(__name__)

# Win32 message and notification constants.
WM_POWERBROADCAST: int = 0x0218
PBT_POWERSETTINGCHANGE: int = 0x8013
WM_QUIT: int = 0x0012
DEVICE_NOTIFY_WINDOW_HANDLE: int = 0
WS_EX_TOOLWINDOW: int = 0x00000080
ERROR_CLASS_ALREADY_EXISTS: int = 1410

# MONITOR_DISPLAY_STATE values carried in POWERBROADCAST_SETTING.Data.
POWER_MONITOR_OFF: int = 0
POWER_MONITOR_ON: int = 1
POWER_MONITOR_DIM: int = 2

# Display power GUIDs from WinNT.h. GUID_CONSOLE_DISPLAY_STATE tracks the
# physical console display, which is exactly the signal the panel needs:
# it stays off after the idle timeout and the whole time the user works
# over RDP, and its notifications also reach processes running inside RDP
# sessions. GUID_SESSION_DISPLAY_STATUS is deliberately not registered (it
# reflects the RDP session and would wake the panel on every reconnect),
# nor is the legacy GUID_MONITOR_POWER_ON, which can report a spurious
# "off" at registration while the display is actually on.
GUID_CONSOLE_DISPLAY_STATE: str = "{6FE69556-704A-47A0-8F24-C28D936FDA47}"

# Registered GUIDs with short names used in log lines.
DISPLAY_POWER_GUIDS: tuple[tuple[str, str], ...] = (
    (GUID_CONSOLE_DISPLAY_STATE, "console_display_state"),
)

# Lookup from parsed notification GUID to its short log name.
_GUID_NAMES: dict[uuid.UUID, str] = {
    uuid.UUID(guid_text): name for guid_text, name in DISPLAY_POWER_GUIDS
}

# LRESULT is a LONG_PTR (pointer-sized signed integer); ctypes.wintypes
# does not define it.
_LRESULT = ctypes.c_ssize_t

_WNDPROC = ctypes.WINFUNCTYPE(
    _LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class _GUID(ctypes.Structure):
    """Windows GUID layout (16 bytes, no padding)."""

    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _WNDCLASSW(ctypes.Structure):
    """RegisterClassW window class descriptor."""

    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class _POWERBROADCAST_SETTING(ctypes.Structure):
    """WM_POWERBROADCAST payload for PBT_POWERSETTINGCHANGE.

    ``Data`` is declared oversized (8 bytes) so reading the DWORD value in
    place stays inside the declared buffer.
    """

    _fields_ = [
        ("PowerSetting", _GUID),
        ("DataLength", wintypes.DWORD),
        ("Data", ctypes.c_ubyte * 8),
    ]


def _guid_structure(guid_text: str) -> _GUID:
    """Build a GUID structure from its canonical string form.

    Args:
        guid_text: GUID string with braces, e.g. ``{2B84C20E-...}``.

    Returns:
        GUID structure for RegisterPowerSettingNotification.
    """
    raw = uuid.UUID(guid_text)
    return _GUID(
        Data1=raw.time_low,
        Data2=raw.time_mid,
        Data3=raw.time_hi_version,
        Data4=(ctypes.c_ubyte * 8).from_buffer_copy(raw.bytes[8:]),
    )


def _guid_uuid(guid: _GUID) -> uuid.UUID:
    """Convert a GUID structure back to a Python UUID.

    Windows GUID memory layout matches uuid's ``bytes_le`` encoding.

    Args:
        guid: GUID structure read from a notification payload.

    Returns:
        The equivalent UUID.
    """
    raw = ctypes.string_at(ctypes.byref(guid), ctypes.sizeof(guid))
    return uuid.UUID(bytes_le=raw)


# Live WNDPROC trampolines; window classes outlive the thread that
# registered them, so the callback must never be garbage collected.
# (ctypes callback types are opaque to mypy, hence Any.)
_WND_PROC_REFS: list[Any] = []


def _user32() -> Any:
    """Return the user32 library with prototypes bound for 64-bit safety.

    Returns:
        Configured WinDLL instance.
    """
    lib = ctypes.WinDLL("user32", use_last_error=True)
    lib.DefWindowProcW.restype = _LRESULT
    lib.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    lib.CreateWindowExW.restype = wintypes.HWND
    lib.RegisterPowerSettingNotification.restype = wintypes.HANDLE
    lib.RegisterPowerSettingNotification.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
    ]
    lib.UnregisterPowerSettingNotification.argtypes = [wintypes.HANDLE]
    lib.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    lib.PostThreadMessageW.argtypes = [
        wintypes.DWORD,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    return lib


class DisplayPowerWatcher:
    """Listens for the Windows console display power state in the background.

    Creates a hidden top-level window and registers for the console
    display state notification (the physical display, not the RDP
    session), then invokes the callback with ``True`` when the console
    display turns on and ``False`` when it turns off. Windows reports the
    current state right after registration, so the first callback also
    syncs a display that is already off. A dimmed display still counts as
    on. The callback runs on the watcher thread; callers must marshal it
    into their own context.
    """

    def __init__(self, on_monitor_power: Callable[[bool], None]) -> None:
        """Store the callback and reset the thread handles.

        Args:
            on_monitor_power: Callback invoked with the display power state.
        """
        self._callback = on_monitor_power
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._notify_handles: list[int] = []
        self._last_state: bool | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        """Start the watcher thread; a second call while running is a no-op."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="display-power-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Post WM_QUIT to the watcher thread and wait for it to finish."""
        self._stop.set()
        if self._thread_id:
            _user32().PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
            self._thread_id = 0

    @property
    def last_state(self) -> bool | None:
        """Last known display state; None until the first notification."""
        return self._last_state

    def _run(self) -> None:
        """Run the message loop until WM_QUIT, then clean up."""
        user32 = _user32()
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        instance = ctypes.windll.kernel32.GetModuleHandleW(None)

        wnd_proc = _WNDPROC(self._wnd_proc)
        # Window classes live for the whole process: keep the callback
        # alive at module level so a stale class can never point at freed
        # trampoline code, and unregister the class on exit (below).
        _WND_PROC_REFS.append(wnd_proc)
        class_name = "OledWebUIMonitorPowerWatcher"

        window_class = _WNDCLASSW(
            style=0,
            lpfnWndProc=wnd_proc,
            hInstance=instance,
            lpszClassName=class_name,
        )
        # RegisterClassW failing with 1410 means this process already
        # registered the class (watcher restart); any other error is fatal.
        if (
            not user32.RegisterClassW(ctypes.byref(window_class))
            and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS
        ):
            logger.error(
                "monitor_power_register_class_failed",
                error=ctypes.get_last_error(),
            )
            return

        # A hidden top-level window (never shown, no taskbar button) is
        # required: message-only windows do not receive power messages.
        hwnd = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW,
            class_name,
            class_name,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            logger.error("monitor_power_window_failed", error=ctypes.get_last_error())
            user32.UnregisterClassW(class_name, instance)
            return

        notify_handles: list[int] = []
        for guid_text, guid_name in DISPLAY_POWER_GUIDS:
            handle = user32.RegisterPowerSettingNotification(
                hwnd,
                ctypes.byref(_guid_structure(guid_text)),
                DEVICE_NOTIFY_WINDOW_HANDLE,
            )
            if handle:
                notify_handles.append(handle)
            else:
                logger.error(
                    "display_power_registration_failed",
                    guid=guid_name,
                    error=ctypes.get_last_error(),
                )
        if not notify_handles:
            logger.error(
                "monitor_power_notification_failed", error=ctypes.get_last_error()
            )
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(class_name, instance)
            return
        self._notify_handles = notify_handles

        logger.info("monitor_power_watcher_started")
        message = wintypes.MSG()
        while not self._stop.is_set():
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result <= 0:  # WM_QUIT or error ends the loop
                break
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

        for handle in self._notify_handles:
            user32.UnregisterPowerSettingNotification(handle)
        self._notify_handles = []
        user32.DestroyWindow(hwnd)
        # Drop the class so a future watcher instance registers its own
        # live window procedure instead of reusing this thread's trampoline.
        user32.UnregisterClassW(class_name, instance)
        _WND_PROC_REFS.clear()
        logger.info("monitor_power_watcher_stopped")

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """Handle power broadcast messages; delegate everything else.

        Args:
            hwnd: Window handle.
            msg: Message identifier.
            wparam: Message word parameter.
            lparam: Message long parameter.

        Returns:
            Message result; 0 for handled power broadcasts.
        """
        if msg == WM_POWERBROADCAST and wparam == PBT_POWERSETTINGCHANGE:
            setting = ctypes.cast(
                lparam, ctypes.POINTER(_POWERBROADCAST_SETTING)
            ).contents
            guid_name = _GUID_NAMES.get(_guid_uuid(setting.PowerSetting))
            if guid_name is not None and setting.DataLength >= 4:
                value = ctypes.cast(
                    setting.Data, ctypes.POINTER(ctypes.c_ulong)
                ).contents.value
                self._emit(value != POWER_MONITOR_OFF, guid_name)
            return 0
        return int(_user32().DefWindowProcW(hwnd, msg, wparam, lparam))

    def _emit(self, monitor_on: bool, source: str) -> None:
        """Forward a display state change to the callback once per flip.

        Several registered GUIDs can report the same transition in a burst;
        the callback is only invoked when the boolean state actually changes.

        Args:
            monitor_on: True when the display is on (or dimmed).
            source: Short name of the GUID that reported the change.
        """
        if monitor_on == self._last_state:
            return
        self._last_state = monitor_on
        logger.info("monitor_power_changed", monitor_on=monitor_on, source=source)
        try:
            self._callback(monitor_on)
        except Exception as exc:  # the window proc must never raise
            logger.warning("monitor_power_callback_failed", error=str(exc))
