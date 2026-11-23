"""System-wide hotkey through Carbon's RegisterEventHotKey.

Unlike an NSEvent global monitor, this needs no Accessibility permission, and the
key press is consumed instead of also reaching the frontmost app.
"""

from __future__ import annotations

import ctypes
from ctypes import CFUNCTYPE, POINTER, Structure, byref, c_int32, c_uint32, c_void_p
from typing import Callable

CMD, SHIFT, OPTION, CONTROL = 0x100, 0x200, 0x800, 0x1000
KEY_L = 37                       # virtual key code (ANSI layout)
EVENT_CLASS_KEYBOARD = int.from_bytes(b"keyb", "big")
EVENT_HOTKEY_PRESSED = 5
SIGNATURE = int.from_bytes(b"lnfh", "big")


class _EventTypeSpec(Structure):
    _fields_ = [("eventClass", c_uint32), ("eventKind", c_uint32)]


class _EventHotKeyID(Structure):
    _fields_ = [("signature", c_uint32), ("id", c_uint32)]


_HANDLER = CFUNCTYPE(c_int32, c_void_p, c_void_p, c_void_p)

_carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
_carbon.GetApplicationEventTarget.restype = c_void_p
_carbon.InstallEventHandler.argtypes = [
    c_void_p, _HANDLER, c_uint32, POINTER(_EventTypeSpec), c_void_p, POINTER(c_void_p)]
_carbon.InstallEventHandler.restype = c_int32
_carbon.RegisterEventHotKey.argtypes = [
    c_uint32, c_uint32, _EventHotKeyID, c_void_p, c_uint32, POINTER(c_void_p)]
_carbon.RegisterEventHotKey.restype = c_int32

_keep_alive: list = []           # ctypes callbacks must outlive the registration


def register(key_code: int, modifiers: int, callback: Callable[[], None]) -> bool:
    """Call `callback` on the main thread whenever the key combo is pressed. False if taken."""

    def handler(_call, _event, _data) -> int:
        try:
            callback()
        except Exception as exc:  # an exception must not cross back into Carbon
            print(f"hotkey callback failed: {exc}")
        return 0

    target = _carbon.GetApplicationEventTarget()
    c_handler = _HANDLER(handler)
    spec = _EventTypeSpec(EVENT_CLASS_KEYBOARD, EVENT_HOTKEY_PRESSED)
    if _carbon.InstallEventHandler(target, c_handler, 1, byref(spec), None, byref(c_void_p())) != 0:
        return False
    ref = c_void_p()
    if _carbon.RegisterEventHotKey(key_code, modifiers, _EventHotKeyID(SIGNATURE, 1), target, 0, byref(ref)) != 0:
        return False
    _keep_alive.extend([c_handler, spec, ref])
    return True
