"""Console presentation shared by interactive install and preview."""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

def configure_console() -> None:
    """Use UTF-8 directly from the EXE; no CMD launcher is required."""
    if os.name != "nt" or not sys.stdout.isatty():
        return
    try:
        import ctypes

        kernel32 = getattr(ctypes, "windll").kernel32
        kernel32.SetConsoleOutputCP(65001)
        if sys.stdin.isatty():
            kernel32.SetConsoleCP(65001)
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def format_duration(seconds: int) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if hours
        else f"{minutes:02d}:{seconds:02d}"
    )


class ProgressTimer:
    """Keep a single elapsed-time line below the current patch stage."""

    def __init__(self) -> None:
        self.started_at = time.monotonic()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_second = -1

    def elapsed_seconds(self) -> int:
        return int(time.monotonic() - self.started_at)

    def _render(self) -> None:
        if not sys.stdout.isatty():
            return
        print(
            f"\r진행 시간: {format_duration(self.elapsed_seconds())}",
            end="",
            flush=True,
        )

    def _clear_line(self) -> None:
        if not sys.stdout.isatty():
            return
        print("\r" + " " * 32 + "\r", end="", flush=True)

    def _tick(self) -> None:
        while not self._stop_event.wait(0.1):
            with self._lock:
                elapsed = self.elapsed_seconds()
                if elapsed != self._last_second:
                    self._last_second = elapsed
                    self._render()

    def start(self) -> None:
        with self._lock:
            self._last_second = self.elapsed_seconds()
            self._render()
        if sys.stdout.isatty():
            self._thread = threading.Thread(
                target=self._tick, name="progress-timer", daemon=True
            )
            self._thread.start()

    def stage(self, message: str) -> None:
        with self._lock:
            self._clear_line()
            print(message)
            self._render()

    def stop(self) -> int:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        with self._lock:
            elapsed = self.elapsed_seconds()
            self._clear_line()
            print(f"진행 시간: {format_duration(elapsed)}")
        return elapsed


def set_warning_color() -> tuple[Any, int] | None:
    """Set bright-green text in a Windows console and retain its original color."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        class Coord(ctypes.Structure):
            _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short)]

        class SmallRect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_short),
                ("top", ctypes.c_short),
                ("right", ctypes.c_short),
                ("bottom", ctypes.c_short),
            ]

        class ConsoleScreenBufferInfo(ctypes.Structure):
            _fields_ = [
                ("size", Coord),
                ("cursor_position", Coord),
                ("attributes", ctypes.c_ushort),
                ("window", SmallRect),
                ("maximum_window_size", Coord),
            ]

        kernel32 = getattr(ctypes, "windll").kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        info = ConsoleScreenBufferInfo()
        if handle in (0, -1) or not kernel32.GetConsoleScreenBufferInfo(
            handle, ctypes.byref(info)
        ):
            return None
        original = int(info.attributes)
        bright_green = (original & 0xFFF0) | 0x000A
        kernel32.SetConsoleTextAttribute(handle, bright_green)
        return kernel32, original
    except Exception:
        return None


def restore_console_color(state: tuple[Any, int] | None) -> None:
    if state is not None:
        kernel32, original = state
        kernel32.SetConsoleTextAttribute(kernel32.GetStdHandle(-11), original)


def read_confirmation() -> str:
    if os.name == "nt" and sys.stdin.isatty():
        import msvcrt

        while True:
            print("계속하시겠습니까?  1. Yes  2. No : ", end="", flush=True)
            answer = getattr(msvcrt, "getwch")()
            if answer in {"1", "2"}:
                print(answer)
                return answer
            print("\n1 또는 2를 입력하세요.")
    while True:
        answer = input("계속하시겠습니까?  1. Yes  2. No : ").strip()
        if answer in {"1", "2"}:
            return answer
        print("1 또는 2를 입력하세요.")
