"""Click engine, macro engine, bind listener and CPS tracker."""

import platform
import random
import subprocess
import threading
import time
from collections import deque

from PySide6.QtCore import QObject, QTimer, Signal

from pynput import keyboard, mouse

IS_WIN = platform.system() == "Windows"

if IS_WIN:
    import ctypes
    import ctypes.wintypes

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("union", _INPUT_UNION),
        ]

    def _win_click() -> None:
        inp = (INPUT * 2)()
        inp[0].type = INPUT_MOUSE
        inp[0].union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
        inp[1].type = INPUT_MOUSE
        inp[1].union.mi.dwFlags = MOUSEEVENTF_LEFTUP
        ctypes.windll.user32.SendInput(2, ctypes.pointer(inp[0]), ctypes.sizeof(INPUT))

    def _is_roblox_focused() -> bool:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value.lower()
        return "roblox" in title

else:
    _mouse_ctrl = mouse.Controller()
    _kb_ctrl = keyboard.Controller()

    def _win_click() -> None:
        _mouse_ctrl.click(mouse.Button.left, 1)

    def _is_roblox_focused() -> bool:
        try:
            out = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowname"],
                stderr=subprocess.DEVNULL,
                timeout=0.5,
            )
            return "roblox" in out.decode().lower()
        except Exception:
            return False


def _press_key(key) -> None:
    """Press and release a key using pynput controller."""
    try:
        ctrl = keyboard.Controller()
        ctrl.press(key)
        ctrl.release(key)
    except Exception:
        pass


def _key_name(key) -> str:
    if isinstance(key, keyboard.Key):
        return key.name.replace("_", " ").title()
    if isinstance(key, keyboard.KeyCode):
        ch = key.char
        if ch and ch.isprintable():
            return ch.upper()
        if key.vk is not None:
            return f"VK {key.vk}"
    return str(key)


def _btn_name(button) -> str:
    mapping = {
        mouse.Button.left: "LMB",
        mouse.Button.right: "RMB",
        mouse.Button.middle: "MMB",
    }
    if button in mapping:
        return mapping[button]
    name = str(button)
    if "x1" in name.lower():
        return "X1"
    if "x2" in name.lower():
        return "X2"
    return name


class BindListener(QObject):
    """Global key/mouse listener for binds."""

    bind_set = Signal(str, object)  # (display_name, raw_key)
    bind_pressed = Signal()
    bind_released = Signal()
    hide_pressed = Signal()
    macro_key_captured = Signal(object, str)  # (raw_key, display_name)

    def __init__(self) -> None:
        super().__init__()
        self._listening_for: str | None = None  # "click" | "hide" | "macro_key"
        self._click_bind = None
        self._hide_bind = None
        self._click_bind_type: str = ""
        self._hide_bind_type: str = ""
        self._pressed_keys: set = set()
        self._pressed_buttons: set = set()
        self._lock = threading.Lock()

        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._ms_listener = mouse.Listener(
            on_click=self._on_mouse_click,
        )
        self._kb_listener.daemon = True
        self._ms_listener.daemon = True
        self._kb_listener.start()
        self._ms_listener.start()

    def start_listening(self, target: str) -> None:
        with self._lock:
            self._listening_for = target

    def stop_listening(self) -> None:
        with self._lock:
            self._listening_for = None

    def _on_key_press(self, key) -> None:
        with self._lock:
            if self._listening_for:
                target = self._listening_for
                self._listening_for = None
                name = _key_name(key)

                if target == "macro_key":
                    self.macro_key_captured.emit(key, name)
                    return

                if target == "click":
                    self._click_bind = key
                    self._click_bind_type = "key"
                else:
                    self._hide_bind = key
                    self._hide_bind_type = "key"
                self.bind_set.emit(name, ("key", key, target))
                return

            if self._click_bind and self._click_bind_type == "key":
                if self._match_key(key, self._click_bind):
                    if key not in self._pressed_keys:
                        self._pressed_keys.add(key)
                        self.bind_pressed.emit()

            if self._hide_bind and self._hide_bind_type == "key":
                if self._match_key(key, self._hide_bind):
                    self.hide_pressed.emit()

    def _on_key_release(self, key) -> None:
        with self._lock:
            self._pressed_keys.discard(key)
            if self._click_bind and self._click_bind_type == "key":
                if self._match_key(key, self._click_bind):
                    self.bind_released.emit()

    def _on_mouse_click(self, _x, _y, button, pressed) -> None:
        with self._lock:
            if self._listening_for:
                if not pressed:
                    return
                target = self._listening_for
                self._listening_for = None
                name = _btn_name(button)

                if target == "macro_key":
                    self.macro_key_captured.emit(button, name)
                    return

                if target == "click":
                    self._click_bind = button
                    self._click_bind_type = "mouse"
                else:
                    self._hide_bind = button
                    self._hide_bind_type = "mouse"
                self.bind_set.emit(name, ("mouse", button, target))
                return

            if self._click_bind and self._click_bind_type == "mouse":
                if button == self._click_bind:
                    if pressed:
                        if button not in self._pressed_buttons:
                            self._pressed_buttons.add(button)
                            self.bind_pressed.emit()
                    else:
                        self._pressed_buttons.discard(button)
                        self.bind_released.emit()

            if self._hide_bind and self._hide_bind_type == "mouse":
                if button == self._hide_bind and pressed:
                    self.hide_pressed.emit()

    @staticmethod
    def _match_key(a, b) -> bool:
        if type(a) is type(b):
            if isinstance(a, keyboard.Key):
                return a == b
            if isinstance(a, keyboard.KeyCode):
                if a.vk is not None and b.vk is not None:
                    return a.vk == b.vk
                return a.char == b.char
        return False

    def clear_bind(self, target: str) -> None:
        with self._lock:
            if target == "click":
                self._click_bind = None
                self._click_bind_type = ""
            elif target == "hide":
                self._hide_bind = None
                self._hide_bind_type = ""

    def shutdown(self) -> None:
        self._kb_listener.stop()
        self._ms_listener.stop()


class ClickEngine(QObject):
    """High-performance auto-clicker running in a dedicated thread."""

    cps_update = Signal(float)
    status_changed = Signal(bool)

    RAMP_DURATION = 1.5  # seconds for smooth ramp-up

    def __init__(self) -> None:
        super().__init__()
        self._running = False
        self._active = threading.Event()
        self._stop = threading.Event()
        self._target_cps: float = 10.0
        self._min_cps: float = 10.0
        self._max_cps: float = 20.0
        self._mode: str = "smooth"  # smooth | insta | mixed
        self._only_roblox: bool = False
        self._click_times: deque = deque(maxlen=2000)
        self._lock = threading.Lock()
        self._start_time: float = 0.0

        self._thread: threading.Thread | None = None

        self._cps_timer = QTimer()
        self._cps_timer.setInterval(50)
        self._cps_timer.timeout.connect(self._emit_cps)
        self._cps_timer.start()

    @property
    def is_active(self) -> bool:
        return self._active.is_set()

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode

    def set_cps(self, cps: float) -> None:
        with self._lock:
            self._target_cps = max(1.0, cps)

    def set_cps_range(self, mn: float, mx: float) -> None:
        with self._lock:
            self._min_cps = max(1.0, mn)
            self._max_cps = max(self._min_cps, mx)

    def set_only_roblox(self, v: bool) -> None:
        with self._lock:
            self._only_roblox = v

    def start(self) -> None:
        if self._active.is_set():
            return
        self._start_time = time.perf_counter()
        self._active.set()
        self._stop.clear()
        self._click_times.clear()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        self.status_changed.emit(True)

    def stop(self) -> None:
        if not self._active.is_set():
            return
        self._active.clear()
        self.status_changed.emit(False)

    def shutdown(self) -> None:
        self._stop.set()
        self._active.clear()
        self._cps_timer.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._active.wait(timeout=0.05)
            if self._stop.is_set():
                break
            if not self._active.is_set():
                continue

            with self._lock:
                mode = self._mode
                target = self._target_cps
                mn = self._min_cps
                mx = self._max_cps
                only_roblox = self._only_roblox
                start_time = self._start_time

            if mode == "mixed":
                cps = random.uniform(mn, mx)
            elif mode == "smooth":
                elapsed = time.perf_counter() - start_time
                progress = min(1.0, elapsed / self.RAMP_DURATION)
                eased = progress * progress  # quadratic ease-in
                cps = max(1.0, target * eased)
            else:
                cps = target

            interval = 1.0 / cps if cps > 0 else 1.0
            next_click = time.perf_counter()

            while self._active.is_set() and not self._stop.is_set():
                now = time.perf_counter()
                if now < next_click:
                    remaining = next_click - now
                    if remaining > 0.002:
                        time.sleep(remaining * 0.7)
                    continue

                if only_roblox and not _is_roblox_focused():
                    next_click = now + 0.05
                    continue

                _win_click()
                self._click_times.append(now)
                next_click = now + interval

                if mode == "mixed":
                    with self._lock:
                        mn = self._min_cps
                        mx = self._max_cps
                    cps = random.uniform(mn, mx)
                    interval = 1.0 / cps if cps > 0 else 1.0
                elif mode == "smooth":
                    elapsed = now - start_time
                    progress = min(1.0, elapsed / self.RAMP_DURATION)
                    eased = progress * progress
                    with self._lock:
                        target = self._target_cps
                    cps = max(1.0, target * eased)
                    interval = 1.0 / cps if cps > 0 else 1.0

    def _emit_cps(self) -> None:
        now = time.perf_counter()
        window = 0.5
        cutoff = now - window
        while self._click_times and self._click_times[0] < cutoff:
            self._click_times.popleft()
        cps = len(self._click_times) / window
        self.cps_update.emit(cps)


class MacroEngine(QObject):
    """Engine that presses a list of keys with delays."""

    status_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._active = threading.Event()
        self._stop = threading.Event()
        self._macros: list[tuple] = []  # [(raw_key, delay_ms), ...]
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def is_active(self) -> bool:
        return self._active.is_set()

    def set_macros(self, macros: list[tuple]) -> None:
        with self._lock:
            self._macros = list(macros)

    def start(self) -> None:
        if self._active.is_set():
            return
        self._active.set()
        self._stop.clear()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        self.status_changed.emit(True)

    def stop(self) -> None:
        if not self._active.is_set():
            return
        self._active.clear()
        self.status_changed.emit(False)

    def shutdown(self) -> None:
        self._stop.set()
        self._active.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._active.wait(timeout=0.05)
            if self._stop.is_set():
                break
            if not self._active.is_set():
                continue

            with self._lock:
                macros = list(self._macros)

            if not macros:
                time.sleep(0.05)
                continue

            for raw_key, delay_ms in macros:
                if not self._active.is_set() or self._stop.is_set():
                    break
                _press_key(raw_key)
                delay_s = delay_ms / 1000.0
                if delay_s > 0:
                    end_time = time.perf_counter() + delay_s
                    while time.perf_counter() < end_time:
                        if not self._active.is_set() or self._stop.is_set():
                            break
                        time.sleep(min(0.01, end_time - time.perf_counter()))
