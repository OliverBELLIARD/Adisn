"""Live CLI activity display (Claude Code-style spinner and status updates)."""

from __future__ import annotations

import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from harness.core.thinking import format_thinking_for_display

_VT_ENABLED = False

SPINNER_FRAMES_UNICODE = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
SPINNER_FRAMES_ASCII = ("|", "/", "-", "\\")
SPINNER_INTERVAL_S = 0.08


def enable_vt_processing() -> bool:
    """Enable ANSI escape processing on Windows consoles (no-op elsewhere)."""
    global _VT_ENABLED
    if _VT_ENABLED:
        return True
    if sys.platform != "win32":
        _VT_ENABLED = True
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enable_virtual_terminal_processing = 0x0004
        if not kernel32.SetConsoleMode(handle, mode.value | enable_virtual_terminal_processing):
            return False
        _VT_ENABLED = True
        return True
    except (AttributeError, OSError, ValueError):
        return False


def _unicode_safe() -> bool:
    enc = (sys.stdout.encoding or "").lower()
    return "utf" in enc


def _spinner_frames() -> tuple[str, ...]:
    return SPINNER_FRAMES_UNICODE if _unicode_safe() else SPINNER_FRAMES_ASCII


def _status_glyph(*, done: bool, ok: bool = True, frame: int = 0) -> str:
    if done:
        return "*" if not _unicode_safe() else ("●" if ok else "●")
    frames = _spinner_frames()
    return frames[frame % len(frames)]


@dataclass
class LiveState:
    """Snapshot of what the live region should show."""

    headline: str = "Working…"
    step_label: str = ""
    model_label: str = ""
    thinking_lines: List[str] = field(default_factory=list)
    response_preview: str = ""
    activity_detail: str = ""
    done: bool = False
    ok: bool = True


def _terminal_width() -> int:
    try:
        import shutil

        return shutil.get_terminal_size(fallback=(100, 24)).columns
    except OSError:
        return 100


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033[^m]*m", "", text)


def _truncate_visible(text: str, max_width: int) -> str:
    """Truncate text to a maximum visible width, preserving ANSI codes."""
    if max_width <= 0:
        return ""

    visible_len = 0
    result = []
    ansi_pattern = re.compile(r"(\033\[[0-9;]*m)")
    parts = ansi_pattern.split(text)

    for part in parts:
        if not part:
            continue
        if ansi_pattern.match(part):
            result.append(part)
        else:
            remaining = max_width - visible_len
            if len(part) <= remaining:
                result.append(part)
                visible_len += len(part)
            else:
                result.append(part[:remaining])
                visible_len += remaining
                break

    return "".join(result)


class ActivityRenderer:
    """Animated status region while the agent or model is working."""

    def __init__(self, *, enabled: Optional[bool] = None) -> None:
        self.enabled = enabled if enabled is not None else sys.stdout.isatty()
        self._state = LiveState()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lines_drawn = 0
        self._frame_idx = 0
        self._started = False
        self._finished_body: List[str] = []
        self._single_line = True

    def start(self, headline: str = "Working…") -> None:
        if self._started:
            return
        self._started = True
        with self._lock:
            self._state.headline = headline
        if not self.enabled:
            print(f"{_status_glyph(done=False)} {headline}", flush=True)
            return
        enable_vt_processing()
        sys.stdout.write("\033[?25l")  # hide cursor
        sys.stdout.flush()
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._thread.start()

    def set_headline(self, text: str) -> None:
        with self._lock:
            self._state.headline = text

    def set_step(self, step: int, maximum: int, phase: str) -> None:
        phase_label = phase.replace("_", " ").title()
        with self._lock:
            self._state.step_label = f"Step {step}/{maximum} · {phase_label}"

    def set_model(self, model: str, *, active: bool) -> None:
        with self._lock:
            if active and model:
                self._state.model_label = f"Model · {model}"
            elif not active:
                self._state.model_label = ""

    def push_thinking(self, text: str) -> None:
        if not text.strip():
            return
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            with self._lock:
                self._state.thinking_lines.append(line)
                if len(self._state.thinking_lines) > 8:
                    self._state.thinking_lines = self._state.thinking_lines[-8:]

    def set_thinking_stream(self, text: str) -> None:
        """Replace thinking preview (Ollama native think stream)."""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines and text.strip():
            lines = [text.strip()[:200]]
        with self._lock:
            self._state.thinking_lines = lines[-3:]
            if lines:
                self._state.activity_detail = lines[-1][:96]

    def set_response_preview(self, text: str) -> None:
        preview = text.strip().replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:117] + "…"
        with self._lock:
            self._state.response_preview = preview

    def set_activity_detail(self, text: str) -> None:
        detail = text.strip().replace("\n", " ")
        if len(detail) > 96:
            detail = detail[:93] + "…"
        with self._lock:
            self._state.activity_detail = detail

    def finish(self, *, ok: bool = True) -> None:
        if not self._started:
            return
        with self._lock:
            self._state.done = True
            self._state.ok = ok
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self.enabled:
            self._clear_live_region()
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()
            self._lines_drawn = 0
        self._started = False

    def _clear_live_region(self) -> None:
        if self._single_line:
            sys.stdout.write("\r\033[2K")
            return
        if not self._lines_drawn:
            return
        sys.stdout.write(f"\033[{self._lines_drawn}A")
        for _ in range(self._lines_drawn):
            sys.stdout.write("\033[2K\033[1B")
        sys.stdout.write(f"\033[{self._lines_drawn}A")

    def _spin_loop(self) -> None:
        while not self._stop.is_set():
            frames = _spinner_frames()
            self._frame_idx = (self._frame_idx + 1) % len(frames)
            self._draw_once(final=False)
            time.sleep(SPINNER_INTERVAL_S)

    def _draw_once(self, *, final: bool) -> None:
        with self._lock:
            state = LiveState(
                headline=self._state.headline,
                step_label=self._state.step_label,
                model_label=self._state.model_label,
                thinking_lines=list(self._state.thinking_lines),
                response_preview=self._state.response_preview,
                activity_detail=self._state.activity_detail,
                done=final or self._state.done,
                ok=self._state.ok,
            )
            lines = self._build_lines(state)
            if not self.enabled:
                return
            width = _terminal_width()
            if not state.done:
                line = lines[0] if lines else ""
                truncated = _truncate_visible(line, width - 1)
                self._single_line = True
                sys.stdout.write(f"\r\033[2K{truncated}")
                self._lines_drawn = 0 if final else 1
            else:
                if self._lines_drawn:
                    sys.stdout.write(f"\033[{self._lines_drawn}A")
                for line in lines:
                    sys.stdout.write("\033[2K")
                    sys.stdout.write(line + "\n")
                self._single_line = False
                self._lines_drawn = len(lines)
            sys.stdout.flush()

    def _build_lines(self, state: LiveState) -> List[str]:
        dim = "\033[2m" if self.enabled else ""
        reset = "\033[0m" if self.enabled else ""
        accent = "\033[36m" if self.enabled else ""
        green = "\033[32m" if self.enabled else ""
        red = "\033[31m" if self.enabled else ""

        frames = _spinner_frames()
        if state.done:
            g = _status_glyph(done=True, ok=state.ok)
            glyph = f"{green}{g}{reset}" if state.ok else f"{red}{g}{reset}"
        else:
            g = frames[self._frame_idx % len(frames)]
            glyph = f"{accent}{g}{reset}"

        if not state.done:
            parts: List[str] = []
            if state.step_label:
                parts.append(state.step_label.strip())
            if state.model_label:
                parts.append(state.model_label.replace("Model · ", "Model: "))

            # Add a bit of animation to the detail if it's there
            detail = state.activity_detail
            if detail:
                dots = "." * (self._frame_idx % 4)
                parts.append(f"{detail}{dots}")

            line = f"{glyph} {state.headline}"
            if parts:
                line += f" {dim}· " + " · ".join(parts) + reset
            return [line]

        lines: List[str] = [f"{glyph} {state.headline}"]
        if state.step_label:
            lines.append(f"{dim}  {state.step_label}{reset}")
        if state.model_label:
            lines.append(f"{dim}  {state.model_label}{reset}")
        if state.thinking_lines:
            body, truncated = format_thinking_for_display(
                "\n".join(state.thinking_lines),
                max_collapsed_lines=3,
            )
            if body:
                lines.append(f"{dim}  Thinking{reset}")
                for part in body.splitlines()[:3]:
                    lines.append(f"{dim}{part}{reset}")
                if truncated:
                    lines.append(f"{dim}  … (more in final output){reset}")
        if state.response_preview and state.done:
            preview = state.response_preview
            if len(preview) > 120:
                preview = preview[:117] + "…"
            lines.append(f"{dim}  └ {preview}{reset}")
        return lines


def run_with_live_activity(
    headline: str,
    work: Callable[[Callable[[dict], None]], dict],
    *,
    enabled: Optional[bool] = None,
) -> dict:
    """Run ``work(on_progress)`` under a live activity renderer."""

    live = ActivityRenderer(enabled=enabled)
    live.start(headline)

    def on_progress(event: dict) -> None:
        kind = event.get("kind", "")
        if kind == "headline":
            live.set_headline(str(event.get("text", "Working…")))
        elif kind == "step":
            live.set_step(
                int(event.get("step", 1)),
                int(event.get("max_steps", 6)),
                str(event.get("phase", "think")),
            )
        elif kind == "model":
            live.set_model(str(event.get("model", "")), active=bool(event.get("active")))
        elif kind == "thinking":
            live.push_thinking(str(event.get("text", "")))
        elif kind == "token":
            live.set_response_preview(str(event.get("text", "")))

    try:
        result = work(on_progress)
        live.finish(ok=bool(result.get("ok", True) if isinstance(result, dict) else True))
        return result
    except Exception:
        live.finish(ok=False)
        raise
