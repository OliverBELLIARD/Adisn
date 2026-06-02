"""Live CLI activity display (Claude Code-style spinner and status updates)."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from harness.core.thinking import format_thinking_for_display

SPINNER_FRAMES_UNICODE = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
SPINNER_FRAMES_ASCII = ("|", "/", "-", "\\")
SPINNER_INTERVAL_S = 0.08


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
    done: bool = False
    ok: bool = True


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

    def start(self, headline: str = "Working…") -> None:
        if self._started:
            return
        self._started = True
        with self._lock:
            self._state.headline = headline
        if not self.enabled:
            print(f"{_status_glyph(done=False)} {headline}", flush=True)
            return
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

    def set_response_preview(self, text: str) -> None:
        preview = text.strip()
        if len(preview) > 120:
            preview = preview[:117] + "…"
        with self._lock:
            self._state.response_preview = preview

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
            self._draw_once(final=True)
            sys.stdout.write("\033[?25h\n")
            sys.stdout.flush()
        self._started = False

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
                done=final or self._state.done,
                ok=self._state.ok,
            )
        lines = self._build_lines(state)
        if not self.enabled:
            return
        if self._lines_drawn:
            sys.stdout.write(f"\033[{self._lines_drawn}A")
        for line in lines:
            sys.stdout.write("\033[2K\r")
            sys.stdout.write(line + "\n")
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

        lines: List[str] = [f"{glyph} {state.headline}"]
        if state.step_label:
            lines.append(f"{dim}  {state.step_label}{reset}")
        if state.model_label:
            lines.append(f"{dim}  {state.model_label}{reset}")
        if state.thinking_lines:
            body, truncated = format_thinking_for_display(
                "\n".join(state.thinking_lines),
                max_collapsed_lines=4,
            )
            if body:
                lines.append(f"{dim}  Thinking{reset}")
                for part in body.splitlines():
                    lines.append(f"{dim}{part}{reset}")
                if truncated:
                    lines.append(f"{dim}  … (more in final output){reset}")
        if state.response_preview:
            lines.append(f"{dim}  └ {state.response_preview}{reset}")
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
